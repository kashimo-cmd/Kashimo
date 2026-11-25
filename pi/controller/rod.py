"""Rod: FOLDED, LIFTING, UPRIGHT, FOLDING with 30 deg/s servo, 5 s timeout and ALERT_ROD (K07)."""
from __future__ import annotations

try:
    from common.constants import LOOP_S
except ImportError:  # constants module missing or renamed: use the frozen value of 4.3
    LOOP_S = 0.05

ROD_RATE = 30.0  # deg/s
ROD_TIMEOUT_S = 5.0
DEFAULT_FOLDED_DEG = 0.0  # CHECK ON PI: fold servo angle with the rod flat
DEFAULT_UPRIGHT_DEG = 90.0  # CHECK ON PI: fold servo angle with the rod upright
BUSY = ("LIFTING", "FOLDING")

REFUSE_STOP_FIRST = "Stop first: rod refused while moving"
REFUSE_BUSY = "Rod already moving"


class Rod:
    """Rod state machine. The rod is assumed FOLDED at boot (a hobby servo has no feedback).

    Per tick call head.step() first, then rod.step(). The head must provide goto(), settled, rest, fold_pose, home_rate.
    """

    def __init__(self, hw, head, folded_deg: float = DEFAULT_FOLDED_DEG, upright_deg: float = DEFAULT_UPRIGHT_DEG,
                 rate: float = ROD_RATE, timeout_s: float = ROD_TIMEOUT_S):
        for name, v in (("folded_deg", folded_deg), ("upright_deg", upright_deg)):
            if not 0 <= v <= 180:
                raise ValueError(f"rod.{name} must be in [0, 180], got {v!r}")
        if folded_deg == upright_deg:
            raise ValueError("rod.folded_deg and rod.upright_deg must differ")
        if not rate > 0:
            raise ValueError(f"rod.rate must be > 0, got {rate!r}")
        if not timeout_s > 0:
            raise ValueError(f"rod.timeout_s must be > 0, got {timeout_s!r}")
        self.hw, self.head = hw, head
        self.folded_deg, self.upright_deg = float(folded_deg), float(upright_deg)
        self.rate, self.timeout_s = float(rate), float(timeout_s)
        self.state = "FOLDED"
        self.timed_out = False
        self._angle = self.folded_deg
        self._t = 0.0
        self._servo_on = False
        self._alert: str | None = None
        self._sent: float | None = None

    @classmethod
    def from_config(cls, hw, head, cfg: dict | None) -> "Rod":
        """Build from config.yaml (the whole dict or its `rod` section); missing values use defaults."""
        d = ((cfg or {}).get("rod", cfg) if cfg else None) or {}
        pick = lambda k, default: default if d.get(k) is None else d[k]
        return cls(hw, head, pick("folded_deg", DEFAULT_FOLDED_DEG), pick("upright_deg", DEFAULT_UPRIGHT_DEG),
                   pick("rate", ROD_RATE), pick("timeout_s", ROD_TIMEOUT_S))

    @property
    def moving(self) -> bool:
        """True while LIFTING or FOLDING (Drive refuses to run then)."""
        return self.state in BUSY

    def pop_alert(self) -> str | None:
        """The state ("LIFTING" or "FOLDING") once after a timeout, else None (controller turns it into EVENT ALERT_ROD)."""
        alert, self._alert = self._alert, None
        return alert

    def request(self, robot_moving: bool) -> str | None:
        """R key: lift a folded rod, fold an upright one. Returns a refusal text, or None when accepted."""
        if self.moving and not self.timed_out:
            return REFUSE_BUSY
        if robot_moving:
            return REFUSE_STOP_FIRST
        lift = self.state in ("FOLDED", "FOLDING")  # after a timeout the rod goes back the other way
        self.timed_out = False
        self._t = 0.0
        if lift:
            self.state, self._servo_on = "LIFTING", True  # fold servo up, head to REST
            self.head.goto(self.head.rest, self.head.home_rate)
        else:
            self.state, self._servo_on = "FOLDING", False  # head to FOLD_POSE first, then the servo goes down
            self.head.goto(self.head.fold_pose, self.head.home_rate)
        return None

    def step(self, dt: float = LOOP_S) -> None:
        """One loop tick."""
        if not self.moving or self.timed_out:
            return
        self._t += max(dt, 0.0)
        if self.state == "FOLDING" and not self._servo_on and self.head.settled:
            self._servo_on, self._t = True, 0.0  # head is in FOLD_POSE: the 5 s clock for the servo starts now
        goal = self.upright_deg if self.state == "LIFTING" else self.folded_deg
        if self._servo_on:
            room = self.rate * max(dt, 0.0)
            if abs(goal - self._angle) <= room:
                self._angle = goal
            else:
                self._angle += room if goal > self._angle else -room
            self._send()
        arrived = self._servo_on and self._angle == goal
        if self.state == "LIFTING" and arrived and self.head.settled:
            self.state = "UPRIGHT"
        elif self.state == "FOLDING" and arrived:
            self.state = "FOLDED"
        elif self._t > self.timeout_s:
            self.timed_out, self._alert = True, self.state  # servo stops: nothing more is sent

    def _send(self) -> None:
        v = round(self._angle, 2)
        if self._sent != v:
            self.hw.servo("fold", v)
            self._sent = v
