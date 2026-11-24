"""K12 checks: link stats, CSV, photo naming, and a real fake_pi + PC server + browser WebSocket round trip."""
import asyncio
import csv
import json
import re
import socket
import threading
import time
import urllib.error
import urllib.request

import cv2
import numpy as np
import pytest
import uvicorn
import websockets

from common import protocol as P
from pc.server import app as A
from pc.server import csvlog, photo, screenshot
from tools import fake_pi as F


def free_port():
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        return sk.getsockname()[1]


def serve(app, port):
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    while not srv.started:
        time.sleep(0.05)
    return srv


class Stack:
    def __init__(self, tmp, *fake_args, pi_up=True):
        self.pi_port, self.port = free_port(), free_port()
        self.servers = []
        if pi_up:
            self.servers.append(serve(F.make_app(F.parse_args(["--no-webcam", "--port", str(self.pi_port), *fake_args])), self.pi_port))
        cfg = {"pi_ip": "127.0.0.1", "ws_port": self.pi_port,
               "video": {"mjpeg_url": "http://{pi_ip}:%d/video.mjpg" % self.pi_port, "rtsp_url": ""}}
        self.app = A.make_app(cfg, video="mjpeg", runs=tmp)
        self.servers.append(serve(self.app, self.port))
        self.st = self.app.state.st
        self.base, self.ws_url = f"http://127.0.0.1:{self.port}", f"ws://127.0.0.1:{self.port}/ws"

    def post(self, path):
        try:
            with urllib.request.urlopen(urllib.request.Request(self.base + path, data=b"", method="POST"), timeout=10) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as err:
            return err.code, json.load(err)

    def wait(self, cond, timeout=6.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if cond():
                return True
            time.sleep(0.05)
        return False

    def rows(self, name):
        path = self.st.run.path / name
        return list(csv.DictReader(path.open(encoding="utf-8"))) if path.exists() else []

    def stop(self):
        self.st.grabber.close()
        for s in self.servers:
            s.should_exit = s.force_exit = True


@pytest.fixture
def stack(tmp_path):
    s = Stack(tmp_path, "--alert-s", "0.4")
    assert s.wait(lambda: s.st.tel is not None), "server never got telemetry from the fake Pi"
    yield s
    s.stop()


def ctrl(seq, **kw):
    return P.encode(P.Control(seq=seq, ts=time.time(), drive=P.DriveCmd(fwd=0, turn=0), head=P.HeadCmd(pan=0, tilt=0)))


async def beat(ws, seconds, seq0=1, want=None):
    """Send heartbeats like the dashboard does; return the browser-side messages seen."""
    seen, seq, end = [], seq0, time.monotonic() + seconds
    while time.monotonic() < end:
        await ws.send(ctrl(seq))
        seq += 1
        try:
            while True:
                seen.append(json.loads(await asyncio.wait_for(ws.recv(), 0.1)))
        except asyncio.TimeoutError:
            pass
        if want and want(seen):
            break
    return seen


def test_link_stats_delay_and_loss():
    s = A.LinkStats()
    s.control_sent(5, 0.0)
    s.telemetry(5, 0.12)
    assert s.rtt_ms == 120.0 and s.loss_pct() == 0.0
    s.telemetry(5, 0.22)
    s.telemetry(5, 0.52)  # two 100 ms slots missed
    assert s.loss_pct() == 40.0  # 3 received, 2 missed
    s.telemetry(5, 30.0)  # the old samples fall out of the 10 s window, only the long gap is left
    assert len(s.slots) == 1 and s.loss_pct() > 90


def test_csv_header_once_and_columns(tmp_path):
    tel = type("T", (), dict(slab=7, s=12.44, x=12.3, y=-0.2, pan=90.0, tilt=90.0))()
    path = tmp_path / "r" / "photos.csv"
    for n in range(2):
        csvlog.append(path, csvlog.row(1000.0 + n, tel, frame=f"photos/{n}.jpg"))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].split(",") == csvlog.COLUMNS and len(lines) == 3
    assert csvlog.row(1.0)["slab_no"] == "" and csvlog.row(1.0, tel)["delayed"] == "false"


def test_photo_file_name():
    tel = type("T", (), dict(slab=7, s=12.44, pan=90.0, tilt=80.4))()
    assert photo.file_name(1, tel) == "photo_0001_slab07_d12.4m_p090_t080.jpg"
    assert photo.file_name(12, None) == "photo_0012_nopos.jpg"


def test_photo_and_csv_line(stack):
    t0 = time.monotonic()
    code, body = stack.post("/api/photo")
    first = time.monotonic() - t0
    assert code == 200 and body["ok"] and body["n"] == 1
    path = stack.st.run.path / body["file"]
    img = cv2.imread(str(path))
    assert re.fullmatch(r"photo_0001_slab\d{2}_d-?\d+\.\dm_p090_t090\.jpg", path.name) and img.shape[1] == 1280
    row = stack.rows("photos.csv")[0]
    assert row["frame_file"] == body["file"] and row["pan"] == "90.0" and row["slab_no"] == str(body["slab"])
    t0 = time.monotonic()
    assert stack.post("/api/photo")[1]["n"] == 2
    print(f"photo timing: first {first:.2f} s, second {time.monotonic() - t0:.2f} s")
    assert len(stack.rows("photos.csv")) == 2


