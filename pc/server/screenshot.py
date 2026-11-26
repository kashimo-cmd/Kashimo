"""Screenshot with mss (design 5.3: shot_0001_HHMMSS.png). Dashboard only when the browser sends its window region."""
import json
from datetime import datetime

import mss
import mss.tools

MIN_PX, MAX_PX = 50, 20000


def region_from(raw):
    """Request body (bytes) {"region": {x, y, w, h}} in screen pixels -> dict of ints, or None (whole screen)."""
    try:
        reg = json.loads(raw or b"{}").get("region")
        vals = {k: int(reg[k]) for k in ("x", "y", "w", "h")}
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return None
    return vals if all(MIN_PX <= vals[k] <= MAX_PX for k in ("w", "h")) else None


def clamp(region, bounds):
    """Cut region {x, y, w, h} to bounds {left, top, width, height}. None if less than MIN_PX is left."""
    left, top = max(region["x"], bounds["left"]), max(region["y"], bounds["top"])
    right = min(region["x"] + region["w"], bounds["left"] + bounds["width"])
    bottom = min(region["y"] + region["h"], bounds["top"] + bounds["height"])
    if right - left < MIN_PX or bottom - top < MIN_PX:
        return None
    return {"left": left, "top": top, "width": right - left, "height": bottom - top}


def grab_png(path, region=None):
    """Write the primary monitor, or the region (virtual screen coordinates), to a PNG file."""
    with mss.mss() as sct:
        box = sct.monitors[1]
        if region is not None:
            box = clamp(region, sct.monitors[0])
            if box is None:
                raise OSError("the dashboard window is outside the screen")
        shot = sct.grab(box)
        mss.tools.to_png(shot.rgb, shot.size, output=str(path))


def save(folder, n, now=None, region=None):
    """Take the screenshot and confirm the file exists and is not empty. Returns its path."""
    path = folder / f"shot_{n:04d}_{(now or datetime.now()):%H%M%S}.png"
    grab_png(path) if region is None else grab_png(path, region)
    if not path.is_file() or path.stat().st_size == 0:
        raise OSError("screenshot file was not written")
    return path
