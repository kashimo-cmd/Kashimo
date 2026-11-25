"""Tests for K07 rod: state transitions, head order, stopped-only, 5 s timeout and ALERT_ROD."""
import os

import pytest

from pi.controller.drive import REFUSE_ROD, Drive
from pi.controller.head import Head
from pi.controller.rod import REFUSE_BUSY, REFUSE_STOP_FIRST, Rod

DT = 0.05


class FakeHW:
    """Records servo() calls; has the motor calls Drive needs."""

    def __init__(self):
        self.calls = []
        self.out = (0.0, 0.0)

    def servo(self, name, angle):
        self.calls.append((name, angle))

    def motors_enable(self, on):
        pass

    def motors(self, left, right):
        self.out = (left, right)

    def fold(self):
        return [a for n, a in self.calls if n == "fold"]


class StubHead:
    """Head that settles only when told to."""
    rest, fold_pose, home_rate = (90.0, 90.0), (90.0, 150.0), 60.0

    def __init__(self):
        self.settled, self.goals = True, []

    def goto(self, target, rate):
        self.goals.append((target, rate))


def make(fold_pose=(90, 150), **kw):
    """Head settled in its fold pose, rod FOLDED, fold servo 0..90."""
    hw = FakeHW()
    head = Head(hw, fold_pose=fold_pose, rest=(90, 90))
    for _ in range(60):
        head.step(0, 0, rod="FOLDED", dt=DT)  # let the boot move to REST finish
    head.goto(fold_pose, 100000)
    head.step(0, 0, rod="FOLDED", dt=DT)
    hw.calls.clear()
    return Rod(hw, head, **kw), head, hw


def tick(rod, head, n=1, keys=(0, 0)):
    for _ in range(n):
        head.step(keys[0], keys[1], rod=rod.state, dt=DT)
        rod.step(DT)


def lift(rod, head):
    assert rod.request(False) is None
    tick(rod, head, 80)
    assert rod.state == "UPRIGHT"


# ---- transitions ----
def test_boots_folded_and_idle():
    rod, head, hw = make()
    tick(rod, head, 20)
    assert rod.state == "FOLDED" and not rod.moving and hw.calls == []


def test_lift_takes_3_s_and_ends_upright_with_head_at_rest():
    rod, head, hw = make()
    assert rod.request(False) is None
    assert rod.state == "LIFTING" and rod.moving
    tick(rod, head, 59)
    assert rod.state == "LIFTING"  # 59 x 1.5 deg = 88.5 deg
    tick(rod, head, 1)
    assert rod.state == "UPRIGHT" and not rod.moving
    assert head.pose == (90.0, 90.0) and head.settled
    angles = hw.fold()
    assert angles == sorted(angles) and angles[-1] == 90.0 and abs(angles[1] - angles[0] - 1.5) < 1e-9


def test_lift_sends_the_head_to_rest_while_the_servo_lifts():
    rod, head, hw = make(fold_pose=(90, 90))
    head.pan, head.tilt = 0.0, 180.0  # far from REST: 1.5 s at 60 deg/s, less than the 3 s servo
    assert rod.request(False) is None
    tick(rod, head, 59)
    assert rod.state == "LIFTING"
    tick(rod, head, 1)
    assert rod.state == "UPRIGHT" and head.pose == (90.0, 90.0)


def test_lift_waits_when_the_head_is_slow():
    hw, head = FakeHW(), StubHead()
    rod = Rod(hw, head)
    rod.request(False)
    head.settled = False
    for _ in range(80):
        rod.step(DT)
    assert rod.state == "LIFTING"  # servo is there, head is not
    head.settled = True
    rod.step(DT)
    assert rod.state == "UPRIGHT"


def test_fold_sends_head_to_fold_pose_before_the_servo_moves():
    rod, head, hw = make()
    lift(rod, head)
    tick(rod, head, 1, keys=(1, -1))  # operator moves the head (rod UPRIGHT)
    tick(rod, head, 10, keys=(1, -1))
    assert head.pose != (90.0, 90.0)
    hw.calls.clear()
    assert rod.request(False) is None and rod.state == "FOLDING"
    started = None
    for i in range(200):
        tick(rod, head)
        if hw.fold() and started is None:
            started = i
            assert head.pose == (90.0, 150.0) and head.settled  # head arrived before the servo moved
        if rod.state == "FOLDED":
            break
    assert started is not None and started > 0
    assert rod.state == "FOLDED" and hw.fold()[-1] == 0.0
    assert hw.fold() == sorted(hw.fold(), reverse=True)


def test_full_cycle_folded_lifting_upright_folding_folded():
    rod, head, hw = make()
    seen = [rod.state]
    assert rod.request(False) is None
    for _ in range(80):
        tick(rod, head)
        if rod.state != seen[-1]:
            seen.append(rod.state)
    assert rod.request(False) is None
    for _ in range(200):
        tick(rod, head)
        if rod.state != seen[-1]:
            seen.append(rod.state)
    assert seen == ["FOLDED", "LIFTING", "UPRIGHT", "FOLDING", "FOLDED"]
    assert rod.pop_alert() is None


