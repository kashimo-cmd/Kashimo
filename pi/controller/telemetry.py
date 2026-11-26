"""Telemetry snapshot (10 Hz) and slab numbering (K09, design 4.5 and 5.3)."""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

from common import protocol as P

log = logging.getLogger("kashimo.telemetry")
NO_RSSI = -100.0  # no Wi-Fi reading: shows as the worst bar


def finite(v, default=0.0, nd=3):
    """Rounded float, or default for None, junk, NaN and inf."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return round(v, nd) if math.isfinite(v) else default


class Slabs:
    """slab = floor((x - origin_m) / slab_width_m) + 1; overrides {"<computed>": number} rename a slab (5.3)."""

    def __init__(self, slab_width_m: float = 0.5, origin_m: float = 0.0, overrides: dict | None = None):
        if not slab_width_m > 0:
            raise ValueError(f"slab_width_m must be > 0, got {slab_width_m!r}")
        self.width, self.origin = float(slab_width_m), float(origin_m)
        self.overrides = {str(k): int(v) for k, v in (overrides or {}).items()}

    @classmethod
    def from_file(cls, path, default_width: float = 0.5) -> "Slabs":
        """Read slabs.json; a missing or unreadable file falls back to the gallery width with origin 0."""
        try:
            d = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(d, dict):
                raise ValueError("not an object")
        except (OSError, ValueError) as exc:
            log.warning("slabs file %s unusable (%s): width %s m, origin 0", path, exc, default_width)
            d = {}
        pick = lambda k, default: default if d.get(k) is None else d[k]
        return cls(pick("slab_width_m", default_width), pick("origin_m", 0.0), d.get("overrides"))

    def number(self, x) -> int:
        """Slab number for the along-axis distance x (m)."""
        n = math.floor((finite(x) - self.origin) / self.width) + 1
        return self.overrides.get(str(n), n)


def make_telemetry(seq: int, ts: float, **v) -> P.Telemetry:
    """Build a validated TELEMETRY from raw values: junk numbers become safe defaults, never an exception."""
    cm = lambda k: None if v[k] is None else finite(v[k], None, 1)  # noqa: E731
    return P.Telemetry(
        seq=seq, ts=ts, state=v["state"], latch=bool(v["latch"]), hb_seq=int(v["hb_seq"]),
        fc=cm("fc"), fl=cm("fl"), fr=cm("fr"),
        s=finite(v["s"]), x=finite(v["x"]), y=finite(v["y"]), yaw=finite(v["yaw"], nd=2), slab=int(v["slab"]),
        pan=finite(v["pan"], nd=2), tilt=finite(v["tilt"], nd=2), led=bool(v["led"]), rod=v["rod"],
        pitch=finite(v["pitch"], nd=2), roll=finite(v["roll"], nd=2), imu=v["imu"],
        rssi_dbm=finite(v["rssi_dbm"], NO_RSSI, 1), cpu_temp=finite(v["cpu_temp"], 0.0, 1),
        cpu_load=finite(v["cpu_load"], 0.0, 1), ai=v["ai"], ai_ms=finite(v["ai_ms"], 0.0, 1),
        rec=bool(v["rec"]), refusal=v["refusal"])
