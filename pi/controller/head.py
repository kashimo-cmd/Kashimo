"""Head: pan/tilt keys, HOME and goto for the rod (K07)."""
from __future__ import annotations

try:
    from common.constants import LOOP_S
except ImportError:  # constants module missing or renamed: use the frozen value of 4.3
    LOOP_S = 0.05

HEAD_RATE = 40.0  # deg/s while a key is held (2 deg per 50 ms step)
HOME_RATE = 60.0  # deg/s for HOME and for the moves the rod asks for
INIT_RATE = 30.0  # deg/s for the move to REST at boot
REST = (90.0, 90.0)  # (pan, tilt)
DEFAULT_FOLD_POSE = (90.0, 90.0)  # CHECK ON PI: placeholder, FOLD_POSE is measured on the prototype
MIN_DEG, MAX_DEG = 0.0, 180.0
EPS = 1e-6


def _sign(v) -> int:
    """Clamp any key value to -1, 0 or 1 (None or junk counts as 0)."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0
    return 1 if v > 0 else -1 if v < 0 else 0


def _clamp(v: float) -> float:
    return min(MAX_DEG, max(MIN_DEG, v))


def _pose(name: str, p) -> tuple[float, float]:
    try:
        pan, tilt = (float(p[0]), float(p[1]))
        ok = len(p) == 2 and MIN_DEG <= pan <= MAX_DEG and MIN_DEG <= tilt <= MAX_DEG
    except (TypeError, ValueError, IndexError):
        ok = False
    if not ok:
        raise ValueError(f"head.{name} must be (pan, tilt) with both in 0..180, got {p!r}")
    return (pan, tilt)


class Head:
    """Moves the pan and tilt servos, once per 50 ms loop. Call step() before Rod.step() each tick."""

    def __init__(self, hw, rate: float = HEAD_RATE, home_rate: float = HOME_RATE, rest=REST,
                 fold_pose=DEFAULT_FOLD_POSE, init_rate: float = INIT_RATE):
        for name, v in (("rate", rate), ("home_rate", home_rate), ("init_rate", init_rate)):
            if not v > 0:
                raise ValueError(f"head.{name} must be > 0, got {v!r}")
        self.hw = hw
        self.rate, self.home_rate = float(rate), float(home_rate)
        self.rest, self.fold_pose = _pose("rest", rest), _pose("fold_pose", fold_pose)
        self.pan, self.tilt = self.fold_pose  # a servo has no feedback: assume the rod is folded, head in fold pose
        self._goal: tuple[float, float] | None = None
        self._goal_rate = 0.0
        self._sent: list = [None, None]
        self._send()
        self.goto(self.rest, init_rate)  # init: head to REST at 30 deg/s

    @classmethod
    def from_config(cls, hw, cfg: dict | None) -> "Head":
        """Build from config.yaml (the whole dict or its `head` section); missing values use defaults."""
        d = ((cfg or {}).get("head", cfg) if cfg else None) or {}
        pick = lambda k, default: default if d.get(k) is None else d[k]
        return cls(hw, pick("rate", HEAD_RATE), pick("home_rate", HOME_RATE), pick("rest", REST),
                   pick("fold_pose", DEFAULT_FOLD_POSE))

    @property
    def pose(self) -> tuple[float, float]:
        return (self.pan, self.tilt)

    @property
    def settled(self) -> bool:
        """True when no goto or HOME is running."""
        return self._goal is None

    def goto(self, target, rate: float) -> None:
        """Move to target at rate deg/s whatever the rod does (used by Rod and at boot)."""
        self._goal = _pose("goto target", target)
        self._goal_rate = float(rate)

    def home(self, rod: str = "FOLDED") -> bool:
        """HOME: back to REST at 60 deg/s. Ignored (False) unless the rod is UPRIGHT."""
        if rod != "UPRIGHT":
            return False
        self.goto(self.rest, self.home_rate)
        return True

    def step(self, pan, tilt, rod: str = "FOLDED", dt: float = LOOP_S) -> None:
        """One loop tick. Held keys integrate at 40 deg/s and hold on release; keys only count when the rod is UPRIGHT."""
        p, t = _sign(pan), _sign(tilt)
        dt = max(dt, 0.0)
        if rod == "UPRIGHT" and (p or t):
            self._goal = None  # the operator takes over from a HOME
            self.pan = _clamp(self.pan + p * self.rate * dt)
            self.tilt = _clamp(self.tilt + t * self.rate * dt)
        elif self._goal is not None:
            room = self._goal_rate * dt
            self.pan = self._slew(self.pan, self._goal[0], room)
            self.tilt = self._slew(self.tilt, self._goal[1], room)
            if abs(self.pan - self._goal[0]) < EPS and abs(self.tilt - self._goal[1]) < EPS:
                self._goal = None
        self._send()

    @staticmethod
    def _slew(cur: float, target: float, room: float) -> float:
        """Move cur toward target by at most room."""
        if abs(target - cur) <= room:
            return target
        return cur + room if target > cur else cur - room

    def _send(self) -> None:
        """Write an axis to the servo only when it changed."""
        for i, (name, v) in enumerate((("pan", self.pan), ("tilt", self.tilt))):
            v = round(v, 2)
            if self._sent[i] != v:
                self.hw.servo(name, v)
                self._sent[i] = v
