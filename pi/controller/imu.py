"""IMU state: gyro calibration, standstill bias, tilt and bump (K08, spec 5.6 and 4.3).

Pure functions fed with samples (ax, ay, az in g, gx, gy, gz in deg/s, as hw.imu_read() returns): no threads, no clock.
Axis directions depend on how the MPU6050 is mounted [CHECK ON PI]: x forward, y left, z up is assumed.
"""
from __future__ import annotations

import math

STATUSES = ("CALIBRATING", "OK", "UNCERTAIN", "LOST")
GYRO_CAL_S = 3.0  # still time needed for the boot bias
IMU_RATE_HZ = 100
STANDSTILL_S = 1.0  # all standstill conditions must hold this long
STILL_DPS = 1.0  # standstill: gyro under 1 deg/s
STILL_G = 0.03  # standstill: accel within 0.03 g of 1 g
CAL_SPREAD_DPS = 2.0  # calibration restarts if gz moves more than this inside the window
CAL_G = 0.05  # calibration restarts if the accel norm leaves 1 g by more than this
BIAS_TAU_S = 10.0  # [EST] how slowly the bias follows the gyro at standstill
TILT_TAU_S = 0.5  # [EST] tilt low-pass
TILT_WARN, TILT_ALERT = 25.0, 35.0  # deg
BUMP_G = 0.5  # g above rest
BUMP_COOLDOWN_S = 0.5  # [EST] one EVENT per bump, not one per ringing sample
LOST_AFTER_S = 0.5  # [EST] no valid sample for this long = IMU LOST


def _valid(sample):
    """Six finite floats, or None."""
    try:
        v = tuple(float(x) for x in sample)
    except (TypeError, ValueError):
        return None
    return v if len(v) == 6 and all(math.isfinite(x) for x in v) else None


