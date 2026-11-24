"""Run folder runs/<date_time>/ and the CSV lines of design 5.3."""
import csv
from datetime import datetime
from pathlib import Path

COLUMNS = ["timestamp", "slab_no", "distance_m", "x_m", "y_m", "pan", "tilt", "score", "class",
           "frame_file", "heatmap_file", "delayed"]


class Run:
    """One server start = one folder. Sub-folders are created on first use."""

    def __init__(self, base, now=None):
        self.path = Path(base) / (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")

    def sub(self, name):
        folder = self.path / name
        folder.mkdir(parents=True, exist_ok=True)
        return folder


def row(ts, src=None, score="", cls="", frame="", heat="", delayed=False):
    """src = Telemetry or Event (slab s x y pan tilt), or None when the Pi never sent one."""
    pos = [getattr(src, k, "") if src is not None else "" for k in ("slab", "s", "x", "y", "pan", "tilt")]
    stamp = datetime.fromtimestamp(ts).isoformat(timespec="milliseconds")
    return dict(zip(COLUMNS, [stamp, *pos, score, cls, frame, heat, str(bool(delayed)).lower()]))


def append(path, record):
    """Add one line, header first if the file is new. Closed (flushed) before returning."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        if fresh:
            writer.writeheader()
        writer.writerow(record)
