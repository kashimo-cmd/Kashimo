"""Tests for K08 imu: calibration, standstill bias, tilt, bump, LOST."""
import math

import pytest

from pi.controller.imu import BUMP_G, TILT_ALERT, TILT_WARN, Imu

DT = 0.01
STILL = (0.0, 0.0, 1.0, 0.1, -0.2, 0.5)  # robot at rest, gyro z reads 0.5 deg/s (the bias)


def feed(imu, sample, n, moved=False):
    for _ in range(n):
        imu.update(sample, DT, moved)


def tilted(deg):
    """Accel sample of a robot pitched by deg (gravity 1 g)."""
    r = math.radians(deg)
    return (-math.sin(r), 0.0, math.cos(r), 0.0, 0.0, 0.5)


def ready(**kw):
    imu = Imu(**kw)
    feed(imu, STILL, 300)
    assert imu.status == "OK"
    imu.pop_calibrated()
    return imu


# ---- calibration ----
def test_starts_calibrating_and_ends_after_3_s_of_stillness():
    imu = Imu()
    assert imu.status == "CALIBRATING" and imu.heading_rate is None
    feed(imu, STILL, 299)
    assert imu.status == "CALIBRATING" and imu.pop_calibrated() is False
    feed(imu, STILL, 1)
    assert imu.status == "OK" and imu.pop_calibrated() is True and imu.pop_calibrated() is False
    assert imu.bias == pytest.approx(0.5)
    assert imu.heading_rate == 0.5


def test_bias_is_the_mean_of_the_window():
    imu = Imu()
    for i in range(300):
        imu.update((0, 0, 1, 0, 0, 1.0 + (0.2 if i % 2 else -0.2)), DT)
    assert imu.status == "OK" and imu.bias == pytest.approx(1.0, abs=1e-9)


def test_movement_restarts_the_3_s():
    imu = Imu()
    feed(imu, STILL, 250)
    imu.update((0, 0, 1, 0, 0, 12.0), DT)  # the robot was turned
    feed(imu, STILL, 299)
    assert imu.status == "CALIBRATING"  # the first 250 samples were thrown away
    feed(imu, STILL, 1)
    assert imu.status == "OK"


def test_encoder_count_or_accel_change_also_restarts():
    imu = Imu()
    feed(imu, STILL, 250)
    imu.update(STILL, DT, moved=True)
    feed(imu, STILL, 299)
    assert imu.status == "CALIBRATING"
    imu.update((0, 0, 1.2, 0, 0, 0.5), DT)  # picked up
    feed(imu, STILL, 299)
    assert imu.status == "CALIBRATING"
    feed(imu, STILL, 1)
    assert imu.status == "OK"


def test_recalibrate_restarts():
    imu = ready()
    imu.recalibrate()
    assert imu.status == "CALIBRATING" and imu.heading_rate is None
    feed(imu, (0, 0, 1, 0, 0, -0.3), 300)
    assert imu.status == "OK" and imu.bias == pytest.approx(-0.3)


# ---- standstill ----
def test_standstill_after_1_s_and_bias_follows_slowly():
    imu = ready()
    feed(imu, (0, 0, 1, 0, 0, 0.8), 99)  # gz 0.3 above the bias
    assert imu.standstill is False and imu.bias == 0.5
    feed(imu, (0, 0, 1, 0, 0, 0.8), 1)
    assert imu.standstill is True
    feed(imu, (0, 0, 1, 0, 0, 0.8), 500)  # 5 s
    assert 0.5 < imu.bias < 0.8  # moved toward the reading, not all the way
    b = imu.bias
    feed(imu, (0, 0, 1, 0, 0, 0.8), 6000)  # 60 s
    assert imu.bias > b and imu.bias == pytest.approx(0.8, abs=0.01)


def test_no_standstill_when_moving_turning_or_shaken():
    for sample, moved in (((0, 0, 1, 0, 0, 5.5), False), (STILL, True), ((0, 0, 1.1, 0, 0, 0.5), False)):
        imu = ready()
        feed(imu, sample, 300, moved)
        assert imu.standstill is False and imu.bias == 0.5


def test_standstill_restarts_its_1_s_after_a_move():
    imu = ready()
    feed(imu, STILL, 99)
    imu.update(STILL, DT, moved=True)
    feed(imu, STILL, 99)
    assert imu.standstill is False
    feed(imu, STILL, 1)
    assert imu.standstill is True


# ---- UNCERTAIN ----
def test_uncertain_once_it_moves_and_ok_again_after_a_correction():
    imu = ready()
    assert imu.status == "OK"
    feed(imu, STILL, 50)
    assert imu.status == "OK"
    imu.update(STILL, DT, moved=True)
    assert imu.status == "UNCERTAIN" and imu.heading_rate == 0.5
    imu.note_correction()
    assert imu.status == "OK"
    imu.update((0, 0, 1, 0, 0, 30.0), DT)  # turning
    assert imu.status == "UNCERTAIN"


# ---- tilt ----
def test_tilt_thresholds_25_and_35():
    assert (TILT_WARN, TILT_ALERT) == (25.0, 35.0)
    imu = ready()
    feed(imu, tilted(20), 300)
    assert imu.tilt_level == "OK" and imu.tilt == pytest.approx(20, abs=0.1)
    assert imu.pitch == pytest.approx(20, abs=0.1) and imu.roll == pytest.approx(0, abs=0.1)
    feed(imu, tilted(30), 300)
    assert imu.tilt_level == "WARN"
    assert imu.pop_tilt_alert() is False
    feed(imu, tilted(40), 300)
    assert imu.tilt_level == "ALERT"


