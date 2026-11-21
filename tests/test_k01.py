"""K01 checks: tree of 4.1, config of 4.2, slabs, requirements, setup.sh, units."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent

TREE = """
common/protocol.py common/constants.py
pi/controller/main.py pi/controller/ws_server.py pi/controller/telemetry.py pi/controller/events.py
pi/controller/hw.py pi/controller/sensors.py pi/controller/drive.py pi/controller/head.py
pi/controller/rod.py pi/controller/imu.py pi/controller/position.py
pi/ai/worker.py pi/ai/rules.py pi/ai/detectors/base.py pi/ai/detectors/dummy.py pi/ai/detectors/onnx_det.py
pi/video/pipeline.sh pi/video/mediamtx.yml pi/video/prune.sh
pc/server/app.py pc/server/photo.py pc/server/screenshot.py pc/server/csvlog.py
pc/web/index.html pc/web/css/tokens.css pc/web/css/layout.css pc/web/css/components.css
pc/web/js/keys.js pc/web/js/link.js pc/web/js/whep.js pc/web/js/app.js pc/web/js/map.js pc/web/js/log.js
config/config.yaml config/slabs.json
tools/fake_pi.py tools/ws_smoke.py tools/bench_detector.py tools/record_normal.py
tools/calib_encoders.py tools/calib_imu.py tools/latency_test.py tools/verify.py
tools/check_video.sh tools/make_dummy_onnx.py
docs/design.md systemd/kashimo-mediamtx.service systemd/kashimo-video.service
systemd/kashimo-controller.service systemd/kashimo-ai.service
setup.sh requirements-pi.txt requirements-pc.txt README.md .gitignore
""".split()

needs_bash = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None, reason="needs bash"
)


def load_config():
    return yaml.safe_load((ROOT / "config/config.yaml").read_text(encoding="utf-8"))


def test_tree_matches_contract():
    assert [p for p in TREE if not (ROOT / p).is_file()] == []


def test_config_loads_with_contract_keys():
    cfg = load_config()
    top = {"pi_ip", "ws_port", "hw_mode", "video", "rec_cap_gb", "drive", "odo", "imu", "ai", "gallery", "slabs_file"}
    assert top <= set(cfg)
    assert set(cfg["video"]) == {"mode", "whep_url", "rtsp_url", "mjpeg_url", "w", "h", "fps", "kbps"}
    assert set(cfg["drive"]) == {"pwm_at_speed", "inner_ratio", "ramp_s"}
    assert set(cfg["odo"]) == {"track_circumference_m", "counts_per_rev", "cal_factor"}
    assert set(cfg["imu"]) == {"snap", "snap_window_deg", "snap_straight_m"}
    assert set(cfg["ai"]) == {"detector", "model_dir", "fps", "threads", "nice", "roi", "pose_gate_deg", "consecutive", "cooldown_s"}
    assert set(cfg["gallery"]) == {"width_m", "length_m", "slab_width_m"}


def test_config_contract_values():
    cfg = load_config()
    assert cfg["ws_port"] == 8765 and cfg["hw_mode"] == "mock" and cfg["rec_cap_gb"] == 8
    assert (cfg["video"]["w"], cfg["video"]["h"], cfg["video"]["fps"], cfg["video"]["kbps"]) == (1280, 720, 15, 2500)
    assert cfg["drive"]["inner_ratio"] == 0.4 and cfg["drive"]["ramp_s"] == 0.3
    assert cfg["odo"]["counts_per_rev"] == 20 and cfg["odo"]["cal_factor"] == 1.0
    assert cfg["imu"]["snap"] is False
    assert cfg["ai"]["detector"] == "dummy" and cfg["ai"]["consecutive"] == 3 and cfg["ai"]["pose_gate_deg"] is None
    assert cfg["gallery"] == {"width_m": 2.0, "length_m": 30, "slab_width_m": 0.5}
    assert (ROOT / cfg["slabs_file"]).is_file()


def test_slabs_json_exact():
    data = json.loads((ROOT / "config/slabs.json").read_text(encoding="utf-8"))
    assert data == {"sample": True, "slab_width_m": 0.5, "origin_m": 0.0, "overrides": {}}


def test_gitignore_blocks_heavy_and_private_files():
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
    for entry in ["model/", "runs/", "*.db", "venv/", "__pycache__/", "*.onnx", "*.npy", "*.pt"]:
        assert entry in lines


def test_requirements_cover_stack():
    pc = (ROOT / "requirements-pc.txt").read_text(encoding="utf-8")
    pi = (ROOT / "requirements-pi.txt").read_text(encoding="utf-8")
    for name in ["fastapi", "uvicorn", "websockets", "opencv-python", "mss"]:
        assert name in pc
    for name in ["gpiozero", "lgpio", "smbus2", "aiohttp", "numpy", "opencv-python-headless", "onnxruntime"]:
        assert name in pi


def test_units_have_exec_and_placeholders():
    for name in ["mediamtx", "video", "controller", "ai"]:
        text = (ROOT / f"systemd/kashimo-{name}.service").read_text(encoding="utf-8")
        assert "ExecStart=" in text and "@ROOT@" in text and "@USER@" in text


def test_ai_unit_respects_resource_budget():
    text = (ROOT / "systemd/kashimo-ai.service").read_text(encoding="utf-8")
    assert "Nice=10" in text and "MemoryMax=1500M" in text and "CPUQuota=200%" in text


def test_readme_is_short():
    assert len((ROOT / "README.md").read_text(encoding="utf-8").splitlines()) <= 40


def test_scripts_use_lf_endings():
    for p in ["setup.sh", "pi/video/pipeline.sh", "pi/video/prune.sh", "tools/check_video.sh"]:
        assert b"\r" not in (ROOT / p).read_bytes()


@needs_bash
def test_shell_syntax():
    for p in ["setup.sh", "pi/video/pipeline.sh", "pi/video/prune.sh", "tools/check_video.sh"]:
        assert subprocess.run(["bash", "-n", str(ROOT / p)]).returncode == 0


@needs_bash
def test_setup_dry_run_changes_nothing():
    out = subprocess.run(["bash", str(ROOT / "setup.sh"), "--dry-run"], capture_output=True, text=True)
    assert out.returncode == 0
    assert "apt-get install" in out.stdout and "kashimo-controller.service" in out.stdout
