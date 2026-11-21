"""K03 fake Pi: speaks design 4.5 on :8765 with no robot. Run: python tools/fake_pi.py [--turn] [--no-imu] [--drop-link N]"""
import argparse
import asyncio
import itertools
import math
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.responses import Response, StreamingResponse  # noqa: E402

from common import constants as C  # noqa: E402
from common import protocol as P  # noqa: E402

SLAB_W, ROD_MOVE_S, MAX_CM = 0.5, 3.0, 400.0  # slab width m, rod move time s, no echo beyond (cm)
PIVOT_DPS, CURVE_DPS = 60.0, 30.0  # yaw rate: pivot in place / curve while driving
START = (0.25, 0.0)
REST = tuple(map(float, C.REST))

def polygon(turn):
    # gallery outline in m: straight 30 x 2, or one 90 degree left turn (+y) after x = 20
    if turn:
        return [(0, -1), (21, -1), (21, 29), (19, 29), (19, 1), (0, 1)]
    return [(0, -1), (30, -1), (30, 1), (0, 1)]

def ray(poly, x, y, ang):
    dx, dy, best = math.cos(ang), math.sin(ang), None
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        ex, ey = x2 - x1, y2 - y1
        den = dx * ey - dy * ex
        if abs(den) < 1e-9:
            continue
        t, u = ((x1 - x) * ey - (y1 - y) * ex) / den, ((x1 - x) * dy - (y1 - y) * dx) / den
        if t >= 0 and 0 <= u <= 1 and (best is None or t < best):
            best = t
    return best

def slew(v, goal, step):
    return goal if abs(goal - v) <= step else v + math.copysign(step, goal - v)
def jpg(img):
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])[1].tobytes()

def pattern(n, w=1280, h=720):
    img = np.full((h, w, 3), (60, 40, 20), np.uint8)
    cv2.rectangle(img, ((n * 12) % w, 0), ((n * 12) % w + 40, h), (0, 200, 255), -1)
    cv2.putText(img, "FAKE PI " + datetime.now().strftime("%H:%M:%S.%f")[:-3], (40, 100), 0, 2, (255, 255, 255), 3)
    return img

def alert_jpgs(eid, score):
    frame = np.full((360, 640, 3), 50, np.uint8)
    cv2.line(frame, (0, 220), (640, 180), (30, 90, 200), 14)
    cv2.putText(frame, f"FAKE DEFECT #{eid} score {score:.1f}", (20, 40), 0, 1, (255, 255, 255), 2)
    heat = cv2.applyColorMap(np.tile(np.linspace(0, 255, 640).astype(np.uint8), (360, 1)), cv2.COLORMAP_JET)
    return jpg(frame), jpg(cv2.addWeighted(frame, 0.5, heat, 0.5, 0))

