"""K02 checks: every message round-trips, bad input is rejected, constants and key map match 4.3 / 4.6."""
import copy
import json

import pytest

from common import constants as C
from common import protocol as P

DEFECT = {"score": 3.2, "frame": "/alerts/000012.jpg", "heat": "/alerts/000012_heat.jpg", "detector": "dummy"}


def telemetry(**over):
    base = dict(
        seq=7, ts=1000.5, state="MANUAL", latch=False, hb_seq=42, fc=120.0, fl=95.5, fr=None,
        s=3.25, x=3.2, y=-0.1, yaw=1.5, slab=7, pan=90.0, tilt=90.0, led=True, rod="FOLDED",
        pitch=0.4, roll=-0.2, imu="OK", rssi_dbm=-61.0, cpu_temp=55.1, cpu_load=0.3,
        ai="DUMMY", ai_ms=0.0, rec=True, refusal=None,
    )
    base.update(over)
    return P.Telemetry(**base)


def event(kind="BUMP", data=None, **over):
    base = dict(seq=8, ts=1001.0, id=3, kind=kind, s=4.0, x=4.0, y=0.2, slab=9, pan=90.0, tilt=80.0,
                data={} if data is None else data)
    base.update(over)
    return P.Event(**base)


def control(fwd=1, turn=0, pan=0, tilt=-1):
    return P.Control(seq=1, ts=1.0, drive=P.DriveCmd(fwd=fwd, turn=turn), head=P.HeadCmd(pan=pan, tilt=tilt))


ALL = [control(), control(-1, 1, 1, 0)]
ALL += [P.Cmd(seq=2, ts=2.0, cmd=c) for c in P.CMDS]
ALL += [P.Sync(seq=3, ts=3.0, since_id=0), telemetry(), telemetry(fc=None, fl=None, refusal="stop first")]
ALL += [telemetry(state=s) for s in P.STATES] + [telemetry(rod=r) for r in P.RODS]
ALL += [telemetry(imu=i) for i in P.IMUS] + [telemetry(ai=a) for a in P.AIS]
ALL += [event(k) for k in P.KINDS if k != "ALERT_DEFECT"] + [event("ALERT_DEFECT", DEFECT)]


@pytest.mark.parametrize("msg", ALL)
def test_round_trip(msg):
    text = P.encode(msg)
    assert P.decode(text) == msg
    assert json.loads(text)["t"] == msg.t


def test_every_type_covered():
    assert {m.t for m in ALL} == set(P.REGISTRY) == {"CONTROL", "CMD", "SYNC", "TELEMETRY", "EVENT"}


def test_wire_shape_of_control():
    raw = json.loads(P.encode(control()))
    assert raw == {"t": "CONTROL", "seq": 1, "ts": 1.0, "drive": {"fwd": 1, "turn": 0}, "head": {"pan": 0, "tilt": -1}}


def test_telemetry_wire_fields_match_contract():
    keys = set(json.loads(P.encode(telemetry())))
    want = ("t seq ts state latch hb_seq fc fl fr s x y yaw slab pan tilt led rod pitch roll imu "
            "rssi_dbm cpu_temp cpu_load ai ai_ms rec refusal").split()
    assert keys == set(want)


def test_int_accepted_as_float_and_encoded_as_float():
    msg = P.decode(P.encode(telemetry(x=3)))
    assert msg.x == 3.0 and isinstance(msg.x, float)


def test_decode_accepts_bytes():
    assert P.decode(P.encode(control()).encode()) == control()


def test_extra_fields_ignored():
    raw = json.loads(P.encode(control()))
    raw["future"] = 1
    assert P.decode(json.dumps(raw)) == control()


@pytest.mark.parametrize("text", [
    "", "not json", "[]", "null", "42", '"CONTROL"', "{}", '{"t":"NOPE","seq":1,"ts":1}',
    '{"t":5,"seq":1,"ts":1}', '{"seq":1,"ts":1}', '{"t":"CMD","seq":1,"ts":NaN,"cmd":"STOP"}',
    '{"t":"CMD","seq":1,"ts":Infinity,"cmd":"STOP"}',
])
def test_garbage_rejected(text):
    with pytest.raises(P.ProtocolError):
        P.decode(text)