class Imu:
    """Status and derived values from the IMU samples. Call update() at 100 Hz (or read() to also catch hw errors)."""

    def __init__(self, cal_s: float = GYRO_CAL_S, bias_tau_s: float = BIAS_TAU_S, tilt_tau_s: float = TILT_TAU_S,
                 lost_after_s: float = LOST_AFTER_S):
        for name, v in (("cal_s", cal_s), ("bias_tau_s", bias_tau_s), ("tilt_tau_s", tilt_tau_s),
                        ("lost_after_s", lost_after_s)):
            if not v > 0:
                raise ValueError(f"imu.{name} must be > 0, got {v!r}")
        self.cal_s, self.bias_tau_s, self.tilt_tau_s, self.lost_after_s = cal_s, bias_tau_s, tilt_tau_s, lost_after_s
        self.bias = 0.0  # deg/s
        self.pitch = self.roll = self.tilt = 0.0
        self.tilt_level = "OK"  # OK | WARN (above 25 deg) | ALERT (above 35 deg)
        self.standstill = False
        self.gz: float | None = None  # last raw gyro z
        self._calibrating = True
        self._lost = False
        self._uncertain = False
        self._bad_t = 0.0
        self._lp: tuple[float, float, float] | None = None
        self._still_t = 0.0
        self._bump_cool = 0.0
        self._bump = False
        self._tilt_alert, self._tilt_armed = False, True
        self._calibrated_flag = False
        self._restart_calibration()

    # ---- state ----
    @property
    def status(self) -> str:
        """CALIBRATING | OK | UNCERTAIN | LOST. UNCERTAIN = the heading was integrated since the last correction."""
        if self._lost:
            return "LOST"
        if self._calibrating:
            return "CALIBRATING"
        return "UNCERTAIN" if self._uncertain else "OK"

    @property
    def heading_rate(self) -> float | None:
        """Raw gyro z for Position.integrate_gyro(): None unless the status is OK or UNCERTAIN (map stops turning)."""
        return self.gz if self.status in ("OK", "UNCERTAIN") else None

    def recalibrate(self) -> None:
        """Start the 3 s bias measurement again."""
        self._calibrating = True
        self._restart_calibration()

    def note_correction(self) -> None:
        """A heading correction was applied (snap): the heading is trusted again until the robot moves."""
        self._uncertain = False

    def pop_calibrated(self) -> bool:
        """True once when the calibration just ended (controller then copies bias and resets Position)."""
        flag, self._calibrated_flag = self._calibrated_flag, False
        return flag

    def pop_bump(self) -> bool:
        """True once per bump (controller turns it into EVENT BUMP)."""
        flag, self._bump = self._bump, False
        return flag

    def pop_tilt_alert(self) -> bool:
        """True once per episode above 35 deg; re-armed when the tilt is back under 25 deg (EVENT ALERT_TILT)."""
        flag, self._tilt_alert = self._tilt_alert, False
        return flag

    # ---- input ----
    def read(self, hw, dt: float = 1.0 / IMU_RATE_HZ, moved: bool = False) -> None:
        """update() with hw.imu_read(); a read error counts as a missing sample."""
        try:
            sample = hw.imu_read()
        except Exception:
            sample = None
        self.update(sample, dt, moved)

    def update(self, sample, dt: float = 1.0 / IMU_RATE_HZ, moved: bool = False) -> None:
        """One sample. moved = an encoder counted since the last sample. sample None or invalid = missing."""
        dt = max(dt, 0.0)
        s = _valid(sample)
        if s is None:
            self.gz = None  # no stale rate for Position while samples are missing
            self._bad_t += dt
            if self._bad_t >= self.lost_after_s and not self._lost:
                self._lost = True
                self._still_t = 0.0
                if self._calibrating:
                    self._restart_calibration()
            return
        self._bad_t = 0.0
        if self._lost:
            self._lost = False
            self._uncertain = True  # turns may have been missed
        ax, ay, az, _gx, _gy, gz = s
        self.gz = gz
        norm = math.sqrt(ax * ax + ay * ay + az * az)
        self._tilt(ax, ay, az, dt)
        if self._calibrating:
            self._calibrate(gz, norm, moved, dt)
            return
        rate = gz - self.bias
        if moved or abs(rate) >= STILL_DPS:
            self._uncertain = True
        still = not moved and abs(rate) < STILL_DPS and abs(norm - 1.0) < STILL_G
        self._still_t = self._still_t + dt if still else 0.0
        self.standstill = self._still_t >= STANDSTILL_S - 1e-9
        if self.standstill:
            self.bias += rate * min(1.0, dt / self.bias_tau_s)  # pull the bias slowly toward the gyro
        self._bump_cool = max(0.0, self._bump_cool - dt)
        if norm - 1.0 >= BUMP_G and self._bump_cool <= 0.0:
            self._bump, self._bump_cool = True, BUMP_COOLDOWN_S

    # ---- internals ----
    def _restart_calibration(self) -> None:
        self._cal_t, self._cal_n, self._cal_sum = 0.0, 0, 0.0
        self._cal_min, self._cal_max = math.inf, -math.inf

    def _calibrate(self, gz: float, norm: float, moved: bool, dt: float) -> None:
        """3 s of a still robot: average gz is the bias. Any movement restarts the 3 s."""
        lo, hi = min(self._cal_min, gz), max(self._cal_max, gz)
        if moved or abs(norm - 1.0) > CAL_G or hi - lo > CAL_SPREAD_DPS:
            self._restart_calibration()
            return
        self._cal_min, self._cal_max = lo, hi
        self._cal_t += dt
        self._cal_n += 1
        self._cal_sum += gz
        if self._cal_t >= self.cal_s - 1e-9:
            self.bias = self._cal_sum / self._cal_n
            self._calibrating, self._uncertain = False, False
            self._still_t = 0.0
            self._calibrated_flag = True

    def _tilt(self, ax: float, ay: float, az: float, dt: float) -> None:
        """Tilt from gravity through a low-pass; ALERT_TILT once per episode."""
        if self._lp is None:
            self._lp = (ax, ay, az)
        else:
            k = dt / (self.tilt_tau_s + dt)
            self._lp = tuple(p + (n - p) * k for p, n in zip(self._lp, (ax, ay, az)))
        lx, ly, lz = self._lp
        self.pitch = math.degrees(math.atan2(-lx, math.hypot(ly, lz)))
        self.roll = math.degrees(math.atan2(ly, lz))
        self.tilt = math.degrees(math.atan2(math.hypot(lx, ly), lz))
        if self.tilt > TILT_ALERT:
            self.tilt_level = "ALERT"
            if self._tilt_armed:
                self._tilt_alert, self._tilt_armed = True, False
        elif self.tilt > TILT_WARN:
            self.tilt_level = "WARN"
        else:
            self.tilt_level = "OK"
            self._tilt_armed = True