class Sim:
    """Robot model, clock passed in so tests can step it. yaw 0 = along x, counter-clockwise positive,
    so turn -1 (Q) = left = +yaw. A key +1 makes pan/tilt angle grow."""

    def __init__(self, now=0.0, turn=False, no_imu=False, alert_s=20.0):
        self.poly, self.no_imu, self.alert_s = polygon(turn), no_imu, alert_s
        self.t0 = self.prev = self.now = now
        self.tx, self.ty, self.tyaw = *START, 0.0  # true pose, what the sensors see
        self.x, self.y, self.yaw, self.s = *START, 0.0, 0.0  # estimate, what telemetry reports
        self.pan, self.tilt, self.target, self.led, self.rod, self.rod_t = *REST, None, True, "FOLDED", 0.0
        self.latch, self.state, self.drive, self.head, self.hb_seq = False, "MANUAL", (0, 0), (0, 0), 0
        self.last_ctrl, self.moving, self.near = None, False, False
        self.refusal, self.cmd_ref, self.cmd_ref_until = None, None, 0.0
        self.events, self.fresh, self.images, self.eid, self.seq = [], [], {}, 0, itertools.count(1)
        self.next_alert = now + alert_s  # fake defect timer

    def slab(self):
        return int(math.floor(self.x / SLAB_W)) + 1

    def imu(self):
        return "LOST" if self.no_imu else ("CALIBRATING" if self.now - self.t0 < C.GYRO_CAL_S else "OK")

    def dist(self, off):
        t = ray(self.poly, self.tx, self.ty, self.tyaw + off)
        return None if t is None or t * 100 > MAX_CM else round(t * 100, 1)

    def add_event(self, kind, data=None):
        self.eid += 1
        ev = P.Event(seq=next(self.seq), ts=time.time(), id=self.eid, kind=kind, s=round(self.s, 3), x=round(self.x, 3),
                     y=round(self.y, 3), slab=self.slab(), pan=self.pan, tilt=self.tilt, data=data or {})
        self.events.append(ev)
        self.fresh.append(ev)
        return ev

    def on_control(self, msg, now):
        self.now = now
        self.drive, self.head = (msg.drive.fwd, msg.drive.turn), (msg.head.pan, msg.head.tilt)
        self.hb_seq, self.last_ctrl = msg.seq, now
        if self.state == "LINK_LOST":
            self.state = "STOPPED"  # latch stays on until START
            self.add_event("LINK_BACK")

    def on_cmd(self, cmd, now):
        self.now = now
        if cmd == "STOP":
            self.latch = True
            self.state = self.state if self.state == "LINK_LOST" else "STOPPED"
        elif cmd == "START" and self.state != "LINK_LOST":
            self.latch, self.state = False, "MANUAL"
        elif cmd == "LED":
            self.led = not self.led
        elif cmd == "HEAD_HOME" and self.rod == "UPRIGHT":
            self.target = REST
        elif cmd == "ROD" and self.moving:
            self.cmd_ref, self.cmd_ref_until = "stop first", now + 1.5
        elif cmd == "ROD" and self.rod in ("FOLDED", "UPRIGHT"):
            self.rod, self.rod_t = ("LIFTING" if self.rod == "FOLDED" else "FOLDING"), now
            self.target = tuple(map(float, C.FOLD_POSE or C.REST))

    def step(self, now):
        dt = min(now - self.prev, 0.2)
        self.prev = self.now = now
        if self.last_ctrl is not None and self.state != "LINK_LOST" and now - self.last_ctrl > C.WATCHDOG_S:
            self.state, self.latch, self.drive, self.head = "LINK_LOST", True, (0, 0), (0, 0)
            self.add_event("LINK_LOST")
        if self.rod in ("LIFTING", "FOLDING") and now - self.rod_t >= ROD_MOVE_S:
            self.rod = "UPRIGHT" if self.rod == "LIFTING" else "FOLDED"
        self._head(dt)
        self._drive(dt)
        if now >= self.next_alert:
            self.next_alert += self.alert_s
            score, ev = round(3.0 + (self.eid * 1.7) % 6, 2), self.add_event("ALERT_DEFECT")
            name = f"{ev.id:06d}"
            ev.data.update(score=score, frame=f"/alerts/{name}.jpg", heat=f"/alerts/{name}_heat.jpg", detector="dummy")
            self.images[f"{name}.jpg"], self.images[f"{name}_heat.jpg"] = alert_jpgs(ev.id, score)

    def _head(self, dt):
        pk, tk = self.head if self.rod == "UPRIGHT" else (0, 0)  # head keys ignored unless the rod is upright
        if pk or tk:
            self.target = None
        if self.target is not None:
            self.pan, self.tilt = (slew(v, g, C.HOME_RATE * dt) for v, g in zip((self.pan, self.tilt), self.target))
            self.target = None if (self.pan, self.tilt) == self.target else self.target
        else:
            self.pan = min(180.0, max(0.0, self.pan + pk * C.HEAD_RATE * dt))
            self.tilt = min(180.0, max(0.0, self.tilt + tk * C.HEAD_RATE * dt))

    def _drive(self, dt):
        fwd, turn = self.drive
        front, ref = self.dist(0), None
        if front is None or front >= C.OBSTACLE_CM + 5:
            self.near = False
        if fwd or turn:
            if self.latch:
                ref = "STOP latched: press Space"
            elif self.imu() == "CALIBRATING":
                ref = "IMU calibrating"
            elif self.rod in ("LIFTING", "FOLDING"):
                ref = "rod moving"
            if ref:
                fwd = turn = 0
            elif fwd == 1 and front is not None and front < C.OBSTACLE_CM:
                ref, fwd = "front obstacle", 0  # forward refused, S Q D still work
                if not self.near:
                    self.near = True
                    self.add_event("ALERT_OBSTACLE", {"front_cm": front})
        ds = fwd * C.DRIVE_SPEED * dt
        dyaw = math.radians(-turn * (CURVE_DPS if fwd else PIVOT_DPS) * dt)
        back = ray(self.poly, self.tx, self.ty, self.tyaw + math.pi)
        if ds < 0 and back is not None and back < 0.1:  # backward is blind, but the wall still stops it
            ds = 0.0
        self.tyaw += dyaw
        self.tx, self.ty = self.tx + ds * math.cos(self.tyaw), self.ty + ds * math.sin(self.tyaw)
        self.yaw += 0.0 if self.no_imu else dyaw  # without the IMU the reported heading never turns
        self.s += ds
        self.x, self.y = self.x + ds * math.cos(self.yaw), self.y + ds * math.sin(self.yaw)
        self.moving = bool(fwd or turn)
        self.refusal = ref or (self.cmd_ref if self.now < self.cmd_ref_until else None)

    def telemetry(self):
        r = lambda v: round(v, 3)  # noqa: E731
        return P.Telemetry(
            seq=next(self.seq), ts=time.time(), state=self.state, latch=self.latch, hb_seq=self.hb_seq,
            fc=self.dist(0), fl=self.dist(math.pi / 2), fr=self.dist(-math.pi / 2), s=r(self.s), x=r(self.x),
            y=r(self.y), yaw=r(math.degrees(self.yaw)), slab=self.slab(), pan=r(self.pan), tilt=r(self.tilt),
            led=self.led, rod=self.rod, pitch=0.0, roll=0.0, imu=self.imu(), cpu_temp=48.0, cpu_load=0.3,
            rssi_dbm=r(-50.0 - 0.8 * abs(self.s) + 2 * math.sin(self.now / 5)), ai="DUMMY", ai_ms=4.0, rec=True,
            refusal=self.refusal)

