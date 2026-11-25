"""Tests for K06 drive: mixing, ramp, interlocks (table 5.4) and STOP latch."""
import os

import pytest

from pi.controller.drive import (INNER_RATIO, OBSTACLE_CM, REFUSE_IMU, REFUSE_LATCH, REFUSE_OBSTACLE,
                                 REFUSE_ROD, Drive, mix)

DT = 0.05


class FakeHW:
    """Records motors() and motors_enable() like the mock HW; output is 0 while enable is low."""

    def __init__(self):
        self.enabled, self.out, self.calls = False, (0.0, 0.0), []

    def motors_enable(self, on):
        self.calls.append(("enable", bool(on)))
        self.enabled = bool(on)
        if not on:
            self.out = (0.0, 0.0)

    def motors(self, left, right):
        self.calls.append(("motors", left, right))
        self.out = (left, right) if self.enabled else (0.0, 0.0)


class FakeSensors:
    def __init__(self):
        self.dirs = []

    def set_direction(self, left, right):
        self.dirs.append((left, right))


def make(pwm=0.5, **kw):
    hw = FakeHW()
    return Drive(hw, pwm_at_speed=pwm, **kw), hw


def run(drive, n, fwd=0, turn=0, **kw):
    """Step n ticks of 50 ms; returns the last refusal text."""
    r = None
    for _ in range(n):
        r = drive.step(fwd, turn, dt=DT, **kw)
    return r


def approx(a, b):
    return abs(a - b) < 1e-9


# ---- mix ----
def test_mix_forward_and_backward_are_equal_tracks():
    assert mix(1, 0) == (1.0, 1.0)
    assert mix(-1, 0) == (-1.0, -1.0)


def test_mix_curve_inner_track_is_40_percent_of_outer():
    assert mix(1, 1) == (1.0, INNER_RATIO)  # right curve: left track outer
    assert mix(1, -1) == (INNER_RATIO, 1.0)
    assert mix(-1, 1) == (-1.0, -INNER_RATIO)
    assert INNER_RATIO == 0.4


def test_mix_turn_alone_is_pivot():
    assert mix(0, 1) == (1.0, -1.0)
    assert mix(0, -1) == (-1.0, 1.0)


def test_mix_idle_and_junk_inputs():
    assert mix(0, 0) == (0.0, 0.0)
    assert mix(None, "x") == (0.0, 0.0)
    assert mix(5, 0) == (1.0, 1.0)  # clamped to -1..1


def test_mix_custom_ratio():
    assert mix(1, 1, inner_ratio=0.25) == (1.0, 0.25)


# ---- pwm scaling and ramp ----
def test_pwm_at_speed_scales_output():
    d, hw = make(pwm=0.5)
    run(d, 10, fwd=1)
    assert hw.out == (0.5, 0.5)
    run(d, 10, fwd=1, turn=1)
    assert approx(hw.out[0], 0.5) and approx(hw.out[1], 0.2)


def test_ramp_reaches_target_in_0_3_s_not_before():
    d, hw = make(pwm=0.5)
    run(d, 3, fwd=1)  # 0.15 s: half way
    assert approx(hw.out[0], 0.25)
    run(d, 3, fwd=1)  # 0.30 s: there
    assert approx(hw.out[0], 0.5)


def test_ramp_down_on_release_is_gradual():
    d, hw = make(pwm=0.5)
    run(d, 10, fwd=1)
    run(d, 1)
    assert 0 < hw.out[0] < 0.5
    run(d, 10)
    assert hw.out == (0.0, 0.0)


def test_ramp_zero_means_instant():
    d, hw = make(pwm=0.5, ramp_s=0)
    run(d, 1, fwd=1)
    assert hw.out == (0.5, 0.5)


# ---- interlock rows of table 5.4 (the rows that belong to drive) ----
def test_row_front_under_30_refuses_forward():
    d, hw = make()
    r = run(d, 10, fwd=1, front_cm=OBSTACLE_CM - 1)
    assert r == REFUSE_OBSTACLE and str(OBSTACLE_CM) in r
    assert hw.out == (0.0, 0.0) and not d.moving


def test_row_front_exactly_30_is_allowed():
    d, hw = make()
    assert run(d, 10, fwd=1, front_cm=OBSTACLE_CM) is None
    assert hw.out[0] > 0


