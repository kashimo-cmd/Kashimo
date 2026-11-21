"""Messages of design section 4.5: dataclasses, encode(), decode() with validation."""
import json
import math
from dataclasses import dataclass, field, fields
from typing import Any, ClassVar


class ProtocolError(ValueError):
    """Raised for any invalid message."""


def _bad(name, why):
    raise ProtocolError(f"{name}: {why}")


def v_int(name, x):
    if isinstance(x, bool) or not isinstance(x, int):
        _bad(name, "expected int")
    return x


def v_num(name, x):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        _bad(name, "expected number")
    if not math.isfinite(x):
        _bad(name, "not finite")
    return float(x)


def v_opt_num(name, x):
    return None if x is None else v_num(name, x)


def v_bool(name, x):
    if not isinstance(x, bool):
        _bad(name, "expected bool")
    return x


def v_str(name, x):
    if not isinstance(x, str):
        _bad(name, "expected string")
    return x


def v_opt_str(name, x):
    return None if x is None else v_str(name, x)


def v_enum(*allowed):
    def check(name, x):
        if not isinstance(x, str) or x not in allowed:
            _bad(name, f"expected one of {'|'.join(allowed)}")
        return x
    return check


def v_axis(name, x):
    if isinstance(x, bool) or not isinstance(x, int) or x not in (-1, 0, 1):
        _bad(name, "expected -1, 0 or 1")
    return x


def v_dict(name, x):
    if not isinstance(x, dict):
        _bad(name, "expected object")
    return x


def _f(check):
    return field(metadata={"v": check})


@dataclass(kw_only=True)
class DriveCmd:
    fwd: int = _f(v_axis)
    turn: int = _f(v_axis)


@dataclass(kw_only=True)
class HeadCmd:
    pan: int = _f(v_axis)
    tilt: int = _f(v_axis)


def _nested(cls):
    def check(name, x):
        v_dict(name, x)
        return _build(cls, x, name)
    return check


STATES = ("MANUAL", "STOPPED", "LINK_LOST")
RODS = ("FOLDED", "LIFTING", "UPRIGHT", "FOLDING")
IMUS = ("CALIBRATING", "OK", "UNCERTAIN", "LOST")
AIS = ("OFF", "DUMMY", "RUNNING", "PAUSED_LED", "PAUSED_MOTION", "NO_MODEL")
CMDS = ("HEAD_HOME", "LED", "ROD", "STOP", "START")
KINDS = ("ALERT_OBSTACLE", "ALERT_ROD", "ALERT_TILT", "BUMP", "ALERT_DEFECT", "LINK_LOST", "LINK_BACK")


@dataclass(kw_only=True)
class Message:
    t: ClassVar[str] = ""
    seq: int = _f(v_int)
    ts: float = _f(v_num)


@dataclass(kw_only=True)
class Control(Message):
    t: ClassVar[str] = "CONTROL"
    drive: DriveCmd = _f(_nested(DriveCmd))
    head: HeadCmd = _f(_nested(HeadCmd))


@dataclass(kw_only=True)
class Cmd(Message):
    t: ClassVar[str] = "CMD"
    cmd: str = _f(v_enum(*CMDS))


@dataclass(kw_only=True)
class Sync(Message):
    t: ClassVar[str] = "SYNC"
    since_id: int = _f(v_int)


@dataclass(kw_only=True)
class Telemetry(Message):
    t: ClassVar[str] = "TELEMETRY"
    state: str = _f(v_enum(*STATES))
    latch: bool = _f(v_bool)
    hb_seq: int = _f(v_int)
    fc: float | None = _f(v_opt_num)
    fl: float | None = _f(v_opt_num)
    fr: float | None = _f(v_opt_num)
    s: float = _f(v_num)
    x: float = _f(v_num)
    y: float = _f(v_num)
    yaw: float = _f(v_num)
    slab: int = _f(v_int)
    pan: float = _f(v_num)
    tilt: float = _f(v_num)
    led: bool = _f(v_bool)
    rod: str = _f(v_enum(*RODS))
    pitch: float = _f(v_num)
    roll: float = _f(v_num)
    imu: str = _f(v_enum(*IMUS))
    rssi_dbm: float = _f(v_num)
    cpu_temp: float = _f(v_num)
    cpu_load: float = _f(v_num)
    ai: str = _f(v_enum(*AIS))
    ai_ms: float = _f(v_num)
    rec: bool = _f(v_bool)
    refusal: str | None = _f(v_opt_str)


@dataclass(kw_only=True)
class Event(Message):
    t: ClassVar[str] = "EVENT"
    id: int = _f(v_int)
    kind: str = _f(v_enum(*KINDS))
    s: float = _f(v_num)
    x: float = _f(v_num)
    y: float = _f(v_num)
    slab: int = _f(v_int)
    pan: float = _f(v_num)
    tilt: float = _f(v_num)
    data: dict[str, Any] = _f(v_dict)


REGISTRY = {c.t: c for c in (Control, Cmd, Sync, Telemetry, Event)}
DEFECT_FIELDS = {"score": v_num, "frame": v_str, "heat": v_str, "detector": v_str}


def _build(cls, raw, path=""):
    kwargs = {}
    for f in fields(cls):
        name = f"{path}.{f.name}" if path else f.name
        if f.name not in raw:
            _bad(name, "missing")
        kwargs[f.name] = f.metadata["v"](name, raw[f.name])
    return cls(**kwargs)


def _check_defect(msg):
    for key, check in DEFECT_FIELDS.items():
        if key not in msg.data:
            _bad(f"data.{key}", "missing")
        check(f"data.{key}", msg.data[key])
    if msg.data["score"] < 0:
        _bad("data.score", "must be >= 0")


def _post(msg):
    if isinstance(msg, Event) and msg.kind == "ALERT_DEFECT":
        _check_defect(msg)
    return msg


def _reject_constant(token):
    raise ProtocolError(f"invalid JSON constant {token}")


def decode(text):
    """Parse and validate one JSON message. Raises ProtocolError on any fault."""
    if not isinstance(text, (str, bytes)):
        _bad("message", "expected string")
    try:
        raw = json.loads(text, parse_constant=_reject_constant)
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, ProtocolError):
            raise
        raise ProtocolError(f"bad JSON: {exc}") from None
    if not isinstance(raw, dict):
        _bad("message", "expected object")
    kind = raw.get("t")
    if not isinstance(kind, str) or kind not in REGISTRY:
        _bad("t", f"unknown type {kind!r}")
    return _post(_build(REGISTRY[kind], raw))


def _plain(msg):
    out = {"t": msg.t} if isinstance(msg, Message) else {}
    for f in fields(msg):
        val = getattr(msg, f.name)
        out[f.name] = _plain(val) if hasattr(val, "__dataclass_fields__") else val
    return out


def encode(msg):
    """Validate then serialise a message to a compact JSON string."""
    if not isinstance(msg, Message):
        _bad("message", "not a protocol message")
    plain = _plain(msg)
    _post(_build(type(msg), plain))  # refuse to send what decode would refuse
    try:
        return json.dumps(plain, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ProtocolError(f"cannot serialise: {exc}") from None