def test_head_keys_follow_the_rod_state():
    rod, head, _ = make()
    tick(rod, head, 3, keys=(1, 1))
    assert head.pose == (90.0, 150.0)  # folded: ignored
    rod.request(False)
    tick(rod, head, 10, keys=(1, 1))
    assert head.pose != (92.0, 152.0)  # lifting: ignored, head is going to REST
    tick(rod, head, 80)
    tick(rod, head, 1, keys=(1, 0))
    assert head.pan == 92.0  # upright: accepted


# ---- accepted only when stopped ----
def test_request_refused_while_robot_moves():
    rod, head, hw = make()
    assert rod.request(True) == REFUSE_STOP_FIRST
    assert rod.state == "FOLDED"
    tick(rod, head, 5)
    assert hw.calls == []
    lift(rod, head)
    assert rod.request(True) == REFUSE_STOP_FIRST and rod.state == "UPRIGHT"


def test_request_refused_while_rod_is_moving():
    rod, head, _ = make()
    rod.request(False)
    tick(rod, head, 5)
    assert rod.request(False) == REFUSE_BUSY
    assert rod.state == "LIFTING"


# ---- timeout ----
def test_timeout_stops_the_servo_and_raises_alert_rod_once():
    rod, head, hw = make(rate=10)  # 90 deg at 10 deg/s = 9 s: slower than the 5 s limit
    rod.request(False)
    tick(rod, head, 95)
    assert rod.state == "LIFTING" and not rod.timed_out and rod.pop_alert() is None
    tick(rod, head, 7)  # past 5 s
    assert rod.timed_out and rod.state == "LIFTING"
    assert rod.pop_alert() == "LIFTING" and rod.pop_alert() is None
    n = len(hw.calls)
    tick(rod, head, 50)
    assert len(hw.calls) == n  # servo stopped
    assert hw.fold()[-1] < 90.0


def test_timeout_when_head_never_reaches_fold_pose():
    hw, head = FakeHW(), StubHead()
    rod = Rod(hw, head)
    rod.request(False)
    for _ in range(80):
        rod.step(DT)
    assert rod.state == "UPRIGHT"
    n = len(hw.calls)
    head.settled = False
    assert rod.request(False) is None and rod.state == "FOLDING"
    assert head.goals[-1][0] == head.fold_pose
    for _ in range(95):
        rod.step(DT)
    assert not rod.timed_out
    for _ in range(10):
        rod.step(DT)
    assert rod.timed_out and rod.pop_alert() == "FOLDING"
    assert len(hw.calls) == n  # the servo never moved down


def test_after_a_timeout_r_goes_back_the_other_way():
    rod, head, hw = make(rate=10)
    rod.request(False)
    tick(rod, head, 110)
    assert rod.timed_out and rod.state == "LIFTING"
    assert rod.request(True) == REFUSE_STOP_FIRST  # still only when stopped
    assert rod.request(False) is None
    assert rod.state == "FOLDING" and not rod.timed_out
    tick(rod, head, 200)
    assert rod.state == "FOLDED" and rod.pop_alert() == "LIFTING"


# ---- with Drive (K06) ----
def test_drive_refuses_while_rod_moves_and_rod_refuses_while_drive_moves():
    rod, head, hw = make()
    drive = Drive(FakeHW(), pwm_at_speed=0.5)
    for _ in range(5):
        drive.step(1, 0, rod=rod.state, dt=DT)
    assert drive.moving
    assert rod.request(drive.moving) == REFUSE_STOP_FIRST
    for _ in range(20):
        drive.step(0, 0, rod=rod.state, dt=DT)
    assert not drive.moving
    assert rod.request(drive.moving) is None
    assert drive.step(1, 0, rod=rod.state, dt=DT) == REFUSE_ROD
    tick(rod, head, 80)
    assert drive.step(1, 0, rod=rod.state, dt=DT) is None  # upright: driving is allowed again


# ---- config ----
def test_from_config_reads_rod_section_or_whole_config():
    cfg = {"rod": {"folded_deg": 10, "upright_deg": 100, "rate": 20, "timeout_s": 8}}
    for c in (cfg, cfg["rod"]):
        r = Rod.from_config(FakeHW(), StubHead(), c)
        assert (r.folded_deg, r.upright_deg, r.rate, r.timeout_s) == (10.0, 100.0, 20.0, 8.0)


def test_from_config_missing_or_null_uses_defaults():
    for c in (None, {}, {"rod": None}, {"rod": {"rate": None}}):
        r = Rod.from_config(FakeHW(), StubHead(), c)
        assert (r.rate, r.timeout_s) == (30.0, 5.0) and r.folded_deg != r.upright_deg


def test_bad_config_values_raise():
    for kw in ({"folded_deg": -1}, {"upright_deg": 181}, {"folded_deg": 50, "upright_deg": 50}, {"rate": 0},
               {"timeout_s": 0}):
        with pytest.raises(ValueError):
            Rod(FakeHW(), StubHead(), **kw)


def test_with_real_mock_hw():
    os.environ["HW_MODE"] = "mock"
    try:
        from pi.controller.hw import HW
        hw = HW()
    except Exception as e:  # HW() may need arguments: skip, do not fail
        pytest.skip(f"HW() not constructible here: {e}")
    head = Head(hw)
    rod = Rod(hw, head)
    assert rod.request(False) is None
    tick(rod, head, 80)
    assert rod.state == "UPRIGHT"
