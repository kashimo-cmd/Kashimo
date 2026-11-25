"""Tests for K08 position: yaw, path, pivot, L-shaped run, heading snap."""
import math

import pytest

from pi.controller.position import Position, ds_from_tracks, wrap_deg

DT = 0.05
V = 0.25  # m/s
STEP = V * DT  # 12.5 mm per tick


def drive(pos, metres, gz=0.0, **kw):
    """Straight run at 0.25 m/s, 20 ticks per second."""
    for _ in range(round(metres / STEP)):
        pos.update(STEP, gz, DT, **kw)


def pivot(pos, deg, rate=60.0, sub=5):
    """Turn on the spot: ds = 0, gyro sampled five times per 50 ms tick (100 Hz)."""
    for _ in range(round(deg / rate / DT)):
        for _ in range(sub):
            pos.integrate_gyro(rate, DT / sub)
        pos.move(0.0)


# ---- distance ----
def test_ds_is_the_mean_of_both_tracks():
    assert ds_from_tracks((0, 0), (0.1, 0.1)) == pytest.approx(0.1)
    assert ds_from_tracks((1.0, 1.0), (0.9, 0.9)) == pytest.approx(-0.1)  # reversing
    assert ds_from_tracks((0, 0), (0.1, 0.0)) == pytest.approx(0.05)  # curve


def test_pivot_adds_zero_distance():
    assert ds_from_tracks((0, 0), (0.05, -0.05)) == 0.0
    pos = Position()
    pivot(pos, 90)
    assert pos.yaw == pytest.approx(90.0)
    assert pos.s == 0.0 and pos.x == 0.0 and pos.y == 0.0


# ---- yaw ----
def test_yaw_integrates_gyro_minus_bias():
    pos = Position(bias=0.5)
    for _ in range(100):
        pos.update(0.0, 0.5, DT)  # gyro reads only the bias
    assert pos.yaw == 0.0
    pos.update(0.0, 60.5, DT)
    assert pos.yaw == pytest.approx(3.0)


def test_positive_gyro_turns_left_and_y_grows():
    pos = Position()
    pivot(pos, 90)
    drive(pos, 1.0)
    assert pos.x == pytest.approx(0.0, abs=1e-9) and pos.y == pytest.approx(1.0)


def test_yaw_wraps():
    pos = Position()
    pivot(pos, 270)
    assert pos.yaw == pytest.approx(-90.0)
    assert wrap_deg(190) == -170 and wrap_deg(-180) == 180 and wrap_deg(180) == 180


def test_lost_gyro_freezes_yaw_but_not_the_path():
    pos = Position()
    pivot(pos, 90)
    for _ in range(40):
        pos.update(STEP, None, DT)  # IMU LOST
        pos.update(STEP, float("nan"), DT)
    assert pos.yaw == pytest.approx(90.0)
    assert pos.s == pytest.approx(80 * STEP) and pos.y == pytest.approx(80 * STEP)


def test_junk_ds_counts_as_zero():
    pos = Position()
    for ds in (None, "x", float("inf")):
        pos.update(ds, 0.0, DT)
    assert pos.s == 0.0


def test_reset():
    pos = Position()
    pivot(pos, 90)
    drive(pos, 1.0)
    pos.reset()
    assert (pos.x, pos.y, pos.s, pos.yaw) == (0.0, 0.0, 0.0, 0.0)


# ---- synthetic runs ----
def test_l_shaped_run_ends_within_1_percent():
    pos = Position()
    drive(pos, 10.0)
    pivot(pos, 90)
    drive(pos, 5.0)
    true_end = (10.0, 5.0)
    err = math.hypot(pos.x - true_end[0], pos.y - true_end[1])
    assert err < 0.01 * math.hypot(*true_end)
    assert pos.s == pytest.approx(15.0)


def test_l_run_with_gyro_bias_and_noise_ends_within_1_percent():
    pos = Position(bias=0.3)  # bias measured at boot
    noise = [0.2, -0.2]
    k = 0
    for _ in range(800):
        pos.update(STEP, 0.3 + noise[k % 2], DT)
        k += 1
    for _ in range(30):
        for _ in range(5):
            pos.integrate_gyro(60.3 + noise[k % 2], DT / 5)
            k += 1
        pos.move(0.0)
    for _ in range(400):
        pos.update(STEP, 0.3 + noise[k % 2], DT)
        k += 1
    assert math.hypot(pos.x - 10.0, pos.y - 5.0) < 0.01 * math.hypot(10.0, 5.0)