def test_decode_rejects_non_text():
    with pytest.raises(P.ProtocolError):
        P.decode(None)


def good_raw(msg):
    return json.loads(P.encode(msg))


def reject(raw):
    with pytest.raises(P.ProtocolError):
        P.decode(json.dumps(raw))


@pytest.mark.parametrize("msg", [control(), P.Cmd(seq=1, ts=1.0, cmd="STOP"), P.Sync(seq=1, ts=1.0, since_id=4),
                                 telemetry(), event("ALERT_DEFECT", DEFECT)])
def test_missing_field_rejected(msg):
    raw = good_raw(msg)
    for key in raw:
        if key != "t":
            broken = copy.deepcopy(raw)
            del broken[key]
            reject(broken)


def test_missing_nested_field_rejected():
    raw = good_raw(control())
    del raw["drive"]["turn"]
    reject(raw)
    raw = good_raw(control())
    del raw["head"]["pan"]
    reject(raw)


@pytest.mark.parametrize("path,value", [
    (("seq",), "1"), (("seq",), 1.5), (("seq",), True), (("seq",), None), (("ts",), "now"), (("ts",), True),
    (("drive",), [1, 0]), (("drive", "fwd"), 2), (("drive", "fwd"), True), (("drive", "turn"), "1"),
    (("drive", "turn"), 0.5), (("head", "pan"), -2), (("head", "tilt"), None), (("head",), None),
])
def test_control_wrong_type_or_range(path, value):
    raw = good_raw(control())
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    reject(raw)


@pytest.mark.parametrize("field,value", [
    ("state", "RUNNING"), ("state", 1), ("state", None), ("latch", 1), ("latch", "true"), ("hb_seq", 1.5),
    ("fc", "12"), ("fc", True), ("s", None), ("s", "1"), ("slab", 1.5), ("slab", None), ("led", 0),
    ("rod", "UP"), ("imu", "ok"), ("ai", "ON"), ("rec", "yes"), ("refusal", 5), ("rssi_dbm", None),
    ("cpu_temp", "hot"),
])
def test_telemetry_wrong_type(field, value):
    raw = good_raw(telemetry())
    raw[field] = value
    reject(raw)


@pytest.mark.parametrize("field,value", [
    ("cmd", "FIRE"), ("cmd", "stop"), ("cmd", 1), ("cmd", None),
])
def test_cmd_wrong_value(field, value):
    raw = good_raw(P.Cmd(seq=1, ts=1.0, cmd="STOP"))
    raw[field] = value
    reject(raw)


@pytest.mark.parametrize("value", ["3", 1.5, None, True])
def test_sync_wrong_type(value):
    raw = good_raw(P.Sync(seq=1, ts=1.0, since_id=3))
    raw["since_id"] = value
    reject(raw)


@pytest.mark.parametrize("field,value", [
    ("id", "1"), ("id", 1.5), ("kind", "ALERT_FIRE"), ("kind", None), ("data", []), ("data", None),
    ("slab", "7"), ("pan", None),
])
def test_event_wrong_type(field, value):
    raw = good_raw(event())
    raw[field] = value
    reject(raw)


@pytest.mark.parametrize("key", list(DEFECT))
def test_defect_data_missing_key(key):
    data = {k: v for k, v in DEFECT.items() if k != key}
    with pytest.raises(P.ProtocolError):
        P.encode(event("ALERT_DEFECT", data))
    reject(dict(good_raw(event()), kind="ALERT_DEFECT", data=data))


@pytest.mark.parametrize("key,value", [("score", "high"), ("score", -1), ("frame", 5), ("heat", None), ("detector", 1)])
def test_defect_data_wrong_type(key, value):
    reject(dict(good_raw(event()), kind="ALERT_DEFECT", data=dict(DEFECT, **{key: value})))


def test_other_events_keep_free_form_data():
    msg = event("ALERT_TILT", {"pitch": 36.0, "note": "x"})
    assert P.decode(P.encode(msg)) == msg


