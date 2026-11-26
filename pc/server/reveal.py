"""Show a saved file in the file manager (Explorer with the file selected on Windows)."""
import json
import subprocess
import sys
from pathlib import Path


def inside(base, raw):
    """Request body (bytes) {"file": "photos/x.jpg"} -> existing file inside base, else None. No way out of base."""
    try:
        name = json.loads(raw or b"{}").get("file")
        base = Path(base).resolve()
        path = (base / name).resolve()
    except (ValueError, TypeError, AttributeError, OSError):
        return None
    return path if base in path.parents and path.is_file() else None


def command(path, platform=None):
    plat = platform or sys.platform
    if plat.startswith("win"):
        return ["explorer", "/select,", str(path)]
    if plat == "darwin":
        return ["open", "-R", str(path)]
    return ["xdg-open", str(Path(path).parent)]


def show(path):
    """Start the file manager and return at once. Explorer exits with 1 even on success, so no exit code check."""
    subprocess.Popen(command(path))