def test_alert_tilt_once_per_episode_and_rearms_under_25():
    imu = ready()
    feed(imu, tilted(40), 300)
    assert imu.pop_tilt_alert() is True and imu.pop_tilt_alert() is False
    feed(imu, tilted(40), 300)
    assert imu.pop_tilt_alert() is False  # same episode
    feed(imu, tilted(30), 300)  # between 25 and 35: not re-armed
    feed(imu, tilted(40), 300)
    assert imu.pop_tilt_alert() is False
    feed(imu, tilted(5), 300)
    feed(imu, tilted(40), 300)
    assert imu.pop_tilt_alert() is True


def test_roll_sign():
    imu = ready()
    r = math.radians(15)
    feed(imu, (0.0, math.sin(r), math.cos(r), 0, 0, 0.5), 300)
    assert imu.roll == pytest.approx(15, abs=0.1) and imu.tilt == pytest.approx(15, abs=0.1)


def test_tilt_is_low_passed():
    imu = ready()
    imu.update(tilted(60), DT)  # one spike
    assert imu.tilt < 25 and imu.tilt_level == "OK" and imu.pop_tilt_alert() is False


# ---- bump ----
def test_bump_at_half_a_g_above_rest_once():
    assert BUMP_G == 0.5
    imu = ready()
    imu.update((0, 0, 1.4, 0, 0, 0.5), DT)
    assert imu.pop_bump() is False  # 0.4 g above rest
    imu.update((0, 0, 1.5, 0, 0, 0.5), DT)
    assert imu.pop_bump() is True and imu.pop_bump() is False
    feed(imu, (0, 0, 1.8, 0, 0, 0.5), 20)  # ringing inside the cooldown
    assert imu.pop_bump() is False
    feed(imu, STILL, 60)
    imu.update((0, 0, 1.6, 0, 0, 0.5), DT)
    assert imu.pop_bump() is True


def test_bump_uses_the_whole_acceleration_vector():
    imu = ready()
    imu.update((1.2, 0.9, 1.0, 0, 0, 0.5), DT)
    assert imu.pop_bump() is True


# ---- LOST ----
def test_lost_after_half_a_second_without_a_sample():
    imu = ready()
    feed(imu, None, 49)
    assert imu.status == "OK"
    feed(imu, None, 1)
    assert imu.status == "LOST" and imu.heading_rate is None


def test_invalid_samples_count_as_missing():
    imu = ready()
    for bad in ((0, 0, 1), "xx", (0, 0, 1, 0, 0, float("nan")), [None] * 6):
        imu2 = ready()
        feed(imu2, bad, 50)
        assert imu2.status == "LOST", bad


def test_back_from_lost_is_uncertain_without_recalibration():
    imu = ready()
    feed(imu, None, 60)
    assert imu.status == "LOST"
    imu.update(STILL, DT)
    assert imu.status == "UNCERTAIN" and imu.bias == 0.5
    imu.note_correction()
    assert imu.status == "OK"


def test_lost_while_calibrating_restarts_the_window():
    imu = Imu()
    feed(imu, STILL, 250)
    feed(imu, None, 60)
    assert imu.status == "LOST"
    feed(imu, STILL, 299)
    assert imu.status == "CALIBRATING"
    feed(imu, STILL, 1)
    assert imu.status == "OK"


def test_read_catches_hardware_errors():
    class HW:
        def __init__(self):
            self.fail = False

        def imu_read(self):
            if self.fail:
                raise OSError("i2c error")
            return STILL

    hw, imu = HW(), Imu()
    for _ in range(300):
        imu.read(hw)
    assert imu.status == "OK"
    hw.fail = True
    for _ in range(50):
        imu.read(hw)
    assert imu.status == "LOST"
    hw.fail = False
    imu.read(hw)
    assert imu.status == "UNCERTAIN"


# ---- with Position ----
def test_position_follows_the_imu_status():
    from pi.controller.position import Position
    imu, pos = Imu(), Position()
    for _ in range(300):
        imu.update(STILL, DT)
    assert imu.pop_calibrated()
    pos.bias = imu.bias
    pos.reset()
    for _ in range(40):
        imu.update((0, 0, 1, 0, 0, 60.5), DT)
        pos.integrate_gyro(imu.heading_rate, DT)
    assert pos.yaw == pytest.approx(24.0)  # 60 deg/s for 0.4 s
    for _ in range(100):
        imu.update(None, DT)
        pos.integrate_gyro(imu.heading_rate, DT)
    assert imu.status == "LOST" and pos.yaw == pytest.approx(24.0)  # frozen from the first missing sample


def test_bad_config_values_raise():
    for kw in ({"cal_s": 0}, {"bias_tau_s": -1}, {"tilt_tau_s": 0}, {"lost_after_s": 0}):
        with pytest.raises(ValueError):
            Imu(**kw)


def test_with_real_mock_hw():
    import os
    os.environ["HW_MODE"] = "mock"
    try:
        from pi.controller.hw import HW
        hw = HW()
    except Exception as e:  # HW() may need arguments: skip, do not fail
        pytest.skip(f"HW() not constructible here: {e}")
    imu = Imu()
    for _ in range(300):
        imu.read(hw)  # mock IMU = robot standing still
    assert imu.status == "OK" and abs(imu.bias) < 1.0 and imu.tilt_level == "OK"
