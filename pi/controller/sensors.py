"""K05 sensors: 3 ultrasonic (median of 3) and 2 encoders (signed distance)."""
import logging
import threading
import time
from collections import deque

log = logging.getLogger("kashimo.sensors")

SLOT_S = 0.05
SLOT_ORDER = ("front", "left", "front", "right")  # front 10 Hz, sides 5 Hz
OUT_KEY = {"front": "fc", "left": "fl", "right": "fr"}


def median3(window):
    """Median of the last readings (cm), None when most of them are no-echo."""
    vals = sorted(v for v in window if v is not None)
    if not vals or len(vals) * 2 <= len(window):
        return None
    return vals[(len(vals) - 1) // 2]  # two values: the lower (safer) one


def _sign(x):
    return (x > 0) - (x < 0)


class Sensors:
    """Call step() every 50 ms (or start() for a thread), read() any time."""

    def __init__(self, hw, circumference_m, counts_per_rev=20, cal_factor=1.0):
        if not circumference_m or circumference_m <= 0:
            raise ValueError("odo.track_circumference_m must be > 0")
        self.hw = hw
        self.m_per_count = circumference_m / counts_per_rev * cal_factor
        self._lock = threading.Lock()
        self._win = {n: deque(maxlen=3) for n in OUT_KEY}
        self._slot = 0
        self._dir = [1, 1]          # last non-zero commanded sign per track
        self._last = None           # last raw (l, r) counts
        self._dist = [0.0, 0.0]     # cumulative signed metres per track
        self._ds = 0.0              # metres since the last read()
        self._thread = None
        self._stop = threading.Event()

    @classmethod
    def from_config(cls, hw, cfg):
        o = cfg.get("odo") or {}
        return cls(hw, o.get("track_circumference_m"),
                   o.get("counts_per_rev", 20), o.get("cal_factor", 1.0))

    def set_direction(self, left, right):
        """Commanded track values (-1..1): encoders have no direction of their own."""
        with self._lock:
            for i, v in enumerate((left, right)):
                if v:
                    self._dir[i] = _sign(v)

    def _update_encoders(self):
        l, r = self.hw.encoder_counts()
        with self._lock:
            if self._last is None:
                self._last = (l, r)
                return
            dl, dr = l - self._last[0], r - self._last[1]
            self._last = (l, r)
            if dl < 0 or dr < 0:    # counter was reset: resync, no jump
                return
            ml = dl * self.m_per_count * self._dir[0]
            mr = dr * self.m_per_count * self._dir[1]
            self._dist[0] += ml
            self._dist[1] += mr
            self._ds += (ml + mr) / 2.0

    def step(self):
        """One 50 ms slot: encoders, then one ultrasonic trigger (blocks up to 30 ms)."""
        self._update_encoders()
        name = SLOT_ORDER[self._slot]
        self._slot = (self._slot + 1) % len(SLOT_ORDER)
        try:
            cm = self.hw.pulse(name)
        except Exception:
            log.exception("pulse(%s) failed", name)
            cm = None
        with self._lock:
            self._win[name].append(cm)

    def read(self):
        """{fl,fc,fr} cm or None, ds = metres since last read(), left_m/right_m cumulative."""
        self._update_encoders()
        with self._lock:
            out = {OUT_KEY[n]: median3(w) for n, w in self._win.items()}
            out["ds"], self._ds = self._ds, 0.0
            out["left_m"], out["right_m"] = self._dist
            return out

    def start(self):
        """Run step() on a 50 ms schedule in a daemon thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="sensors", daemon=True)
        self._thread.start()

    def _run(self):
        nxt = time.monotonic()
        while not self._stop.is_set():
            self.step()
            nxt += SLOT_S
            wait = nxt - time.monotonic()
            if wait > 0:
                self._stop.wait(wait)
            else:
                nxt = time.monotonic()  # fell behind: do not burst

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
