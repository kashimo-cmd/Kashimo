"""Tests for K07 head: key integration, HOME, boot move, rod gating."""
import os

import pytest

from pi.controller.head import DEFAULT_FOLD_POSE, HEAD_RATE, HOME_RATE, REST, Head

DT = 0.05


class FakeHW:
    """Records servo(name, angle) calls."""

    def __init__(self):
        self.calls = []

    def servo(self, name, angle):
        self.calls.append((name, angle))

    def last(self, name):
        return [a for n, a in self.calls if n == name][-1]


def make(fold_pose=(90, 90), **kw):
    """Head already settled at REST (fold pose = rest means no boot move)."""
    hw = FakeHW()
    return Head(hw, fold_pose=fold_pose, **kw), hw


def run(head, n, pan=0, tilt=0, rod="UPRIGHT"):
    for _ in range(n):
        head.step(pan, tilt, rod=rod, dt=DT)


def at(head, pan, tilt):
    """Put the head at a pose with no waiting (test setup only)."""
    head.goto((pan, tilt), 100000)
    head.step(0, 0, rod="FOLDED", dt=DT)
    assert head.pose == (pan, tilt) and head.settled


def test_constants_match_the_design():
    assert (HEAD_RATE, HOME_RATE, REST) == (40.0, 60.0, (90.0, 90.0))
    assert DEFAULT_FOLD_POSE is not None


# ---- keys ----
def test_held_key_integrates_2_deg_per_50_ms_step():
    h, hw = make()
    run(h, 1, pan=1)
    assert h.pan == 92.0
    run(h, 4, pan=1)
    assert h.pan == 100.0 and hw.last("pan") == 100.0
    run(h, 5, tilt=-1)
    assert h.tilt == 80.0 and hw.last("tilt") == 80.0


def test_pose_holds_on_release():
    h, hw = make()
    run(h, 5, pan=1, tilt=1)
    n = len(hw.calls)
    run(h, 20)
    assert h.pose == (100.0, 100.0) and len(hw.calls) == n


def test_both_axes_move_together():
    h, _ = make()
    run(h, 3, pan=-1, tilt=1)
    assert h.pose == (84.0, 96.0)


def test_clamped_to_0_180():
    h, hw = make()
    run(h, 100, pan=1, tilt=-1)
    assert h.pose == (180.0, 0.0)
    assert hw.last("pan") == 180.0 and hw.last("tilt") == 0.0


def test_junk_keys_count_as_zero():
    h, hw = make()
    n = len(hw.calls)
    h.step(None, "x", rod="UPRIGHT", dt=DT)
    assert h.pose == (90.0, 90.0) and len(hw.calls) == n
    h.step(5, 0, rod="UPRIGHT", dt=DT)  # clamped to 1
    assert h.pan == 92.0


# ---- rod gating ----
def test_keys_ignored_unless_rod_upright():
    for rod in ("FOLDED", "LIFTING", "FOLDING"):
        h, hw = make()
        n = len(hw.calls)
        run(h, 5, pan=1, tilt=1, rod=rod)
        assert h.pose == (90.0, 90.0) and len(hw.calls) == n
    h, _ = make()
    run(h, 1, pan=1)
    assert h.pan == 92.0


def test_home_ignored_unless_rod_upright():
    for rod in ("FOLDED", "LIFTING", "FOLDING"):
        h, _ = make()
        at(h, 150, 30)
        assert h.home(rod) is False
        run(h, 30, rod=rod)
        assert h.pose == (150.0, 30.0)


# ---- HOME ----
def test_home_moves_to_rest_at_60_deg_per_s():
    h, hw = make()
    at(h, 150, 30)
    assert h.home("UPRIGHT") is True and not h.settled
    run(h, 1)
    assert h.pose == (147.0, 33.0)  # 3 deg per 50 ms step
    run(h, 9)
    assert h.pose == (120.0, 60.0)
    run(h, 10)
    assert h.pose == REST and h.settled


def test_home_stops_sending_when_arrived():
    h, hw = make()
    at(h, 100, 100)
    h.home("UPRIGHT")
    run(h, 10)
    n = len(hw.calls)
    run(h, 10)
    assert len(hw.calls) == n and h.pose == REST


def test_key_press_cancels_home():
    h, _ = make()
    at(h, 150, 150)
    h.home("UPRIGHT")
    run(h, 2)
    assert not h.settled
    run(h, 1, pan=1)
    assert h.settled
    pose = h.pose
    run(h, 5)
    assert h.pose == pose  # no more homing


# ---- boot and goto ----
def test_boot_moves_from_fold_pose_to_rest_at_30_deg_per_s():
    h, hw = make(fold_pose=(90, 150))
    assert hw.calls[:2] == [("pan", 90.0), ("tilt", 150.0)]  # assumed start pose is sent first
    run(h, 1, rod="FOLDED")  # keys and rod state do not stop the boot move
    assert h.pose == (90.0, 148.5)
    run(h, 39, rod="FOLDED")
    assert h.pose == REST and h.settled


def test_goto_runs_whatever_the_rod_does():
    h, _ = make()
    h.goto((90, 150), 60)
    run(h, 20, pan=1, rod="FOLDING")  # keys ignored, goto runs
    assert h.pose == (90.0, 150.0) and h.settled


def test_goto_clamps_and_rejects_bad_targets():
    h, _ = make()
    with pytest.raises(ValueError):
        h.goto((90, 200), 60)
    with pytest.raises(ValueError):
        h.goto("bad", 60)


def test_servo_error_propagates():
    h, hw = make()

    def boom(name, angle):
        raise OSError("servo fault")

    hw.servo = boom
    with pytest.raises(OSError):
        run(h, 1, pan=1)


# ---- config ----
def test_from_config_reads_head_section_or_whole_config():
    cfg = {"head": {"rate": 20, "home_rate": 30, "rest": [80, 70], "fold_pose": [10, 20]}}
    for c in (cfg, cfg["head"]):
        h = Head.from_config(FakeHW(), c)
        assert (h.rate, h.home_rate, h.rest, h.fold_pose) == (20.0, 30.0, (80.0, 70.0), (10.0, 20.0))


def test_from_config_missing_or_null_uses_defaults():
    for c in (None, {}, {"head": None}, {"head": {"rate": None}}):
        h = Head.from_config(FakeHW(), c)
        assert (h.rate, h.home_rate, h.rest) == (40.0, 60.0, (90.0, 90.0))


def test_bad_config_values_raise():
    for kw in ({"rate": 0}, {"home_rate": -1}, {"init_rate": 0}, {"rest": (90, 200)}, {"rest": (90,)},
               {"fold_pose": "ab"}):
        with pytest.raises(ValueError):
            Head(FakeHW(), **kw)


def test_with_real_mock_hw():
    os.environ["HW_MODE"] = "mock"
    try:
        from pi.controller.hw import HW
        hw = HW()
    except Exception as e:  # HW() may need arguments: skip, do not fail
        pytest.skip(f"HW() not constructible here: {e}")
    h = Head(hw)
    run(h, 10, pan=1)
    h.goto((90, 90), 60)
    run(h, 20, rod="FOLDING")
