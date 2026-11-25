"""Drive: key mixing, 0.3 s ramp, interlocks and STOP latch (K06)."""
from __future__ import annotations

try:
    from common.constants import LOOP_S, OBSTACLE_CM
except ImportError:  # constants module missing or renamed: use the frozen values of 4.3
    OBSTACLE_CM, LOOP_S = 30, 0.05

INNER_RATIO = 0.4  # inner track speed / outer track speed in a curve
RAMP_S = 0.3  # time from zero to full target speed
DEFAULT_PWM_AT_SPEED = 0.6  # CHECK ON PI: placeholder until calib_encoders (K16) measures it
REARM_CM = OBSTACLE_CM + 10  # front must clear this before the next ALERT_OBSTACLE
ROD_BUSY = ("LIFTING", "FOLDING")
EPS = 1e-6

REFUSE_LATCH = "STOPPED: press Space to release"
REFUSE_OBSTACLE = f"Obstacle under {OBSTACLE_CM} cm: forward refused"
REFUSE_ROD = "Rod moving: drive refused"
REFUSE_IMU = "IMU calibrating: drive refused"


def _sign(v) -> int:
    """Clamp any key value to -1, 0 or 1 (None or junk counts as 0)."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0
    return 1 if v > 0 else -1 if v < 0 else 0


def mix(fwd, turn, inner_ratio: float = INNER_RATIO) -> tuple[float, float]:
    """Keys to unit track speeds (l, r): equal = straight, inner at inner_ratio = curve, turn alone = pivot."""
    f, t = _sign(fwd), _sign(turn)
    if f == 0:
        return (0.0, 0.0) if t == 0 else (float(t), float(-t))
    outer, inner = float(f), f * inner_ratio
    if t > 0:
        return (outer, inner)  # right turn: left track is the outer one
    if t < 0:
        return (inner, outer)
    return (outer, outer)


class Drive:
    """Turns held keys into motor commands, once per 50 ms loop (hw needs motors and motors_enable)."""

    def __init__(self, hw, pwm_at_speed: float = DEFAULT_PWM_AT_SPEED, inner_ratio: float = INNER_RATIO,
                 ramp_s: float = RAMP_S, sensors=None):
        if not 0 < pwm_at_speed <= 1:
            raise ValueError(f"drive.pwm_at_speed must be in (0, 1], got {pwm_at_speed!r}")
        if not 0 <= inner_ratio <= 1:
            raise ValueError(f"drive.inner_ratio must be in [0, 1], got {inner_ratio!r}")
        if ramp_s < 0:
            raise ValueError(f"drive.ramp_s must be >= 0, got {ramp_s!r}")
        self.hw, self.sensors = hw, sensors
        self.pwm, self.inner_ratio, self.ramp_s = float(pwm_at_speed), float(inner_ratio), float(ramp_s)
        self.latch = False
        self.refusal: str | None = None
        self._cur = (0.0, 0.0)
        self._enabled = False
        self._obs_armed, self._obs_alert = True, False
        self._apply(0.0, 0.0)  # init: enable low, PWM 0

    @classmethod
    def from_config(cls, hw, cfg: dict | None, sensors=None) -> "Drive":
        """Build from config.yaml (the whole dict or its `drive` section); missing values use defaults."""
        d = ((cfg or {}).get("drive", cfg) if cfg else None) or {}
        pick = lambda k, default: default if d.get(k) is None else d[k]
        return cls(hw, pick("pwm_at_speed", DEFAULT_PWM_AT_SPEED), pick("inner_ratio", INNER_RATIO),
                   pick("ramp_s", RAMP_S), sensors)

    @property
    def applied(self) -> tuple[float, float]:
        """Track command last sent to the motors."""
        return self._cur

    @property
    def moving(self) -> bool:
        """True while the tracks are driven or still ramping down (the rod needs this to say 'stop first')."""
        return abs(self._cur[0]) > EPS or abs(self._cur[1]) > EPS

    def pop_obstacle_alert(self) -> bool:
        """True once per approach to an obstacle (controller turns it into EVENT ALERT_OBSTACLE)."""
        alert, self._obs_alert = self._obs_alert, False
        return alert

    def stop(self) -> None:
        """Set the latch and cut the motors at once (Space, CMD STOP, link loss)."""
        self.latch = True
        self._apply(0.0, 0.0)

    def release(self) -> None:
        """Release the latch (CMD START); motors stay off until a drive key is held."""
        self.latch = False

    def close(self) -> None:
        """Motors off, enable low."""
        self._apply(0.0, 0.0)

    def __enter__(self) -> "Drive":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def step(self, fwd, turn, front_cm=None, rod: str = "FOLDED", imu: str = "OK", dt: float = LOOP_S) -> str | None:
        """Run one loop tick; returns a refusal text for the dashboard, or None when nothing was refused."""
        f, t = _sign(fwd), _sign(turn)
        wanted = bool(f or t)
        reason, hard = None, False
        if front_cm is None or front_cm >= REARM_CM:
            self._obs_armed = True
        if self.latch:
            reason, f, t, hard = REFUSE_LATCH, 0, 0, True
        elif imu == "CALIBRATING":
            reason, f, t, hard = REFUSE_IMU, 0, 0, True
        elif rod in ROD_BUSY:
            reason, f, t, hard = REFUSE_ROD, 0, 0, True
        elif f > 0 and front_cm is not None and front_cm < OBSTACLE_CM:
            reason, f = REFUSE_OBSTACLE, 0  # S, Q and D still work
            hard = self._cur[0] + self._cur[1] > EPS  # was driving forward: stop dead, then ramp the turn
            if self._obs_armed:
                self._obs_armed, self._obs_alert = False, True
        self.refusal = reason if wanted else None
        if hard:
            self._cur = (0.0, 0.0)
        target = tuple(c * self.pwm for c in mix(f, t, self.inner_ratio))
        room = self.pwm / self.ramp_s * max(dt, 0.0) if self.ramp_s > 0 else float("inf")
        self._apply(*(self._slew(c, g, room) for c, g in zip(self._cur, target)))
        return self.refusal

    @staticmethod
    def _slew(cur: float, target: float, room: float) -> float:
        """Move cur toward target by at most room."""
        if abs(target - cur) <= room:
            return target
        return cur + room if target > cur else cur - room

    def _apply(self, left: float, right: float) -> None:
        """Send a track command: enable before the first non-zero PWM, PWM 0 before enable low."""
        self._cur = (left, right)
        try:
            if abs(left) > EPS or abs(right) > EPS:
                if not self._enabled:
                    self.hw.motors_enable(True)
                    self._enabled = True
                self.hw.motors(left, right)
            else:
                self.hw.motors(0.0, 0.0)
                if self._enabled:
                    self.hw.motors_enable(False)
                    self._enabled = False
        except BaseException:
            self._cur, self._enabled = (0.0, 0.0), False
            try:
                self.hw.motors_enable(False)
            except Exception:
                pass  # keep the original error
            raise
        if self.sensors is not None:
            self.sensors.set_direction(left, right)  # encoders have no direction of their own (K05)
