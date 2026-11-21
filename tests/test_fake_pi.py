"""K03 checks: fake Pi kinematics, interlocks, watchdog, events, and one real WebSocket + HTTP round trip."""
import asyncio
import math
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest
import uvicorn
import websockets

from common import constants as C
from common import protocol as P
from tools import fake_pi as F

DT = 0.05


def ctrl(fwd=0, turn=0, pan=0, tilt=0, seq=1):
    return P.Control(seq=seq, ts=0.0, drive=P.DriveCmd(fwd=fwd, turn=turn), head=P.HeadCmd(pan=pan, tilt=tilt))


def run(sim, seconds, **keys):
    """Advance the sim with a heartbeat of the held keys, like the dashboard does."""
    for _ in range(round(seconds / DT)):
        t = sim.now + DT
        sim.on_control(ctrl(**keys), t)
        sim.step(t)


def ready(**kw):
    sim = F.Sim(0.0, **kw)
    run(sim, C.GYRO_CAL_S + 0.2)
    return sim


kinds = lambda sim: [e.kind for e in sim.events]  # noqa: E731


def test_side_distances_come_from_y_and_yaw():
    sim = ready()
    t = sim.telemetry()
    assert (t.fl, t.fr, t.fc) == (100.0, 100.0, None)
    sim.ty = 0.5
    t = sim.telemetry()
    assert (t.fl, t.fr) == (50.0, 150.0)
    sim.ty, sim.tyaw = 0.0, math.pi / 2  # facing the left wall
    assert sim.dist(0) == pytest.approx(100.0, abs=0.1)


def test_forward_speed_and_slab():
    sim = F.Sim(0.0)
    run(sim, 1.0, fwd=1)  # drive refused while the IMU calibrates
    assert sim.s == 0.0 and sim.telemetry().refusal == "IMU calibrating" and sim.telemetry().imu == "CALIBRATING"
    run(sim, C.GYRO_CAL_S)
    s0 = sim.s
    run(sim, 2.0, fwd=1)
    assert sim.s - s0 == pytest.approx(0.5, abs=0.02) and sim.x == pytest.approx(0.75, abs=0.02)
    assert sim.slab() == 2
    run(sim, 2.0, fwd=-1)
    assert sim.s == pytest.approx(s0, abs=0.03)
    run(sim, 5.0, fwd=-1)  # backward is blind, the end wall still stops it
    assert sim.tx >= 0.0


def test_pivot_adds_no_distance():
    sim = ready()
    run(sim, 1.0, turn=-1)  # Q = left = yaw grows
    assert sim.s == 0.0 and (sim.x, sim.y) == (0.25, 0.0)
    assert sim.telemetry().yaw == pytest.approx(60.0, abs=1.5)
    run(sim, 2.0, turn=1)
    assert sim.telemetry().yaw == pytest.approx(-60.0, abs=2.5)


def test_forward_refused_under_30_cm_one_alert_and_back_works():
    sim = ready()
    sim.tx = sim.x = 29.8  # 20 cm from the end wall
    run(sim, 1.0, fwd=1)
    t = sim.telemetry()
    assert sim.s == 0.0 and t.refusal == "front obstacle" and t.fc == pytest.approx(20.0, abs=0.1)
    assert kinds(sim).count("ALERT_OBSTACLE") == 1
    run(sim, 1.0, fwd=-1)
    assert sim.s < -0.2 and sim.telemetry().refusal is None
    run(sim, 1.0, turn=1)  # pivot still works
    assert sim.telemetry().yaw < -30


def test_watchdog_latch_and_link_back():
    sim = F.Sim(0.0)
    sim.step(5.0)  # no watchdog before the first CONTROL
    assert sim.state == "MANUAL" and sim.events == []
    run(sim, 0.1)
    sim.step(sim.now + C.WATCHDOG_S + 0.1)
    assert sim.state == "LINK_LOST" and sim.latch and kinds(sim) == ["LINK_LOST"]
    run(sim, 0.2, fwd=1)  # link returns
    assert sim.state == "STOPPED" and sim.latch and kinds(sim) == ["LINK_LOST", "LINK_BACK"]
    assert sim.s == 0.0 and sim.refusal == "STOP latched: press Space"
    sim.on_cmd("START", sim.now)
    run(sim, 1.0, fwd=1)
    assert sim.state == "MANUAL" and sim.s > 0.2


def test_stop_latch_blocks_drive_but_not_led():
    sim = ready()
    sim.on_cmd("STOP", sim.now)
    assert sim.state == "STOPPED" and sim.latch
    run(sim, 1.0, fwd=1)
    assert sim.s == 0.0
    sim.on_cmd("LED", sim.now)
    sim.on_cmd("START", sim.now)
    assert sim.led is False and not sim.latch and sim.state == "MANUAL"