def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=C.WS_PORT)
    ap.add_argument("--turn", action="store_true", help="gallery with one 90 degree left turn")
    ap.add_argument("--no-imu", action="store_true", help="IMU LOST: reported yaw never turns")
    ap.add_argument("--drop-link", type=float, default=0, metavar="N", help="cut the link for 1 s every N s")
    ap.add_argument("--alert-s", type=float, default=20.0, help="seconds between fake defects")
    ap.add_argument("--no-webcam", action="store_true", help="video = test pattern only")
    return ap.parse_args(argv)

def make_app(opts):
    sim = Sim(time.monotonic(), opts.turn, opts.no_imu, opts.alert_s)
    clients, cam, t0 = set(), {"cap": None, "n": 0, "lock": threading.Lock()}, time.monotonic()

    def cut():
        el = time.monotonic() - t0
        return opts.drop_link > 0 and el >= opts.drop_link and el % opts.drop_link < 1.0

    async def flush():  # send queued events and telemetry to every client
        while sim.fresh:
            text = P.encode(sim.fresh.pop(0))
            for ws in list(clients):
                try:
                    await ws.send_text(text)
                except Exception:
                    clients.discard(ws)

    async def loop():
        n, per = 0, round(1 / (C.LOOP_S * C.TELEM_HZ))
        while True:
            await asyncio.sleep(C.LOOP_S)
            sim.step(time.monotonic())
            if cut():  # link cut: drop every connection, the client reconnects and sends SYNC
                for ws in list(clients):
                    await ws.close(code=1001)
                clients.clear()
                sim.fresh.clear()  # not delivered, only kept for SYNC
                continue
            n += 1
            if n % per == 0:
                sim.fresh.append(sim.telemetry())
            await flush()

    @asynccontextmanager
    async def lifespan(_app):
        task = asyncio.create_task(loop())
        yield
        task.cancel()

    app = FastAPI(lifespan=lifespan)

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        if cut():
            await ws.close(code=1013)
            return
        await ws.accept()
        clients.add(ws)
        try:
            while True:
                text = await ws.receive_text()
                try:
                    msg = None if cut() else P.decode(text)
                except P.ProtocolError as exc:
                    print("ignored bad message:", exc, file=sys.stderr)
                    continue
                if isinstance(msg, P.Control):
                    sim.on_control(msg, time.monotonic())
                elif isinstance(msg, P.Cmd):
                    sim.on_cmd(msg.cmd, time.monotonic())
                elif isinstance(msg, P.Sync):
                    for ev in [e for e in sim.events if e.id > msg.since_id]:
                        await ws.send_text(P.encode(ev))
                await flush()
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            clients.discard(ws)

    @app.get("/alerts/{name}")
    def alert(name: str):
        data = sim.images.get(name)
        return Response(data, media_type="image/jpeg") if data else Response(status_code=404)

    def grab():
        with cam["lock"]:
            if cam["cap"] is None:
                cam["cap"] = False if opts.no_webcam else cv2.VideoCapture(0)
            ok, frame = cam["cap"].read() if cam["cap"] and cam["cap"].isOpened() else (False, None)
            cam["n"] += 1
            return jpg(frame if ok else pattern(cam["n"]))

    @app.get("/video.mjpg")
    async def video():
        async def gen():
            while True:
                data = await asyncio.to_thread(grab)
                yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(data) + data + b"\r\n"
                await asyncio.sleep(1 / 15)
        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")

    return app

if __name__ == "__main__":
    args = parse_args()
    print(f"fake Pi on ws://{args.host}:{args.port}/ws  (Ctrl+C to stop)")
    uvicorn.run(make_app(args), host=args.host, port=args.port, log_level="warning")
