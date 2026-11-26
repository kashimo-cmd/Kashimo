"""Tests for K09 controller: loop wiring, watchdog, latch, events, telemetry, slabs, WebSocket and HTTP."""
import asyncio
import itertools
import math
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from common import protocol as P
from pi.controller import main as M
from pi.controller import telemetry as T
from pi.controller.events import EventStore
from pi.controller.hw import HW
from pi.controller.imu import Imu

ROOT = Path(__file__).resolve().parent.parent
DT = 0.05
SEQ = itertools.count(1)
CFG = {"odo": {"track_circumference_m": 0.2, "counts_per_rev": 20, "cal_factor": 1.0},  # 10 mm per count
       "drive": {"pwm_at_speed": 0.5, "ramp_s": 0.3}}


class Clock:
    t = 100.0

    def __call__(self):
        return self.t


def new(cfg=None, sim=False, imu=None):
    return M.Controller(HW("mock"), cfg or CFG, ":memory:", clock=Clock(), imu=imu, sim=sim)


def beat(c, fwd=0, turn=0, pan=0, tilt=0):
    c.on_control(P.Control(seq=next(SEQ), ts=0.0, drive=P.DriveCmd(fwd=fwd, turn=turn), head=P.HeadCmd(pan=pan, tilt=tilt)))


def run(c, seconds, ctl=None):
    """Advance the controller: IMU every 10 ms, loop and sonar slot every 50 ms, CONTROL every 100 ms when ctl is given."""
    for i in range(round(seconds / 0.01)):
        c.clock.t += 0.01
        if ctl is not None and i % 10 == 0:
            beat(c, *ctl)
        c.imu_step(0.01)
        if i % 5 == 4:
            c.sensors.step()
            c.step(DT)


def ready(**kw):
    c = new(**kw)
    run(c, 3.1)
    assert c.imu.status == "OK"
    return c


def kinds(c):
    return [e.kind for e in c.events.since(0)]


# ---- init and calibration ----
def test_init_follows_5_1():
    c = new()
    assert not c.hw.enabled and c.hw.motor_out == (0.0, 0.0) and c.hw.led_on and c.led
    assert (c.state, c.rod.state, c.drive.latch, c.imu.status) == ("MANUAL", "FOLDED", False, "CALIBRATING")
    assert (c.pos.s, c.pos.x, c.pos.y, c.pos.yaw) == (0, 0, 0, 0) and c.head.pose == (90.0, 90.0)


def test_drive_refused_while_imu_calibrates_then_allowed():
    c = new(sim=True)
    run(c, 1.0, ctl=(1, 0, 0, 0))
    assert c.hw.motor_out == (0.0, 0.0) and "IMU calibrating" in c.telemetry().refusal
    run(c, 2.2, ctl=(0, 0, 0, 0))
    assert c.imu.status == "OK" and c.pos.bias == c.imu.bias
    run(c, 1.0, ctl=(1, 0, 0, 0))
    assert c.hw.motor_out[0] > 0 and c.telemetry().refusal is None


def test_calibration_copies_the_bias_and_resets_the_map():
    c = new()
    c.hw.sim["imu"] = (0.0, 0.0, 1.0, 0.0, 0.0, 0.5)  # the gyro reads 0.5 deg/s at rest
    run(c, 1.0)
    c.hw.sim_encoders(30, 30)  # the robot is pushed 0.3 m: the path counts it, the 3 s start again
    run(c, 0.2)
    assert c.pos.s == pytest.approx(0.3, abs=0.011) and c.imu.status == "CALIBRATING" and c.pos.yaw == 0.0  # the map does not turn yet
    run(c, 3.2)
    assert c.imu.status == "OK" and c.imu.bias == pytest.approx(0.5) and c.pos.bias == pytest.approx(0.5)
    assert (c.pos.s, c.pos.x, c.pos.yaw) == (0.0, 0.0, 0.0)  # the map starts again at the end of the calibration
    run(c, 2.0)
    assert abs(c.pos.yaw) < 0.01  # with the bias removed the map stands still


