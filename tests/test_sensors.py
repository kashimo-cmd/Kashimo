"""Tests for K05 sensors. Use a stand-in HW; one optional test uses the real mock HW."""
import time

import pytest

from pi.controller.sensors import SLOT_ORDER, Sensors, median3


class FakeHW:
    def __init__(self):
        self.calls = []
        self.values = {"front": [], "left": [], "right": []}
        self.counts = (0, 0)

    def pulse(self, sensor):
        self.calls.append(sensor)
        q = self.values[sensor]
        return q.pop(0) if q else 100

    def encoder_counts(self):
        return self.counts


def make(circ=0.2, cal=1.0):
    hw = FakeHW()
    return hw, Sensors(hw, circ, 20, cal)


def run_front(hw, s, seq):
    hw.values["front"] = list(seq)
    for _ in range(len(seq)):
        for _ in range(2):  # F slot then the next non-front slot
            s.step()


def test_median3_removes_spike():
    assert median3([50, 300, 50]) == 50
    assert median3([50, 51, 0]) == 50


def test_median3_no_echo():
    assert median3([None, None, None]) is None
    assert median3([60, None, 61]) == 60
    assert median3([None, None, 70]) is None
    assert median3([]) is None


def test_spike_removed_in_read():
    hw, s = make()
    run_front(hw, s, [50, 300, 50])
    assert s.read()["fc"] == 50


def test_no_echo_gives_none():
    hw, s = make()
    run_front(hw, s, [None, None, None])
    assert s.read()["fc"] is None


def test_slot_order_and_rates():
    hw, s = make()
    for _ in range(8):
        s.step()
    assert tuple(hw.calls[:4]) == SLOT_ORDER
    assert hw.calls == list(SLOT_ORDER) * 2
    assert hw.calls.count("front") == 4
    assert hw.calls.count("left") == 2
    assert hw.calls.count("right") == 2


def test_read_keys():
    hw, s = make()
    assert set(s.read()) == {"fl", "fc", "fr", "ds", "left_m", "right_m"}


def test_distance_forward_signed():
    hw, s = make(circ=0.2)
    s.read()
    s.set_direction(1, 1)
    hw.counts = (20, 20)  # one wheel turn = 0.2 m
    r = s.read()
    assert r["left_m"] == pytest.approx(0.2)
    assert r["right_m"] == pytest.approx(0.2)
    assert r["ds"] == pytest.approx(0.2)


def test_distance_reverse_negative():
    hw, s = make(circ=0.2)
    s.read()
    s.set_direction(-1, -1)
    hw.counts = (10, 10)
    r = s.read()
    assert r["left_m"] == pytest.approx(-0.1)
    assert r["ds"] == pytest.approx(-0.1)


def test_pivot_gives_zero_ds():
    hw, s = make(circ=0.2)
    s.read()
    s.set_direction(-1, 1)
    hw.counts = (20, 20)
    r = s.read()
    assert r["left_m"] == pytest.approx(-0.2)
    assert r["right_m"] == pytest.approx(0.2)
    assert r["ds"] == pytest.approx(0.0)


def test_cal_factor():
    hw, s = make(circ=0.2, cal=1.05)
    s.read()
    hw.counts = (20, 20)
    assert s.read()["ds"] == pytest.approx(0.21)


def test_ds_is_since_last_read_and_cumulative_kept():
    hw, s = make(circ=0.2)
    s.read()
    hw.counts = (20, 20)
    assert s.read()["ds"] == pytest.approx(0.2)
    r = s.read()
    assert r["ds"] == 0.0
    assert r["left_m"] == pytest.approx(0.2)


def test_direction_kept_when_command_is_zero():
    hw, s = make(circ=0.2)
    s.read()
    s.set_direction(-1, -1)
    s.set_direction(0, 0)  # coasting after release
    hw.counts = (5, 5)
    assert s.read()["ds"] == pytest.approx(-0.05)


def test_counter_reset_does_not_jump():
    hw, s = make(circ=0.2)
    hw.counts = (100, 100)
    s.read()
    hw.counts = (0, 0)
    assert s.read()["ds"] == 0.0
    hw.counts = (20, 20)
    assert s.read()["ds"] == pytest.approx(0.2)


def test_pulse_error_is_no_echo():
    hw, s = make()

    def boom(_):
        raise OSError("gpio")

    hw.pulse = boom
    for _ in range(4):
        s.step()
    assert s.read()["fc"] is None


def test_from_config():
    hw = FakeHW()
    s = Sensors.from_config(hw, {"odo": {"track_circumference_m": 0.2,
                                         "counts_per_rev": 20, "cal_factor": 2.0}})
    assert s.m_per_count == pytest.approx(0.02)
    with pytest.raises(ValueError):
        Sensors.from_config(hw, {"odo": {"track_circumference_m": None}})


def test_thread_runs_and_stops():
    hw, s = make()
    hw.values["front"] = [42] * 20
    s.start()
    time.sleep(0.5)
    s.stop()
    n = len(hw.calls)
    assert n >= 6
    assert s.read()["fc"] == 42
    time.sleep(0.15)
    assert len(hw.calls) == n  # stopped


def test_with_real_mock_hw(monkeypatch):
    """Optional: skips if HW() cannot be built that way. Checks the K04 sim hooks."""
    monkeypatch.setenv("HW_MODE", "mock")
    try:
        from pi.controller.hw import HW
        hw = HW()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"HW() not constructible this way: {e}")
    hw.sim["pulse"]["front"] = 20
    s = Sensors(hw, 0.2)
    for _ in range(4):
        s.step()
    assert s.read()["fc"] == 20
    hw.sim_encoders(20, 20)
    assert s.read()["ds"] == pytest.approx(0.2)