def test_encode_refuses_invalid_messages():
    for bad in [control(fwd=2), telemetry(state="NOPE"), telemetry(x=float("nan")), P.Sync(seq=1, ts=1.0, since_id="3"),
                event(data={"a": float("inf")})]:
        with pytest.raises(P.ProtocolError):
            P.encode(bad)
    with pytest.raises(P.ProtocolError):
        P.encode({"t": "CMD"})


def test_encode_has_no_spaces_and_is_one_line():
    text = P.encode(control())
    assert " " not in text and "\n" not in text


def test_constants_match_section_4_3():
    assert (C.OBSTACLE_CM, C.DRIVE_SPEED, C.LOOP_S, C.TELEM_HZ) == (30, 0.25, 0.05, 10)
    assert (C.HEARTBEAT_S, C.WATCHDOG_S, C.WARN_S) == (0.1, 0.5, 0.3)
    assert (C.HEAD_RATE, C.HOME_RATE, C.REST) == (40, 60, (90, 90))
    assert (C.ROD_RATE, C.ROD_TIMEOUT, C.IMU_RATE, C.GYRO_CAL_S) == (30, 5, 100, 3)
    assert (C.SNAP_STRAIGHT, C.SNAP_NO_TURN_DPS, C.SNAP_WINDOW) == (1.0, 3, 25)
    assert (C.TILT_WARN, C.TILT_ALERT, C.BUMP_G, C.ROD_HOLD_S) == (25, 35, 0.5, 1.0)
    assert (C.STANDSTILL_GYRO_DPS, C.STANDSTILL_ACCEL_G, C.STANDSTILL_NO_COUNT_S) == (1, 0.03, 1)
    assert (C.WS_PORT, C.WHEP_PORT, C.RTSP_PORT, C.DASHBOARD_PORT) == (8765, 8889, 8554, 8080)
    assert C.FOLD_POSE is None  # measured on the prototype, not invented


def test_constants_agree_with_config_yaml():
    import yaml
    from pathlib import Path
    cfg = yaml.safe_load((Path(__file__).resolve().parent.parent / "config/config.yaml").read_text(encoding="utf-8"))
    assert cfg["ws_port"] == C.WS_PORT
    assert cfg["imu"]["snap_window_deg"] == C.SNAP_WINDOW and cfg["imu"]["snap_straight_m"] == C.SNAP_STRAIGHT


@pytest.mark.parametrize("cm,colour", [
    (None, "none"), (0, "red"), (29.9, "red"), (30, "orange"), (45, "orange"), (60, "orange"),
    (60.1, "green"), (150, "green"), (250, "green"),
])
def test_front_colour(cm, colour):
    assert C.front_colour(cm) == colour


@pytest.mark.parametrize("dbm,bars", [(-30, 4), (-60, 4), (-61, 3), (-70, 3), (-71, 2), (-80, 2), (-81, 1), (-95, 1)])
def test_link_bars(dbm, bars):
    assert C.link_bars(dbm) == bars


def test_key_map_matches_section_4_6():
    assert C.KEY_MAP == {
        "KeyW": "FORWARD", "KeyS": "BACKWARD", "KeyA": "LEFT", "KeyD": "RIGHT",
        "ArrowLeft": "HEAD_LEFT", "ArrowRight": "HEAD_RIGHT", "ArrowUp": "HEAD_UP", "ArrowDown": "HEAD_DOWN",
        "KeyH": "HEAD_HOME", "KeyL": "LED", "Enter": "PHOTO", "KeyP": "SCREENSHOT", "KeyR": "ROD", "Space": "STOP",
    }
    assert len(C.KEY_MAP) == 14
    assert C.HELD_KEYS | set(C.KEY_TO_CMD) | {"Enter", "KeyP"} == set(C.KEY_MAP)
    assert not C.HELD_KEYS & set(C.KEY_TO_CMD)
    assert set(C.KEY_TO_CMD.values()) <= set(P.CMDS)
    assert {"Space", "Enter", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"} == C.BLOCKED_DEFAULTS