def test_row_front_no_echo_does_not_block():
    d, hw = make()
    assert run(d, 10, fwd=1, front_cm=None) is None
    assert hw.out[0] > 0


def test_row_front_under_30_backward_and_turns_still_work():
    for fwd, turn, sign in ((-1, 0, (-1, -1)), (0, 1, (1, -1)), (0, -1, (-1, 1))):
        d, hw = make()
        assert run(d, 10, fwd=fwd, turn=turn, front_cm=10) is None
        assert (hw.out[0] > 0) == (sign[0] > 0) and (hw.out[1] > 0) == (sign[1] > 0)
        assert hw.out[0] != 0 and hw.out[1] != 0


def test_row_front_under_30_stops_a_moving_robot_at_once():
    d, hw = make()
    run(d, 10, fwd=1, front_cm=100)
    assert hw.out == (0.5, 0.5)
    d.step(1, 0, front_cm=20, dt=DT)
    assert hw.out == (0.0, 0.0)  # no ramp down for an obstacle


def test_row_front_under_30_with_curve_key_pivots_from_zero():
    d, hw = make()
    run(d, 10, fwd=1, front_cm=100)
    d.step(1, 1, front_cm=20, dt=DT)  # Z+D at an obstacle: Z dropped, D stays
    assert abs(hw.out[0]) < 0.5 and hw.out[0] > 0 and hw.out[1] < 0  # ramping a pivot from zero
    assert abs(hw.out[0]) <= 0.5 / 0.3 * DT + 1e-9


def test_row_latch_on_refuses_all_drive():
    d, hw = make()
    run(d, 10, fwd=1)
    d.stop()
    assert d.latch and hw.out == (0.0, 0.0) and hw.enabled is False
    for fwd, turn in ((1, 0), (-1, 0), (0, 1), (1, -1)):
        assert d.step(fwd, turn, dt=DT) == REFUSE_LATCH
        assert hw.out == (0.0, 0.0)


def test_row_latch_silent_when_no_key_held_and_release_works():
    d, hw = make()
    d.stop()
    assert d.step(0, 0, dt=DT) is None
    d.release()
    assert run(d, 10, fwd=1) is None and hw.out[0] > 0


def test_row_link_lost_stop_cuts_motors_immediately():
    d, hw = make()
    run(d, 10, fwd=1)
    d.stop()  # controller calls this on the 500 ms watchdog
    assert hw.out == (0.0, 0.0) and hw.enabled is False and d.moving is False


def test_row_rod_moving_refuses_drive():
    for rod in ("LIFTING", "FOLDING"):
        d, hw = make()
        assert run(d, 5, fwd=1, rod=rod) == REFUSE_ROD
        assert hw.out == (0.0, 0.0)


def test_row_rod_folded_or_upright_allows_drive():
    for rod in ("FOLDED", "UPRIGHT"):
        d, hw = make()
        assert run(d, 5, fwd=1, rod=rod) is None
        assert hw.out[0] > 0


def test_row_imu_calibrating_refuses_drive():
    d, hw = make()
    assert run(d, 5, fwd=1, imu="CALIBRATING") == REFUSE_IMU
    assert hw.out == (0.0, 0.0)


def test_row_imu_ok_uncertain_lost_allow_drive():
    for imu in ("OK", "UNCERTAIN", "LOST"):
        d, hw = make()
        assert run(d, 5, fwd=1, imu=imu) is None
        assert hw.out[0] > 0


def test_row_r_while_moving_needs_moving_flag():
    d, _ = make()
    assert d.moving is False
    run(d, 2, fwd=1)
    assert d.moving is True  # rod must answer "stop first"
    run(d, 1)
    assert d.moving is True  # still ramping down
    run(d, 10)
    assert d.moving is False


def test_refusal_priority_latch_over_imu_over_rod_over_obstacle():
    d, _ = make()
    d.stop()
    assert d.step(1, 0, front_cm=5, rod="LIFTING", imu="CALIBRATING", dt=DT) == REFUSE_LATCH
    d.release()
    assert d.step(1, 0, front_cm=5, rod="LIFTING", imu="CALIBRATING", dt=DT) == REFUSE_IMU
    assert d.step(1, 0, front_cm=5, rod="LIFTING", dt=DT) == REFUSE_ROD
    assert d.step(1, 0, front_cm=5, dt=DT) == REFUSE_OBSTACLE


