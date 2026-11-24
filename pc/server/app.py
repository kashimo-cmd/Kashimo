"""K12 PC server: browser WebSocket relay to the Pi, photo, screenshot, alert download, CSV logs.
Run: python -m pc.server.app [--pi-ip IP] [--video auto|rtsp|mjpeg]   (--video mjpeg for tools/fake_pi.py)"""
import argparse
import asyncio
import collections
import json
import re
import sys
import time
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
import websockets
import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from common import constants as C  # noqa: E402
from common import protocol as P  # noqa: E402
from pc.server import csvlog, photo, screenshot  # noqa: E402

ALERT_NAME = re.compile(r"^\d{6}(_heat)?\.jpg$")
WINDOW_S = 10.0


def log(*a):
    print("[server]", *a, file=sys.stderr)


def settings(cfg, pi_ip=None, video="auto", runs=None):
    """Resolve addresses from config.yaml ({pi_ip} placeholders) and the chosen video source."""
    ip = pi_ip or cfg.get("pi_ip", "127.0.0.1")
    v, base = cfg.get("video", {}), f"{ip}:{cfg.get('ws_port', C.WS_PORT)}"
    rtsp, mjpeg = ((v.get(k) or "").format(pi_ip=ip) for k in ("rtsp_url", "mjpeg_url"))
    url = {"rtsp": rtsp, "mjpeg": mjpeg}.get(video, rtsp or mjpeg)
    return dict(ws_url=f"ws://{base}/ws", http=f"http://{base}", video_url=url, runs=Path(runs or ROOT / "runs"))


class LinkStats:
    """Delay and loss of 5.5. Delay = send time of a CONTROL until a TELEMETRY first echoes its hb_seq
    (includes up to one telemetry period, 100 ms). Loss = missed 100 ms telemetry slots over the last 10 s."""

    def __init__(self):
        self.sent, self.rtt_ms, self.last, self.slots = {}, None, None, collections.deque()

    def reset(self):
        self.sent.clear()
        self.rtt_ms, self.last = None, None
        self.slots.clear()

    def control_sent(self, seq, now):
        self.sent[seq] = now
        while len(self.sent) > 200:
            self.sent.pop(next(iter(self.sent)))

    def telemetry(self, hb_seq, now):
        t0 = self.sent.get(hb_seq)
        for k in [k for k in self.sent if k <= hb_seq]:
            self.sent.pop(k)
        if t0 is not None:
            self.rtt_ms = round((now - t0) * 1000, 1)
        missed = 0 if self.last is None else max(0, round((now - self.last) * C.TELEM_HZ) - 1)
        self.last = now
        self.slots.append((now, missed))
        while self.slots and now - self.slots[0][0] > WINDOW_S:
            self.slots.popleft()

    def loss_pct(self):
        missed = sum(m for _, m in self.slots)
        return round(100.0 * missed / (len(self.slots) + missed), 1) if self.slots else 0.0


class State:
    def __init__(self, st, run):
        self.set, self.run, self.stats = st, run, LinkStats()
        self.grabber = photo.FrameGrabber(st["video_url"])
        self.browsers, self.pi_ws, self.tel, self.tasks = set(), None, None, set()
        self.events, self.n_photo, self.n_shot, self.seq = {}, 0, 0, 0

    def next_seq(self):
        self.seq += 1
        return self.seq

    def link_text(self):
        return json.dumps({"t": "LINK", "pi": self.pi_ws is not None})  # browser-only status message


async def broadcast(st, text):
    for ws in list(st.browsers):
        try:
            await ws.send_text(text)
        except Exception:
            st.browsers.discard(ws)


def fetch(url):
    with urllib.request.urlopen(url, timeout=3) as r:
        return r.read()


async def fetch_alert(st, name):
    """Local copy of an alert image, downloaded from the Pi once. None if the Pi cannot give it."""
    path = st.run.sub("alerts") / name
    if path.is_file():
        return path
    try:
        data = await asyncio.to_thread(fetch, f"{st.set['http']}/alerts/{name}")
    except OSError as exc:
        log("alert download failed:", name, exc)
        return None
    if data[:2] != b"\xff\xd8":
        return None
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(path)
    return path


async def save_alert(st, ev):
    """Download frame and heatmap, then one line in alerts.csv."""
    names = [Path(ev.data[k]).name for k in ("frame", "heat")]
    files = [await fetch_alert(st, n) if ALERT_NAME.match(n) else None for n in names]
    rel = [f"alerts/{f.name}" if f else "" for f in files]
    csvlog.append(st.run.path / "alerts.csv", csvlog.row(
        ev.ts, ev, score=ev.data["score"], cls=ev.data.get("class", ""), frame=rel[0], heat=rel[1],
        delayed=ev.data.get("delayed", False)))


async def on_pi_message(st, text):
    try:
        msg = P.decode(text)
    except P.ProtocolError as exc:
        log("ignored bad message from Pi:", exc)
        return
    if isinstance(msg, P.Telemetry):
        st.stats.telemetry(msg.hb_seq, time.monotonic())
        st.tel = msg
        out = json.loads(text)
        out["link"] = {"rtt_ms": st.stats.rtt_ms, "loss_pct": st.stats.loss_pct(), "pi": True}
        await broadcast(st, json.dumps(out, separators=(",", ":")))
    elif isinstance(msg, P.Event) and msg.id not in st.events:  # a replay of a known event is dropped
        st.events[msg.id] = msg
        await broadcast(st, text)
        if msg.kind == "ALERT_DEFECT":
            task = asyncio.create_task(save_alert(st, msg))
            st.tasks.add(task)
            task.add_done_callback(st.tasks.discard)