def test_quarter_circle_ends_within_1_percent():
    pos = Position()
    r = 2.0
    rate = math.degrees(V / r)  # deg/s for a left arc of radius 2 m
    for _ in range(round(math.pi / 2 * r / STEP)):
        pos.update(STEP, rate, DT)
    assert math.hypot(pos.x - r, pos.y - r) < 0.01 * math.pi / 2 * r
    assert pos.yaw == pytest.approx(90.0, abs=0.5)


# ---- heading snap ----
def test_snap_is_off_by_default():
    pos = Position()
    pos.yaw = 10.0
    drive(pos, 3.0)
    assert pos.yaw == 10.0


def test_snap_inside_25_degrees_after_1_m_straight():
    pos = Position(snap=True)
    pos.yaw = 10.0
    drive(pos, 0.95)
    assert pos.yaw == 10.0  # not yet
    snapped = [pos.move(STEP) for _ in range(5)]
    assert any(snapped) and snapped.count(True) == 1
    assert pos.yaw == 0.0


def test_snap_goes_to_the_nearest_multiple_of_90():
    for start, want in ((80.0, 90.0), (-95.0, -90.0), (170.0, 180.0), (-170.0, 180.0)):
        pos = Position(snap=True)
        pos.yaw = start
        drive(pos, 1.05)
        assert pos.yaw == want, start


def test_snap_not_outside_the_25_degree_window():
    pos = Position(snap=True)
    pos.yaw = 40.0  # 40 from 0, 50 from 90
    drive(pos, 3.0)
    assert pos.yaw == 40.0


def test_turn_above_3_deg_per_s_restarts_the_straight_run():
    pos = Position(snap=True)
    pos.yaw = 10.0
    drive(pos, 0.9)
    pos.update(STEP, 4.0, DT)  # a turn of 4 deg/s
    yaw = pos.yaw
    drive(pos, 0.9)
    assert pos.yaw == pytest.approx(yaw)  # 1.8 m total, but never 1 m without a turn
    drive(pos, 0.2)
    assert pos.yaw == 0.0 or abs(pos.yaw) < 1e-9  # now 1 m straight


def test_slow_turn_under_3_deg_per_s_does_not_restart():
    pos = Position(snap=True)
    pos.yaw = 10.0
    snapped = [pos.update(STEP, 2.0, DT) for _ in range(round(1.05 / STEP))]  # yaw rises 0.1 deg per tick
    assert snapped.count(True) == 1  # 18 deg at the 1 m mark: inside the window, snapped to 0
    assert abs(pos.yaw) < 1.0  # only the last few ticks after the snap


def test_snap_straight_m_is_configurable():
    pos = Position(snap=True, snap_straight_m=2.0)
    pos.yaw = 10.0
    drive(pos, 1.5)
    assert pos.yaw == 10.0
    drive(pos, 0.6)
    assert pos.yaw == 0.0


def test_reversing_counts_as_distance_for_the_snap():
    pos = Position(snap=True)
    pos.yaw = 10.0
    for _ in range(round(1.05 / STEP)):
        pos.update(-STEP, 0.0, DT)
    assert pos.yaw == 0.0


# ---- config ----
def test_from_config_reads_imu_section_or_whole_config():
    cfg = {"imu": {"snap": True, "snap_window_deg": 15, "snap_straight_m": 2.0}}
    for c in (cfg, cfg["imu"]):
        p = Position.from_config(c)
        assert (p.snap, p.snap_window_deg, p.snap_straight_m) == (True, 15.0, 2.0)


def test_from_config_missing_or_null_uses_defaults():
    for c in (None, {}, {"imu": None}, {"imu": {"snap": None}}):
        p = Position.from_config(c)
        assert (p.snap, p.snap_window_deg, p.snap_straight_m) == (False, 25.0, 1.0)


def test_bad_config_values_raise():
    for kw in ({"snap_window_deg": 0}, {"snap_window_deg": 50}, {"snap_straight_m": 0}):
        with pytest.raises(ValueError):
            Position(**kw)
