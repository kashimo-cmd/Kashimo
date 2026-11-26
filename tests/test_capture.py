"""K14 follow-up checks: dashboard-only screenshot region, Show file endpoint."""
import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest
import uvicorn

from pc.server import app as A
from pc.server import reveal, screenshot

BOUNDS = {"left": -1920, "top": 0, "width": 3840, "height": 1080}


def test_region_from_accepts_only_sane_regions():
    ok = json.dumps({"region": {"x": 10.6, "y": -5, "w": 1366, "h": 700}}).encode()
    assert screenshot.region_from(ok) == {"x": 10, "y": -5, "w": 1366, "h": 700}
    for bad in (b"", b"{}", b"not json", b"[]", b'{"region": 5}', b'{"region": {"x": 1}}',
                b'{"region": {"x": 0, "y": 0, "w": 10, "h": 700}}', b'{"region": {"x": 0, "y": 0, "w": 1e9, "h": 700}}',
                b'{"region": {"x": "a", "y": 0, "w": 800, "h": 700}}'):
        assert screenshot.region_from(bad) is None


def test_clamp_cuts_to_the_screen():
    inside = {"x": 100, "y": 50, "w": 800, "h": 600}
    assert screenshot.clamp(inside, BOUNDS) == {"left": 100, "top": 50, "width": 800, "height": 600}
    half = {"x": -2000, "y": 0, "w": 400, "h": 600}  # 80 px stick out on the left
    assert screenshot.clamp(half, BOUNDS) == {"left": -1920, "top": 0, "width": 320, "height": 600}
    assert screenshot.clamp({"x": 5000, "y": 0, "w": 800, "h": 600}, BOUNDS) is None


def test_reveal_command_per_platform(tmp_path):
    f = tmp_path / "photos" / "a.jpg"
    assert reveal.command(f, "win32") == ["explorer", "/select,", str(f)]
    assert reveal.command(f, "darwin") == ["open", "-R", str(f)]
    assert reveal.command(f, "linux") == ["xdg-open", str(f.parent)]


def test_reveal_inside_stays_in_the_run_folder(tmp_path):
    run = tmp_path / "run"
    (run / "photos").mkdir(parents=True)
    (run / "photos" / "a.jpg").write_bytes(b"x")
    (tmp_path / "secret.txt").write_bytes(b"x")
    body = lambda name: json.dumps({"file": name}).encode()  # noqa: E731
    assert reveal.inside(run, body("photos/a.jpg")) == (run / "photos" / "a.jpg").resolve()
    for bad in ("../secret.txt", "photos", "photos/none.jpg", str(tmp_path / "secret.txt"), "a\x00b", None, 5):
        assert reveal.inside(run, body(bad)) is None
    assert reveal.inside(run, b"") is None and reveal.inside(run, b"junk") is None


def free_port():
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        return sk.getsockname()[1]


@pytest.fixture
def server(tmp_path):
    cfg = {"pi_ip": "127.0.0.1", "ws_port": free_port(), "video": {"mjpeg_url": "", "rtsp_url": ""}}  # no Pi, no video
    app, port = A.make_app(cfg, video="mjpeg", runs=tmp_path), free_port()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    while not srv.started:
        time.sleep(0.05)

    def post(path, body=b""):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as err:
            return err.code, json.load(err)
    yield app.state.st, post
    srv.should_exit = srv.force_exit = True


def test_screenshot_gets_the_window_region(server, monkeypatch):
    st, post = server
    calls = []

    def fake(path, *region):
        calls.append(region)
        path.write_bytes(b"png")
    monkeypatch.setattr(screenshot, "grab_png", fake)
    body = json.dumps({"region": {"x": 20, "y": 80, "w": 1366, "h": 690}}).encode()
    code, out = post("/api/screenshot", body)
    assert code == 200 and out["area"] == "window" and calls[-1] == ({"x": 20, "y": 80, "w": 1366, "h": 690},)
    code, out = post("/api/screenshot")  # no region: whole screen, as before
    assert code == 200 and out["area"] == "screen" and calls[-1] == ()


def test_reveal_endpoint(server, monkeypatch):
    st, post = server
    shown = []
    monkeypatch.setattr(reveal, "show", shown.append)
    (st.run.sub("photos") / "a.jpg").write_bytes(b"x")
    code, out = post("/api/reveal", json.dumps({"file": "photos/a.jpg"}).encode())
    assert code == 200 and out["ok"] and shown == [(st.run.path / "photos" / "a.jpg").resolve()]
    for bad in ("../x", "photos/none.jpg"):
        assert post("/api/reveal", json.dumps({"file": bad}).encode())[0] == 404
    assert len(shown) == 1

    def boom(_path):
        raise OSError("no explorer")
    monkeypatch.setattr(reveal, "show", boom)
    code, out = post("/api/reveal", json.dumps({"file": "photos/a.jpg"}).encode())
    assert code == 500 and "no explorer" in out["error"]
