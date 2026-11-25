"""K14 checks: the browser JS (keys.js, link.js) under Node, its messages through protocol.decode, and the video config of /api/status."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from common import protocol as P
from pc.server import app as A

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


@needs_node
def test_js_unit_tests():
    run = subprocess.run([NODE, "--test", "tests/keys.test.mjs", "tests/link.test.mjs", "tests/map.test.mjs", "tests/log.test.mjs"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr


@needs_node
def test_every_key_combination_encodes_to_a_valid_message():
    run = subprocess.run([NODE, "tests/emit_msgs.mjs"], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    msgs = [P.decode(text) for text in json.loads(run.stdout)]
    controls = [m for m in msgs if isinstance(m, P.Control)]
    assert len(controls) == 256 and len(msgs) == 262
    assert {m.cmd for m in msgs if isinstance(m, P.Cmd)} == set(P.CMDS)


def test_status_video_config():
    cfg = {"pi_ip": "10.0.0.5", "video": {"mode": "webrtc", "rtsp_url": "rtsp://{pi_ip}:8554/cam", "mjpeg_url": "http://{pi_ip}:8765/video.mjpg"}}
    want = {"mode": "webrtc", "whep_url": "http://10.0.0.5:8889/cam/whep", "mjpeg_url": "http://10.0.0.5:8765/video.mjpg"}
    assert A.settings(cfg)["video"] == want
    assert A.settings(cfg, video="mjpeg")["video"]["mode"] == "mjpeg"  # fake_pi has no WebRTC
    assert A.settings(dict(cfg, video=dict(cfg["video"], mode="mjpeg")), video="rtsp")["video"]["mode"] == "webrtc"
    assert A.settings({"pi_ip": "1.2.3.4"})["video"] == {"mode": "webrtc", "whep_url": "http://1.2.3.4:8889/cam/whep", "mjpeg_url": ""}


def test_status_gallery_for_the_map():
    cfg = {"pi_ip": "1.2.3.4", "gallery": {"width_m": 2.5, "length_m": 12, "slab_width_m": 0.5}}
    assert A.settings(cfg)["gallery"] == {"width_m": 2.5, "length_m": 12, "slab_width_m": 0.5}
    assert A.settings({"pi_ip": "1.2.3.4"})["gallery"] == {"width_m": 2.0, "length_m": 30, "slab_width_m": 0.5}
