"""Controller: 50 ms loop wiring hw, sensors, drive, head, rod, imu and position (K09, design 5.1).

Run on a PC: HW_MODE=mock python -m pi.controller.main   On the Pi: systemd runs it with HW_MODE=pi.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import math
import os
import time
from collections import deque
from itertools import count
from pathlib import Path

import yaml

from common import constants as C
from common import protocol as P
from pi.controller import telemetry as T
from pi.controller.drive import Drive
from pi.controller.events import EventStore
from pi.controller.head import Head
from pi.controller.imu import Imu
from pi.controller.position import Position, ds_from_tracks
from pi.controller.rod import Rod
from pi.controller.sensors import Sensors

log = logging.getLogger("kashimo.controller")
ROOT = Path(__file__).resolve().parents[2]
IMU_S = 1.0 / C.IMU_RATE
AI_STALE_S = 5.0  # [EST] the AI worker posts its status at least this often, else the badge says OFF
REFUSAL_S = 1.5  # how long a refused CMD stays in TELEMETRY.refusal
FRAMES = Path(os.environ.get("KASHIMO_FRAMES", "/run/kashimo/frames/latest.jpg"))  # CHECK ON PI (K10 writes it)
MOCK_TRACK_GAUGE_M = 0.2  # mock robot only


class MockRobot:
    """Mock only: tracks turn with the applied PWM and the gyro sees the yaw rate, so a mock run has something to show."""

    def __init__(self, pwm_at_speed: float, m_per_count: float):
        self.pwm, self.m_per_count, self._frac = pwm_at_speed, m_per_count, [0.0, 0.0]

    def step(self, hw, dt: float) -> None:
        v = [out / self.pwm * C.DRIVE_SPEED for out in hw.motor_out]  # m/s per track, signed
        for i in (0, 1):
            self._frac[i] += abs(v[i]) * dt / self.m_per_count
        whole = [int(f) for f in self._frac]
        self._frac = [f - w for f, w in zip(self._frac, whole)]
        hw.sim_encoders(*whole)
        hw.sim["imu"] = (0.0, 0.0, 1.0, 0.0, 0.0, math.degrees((v[1] - v[0]) / MOCK_TRACK_GAUGE_M))


def load_config(path=None) -> dict:
    """config/config.yaml (or KASHIMO_CONFIG, or the given path) as a dict."""
    path = Path(path or os.environ.get("KASHIMO_CONFIG") or ROOT / "config" / "config.yaml")
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    return cfg


class Controller:
    """States MANUAL, STOPPED, LINK_LOST. step() every 50 ms, imu_step() every 10 ms, read_slow() every 2 s."""

    def __init__(self, hw, cfg: dict | None = None, db_path: str = ":memory:", clock=time.monotonic,
                 imu: Imu | None = None, alerts_dir=None, sim: bool = False):
        cfg = cfg or {}
        self.hw, self.clock = hw, clock
        self.sensors = Sensors.from_config(hw, cfg)
        self.drive = Drive.from_config(hw, cfg, self.sensors)  # init: enable low, PWM 0
        self.head = Head.from_config(hw, cfg)  # init: head to REST at 30 deg/s
        self.rod = Rod.from_config(hw, self.head, cfg)  # init: FOLDED
        self.imu, self.pos = imu or Imu(), Position.from_config(cfg)  # init: IMU calibrating, s = 0
        self.events = EventStore(db_path)
        self.slabs = T.Slabs.from_file(ROOT / cfg.get("slabs_file", "config/slabs.json"),
                                       (cfg.get("gallery") or {}).get("slab_width_m") or 0.5)
        self.alerts_dir = Path(alerts_dir) if alerts_dir else ROOT / "runs" / "alerts"
        self.sim = MockRobot(self.drive.pwm, self.sensors.m_per_count) if sim else None
        self.led = True
        hw.led(True)
        self.outbox: deque = deque()
        self._seq, self._ticks = count(1), 0
        self.ctl = (0, 0, 0, 0)  # fwd, turn, pan, tilt of the last valid CONTROL
        self.hb_seq, self.last_ctrl, self.link_lost, self.link_lost_at = 0, None, False, None
        self._cmd_refusal: tuple[str, float] | None = None
        self._tracks, self._counts, self._near = (0.0, 0.0), None, {"fc": None, "fl": None, "fr": None}
        self._head_moved = False
        self._ai = ("OFF", 0.0, None)  # ai, ai_ms, when posted
        self._slow = {"rssi_dbm": None, "cpu_temp": None, "cpu_load": None, "rec": False}

    # ---- state ----
    @property
    def state(self) -> str:
        return "LINK_LOST" if self.link_lost else "STOPPED" if self.drive.latch else "MANUAL"

    def pose(self) -> dict:
        return dict(s=T.finite(self.pos.s), x=T.finite(self.pos.x), y=T.finite(self.pos.y), slab=self.slabs.number(self.pos.x),
                    pan=T.finite(self.head.pan, nd=2), tilt=T.finite(self.head.tilt, nd=2))

    def emit(self, kind: str, data: dict | None = None) -> P.Event:
        """Store an event with the current pose and queue it for the dashboards."""
        ev = self.events.add(kind, self.pose(), data)
        self.outbox.append(ev)
        return ev

    # ---- input from the dashboard ----
    def on_control(self, msg: P.Control, now: float | None = None) -> None:
        """A valid CONTROL is the heartbeat. The first one after a link loss sends LINK_BACK; the latch stays on."""
        self.ctl = (msg.drive.fwd, msg.drive.turn, msg.head.pan, msg.head.tilt)
        self.hb_seq, self.last_ctrl = msg.seq, self.clock() if now is None else now
        if self.link_lost:
            self.link_lost = False
            self.emit("LINK_BACK")

    def on_cmd(self, cmd: str, now: float | None = None) -> None:
        now = self.clock() if now is None else now
        if cmd == "STOP":
            self.drive.stop()
        elif cmd == "START":
            if not self.link_lost:  # after a link loss the heartbeat must come back first
                self.drive.release()
        elif cmd == "LED":
            self.led = not self.led
            self.hw.led(self.led)
        elif cmd == "HEAD_HOME":
            self.head.home(self.rod.state)  # ignored unless the rod is UPRIGHT
        elif cmd == "ROD":
            why = self.rod.request(self.drive.moving)
            if why:
                self._cmd_refusal = (why, now + REFUSAL_S)

    def check_watchdog(self, now: float) -> None:
        """No valid CONTROL for 500 ms: motors off, latch on, LINK_LOST. Armed by the first CONTROL."""
        if self.last_ctrl is None or self.link_lost or now - self.last_ctrl < C.WATCHDOG_S:
            return
        self.link_lost, self.link_lost_at, self.ctl = True, now, (0, 0, 0, 0)
        self.drive.stop()
        self.emit("LINK_LOST")

    def post_defect(self, data) -> P.Event:
        """The AI worker's ALERT_DEFECT. Raises ProtocolError when score, frame, heat or detector is missing or wrong."""
        return self.emit("ALERT_DEFECT", data if isinstance(data, dict) else {})

    def set_ai_status(self, ai, ai_ms=0.0) -> None:
        if ai not in P.AIS:
            raise P.ProtocolError(f"ai: expected one of {'|'.join(P.AIS)}")
        self._ai = (ai, P.v_num("ai_ms", ai_ms), self.clock())

    # ---- loops ----
    def imu_step(self, dt: float = IMU_S, now: float | None = None) -> None:
        """Every 10 ms: IMU sample, yaw, calibration end, bump and tilt events, watchdog."""
        if self.sim:
            self.sim.step(self.hw, dt)
        counts = tuple(self.hw.encoder_counts())
        moved, self._counts = counts != self._counts and self._counts is not None, counts
        self.imu.read(self.hw, dt, moved)
        if self.imu.pop_calibrated():
            self.pos.bias = self.imu.bias
            self.pos.reset()
        self.pos.bias = self.imu.bias
        self.pos.integrate_gyro(self.imu.heading_rate, dt)
        if self.imu.pop_bump():
            self.emit("BUMP")
        if self.imu.pop_tilt_alert():
            self.emit("ALERT_TILT", {"tilt": round(self.imu.tilt, 1)})
        self.check_watchdog(self.clock() if now is None else now)

    def step(self, dt: float = C.LOOP_S, now: float | None = None) -> None:
        """Every 50 ms: sensors, drive, head, rod, path, events, and TELEMETRY every second tick (10 Hz)."""
        now = self.clock() if now is None else now
        self.check_watchdog(now)
        r = self.sensors.read()
        self._near = {k: r[k] for k in ("fc", "fl", "fr")}
        cur = (r["left_m"], r["right_m"])
        ds, self._tracks = ds_from_tracks(self._tracks, cur), cur
        fwd, turn, pan, tilt = self.ctl
        self.drive.step(fwd, turn, r["fc"], self.rod.state, self.imu.status, dt)
        before = self.head.pose
        self.head.step(pan, tilt, self.rod.state, dt)
        self.rod.step(dt)
        self._head_moved = self.head.pose != before
        if self.pos.move(ds):  # heading snap applied
            self.imu.note_correction()
        if self.drive.pop_obstacle_alert():
            self.emit("ALERT_OBSTACLE", {"front_cm": r["fc"]})
        alert = self.rod.pop_alert()
        if alert:
            self.emit("ALERT_ROD", {"state": alert})
        self._ticks += 1
        if self._ticks % round(1 / (C.LOOP_S * C.TELEM_HZ)) == 0:
            self.outbox.append(self.telemetry(now))

    def read_slow(self) -> None:
        """Wi-Fi, CPU and recording state. May block (iw), so the loop runs it in a thread."""
        try:
            fresh = time.time() - FRAMES.stat().st_mtime < AI_STALE_S  # the video pipeline writes it at 2 fps
        except OSError:
            fresh = False
        self._slow = {"rssi_dbm": self.hw.rssi(), "cpu_temp": self.hw.cpu_temp(), "cpu_load": self.hw.cpu_load(), "rec": fresh}

    def fail_safe(self) -> None:
        """Any loop error: motors off and latched, so the operator has to press Space."""
        try:
            self.drive.stop()
        except Exception:
            log.exception("drive.stop failed")
        self.hw.safe_stop()

    # ---- output ----
    def refusal(self, now: float) -> str | None:
        if self.drive.refusal:
            return self.drive.refusal
        return self._cmd_refusal[0] if self._cmd_refusal and now < self._cmd_refusal[1] else None

    def telemetry(self, now: float | None = None) -> P.Telemetry:
        now = self.clock() if now is None else now
        ai, ai_ms, posted = self._ai
        if posted is None or now - posted > AI_STALE_S:
            ai, ai_ms = "OFF", 0.0
        return T.make_telemetry(
            next(self._seq), time.time(), state=self.state, latch=self.drive.latch, hb_seq=self.hb_seq, **self._near,
            s=self.pos.s, x=self.pos.x, y=self.pos.y, yaw=self.pos.yaw, slab=self.slabs.number(self.pos.x),
            pan=self.head.pan, tilt=self.head.tilt, led=self.led, rod=self.rod.state, pitch=self.imu.pitch,
            roll=self.imu.roll, imu=self.imu.status, ai=ai, ai_ms=ai_ms, refusal=self.refusal(now), **self._slow)

    def internal_state(self) -> dict:
        """GET /internal/state for the AI worker."""
        return dict(pan=self.head.pan, tilt=self.head.tilt, led=self.led, rod=self.rod.state, moving=self.drive.moving,
                    head_moving=self._head_moved or not self.head.settled, s=T.finite(self.pos.s),
                    slab=self.slabs.number(self.pos.x))

    def close(self) -> None:
        """Motors off, enable low, threads stopped, database closed."""
        try:
            self.drive.close()
        finally:
            self.sensors.stop()
            self.hw.close()
            self.events.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Kashimo controller")
    ap.add_argument("--config", help="config.yaml (default: KASHIMO_CONFIG or config/config.yaml)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, help="default: ws_port of the config")
    ap.add_argument("--db", default=os.environ.get("KASHIMO_DB") or str(ROOT / "robot.db"))
    ap.add_argument("--no-sim", action="store_true", help="mock mode without the simulated robot")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    from pi.controller import ws_server  # aiohttp is imported only here, so the logic above runs without it
    from pi.controller.hw import HW
    cfg = load_config(a.config)
    hw = HW(os.environ.get("HW_MODE") or cfg.get("hw_mode"))
    ctrl = Controller(hw, cfg, a.db, alerts_dir=os.environ.get("KASHIMO_ALERTS_DIR"), sim=hw.mode == "mock" and not a.no_sim)
    try:
        asyncio.run(ws_server.serve(ctrl, a.host, a.port or cfg.get("ws_port") or C.WS_PORT))
    except KeyboardInterrupt:
        pass  # serve() cut the motors in its finally
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
