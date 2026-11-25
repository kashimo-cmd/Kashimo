"""K04 checks: HW in mock mode, and Pi mode against fake gpiozero/smbus2 modules (no real pins)."""
import sys
import types

import pytest

from pi.controller import hw as H


@pytest.fixture
def hw():
    h = H.HW("mock")
    yield h
    h.close()


def test_mode_from_env_and_default(monkeypatch):
    monkeypatch.delenv("HW_MODE", raising=False)
    assert H.HW().mode == "mock"
    monkeypatch.setenv("HW_MODE", "mock")
    assert H.HW().mode == "mock"
    with pytest.raises(ValueError):
        H.HW("banana")


def test_motors_ignored_until_enabled(hw):
    hw.motors(0.5, 0.5)
    assert hw.motor_cmd == (0.5, 0.5) and hw.motor_out == (0.0, 0.0)
    hw.motors_enable(True)
    assert hw.motor_out == (0.5, 0.5)


def test_motors_clamped(hw):
    hw.motors_enable(True)
    hw.motors(3, -9)
    assert hw.motor_out == (1.0, -1.0)


def test_enable_false_forces_zero_and_forgets_command(hw):
    hw.motors_enable(True)
    hw.motors(0.8, -0.8)
    hw.motors_enable(False)
    assert hw.motor_out == (0.0, 0.0) and hw.enabled is False
    hw.motors(1, 1)  # still ignored
    assert hw.motor_out == (0.0, 0.0)
    hw.motors_enable(True)  # re-enable resumes the last request, not an old one
    assert hw.motor_out == (1.0, 1.0)
    hw.motors_enable(False)
    hw.motors_enable(True)
    assert hw.motor_out == (0.0, 0.0)


def test_close_is_safe_stop_and_idempotent():
    with H.HW("mock") as h:
        h.motors_enable(True)
        h.motors(1, 1)
    assert h.motor_out == (0.0, 0.0) and h.enabled is False and h.closed
    h.close()


def test_exception_in_motors_stops_everything(hw):
    hw.motors_enable(True)

    def boom(*a):
        raise RuntimeError("driver fault")

    hw._apply_motors = boom
    with pytest.raises(RuntimeError):
        hw.motors(1, 1)
    assert hw.motor_out == (0.0, 0.0) and hw.enabled is False and hw.motor_cmd == (0.0, 0.0)


def test_pulse_values_none_callable_and_bad_name(hw):
    assert hw.pulse("front") == 100.0
    hw.sim["pulse"]["left"] = None
    assert hw.pulse("left") is None
    seq = iter([50.0, 51.0])
    hw.sim["pulse"]["right"] = lambda: next(seq)
    assert (hw.pulse("right"), hw.pulse("right")) == (50.0, 51.0)
    with pytest.raises(ValueError):
        hw.pulse("rear")


def test_encoders_count_up(hw):
    assert hw.encoder_counts() == (0, 0)
    hw.sim_encoders(5, 7)
    hw.sim_encoders(1, 0)
    assert hw.encoder_counts() == (6, 7)


def test_led_servo_and_clamp(hw):
    hw.led(True)
    assert hw.led_on is True
    hw.servo("pan", 90)
    hw.servo("tilt", 250)
    hw.servo("fold", -5)
    assert hw.servo_angle == {"pan": 90.0, "tilt": 180.0, "fold": 0.0}
    with pytest.raises(ValueError):
        hw.servo("elbow", 10)


def test_mock_readings(hw):
    assert hw.rssi() == -58
    assert hw.imu_read() == (0.0, 0.0, 1.0, 0.0, 0.0, 0.0)
    assert isinstance(hw.cpu_temp(), float) and isinstance(hw.cpu_load(), float)


# ---------- Pi mode with fake libraries ----------
class FakeDev:
    made = []

    def __init__(self, pin, *a, **k):
        self.pin, self.value, self.angle, self.closed = pin, k.get("initial_value", 0), None, False
        self.when_activated = None
        FakeDev.made.append(self)

    def on(self):
        self.value = 1

    def off(self):
        self.value = 0

    def close(self):
        self.closed = True