async def pi_client(st):
    """Connect to the Pi, SYNC after every (re)connect, relay until the link drops, retry."""
    delay = 0.5
    while True:
        try:
            async with websockets.connect(st.set["ws_url"], open_timeout=3, ping_interval=None) as ws:
                st.pi_ws, delay = ws, 0.5
                st.stats.reset()
                await broadcast(st, st.link_text())
                last_id = max(st.events, default=0)
                await ws.send(P.encode(P.Sync(seq=st.next_seq(), ts=time.time(), since_id=last_id)))
                while True:  # Pi sends telemetry at 10 Hz: 2 s of silence = dead link
                    await on_pi_message(st, await asyncio.wait_for(ws.recv(), 2.0))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not isinstance(exc, (OSError, websockets.WebSocketException, asyncio.TimeoutError)):
                log("pi client error:", repr(exc))
        if st.pi_ws is not None:
            st.pi_ws = None
            await broadcast(st, st.link_text())
        await asyncio.sleep(delay)
        delay = min(delay * 2, 2.0)


def make_app(cfg=None, pi_ip=None, video="auto", runs=None):
    cfg = cfg if cfg is not None else yaml.safe_load((ROOT / "config/config.yaml").read_text(encoding="utf-8"))
    set_ = settings(cfg, pi_ip, video, runs)
    set_["runs"].mkdir(parents=True, exist_ok=True)
    st = State(set_, csvlog.Run(set_["runs"]))

    @asynccontextmanager
    async def lifespan(_app):
        task = asyncio.create_task(pi_client(st))
        yield
        task.cancel()
        st.grabber.close()

    app = FastAPI(lifespan=lifespan)
    app.state.st = st

    @app.websocket("/ws")
    async def browser_ws(ws: WebSocket):
        await ws.accept()
        st.browsers.add(ws)
        try:
            await ws.send_text(st.link_text())
            while True:
                text = await ws.receive_text()
                try:
                    msg = P.decode(text)
                except P.ProtocolError as exc:
                    log("ignored bad message from browser:", exc)
                    continue
                if isinstance(msg, (P.Control, P.Cmd)):  # only the browser makes heartbeats, never this server
                    if isinstance(msg, P.Control):
                        st.stats.control_sent(msg.seq, time.monotonic())
                    if st.pi_ws is not None:
                        try:
                            await st.pi_ws.send(text)
                        except Exception:
                            pass
                elif isinstance(msg, P.Sync):  # this browser asks for the past
                    for ev in sorted(st.events.values(), key=lambda e: e.id):
                        if ev.id > msg.since_id:
                            await ws.send_text(P.encode(ev))
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            st.browsers.discard(ws)

    def fail(code, why):
        return JSONResponse({"ok": False, "error": why}, status_code=code)

    @app.post("/api/photo")
    async def api_photo():
        try:
            frame = await asyncio.to_thread(st.grabber.latest)
            path = await asyncio.to_thread(photo.save, frame, st.run.sub("photos"), st.n_photo + 1, st.tel)
        except (photo.NoFrame, OSError) as exc:
            return fail(503, str(exc))
        st.n_photo += 1
        csvlog.append(st.run.path / "photos.csv", csvlog.row(time.time(), st.tel, frame=f"photos/{path.name}"))
        return {"ok": True, "n": st.n_photo, "file": f"photos/{path.name}", "slab": getattr(st.tel, "slab", None)}

    @app.post("/api/screenshot")
    async def api_screenshot():
        try:
            path = await asyncio.to_thread(screenshot.save, st.run.sub("screenshots"), st.n_shot + 1)
        except Exception as exc:  # mss raises its own error types, a missing display is one of them
            return fail(500, f"screenshot failed: {exc}")
        st.n_shot += 1
        csvlog.append(st.run.path / "screenshots.csv", csvlog.row(time.time(), st.tel, frame=f"screenshots/{path.name}"))
        return {"ok": True, "n": st.n_shot, "file": f"screenshots/{path.name}"}

    @app.get("/api/status")
    def api_status():
        return {"pi": st.pi_ws is not None, "run": st.run.path.name, "events": len(st.events),
                "photos": st.n_photo, "screenshots": st.n_shot, "video_url": st.set["video_url"]}

    @app.get("/alerts/{name}")
    async def alert(name: str):
        path = await fetch_alert(st, name) if ALERT_NAME.match(name) else None
        return FileResponse(path, media_type="image/jpeg") if path else JSONResponse({"ok": False}, status_code=404)

    app.mount("/runs", StaticFiles(directory=set_["runs"]), name="runs")
    web = ROOT / "pc" / "web"
    if web.is_dir():
        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    return app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=C.DASHBOARD_PORT)
    ap.add_argument("--pi-ip", default=None, help="default: pi_ip of config.yaml")
    ap.add_argument("--video", choices=("auto", "rtsp", "mjpeg"), default="auto", help="mjpeg = fake_pi video")
    a = ap.parse_args()
    uvicorn.run(make_app(pi_ip=a.pi_ip, video=a.video), host=a.host, port=a.port, log_level="warning")