def test_position_follows_the_slow_standstill_bias():
    c = new()
    c.hw.sim["imu"] = (0.0, 0.0, 1.0, 0.0, 0.0, 0.5)
    run(c, 3.2)
    assert c.pos.bias == pytest.approx(0.5)
    c.hw.sim["imu"] = (0.0, 0.0, 1.0, 0.0, 0.0, 0.8)  # the gyro drifts while the robot stands still
    run(c, 20.0)
    assert 0.5 < c.imu.bias < 0.8 and c.pos.bias == c.imu.bias


def test_path_comes_from_the_encoders_and_a_pivot_adds_nothing():
    c = ready(sim=True)
    run(c, 2.0, ctl=(1, 0, 0, 0))
    run(c, 0.5, ctl=(0, 0, 0, 0))
    l, r = c.hw.encoder_counts()
    assert c.pos.s > 0.3 and c.pos.s == pytest.approx((l + r) / 2 * 0.01, abs=0.011) and c.pos.x == pytest.approx(c.pos.s, abs=0.01)
    assert c.telemetry().slab == int(c.pos.x // 0.5) + 1
    s = c.pos.s
    run(c, 0.5, ctl=(0, 1, 0, 0))  # pivot right
    assert c.pos.s == pytest.approx(s, abs=0.011) and c.pos.yaw < -30 and c.pos.x == pytest.approx(s, abs=0.02)


def test_drive_uses_the_commanded_direction_for_the_encoders():
    c = ready(sim=True)
    run(c, 1.0, ctl=(-1, 0, 0, 0))
    run(c, 0.5, ctl=(0, 0, 0, 0))
    assert c.pos.s < -0.1


# ---- watchdog, latch, link ----
def test_watchdog_cuts_the_motors_within_half_a_second():
    c = ready(sim=True)
    run(c, 1.0, ctl=(1, 0, 0, 0))
    assert c.hw.motor_out[0] > 0
    last, lag = c.last_ctrl, None
    for _ in range(100):
        run(c, 0.01)
        if c.link_lost:
            lag = c.clock.t - last
            break
        assert c.hw.motor_out[0] > 0  # still driving until the watchdog fires
    assert lag is not None and 0.49 < lag <= 0.52
    assert c.hw.motor_out == (0.0, 0.0) and not c.hw.enabled and c.drive.latch and c.state == "LINK_LOST"


def test_link_lost_event_then_back_needs_the_latch_released():
    c = ready(sim=True)
    run(c, 1.0, ctl=(1, 0, 0, 0))
    run(c, 0.7)
    assert kinds(c) == ["LINK_LOST"] and c.events.since(0)[0].x == pytest.approx(c.pos.x, abs=0.3)
    c.on_cmd("START")  # no heartbeat yet: refused
    assert c.state == "LINK_LOST" and c.drive.latch
    run(c, 0.5, ctl=(1, 0, 0, 0))  # heartbeat is back, the key is still held
    assert kinds(c) == ["LINK_LOST", "LINK_BACK"] and c.state == "STOPPED"
    assert c.hw.motor_out == (0.0, 0.0) and "STOPPED" in c.telemetry().refusal
    c.on_cmd("START")
    run(c, 0.5, ctl=(1, 0, 0, 0))
    assert c.state == "MANUAL" and c.hw.motor_out[0] > 0


def test_watchdog_is_armed_by_the_first_control_only():
    c = new()
    run(c, 2.0)
    assert c.state == "MANUAL" and kinds(c) == []


def test_stop_latch_blocks_drive_but_not_led_or_head_home():
    c = ready(sim=True)
    c.on_cmd("STOP")
    assert c.state == "STOPPED" and c.telemetry().latch
    run(c, 0.5, ctl=(1, 0, 0, 0))
    assert c.hw.motor_out == (0.0, 0.0) and "STOPPED" in c.telemetry().refusal
    c.on_cmd("LED")
    assert not c.hw.led_on and not c.telemetry().led
    c.on_cmd("LED")
    assert c.hw.led_on
    c.on_cmd("HEAD_HOME")  # rod folded: ignored, no error
    c.on_cmd("START")
    run(c, 0.5, ctl=(1, 0, 0, 0))
    assert c.state == "MANUAL" and c.hw.motor_out[0] > 0


def test_a_loop_error_cuts_the_motors_and_latches_even_when_the_driver_call_fails():
    c = ready(sim=True)
    run(c, 1.0, ctl=(1, 0, 0, 0))
    assert c.hw.motor_out[0] > 0 and c.hw.enabled

    def boom(*a):
        raise OSError("bus")

    c.hw.motors, c.hw.motors_enable = boom, boom  # the normal way to stop is broken: only safe_stop still works
    c.fail_safe()
    assert c.drive.latch and c.hw.motor_out == (0.0, 0.0) and not c.hw.enabled


def test_a_hardware_error_in_step_propagates_to_the_loop():
    c = ready()
    c.hw.motors = lambda l, r: (_ for _ in ()).throw(OSError("driver"))
    with pytest.raises(OSError):
        run(c, 0.3, ctl=(1, 0, 0, 0))
    assert not c.hw.enabled  # Drive already left enable low


# ---- rod, head, obstacle, imu events ----
def test_rod_cmd_refused_while_moving_then_lifts_and_head_keys_work():
    c = ready(sim=True)
    run(c, 1.0, ctl=(1, 0, 0, 0))
    c.on_cmd("ROD")
    assert "Stop first" in c.telemetry().refusal and c.rod.state == "FOLDED"
    run(c, 1.7, ctl=(0, 0, 0, 0))
    assert c.telemetry().refusal is None  # the refusal text expires
    c.on_cmd("ROD")
    assert c.rod.state == "LIFTING"
    run(c, 0.5, ctl=(1, 0, 0, 0))
    assert "Rod moving" in c.telemetry().refusal and c.hw.motor_out == (0.0, 0.0)
    run(c, 3.0, ctl=(0, 0, 0, 0))
    assert c.rod.state == "UPRIGHT" and c.telemetry().rod == "UPRIGHT"
    run(c, 0.5, ctl=(0, 0, 1, -1))
    assert c.head.pan == pytest.approx(110.0, abs=2.1) and c.head.tilt == pytest.approx(70.0, abs=2.1)
    assert c.internal_state()["head_moving"] is True
    run(c, 0.2, ctl=(0, 0, 0, 0))
    assert c.internal_state()["head_moving"] is False


def test_rod_timeout_becomes_alert_rod():
    c = ready(cfg={**CFG, "rod": {"rate": 1.0, "timeout_s": 0.5}})
    c.on_cmd("ROD")
    run(c, 1.0, ctl=(0, 0, 0, 0))
    ev = [e for e in c.events.since(0) if e.kind == "ALERT_ROD"]
    assert len(ev) == 1 and ev[0].data == {"state": "LIFTING"}


def test_obstacle_alert_once_per_approach():
    c = ready(sim=True)
    c.hw.sim["pulse"]["front"] = 20.0
    run(c, 1.0, ctl=(1, 0, 0, 0))
    assert c.hw.motor_out == (0.0, 0.0) and "Obstacle" in c.telemetry().refusal and c.telemetry().fc == 20.0
    assert kinds(c) == ["ALERT_OBSTACLE"] and c.events.since(0)[0].data == {"front_cm": 20.0}
    c.hw.sim["pulse"]["front"] = 100.0
    run(c, 0.6, ctl=(1, 0, 0, 0))
    c.hw.sim["pulse"]["front"] = 20.0
    run(c, 1.0, ctl=(1, 0, 0, 0))
    assert kinds(c).count("ALERT_OBSTACLE") == 2


def test_bump_and_tilt_events_carry_the_pose():
    c = ready()
    c.hw.sim["imu"] = (0.0, 0.0, 1.6, 0.0, 0.0, 0.0)
    run(c, 0.03)
    c.hw.sim["imu"] = (0.0, 0.0, 1.0, 0.0, 0.0, 0.0)
    run(c, 0.3)
    r = math.radians(40)
    c.hw.sim["imu"] = (-math.sin(r), 0.0, math.cos(r), 0.0, 0.0, 0.0)
    run(c, 3.0)  # the 0.5 s low-pass needs time to settle
    evs = c.events.since(0)
    assert [e.kind for e in evs] == ["BUMP", "ALERT_TILT"] and 35.0 < evs[1].data["tilt"] < 36.5  # fires as it crosses 35
    assert c.telemetry().pitch == pytest.approx(40, abs=1) and evs[0].slab == 1 and (evs[0].pan, evs[0].tilt) == (90.0, 90.0)


def test_imu_lost_freezes_yaw_and_shows_in_telemetry():
    c = ready()
    c.pos.yaw = 30.0
    c.hw.sim["imu"] = lambda: (_ for _ in ()).throw(OSError("i2c"))
    run(c, 1.0)
    assert c.telemetry().imu == "LOST" and c.pos.yaw == 30.0


# ---- events ----
POSE = dict(s=1.0, x=1.0, y=0.5, slab=3, pan=90.0, tilt=90.0)
DEFECT = {"score": 4.2, "frame": "/alerts/000001.jpg", "heat": "/alerts/000001_heat.jpg", "detector": "dummy"}


def test_events_persist_across_restart_and_since_filters(tmp_path):
    path = str(tmp_path / "robot.db")
    st = EventStore(path)
    a, b = st.add("BUMP", POSE), st.add("ALERT_DEFECT", POSE, DEFECT)
    st.close()
    st = EventStore(path)
    c = st.add("LINK_LOST", POSE)
    assert (a.id, b.id, c.id) == (1, 2, 3) and st.last_id == 3
    assert [e.id for e in st.since(0)] == [1, 2, 3] and [e.id for e in st.since(2)] == [3] and st.since(3) == []
    got = st.since(1)[0]
    assert got.kind == "ALERT_DEFECT" and got.data == DEFECT and got.slab == 3 and got.ts == pytest.approx(b.ts)
    P.encode(got)
    st.close()


def test_event_store_refuses_bad_events_without_using_an_id():
    st = EventStore()
    for kind, data in (("NOPE", {}), ("ALERT_DEFECT", {"score": 1}), ("ALERT_DEFECT", {**DEFECT, "score": -1})):
        with pytest.raises(P.ProtocolError):
            st.add(kind, POSE, data)
    assert st.add("BUMP", POSE).id == 1 and st.since(0)[0].id == 1


def test_event_store_keeps_events_when_the_disk_fails():
    class Broken:
        def execute(self, *a):
            raise __import__("sqlite3").OperationalError("disk I/O error")

        commit = close = execute

    st = EventStore()
    st.db = Broken()
    ev = st.add("BUMP", POSE)
    assert ev.id == 1 and [e.id for e in st.since(0)] == [1] and st.add("BUMP", POSE).id == 2


# ---- slabs and telemetry ----
def test_slab_numbers(tmp_path):
    s = T.Slabs()
    assert [s.number(x) for x in (0.0, 0.499, 0.5, 12.4, -0.1)] == [1, 1, 2, 25, 0]
    assert T.Slabs(0.5, origin_m=2.0).number(2.6) == 2 and T.Slabs(overrides={"3": 40}).number(1.2) == 40
    f = tmp_path / "slabs.json"
    f.write_text('{"sample":true,"slab_width_m":0.25,"origin_m":1.0,"overrides":{}}')
    assert T.Slabs.from_file(f).number(1.3) == 2
    assert T.Slabs.from_file(tmp_path / "missing.json", 0.5).number(0.6) == 2
    f.write_text("[1, 2]")
    assert T.Slabs.from_file(f, 0.5).number(0.6) == 2
    with pytest.raises(ValueError):
        T.Slabs(0)


def test_telemetry_is_valid_10_hz_and_never_raises_on_junk():
    c = ready()
    c.outbox.clear()
    run(c, 1.0)
    tel = [m for m in c.outbox if isinstance(m, P.Telemetry)]
    assert len(tel) == 10 and [t.seq for t in tel] == sorted(t.seq for t in tel)
    assert P.decode(P.encode(tel[-1])).state == "MANUAL" and tel[-1].ai == "OFF" and tel[-1].rssi_dbm == -100.0
    bad = T.make_telemetry(1, 0.0, state="MANUAL", latch=False, hb_seq=0, fc=float("nan"), fl=None, fr="x", s=float("inf"),
                           x=None, y=0, yaw=0, slab=1, pan=90, tilt=90, led=True, rod="FOLDED", pitch=0, roll=0, imu="OK",
                           rssi_dbm=None, cpu_temp=None, cpu_load=None, ai="OFF", ai_ms=None, rec=False, refusal=None)
    assert (bad.fc, bad.fl, bad.fr, bad.s, bad.rssi_dbm) == (None, None, None, 0.0, -100.0) and P.encode(bad)


def test_read_slow_and_recording_flag(tmp_path, monkeypatch):
    c = new()
    c.read_slow()
    t = c.telemetry()
    assert (t.rssi_dbm, t.cpu_temp, t.cpu_load, t.rec) == (-58.0, 45.0, 5.0, False)
    frame = tmp_path / "latest.jpg"
    frame.write_bytes(b"x")
    monkeypatch.setattr(M, "FRAMES", frame)
    c.read_slow()
    assert c.telemetry().rec is True


def test_ai_status_is_relayed_and_goes_stale():
    c = new()
    c.set_ai_status("RUNNING", 12.5)
    t = c.telemetry()
    assert (t.ai, t.ai_ms) == ("RUNNING", 12.5)
    c.clock.t += M.AI_STALE_S + 1
    assert c.telemetry().ai == "OFF"
    for ai, ms in (("FAST", 1.0), ("RUNNING", "x"), ("RUNNING", float("nan"))):
        with pytest.raises(P.ProtocolError):
            c.set_ai_status(ai, ms)


def test_post_defect_stores_queues_and_rejects_bad_data():
    c = new()
    ev = c.post_defect(DEFECT)
    assert ev.kind == "ALERT_DEFECT" and c.outbox[-1] is ev and ev.id == 1
    n = len(c.outbox)
    for bad in (None, {}, {**DEFECT, "score": "high"}):
        with pytest.raises(P.ProtocolError):
            c.post_defect(bad)
    assert len(c.outbox) == n and c.events.last_id == 1


def test_config_files_of_the_repo_load():
    c = M.Controller(HW("mock"), M.load_config(ROOT / "config" / "config.yaml"))
    assert c.slabs.width == 0.5 and c.drive.pwm == 0.5 and c.pos.snap is False and c.sensors.m_per_count == pytest.approx(0.0075)
    with pytest.raises(ValueError):
        M.Controller(HW("mock"), {})  # odo.track_circumference_m is missing


def test_close_leaves_the_motors_off():
    c = ready(sim=True)
    run(c, 1.0, ctl=(1, 0, 0, 0))
    c.close()
    assert c.hw.closed and c.hw.motor_out == (0.0, 0.0) and not c.hw.enabled


# ---- WebSocket and HTTP (need aiohttp for the Pi side and websockets for the client) ----
def free_port():
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        return sk.getsockname()[1]


@pytest.fixture
def net():
    pytest.importorskip("aiohttp")
    return pytest.importorskip("websockets")


class Live:
    """A real server on a free port, driven by the real asyncio loops (controller on a mock HW with the simulated robot)."""

    def __init__(self, tmp_path):
        self.ctrl = M.Controller(HW("mock"), CFG, str(tmp_path / "robot.db"), imu=Imu(cal_s=0.2), alerts_dir=tmp_path / "alerts", sim=True)
        self.port, self.stop, self.ready = free_port(), asyncio.Event(), asyncio.Event()
        self.url = f"ws://127.0.0.1:{self.port}/ws"

    async def __aenter__(self):
        from pi.controller import ws_server
        self.task = asyncio.create_task(ws_server.serve(self.ctrl, "127.0.0.1", self.port, self.stop, self.ready))
        await asyncio.wait_for(self.ready.wait(), 5)
        return self

    async def __aexit__(self, *exc):
        self.stop.set()
        await asyncio.wait_for(self.task, 5)


def control(fwd=0, turn=0):
    return P.encode(P.Control(seq=next(SEQ), ts=time.time(), drive=P.DriveCmd(fwd=fwd, turn=turn), head=P.HeadCmd(pan=0, tilt=0)))


async def recv_until(ws, pred, timeout=3.0):
    end = time.monotonic() + timeout
    while True:
        msg = P.decode(await asyncio.wait_for(ws.recv(), max(end - time.monotonic(), 0.01)))
        if pred(msg):
            return msg


def test_ws_drive_then_watchdog_in_real_time(net, tmp_path):
    async def scenario():
        async with Live(tmp_path) as live:
            async with net.connect(live.url) as ws:
                await ws.send(P.encode(P.Sync(seq=1, ts=0.0, since_id=0)))
                await recv_until(ws, lambda m: isinstance(m, P.Telemetry) and m.imu == "OK")
                for _ in range(10):  # 1 s of forward, the heartbeat every 100 ms
                    await ws.send(control(1))
                    await asyncio.sleep(0.1)
                tel = await recv_until(ws, lambda m: isinstance(m, P.Telemetry) and m.s > 0.1)  # skip the queued old ones
                assert tel.hb_seq > 1 and live.ctrl.hw.motor_out[0] > 0
                lost = await recv_until(ws, lambda m: isinstance(m, P.Event) and m.kind == "LINK_LOST")  # the heartbeat stopped
                lag = live.ctrl.link_lost_at - live.ctrl.last_ctrl
                assert 0.49 < lag < 0.56 and live.ctrl.hw.motor_out == (0.0, 0.0) and lost.id == 1  # 0.5 s plus one 10 ms poll
                assert (await recv_until(ws, lambda m: isinstance(m, P.Telemetry) and m.state == "LINK_LOST")).latch
                await ws.send(control(0))
                await recv_until(ws, lambda m: isinstance(m, P.Event) and m.kind == "LINK_BACK")
                assert (await recv_until(ws, lambda m: isinstance(m, P.Telemetry) and m.state == "STOPPED")).latch
            return live.ctrl
    ctrl = asyncio.run(scenario())
    assert ctrl.hw.closed and ctrl.hw.motor_out == (0.0, 0.0)


def test_ws_cmd_stop_led_start_and_telemetry_rate(net, tmp_path):
    async def scenario():
        async with Live(tmp_path) as live:
            async with net.connect(live.url) as ws:
                stamps = []
                end = time.monotonic() + 1.5
                while time.monotonic() < end:
                    await recv_until(ws, lambda m: isinstance(m, P.Telemetry))
                    stamps.append(time.monotonic())
                rate = (len(stamps) - 1) / (stamps[-1] - stamps[0])
                assert 8.0 < rate < 12.0, rate  # 10 Hz
                for cmd, pred in (("STOP", lambda m: m.latch and m.state == "STOPPED"), ("LED", lambda m: not m.led),
                                  ("START", lambda m: not m.latch and m.state == "MANUAL")):
                    await ws.send(P.encode(P.Cmd(seq=next(SEQ), ts=0.0, cmd=cmd)))
                    await recv_until(ws, lambda m: isinstance(m, P.Telemetry) and pred(m))
    asyncio.run(scenario())


def test_ws_sync_replays_events_and_bad_messages_are_ignored(net, tmp_path):
    async def scenario():
        async with Live(tmp_path) as live:
            for kind in ("BUMP", "ALERT_TILT", "BUMP"):
                live.ctrl.emit(kind)
            await asyncio.sleep(0.2)  # the loop flushes them to nobody: a client that connects later only gets a replay
            async with net.connect(live.url) as ws:
                await ws.send("not json")
                await ws.send('{"t":"CONTROL","seq":1,"ts":0,"drive":{"fwd":5,"turn":0},"head":{"pan":0,"tilt":0}}')
                await ws.send(P.encode(P.Sync(seq=2, ts=0.0, since_id=1)))
                got = [await recv_until(ws, lambda m: isinstance(m, P.Event)) for _ in range(2)]
                assert [e.id for e in got] == [2, 3] and got[0].kind == "ALERT_TILT"
                assert live.ctrl.last_ctrl is None  # a bad CONTROL is not a heartbeat
    asyncio.run(scenario())


def test_http_alerts_and_internal_endpoints(net, tmp_path):
    aiohttp = pytest.importorskip("aiohttp")

    async def scenario():
        async with Live(tmp_path) as live:
            (tmp_path / "alerts" / "000001.jpg").write_bytes(b"\xff\xd8jpeg")
            base = f"http://127.0.0.1:{live.port}"
            async with aiohttp.ClientSession() as http, net.connect(live.url) as ws:
                r = await http.get(f"{base}/alerts/000001.jpg")
                assert r.status == 200 and await r.read() == b"\xff\xd8jpeg"
                assert (await http.get(f"{base}/alerts/nope.jpg")).status == 404
                assert (await http.get(f"{base}/alerts/%2e%2e/robot.db")).status in (403, 404)
                st = await (await http.get(f"{base}/internal/state")).json()
                assert set(st) == {"pan", "tilt", "led", "rod", "moving", "head_moving", "s", "slab"} and st["rod"] == "FOLDED"
                r = await http.post(f"{base}/internal/event", json={"data": DEFECT})
                assert r.status == 200 and (await r.json())["id"] == 1
                ev = await recv_until(ws, lambda m: isinstance(m, P.Event))
                assert ev.kind == "ALERT_DEFECT" and ev.data == DEFECT
                for path, body in (("event", {"data": {"score": 1}}), ("event", {"kind": "BUMP", "data": {}}), ("event", [1]),
                                   ("ai_status", {"ai": "FAST"}), ("ai_status", {"ai": "RUNNING", "ai_ms": "x"})):
                    assert (await http.post(f"{base}/internal/{path}", json=body)).status == 400, (path, body)
                assert (await http.post(f"{base}/internal/event", data="{oops")).status == 400
                assert (await http.post(f"{base}/internal/ai_status", json={"ai": "RUNNING", "ai_ms": 31.5})).status == 200
                tel = await recv_until(ws, lambda m: isinstance(m, P.Telemetry) and m.ai == "RUNNING")
                assert tel.ai_ms == 31.5
    asyncio.run(scenario())


def test_internal_endpoints_are_local_only(net):
    import types

    from aiohttp import web

    from pi.controller import ws_server
    assert ws_server.is_local("127.0.0.1") and ws_server.is_local("::1")
    assert not ws_server.is_local("192.168.1.20") and not ws_server.is_local(None)
    stranger = types.SimpleNamespace(remote="192.168.1.20", app={ws_server.CTRL: new(), ws_server.HUB: None})
    for handler in (ws_server.internal_state, ws_server.internal_event, ws_server.internal_ai_status):
        with pytest.raises(web.HTTPForbidden):
            asyncio.run(handler(stranger))
    assert stranger.app[ws_server.CTRL].events.last_id == 0


def test_loop_error_does_not_stop_the_loop_and_latches(net):
    from pi.controller import ws_server
    c, calls = new(), []

    def boom(dt, now):
        calls.append(now)
        raise OSError("sensor bus")

    async def scenario():
        task = asyncio.create_task(ws_server.every(0.01, boom, c))
        await asyncio.sleep(0.15)
        task.cancel()
    asyncio.run(scenario())
    assert len(calls) > 5 and c.drive.latch and c.hw.motor_out == (0.0, 0.0)


def test_real_process_with_ws_smoke(net, tmp_path):
    """HW_MODE=mock python -m pi.controller.main, then tools/ws_smoke.py drives it (the K09 done check)."""
    port = free_port()
    env = {**__import__("os").environ, "HW_MODE": "mock", "KASHIMO_ALERTS_DIR": str(tmp_path / "a"), "PYTHONPATH": str(ROOT)}
    proc = subprocess.Popen([sys.executable, "-m", "pi.controller.main", "--port", str(port), "--host", "127.0.0.1",
                             "--db", str(tmp_path / "robot.db")], cwd=ROOT, env=env, stdout=open(tmp_path / "ctrl.log", "w"), stderr=subprocess.STDOUT)
    try:
        for _ in range(100):
            with socket.socket() as sk:
                if sk.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.1)
        out = subprocess.run([sys.executable, "tools/ws_smoke.py", "--url", f"ws://127.0.0.1:{port}/ws", "--seconds", "2"],
                             cwd=ROOT, capture_output=True, text=True, timeout=40)
        assert out.returncode == 0, out.stdout + out.stderr
        assert "OK: s 0.000 ->" in out.stdout
    finally:
        proc.terminate()
        proc.wait(timeout=10)