class FakeBus:
    def __init__(self, n):
        self.writes = []

    def write_byte_data(self, *a):
        self.writes.append(a)

    def read_i2c_block_data(self, addr, reg, n):
        return [0x40, 0x00, 0, 0, 0x40, 0x00, 0, 0, 0x00, 0x83, 0xFF, 0x7D, 0, 0]  # ax=1 g, gx=1, gy=-1 deg/s


@pytest.fixture
def pi_hw(monkeypatch):
    FakeDev.made.clear()
    gz = types.ModuleType("gpiozero")
    gz.AngularServo = gz.DigitalInputDevice = gz.DigitalOutputDevice = gz.PWMOutputDevice = FakeDev
    pins, lg = types.ModuleType("gpiozero.pins"), types.ModuleType("gpiozero.pins.lgpio")
    lg.LGPIOFactory = lambda: None
    sm = types.ModuleType("smbus2")
    sm.SMBus = FakeBus
    for name, mod in (("gpiozero", gz), ("gpiozero.pins", pins), ("gpiozero.pins.lgpio", lg), ("smbus2", sm)):
        monkeypatch.setitem(sys.modules, name, mod)
    h = H.HW("pi")
    yield h
    h.close()


def test_pi_mode_starts_with_enable_low_and_uses_design_pins(pi_hw):
    assert pi_hw._en.pin == 24 and pi_hw._en.value == 0 and pi_hw.enabled is False
    assert {n: d.pin for n, d in pi_hw._pwm.items()} == {"l_fwd": 17, "l_rev": 27, "r_fwd": 22, "r_rev": 23}
    assert {n: d.pin for n, d in pi_hw._servo.items()} == {"pan": 12, "tilt": 13, "fold": 19}
    assert pi_hw._led.pin == 18
    assert {n: d.pin for n, d in pi_hw._trig.items()} == {"left": 5, "front": 16, "right": 21}
    assert {n: d.pin for n, d in pi_hw._echo.items()} == {"left": 6, "front": 20, "right": 26}
    assert {n: d.pin for n, d in pi_hw._enc.items()} == {"left": 4, "right": 25}


def test_pi_motor_mapping_and_enable_low_zeroes_pwm(pi_hw):
    pi_hw.motors_enable(True)
    pi_hw.motors(0.6, -0.4)
    v = {n: d.value for n, d in pi_hw._pwm.items()}
    assert v == {"l_fwd": 0.6, "l_rev": 0, "r_fwd": 0, "r_rev": 0.4}
    pi_hw.motors_enable(False)
    assert all(d.value == 0 for d in pi_hw._pwm.values()) and pi_hw._en.value == 0


def test_pi_close_zeroes_and_releases(pi_hw):
    pi_hw.motors_enable(True)
    pi_hw.motors(1, 1)
    pi_hw.close()
    assert all(d.value == 0 for d in pi_hw._pwm.values()) and pi_hw._en.value == 0
    assert all(d.closed for d in FakeDev.made)


def test_pi_encoder_edges_and_servo_led(pi_hw):
    for _ in range(3):
        pi_hw._enc["left"].when_activated()
    pi_hw._enc["right"].when_activated()
    assert pi_hw.encoder_counts() == (3, 1)
    pi_hw.servo("pan", 45)
    pi_hw.led(True)
    assert pi_hw._servo["pan"].angle == 45.0 and pi_hw._led.value == 1


def test_pi_imu_scaling_and_wake(pi_hw):
    ax, ay, az, gx, gy, gz = pi_hw.imu_read()
    assert (ax, ay, az) == (1.0, 0.0, 1.0)
    assert gx == pytest.approx(1.0, abs=0.01) and gy == pytest.approx(-1.0, abs=0.01)
    assert (0x68, 0x6B, 0) in pi_hw._bus.writes