def test_photo_without_video_makes_nothing(tmp_path):
    s = Stack(tmp_path, pi_up=False)
    s.st.grabber.url, s.st.grabber.wait = f"http://127.0.0.1:{free_port()}/none.mjpg", 0.5
    code, body = s.post("/api/photo")
    s.stop()
    assert code == 503 and body["ok"] is False and s.rows("photos.csv") == [] and s.st.n_photo == 0
    assert not list(s.st.run.path.rglob("*.jpg"))


def test_screenshot_and_failure(stack, monkeypatch):
    monkeypatch.setattr(screenshot, "grab_png", lambda p: cv2.imwrite(str(p), np.zeros((40, 60, 3), np.uint8)))
    code, body = stack.post("/api/screenshot")
    assert code == 200 and re.fullmatch(r"screenshots/shot_0001_\d{6}\.png", body["file"])
    assert (stack.st.run.path / body["file"]).stat().st_size > 0 and len(stack.rows("screenshots.csv")) == 1

    def boom(_path):
        raise RuntimeError("no display")
    monkeypatch.setattr(screenshot, "grab_png", boom)
    code, body = stack.post("/api/screenshot")
    assert code == 500 and body["ok"] is False and "no display" in body["error"]
    assert stack.st.n_shot == 1 and len(stack.rows("screenshots.csv")) == 1


def test_relay_commands_and_link_numbers(stack):
    async def go():
        async with websockets.connect(stack.ws_url) as ws:
            assert json.loads(await ws.recv()) == {"t": "LINK", "pi": True}
            seen = await beat(ws, 1.5)
            tel = [m for m in seen if m["t"] == "TELEMETRY"]
            assert len(tel) >= 8 and tel[-1]["hb_seq"] > 0 and tel[-1]["state"] == "MANUAL"
            link = tel[-1]["link"]
            assert link["pi"] is True and 0 < link["rtt_ms"] < 500 and link["loss_pct"] < 5
            await ws.send(P.encode(P.Cmd(seq=500, ts=0.0, cmd="LED")))
            await ws.send("not json")  # bad input is ignored, the link stays up
            await ws.send(json.dumps({"t": "CONTROL"}))
            seen = await beat(ws, 3.0, 100, want=lambda m: any(x["t"] == "TELEMETRY" and x["led"] is False for x in m))
            assert any(x["t"] == "TELEMETRY" and x["led"] is False for x in seen)
            await ws.send(P.encode(P.Cmd(seq=501, ts=0.0, cmd="STOP")))
            seen = await beat(ws, 3.0, 200, want=lambda m: any(x["t"] == "TELEMETRY" and x["latch"] for x in m))
            assert any(x["t"] == "TELEMETRY" and x["state"] == "STOPPED" and x["latch"] for x in seen)
    asyncio.run(go())


def test_server_never_makes_heartbeats(stack):
    async def go():
        async with websockets.connect(stack.ws_url) as ws:
            await beat(ws, 0.5)  # the browser stops here: the Pi watchdog must fire
            end, state = time.monotonic() + 3, None
            while time.monotonic() < end and state != "LINK_LOST":
                m = json.loads(await asyncio.wait_for(ws.recv(), 2))
                state = m.get("state", state)
            assert state == "LINK_LOST"
    asyncio.run(go())


def test_alerts_downloaded_logged_and_replayed(stack):
    assert stack.wait(lambda: len(stack.rows("alerts.csv")) >= 2)
    rows = stack.rows("alerts.csv")
    assert rows[0]["frame_file"] == "alerts/000001.jpg" and rows[0]["heatmap_file"] == "alerts/000001_heat.jpg"
    assert float(rows[0]["score"]) > 0 and (stack.st.run.path / rows[0]["frame_file"]).read_bytes()[:2] == b"\xff\xd8"
    with urllib.request.urlopen(stack.base + "/alerts/000001.jpg", timeout=3) as r:
        assert r.headers["Content-Type"] == "image/jpeg" and r.read(2) == b"\xff\xd8"
    for bad in ("/alerts/999999.jpg", "/alerts/..%2Fx.jpg", "/alerts/abc.jpg"):
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(stack.base + bad, timeout=3)
        assert err.value.code == 404

    async def go():
        async with websockets.connect(stack.ws_url) as ws:
            await ws.send(P.encode(P.Sync(seq=1, ts=0.0, since_id=0)))
            got = []
            while len(got) < 2:
                m = json.loads(await asyncio.wait_for(ws.recv(), 3))
                if m["t"] == "EVENT":
                    got.append(m)
            assert [e["id"] for e in got[:2]] == [1, 2] and got[0]["kind"] == "ALERT_DEFECT"
    asyncio.run(go())


def test_reconnect_syncs_and_loses_no_event(tmp_path):
    s = Stack(tmp_path, "--alert-s", "0.4", "--drop-link", "2")
    went_down = s.wait(lambda: not s.st.pi_ws, 6)
    back = s.wait(lambda: s.st.pi_ws is not None, 4)
    time.sleep(1.0)
    ids = sorted(s.st.events)
    s.stop()
    assert went_down and back and len(ids) >= 4
    assert ids == list(range(1, len(ids) + 1))  # events made while the link was cut came back through SYNC


def test_controls_dropped_while_pi_is_down(tmp_path):
    s = Stack(tmp_path, pi_up=False)

    async def go():
        async with websockets.connect(s.ws_url) as ws:
            assert json.loads(await ws.recv()) == {"t": "LINK", "pi": False}
            await ws.send(ctrl(1))
            await ws.send(P.encode(P.Cmd(seq=2, ts=0.0, cmd="LED")))
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(ws.recv(), 0.5)
    asyncio.run(go())
    assert s.st.pi_ws is None
    s.stop()