def test_rod_cycle_and_head_rules():
    sim = ready()
    run(sim, 1.0, pan=1)
    assert sim.pan == 90.0  # head keys ignored while the rod is folded
    sim.on_cmd("ROD", sim.now)
    assert sim.rod == "LIFTING"
    run(sim, 1.0, fwd=1)
    assert sim.s == 0.0 and sim.refusal == "rod moving"
    run(sim, F.ROD_MOVE_S, fwd=0)
    assert sim.rod == "UPRIGHT"
    run(sim, 1.0, pan=1)
    assert sim.pan == pytest.approx(130.0, abs=1.0)  # 40 deg/s
    sim.on_cmd("HEAD_HOME", sim.now)
    run(sim, 1.0)
    assert (sim.pan, sim.tilt) == (90.0, 90.0)
    sim.on_cmd("ROD", sim.now)
    run(sim, F.ROD_MOVE_S + 0.2)
    assert sim.rod == "FOLDED"


def test_rod_refused_while_moving():
    sim = ready()
    run(sim, 0.5, fwd=1)
    sim.on_cmd("ROD", sim.now)
    run(sim, 0.1)  # keys released, the refusal text stays up for a moment
    assert sim.rod == "FOLDED" and sim.telemetry().refusal == "stop first"
    run(sim, 2.0)
    assert sim.telemetry().refusal is None
    sim.on_cmd("ROD", sim.now)
    assert sim.rod == "LIFTING"


def test_no_imu_freezes_reported_yaw():
    sim = ready(no_imu=True)
    assert sim.telemetry().imu == "LOST"
    run(sim, 1.0, turn=-1)
    assert sim.telemetry().yaw == 0.0 and sim.tyaw > 0.5  # the robot turned, the map did not
    run(sim, 1.0, fwd=1)
    assert sim.s > 0.2


def test_turn_gallery_geometry():
    sim = F.Sim(0.0, turn=True)
    sim.tx, sim.ty, sim.tyaw = 20.0, 28.0, math.pi / 2  # far end of the leg after the turn, facing +y
    assert [sim.dist(a) for a in (0, math.pi / 2, -math.pi / 2)] == [pytest.approx(100.0, abs=0.1)] * 3


def test_fake_defect_alert_and_images():
    sim = F.Sim(0.0, alert_s=1.0)
    run(sim, 1.2)
    ev = [e for e in sim.events if e.kind == "ALERT_DEFECT"][0]
    assert P.decode(P.encode(ev)) == ev and P.decode(P.encode(sim.telemetry())).ai == "DUMMY" and ev.data["detector"] == "dummy"
    assert sim.images["000001.jpg"][:2] == b"\xff\xd8" and sim.images["000001_heat.jpg"][:2] == b"\xff\xd8"
    assert ev.data["frame"] == "/alerts/000001.jpg"

@pytest.fixture
def server():
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        port = sk.getsockname()[1]
    app = F.make_app(F.parse_args(["--no-webcam", "--alert-s", "0.4"]))
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    while not srv.started:
        time.sleep(0.05)
    yield port
    srv.should_exit = srv.force_exit = True


def test_websocket_round_trip_and_sync_replay(server):
    async def go():
        url = f"ws://127.0.0.1:{server}/ws"
        seen, seq = [], 0
        async with websockets.connect(url) as ws:
            end = time.monotonic() + 1.5
            while time.monotonic() < end:
                seq += 1
                await ws.send(P.encode(ctrl(seq=seq)))
                try:
                    seen.append(P.decode(await asyncio.wait_for(ws.recv(), 0.1)))
                except asyncio.TimeoutError:
                    pass
        tel = [m for m in seen if isinstance(m, P.Telemetry)]
        assert len(tel) >= 8 and tel[-1].hb_seq > 0 and tel[-1].state == "MANUAL"
        got = []
        async with websockets.connect(url) as ws:  # a second client joins late and asks for the past
            await ws.send(P.encode(P.Sync(seq=1, ts=0.0, since_id=0)))
            while len([m for m in got if isinstance(m, P.Event)]) < 2:
                got.append(P.decode(await asyncio.wait_for(ws.recv(), 3)))
            await ws.send("not json")  # bad input is ignored, the link stays up
            await ws.send(P.encode(ctrl(seq=9)))
            assert isinstance(P.decode(await asyncio.wait_for(ws.recv(), 3)), (P.Telemetry, P.Event))
        events = [m for m in got if isinstance(m, P.Event)]
        assert events[0].id == 1 and all(e.kind == "ALERT_DEFECT" for e in events)
    asyncio.run(go())


def test_http_alert_image_and_video(server):
    base = f"http://127.0.0.1:{server}"
    time.sleep(0.7)  # the first fake defect is due after 0.4 s
    with urllib.request.urlopen(base + "/alerts/000001.jpg", timeout=3) as r:
        assert r.headers["Content-Type"] == "image/jpeg" and r.read(2) == b"\xff\xd8"
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(base + "/alerts/999999.jpg", timeout=3)
    assert err.value.code == 404
    with urllib.request.urlopen(base + "/video.mjpg", timeout=5) as r:
        assert "multipart/x-mixed-replace" in r.headers["Content-Type"]
        assert r.read(200).startswith(b"--frame")
