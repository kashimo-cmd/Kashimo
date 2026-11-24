"""Screenshot of the whole primary screen with mss (design 5.3: shot_0001_HHMMSS.png)."""
from datetime import datetime

import mss
import mss.tools


def grab_png(path):
    """Write the primary monitor to a PNG file."""
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
        mss.tools.to_png(shot.rgb, shot.size, output=str(path))


def save(folder, n, now=None):
    """Take the screenshot and confirm the file exists and is not empty. Returns its path."""
    path = folder / f"shot_{n:04d}_{(now or datetime.now()):%H%M%S}.png"
    grab_png(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise OSError("screenshot file was not written")
    return path
