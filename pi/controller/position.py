"""Position: yaw from the gyro, path from the encoders, optional heading snap (K08, spec 5.6).

Pure functions fed with samples: no threads, no clock. Yaw is in degrees, 0 = direction when lowered
[CHECK Q13], positive = turning left (gyro z up), so y grows to the left. x, y, s in metres.
"""
from __future__ import annotations

import math

TURN_DPS = 3.0  # a turn above this resets the straight-run counter of the snap
DEFAULT_SNAP_WINDOW_DEG = 25.0
DEFAULT_SNAP_STRAIGHT_M = 1.0
EPS = 1e-9


def _num(v) -> float | None:
    """Float, or None for None, junk, NaN and inf."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def wrap_deg(a: float) -> float:
    """Wrap an angle to (-180, 180]."""
    a = (a + 180.0) % 360.0 - 180.0
    return 180.0 if a == -180.0 else a


def ds_from_tracks(prev, cur) -> float:
    """Path length since the last call: mean of both track distances (left_m, right_m). A pivot gives 0."""
    return ((cur[0] - prev[0]) + (cur[1] - prev[1])) / 2.0


class Position:
    """x, y, s and yaw. Call integrate_gyro() every 10 ms and move() every 50 ms, or update() for both at once."""

    def __init__(self, snap: bool = False, snap_window_deg: float = DEFAULT_SNAP_WINDOW_DEG,
                 snap_straight_m: float = DEFAULT_SNAP_STRAIGHT_M, bias: float = 0.0):
        if not 0 < snap_window_deg <= 45:
            raise ValueError(f"imu.snap_window_deg must be in (0, 45], got {snap_window_deg!r}")
        if not snap_straight_m > 0:
            raise ValueError(f"imu.snap_straight_m must be > 0, got {snap_straight_m!r}")
        self.snap, self.snap_window_deg, self.snap_straight_m = bool(snap), float(snap_window_deg), float(snap_straight_m)
        self.bias = float(bias)  # deg/s, the Imu owns it and the controller copies it here
        self.x = self.y = self.s = self.yaw = 0.0
        self._straight = 0.0
        self._turn_seen = False

    @classmethod
    def from_config(cls, cfg: dict | None) -> "Position":
        """Build from config.yaml (the whole dict or its `imu` section); missing values use defaults."""
        d = ((cfg or {}).get("imu", cfg) if cfg else None) or {}
        pick = lambda k, default: default if d.get(k) is None else d[k]
        return cls(pick("snap", False), pick("snap_window_deg", DEFAULT_SNAP_WINDOW_DEG),
                   pick("snap_straight_m", DEFAULT_SNAP_STRAIGHT_M))

    def reset(self) -> None:
        """Back to the start: x = y = s = 0, yaw 0 (done when the gyro calibration ends)."""
        self.x = self.y = self.s = self.yaw = 0.0
        self._straight = 0.0
        self._turn_seen = False

    def integrate_gyro(self, gz, dt: float) -> None:
        """yaw += (gz - bias) x dt. gz None or invalid (IMU LOST): the map stops turning."""
        gz = _num(gz)
        if gz is None:
            return
        rate = gz - self.bias
        self.yaw = wrap_deg(self.yaw + rate * max(dt, 0.0))
        if abs(rate) > TURN_DPS:
            self._turn_seen = True

    def move(self, ds) -> bool:
        """x += ds cos(yaw), y += ds sin(yaw), s += ds. Returns True when the heading snap was applied."""
        ds = _num(ds) or 0.0
        rad = math.radians(self.yaw)
        self.x += ds * math.cos(rad)
        self.y += ds * math.sin(rad)
        self.s += ds
        if self._turn_seen:
            self._straight, self._turn_seen = 0.0, False
        else:
            self._straight += abs(ds)
        if not self.snap:
            self._straight = 0.0
            return False
        if self._straight < self.snap_straight_m - EPS:
            return False
        self._straight = 0.0
        nearest = round(self.yaw / 90.0) * 90.0
        if abs(wrap_deg(self.yaw - nearest)) <= self.snap_window_deg:
            self.yaw = wrap_deg(nearest)
            return True
        return False

    def update(self, ds, gyro_z, dt: float) -> bool:
        """One tick: gyro first, then the distance. Returns True when the snap was applied."""
        self.integrate_gyro(gyro_z, dt)
        return self.move(ds)
