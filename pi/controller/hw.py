"""K04 hardware layer: one HW class, HW_MODE=mock|pi. Pins of design 4.4. Units: imu in g and deg/s."""
import atexit
import os
import re
import subprocess
import time

PINS = {
    "servo": {"pan": 12, "tilt": 13, "fold": 19},
    "motor": {"l_fwd": 17, "l_rev": 27, "r_fwd": 22, "r_rev": 23},
    "enable": 24,
    "sonar": {"left": (5, 6), "front": (16, 20), "right": (21, 26)},  # (trig, echo)
    "encoder": {"left": 4, "right": 25},
    "led": 18,
}
SENSORS = ("front", "left", "right")
SERVOS = ("pan", "tilt", "fold")
MPU_ADDR = 0x68
ECHO_TIMEOUT_S = 0.03  # about 5 m, longer means no echo
SOUND_CM_PER_S = 34300.0


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


class HW:
    """Motors, sonar, encoders, LED, servos, IMU, Wi-Fi and CPU readings behind one object."""

    def __init__(self, mode=None):
        mode = (mode or os.environ.get("HW_MODE") or "mock").lower()
        if mode not in ("mock", "pi"):
            raise ValueError(f"HW_MODE must be mock or pi, got {mode!r}")
        self.mode = mode
        self.enabled = False
        self.motor_cmd = (0.0, 0.0)  # last requested (what the caller asked)
        self.motor_out = (0.0, 0.0)  # what reaches the drivers (0 when disabled)
        self.led_on = False
        self.servo_angle = {}
        self.closed = False
        self._cpu_prev = None
        # Mock inputs: tests and K09 mock runs change these. A value may be a callable returning it.
        self.sim = {
            "pulse": {"front": 100.0, "left": 100.0, "right": 100.0},  # cm or None (no echo)
            "encoders": [0, 0],
            "rssi": -58.0,
            "imu": (0.0, 0.0, 1.0, 0.0, 0.0, 0.0),  # still, z up
            "cpu_temp": 45.0,
            "cpu_load": 5.0,
        }
        if mode == "pi":
            self._init_pi()
            atexit.register(self.close)

    # ---------- context manager ----------
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    # ---------- motors ----------
    def motors_enable(self, on):
        """Enable high lets the drivers run. Enable low forces PWM 0 first, and forgets the command."""
        if not on:
            self._apply_motors(0.0, 0.0)
            self.motor_cmd = (0.0, 0.0)
            self._set_enable(False)
        else:
            self._set_enable(True)
            self._apply_motors(*self.motor_cmd)

    def motors(self, left, right):
        """left, right in -1..1 (+ = forward). Ignored (output 0) while enable is low."""
        left = _clamp(float(left), -1.0, 1.0)
        right = _clamp(float(right), -1.0, 1.0)
        self.motor_cmd = (left, right)
        try:
            self._apply_motors(left, right)
        except Exception:
            self.safe_stop()
            raise

    def safe_stop(self):
        """Enable low, PWM 0. Never raises."""
        self.motor_cmd = (0.0, 0.0)
        self.motor_out = (0.0, 0.0)
        try:
            if self.mode == "pi":
                for n in ("l_fwd", "l_rev", "r_fwd", "r_rev"):
                    self._pwm[n].value = 0
            self._set_enable(False)
        except Exception:
            pass

    def _apply_motors(self, left, right):
        if not self.enabled:
            left = right = 0.0
        self.motor_out = (left, right)
        if self.mode == "pi":
            for side, v in (("l", left), ("r", right)):
                self._pwm[side + "_fwd"].value = max(v, 0.0)
                self._pwm[side + "_rev"].value = max(-v, 0.0)

    def _set_enable(self, on):
        self.enabled = bool(on)
        if self.mode == "pi":
            self._en.value = 1 if on else 0

    # ---------- sensors ----------
    def pulse(self, sensor):
        """One HC-SR04 measurement in cm, or None when there is no echo."""
        if sensor not in SENSORS:
            raise ValueError(f"unknown sensor {sensor!r}")
        if self.mode == "mock":
            v = self.sim["pulse"].get(sensor)
            return v() if callable(v) else v
        return self._pulse_pi(sensor)  # CHECK ON PI

    def encoder_counts(self):
        """Raw edge counts since start (left, right), always increasing. Sign is added by K05."""
        if self.mode == "mock":
            return tuple(self.sim["encoders"])
        return (self._enc_count["left"], self._enc_count["right"])

    def sim_encoders(self, left=0, right=0):
        """Mock only: add counts, as if the tracks turned."""
        self.sim["encoders"][0] += int(left)
        self.sim["encoders"][1] += int(right)

    def rssi(self):
        """Wi-Fi signal in dBm from `iw dev wlan0 link`, None when not connected."""
        if self.mode == "mock":
            return self._sim("rssi")
        try:  # CHECK ON PI
            out = subprocess.run(["iw", "dev", "wlan0", "link"], capture_output=True, text=True, timeout=1).stdout
            m = re.search(r"signal:\s*(-?\d+(?:\.\d+)?)\s*dBm", out)
            return float(m.group(1)) if m else None
        except (OSError, subprocess.SubprocessError):
            return None

    def imu_read(self):
        """MPU6050 -> (ax, ay, az) in g, (gx, gy, gz) in deg/s."""
        if self.mode == "mock":
            return tuple(self._sim("imu"))
        raw = self._bus.read_i2c_block_data(MPU_ADDR, 0x3B, 14)  # CHECK ON PI

        def s16(i):
            v = (raw[i] << 8) | raw[i + 1]
            return v - 65536 if v & 0x8000 else v

        return (s16(0) / 16384.0, s16(2) / 16384.0, s16(4) / 16384.0,
                s16(8) / 131.0, s16(10) / 131.0, s16(12) / 131.0)

    def cpu_temp(self):
        """CPU temperature in deg C, None if unreadable."""
        if self.mode == "mock":
            return self._sim("cpu_temp")
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return int(f.read().strip()) / 1000.0
        except (OSError, ValueError):
            return None

    def cpu_load(self):
        """CPU use in percent since the last call (0 on the first call)."""
        if self.mode == "mock":
            return self._sim("cpu_load")
        try:
            with open("/proc/stat") as f:
                p = [int(x) for x in f.readline().split()[1:]]
        except (OSError, ValueError):
            return None
        idle, total = p[3] + (p[4] if len(p) > 4 else 0), sum(p)
        prev, self._cpu_prev = self._cpu_prev, (idle, total)
        if not prev or total == prev[1]:
            return 0.0
        return round(100.0 * (1 - (idle - prev[0]) / (total - prev[1])), 1)

    # ---------- outputs ----------
    def led(self, on):
        self.led_on = bool(on)
        if self.mode == "pi":
            self._led.value = 1 if on else 0

    def servo(self, name, angle):
        """Move pan, tilt or fold to angle degrees (clamped 0-180)."""
        if name not in SERVOS:
            raise ValueError(f"unknown servo {name!r}")
        angle = _clamp(float(angle), 0.0, 180.0)
        self.servo_angle[name] = angle
        if self.mode == "pi":
            self._servo[name].angle = angle

    def close(self):
        """Enable low, PWM 0, release the pins. Safe to call twice."""
        if self.closed:
            return
        self.closed = True
        self.safe_stop()
        if self.mode == "pi":
            devs = [*self._pwm.values(), self._en, self._led, *self._servo.values(),
                    *self._trig.values(), *self._echo.values(), *self._enc.values()]
            for d in devs:
                try:
                    d.close()
                except Exception:
                    pass

    # ---------- internals ----------
    def _sim(self, key):
        v = self.sim[key]
        return v() if callable(v) else v

    def _init_pi(self):  # CHECK ON PI: gpiozero + lgpio on Pi 5, imports only here so a PC never needs them
        from gpiozero import AngularServo, DigitalInputDevice, DigitalOutputDevice, PWMOutputDevice
        from gpiozero.pins.lgpio import LGPIOFactory
        import smbus2

        f = LGPIOFactory()
        self._en = DigitalOutputDevice(PINS["enable"], initial_value=False, pin_factory=f)  # low first
        self.enabled = False
        self._pwm = {n: PWMOutputDevice(PINS["motor"][n], initial_value=0, pin_factory=f) for n in PINS["motor"]}
        self._led = DigitalOutputDevice(PINS["led"], initial_value=False, pin_factory=f)
        # MG90S: 0.5-2.5 ms. Software PWM on lgpio, hardware PWM on 12/13 is to be checked on the Pi.
        self._servo = {
            n: AngularServo(p, initial_angle=None, min_angle=0, max_angle=180,
                            min_pulse_width=0.0005, max_pulse_width=0.0025, pin_factory=f)
            for n, p in PINS["servo"].items()
        }
        self._trig = {n: DigitalOutputDevice(t, initial_value=False, pin_factory=f) for n, (t, _) in PINS["sonar"].items()}
        self._echo = {n: DigitalInputDevice(e, pin_factory=f) for n, (_, e) in PINS["sonar"].items()}
        self._enc_count = {"left": 0, "right": 0}
        self._enc = {}
        for side, pin in PINS["encoder"].items():
            d = DigitalInputDevice(pin, pull_up=None, active_state=True, pin_factory=f)
            d.when_activated = lambda s=side: self._enc_count.__setitem__(s, self._enc_count[s] + 1)
            self._enc[side] = d
        self._bus = smbus2.SMBus(1)
        self._bus.write_byte_data(MPU_ADDR, 0x6B, 0)  # wake MPU6050, default +-2 g, +-250 deg/s

    def _pulse_pi(self, sensor):  # CHECK ON PI
        trig, echo = self._trig[sensor], self._echo[sensor]
        trig.on()
        time.sleep(0.00001)
        trig.off()
        t0 = time.perf_counter()
        while not echo.value:
            if time.perf_counter() - t0 > ECHO_TIMEOUT_S:
                return None
        start = time.perf_counter()
        while echo.value:
            if time.perf_counter() - start > ECHO_TIMEOUT_S:
                return None
        return round((time.perf_counter() - start) * SOUND_CM_PER_S / 2.0, 1)