# ---- obstacle event ----
def test_obstacle_alert_once_per_approach():
    d, _ = make()
    alerts = 0
    for _ in range(20):
        d.step(1, 0, front_cm=20, dt=DT)
        alerts += d.pop_obstacle_alert()
    assert alerts == 1
    for _ in range(3):
        d.step(1, 0, front_cm=35, dt=DT)  # between 30 and 40: not re-armed
    d.step(1, 0, front_cm=20, dt=DT)
    assert d.pop_obstacle_alert() is False
    d.step(0, 0, front_cm=80, dt=DT)  # cleared
    d.step(1, 0, front_cm=20, dt=DT)
    assert d.pop_obstacle_alert() is True


# ---- hardware order and failsafe ----
def test_enable_goes_high_before_first_pwm_and_low_after_zero():
    d, hw = make()
    assert hw.calls[-1] == ("motors", 0.0, 0.0)  # init: zero PWM, enable never raised
    run(d, 1, fwd=1)
    first = [c for c in hw.calls if c[0] == "enable" or (c[0] == "motors" and c[1] != 0)]
    assert first[0] == ("enable", True) and first[1][0] == "motors"
    run(d, 20)
    enables = [c for c in hw.calls if c[0] == "enable"]
    assert enables[-1] == ("enable", False) and hw.enabled is False
    i = hw.calls.index(enables[-1])
    assert hw.calls[i - 1] == ("motors", 0.0, 0.0)  # PWM 0 before enable low


def test_motor_error_leaves_enable_low_and_reraises():
    class Broken(FakeHW):
        def motors(self, left, right):
            if left:
                raise OSError("driver fault")
            super().motors(left, right)

    hw = Broken()
    d = Drive(hw, pwm_at_speed=0.5)
    with pytest.raises(OSError):
        run(d, 3, fwd=1)
    assert hw.enabled is False and d.moving is False


def test_close_and_context_manager_leave_motors_off():
    hw = FakeHW()
    with Drive(hw, pwm_at_speed=0.5) as d:
        run(d, 10, fwd=1)
        assert hw.out == (0.5, 0.5)
    assert hw.out == (0.0, 0.0) and hw.enabled is False


def test_sensors_get_the_applied_direction():
    hw, s = FakeHW(), FakeSensors()
    d = Drive(hw, pwm_at_speed=0.5, sensors=s)
    run(d, 10, fwd=-1)
    assert s.dirs[-1] == (-0.5, -0.5)
    d.stop()
    assert s.dirs[-1] == (0.0, 0.0)


# ---- config ----
def test_from_config_reads_drive_section_or_whole_config():
    hw = FakeHW()
    cfg = {"drive": {"pwm_at_speed": 0.7, "inner_ratio": 0.3, "ramp_s": 0.5}}
    for c in (cfg, cfg["drive"]):
        d = Drive.from_config(hw, c)
        assert (d.pwm, d.inner_ratio, d.ramp_s) == (0.7, 0.3, 0.5)


def test_from_config_missing_or_null_uses_defaults():
    for c in (None, {}, {"drive": None}, {"drive": {"pwm_at_speed": None}}):
        d = Drive.from_config(FakeHW(), c)
        assert 0 < d.pwm <= 1 and d.inner_ratio == 0.4 and d.ramp_s == 0.3


def test_bad_config_values_raise():
    for kw in ({"pwm_at_speed": 0}, {"pwm_at_speed": 1.5}, {"inner_ratio": -0.1}, {"inner_ratio": 2},
               {"ramp_s": -1}):
        with pytest.raises(ValueError):
            Drive(FakeHW(), **kw)


def test_with_real_mock_hw():
    os.environ["HW_MODE"] = "mock"
    try:
        from pi.controller.hw import HW
        hw = HW()
    except Exception as e:  # HW() may need arguments: skip, do not fail
        pytest.skip(f"HW() not constructible here: {e}")
    d = Drive(hw, pwm_at_speed=0.5)
    run(d, 10, fwd=1)
    d.stop()
    d.close()
