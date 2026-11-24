# Kashimo

[![CI](https://github.com/kashimo-cmd/Kashimo/actions/workflows/ci.yml/badge.svg)](https://github.com/kashimo-cmd/Kashimo/actions/workflows/ci.yml)

Tracked inspection robot for the ACTIA cable gallery (IAS Challenge TSYP14, phase 2).
A Raspberry Pi 5 drives, streams video and runs the AI. The operator works from a web dashboard on a PC.

**Status:** K01-K03 (skeleton, protocol, fake Pi), K00 and K10 (Pi first boot, video pipeline) and K12 (PC server) are done. K10 is not yet run on the real Pi. Next: K13-K15 (dashboard).
Design, contracts, tasks K01-K17 and tests T1-T25: [docs/design.md](docs/design.md).

## Run in mock mode (PC, no robot)
Python 3.11.
```
python -m venv venv
venv\Scripts\activate        (Linux/macOS: source venv/bin/activate)
pip install -r requirements-pc.txt
python -m pytest
```
Fake Pi and PC server: `python tools/fake_pi.py --no-webcam`, then `python -m pc.server.app --video mjpeg` (the dashboard page comes with K13-K14). Code reads `HW_MODE=mock`.

## Run on the Pi
Raspberry Pi OS Lite 64-bit, **Bookworm** (Python 3.11). In Raspberry Pi Imager choose Raspberry Pi OS (other), Legacy 64-bit Lite. The current default image is Trixie (Python 3.13) and `setup.sh` refuses it.
```
git clone https://github.com/kashimo-cmd/Kashimo.git ~/kashimo
cd ~/kashimo && bash setup.sh
```
`model/` is not in Git: copy it with `scp`. Check the install with `python tools/verify.py` (K17).

## Layout
`common/` protocol, `pi/` robot code, `pc/` server and dashboard, `config/`, `tools/`, `tests/`, `systemd/`, `docs/`.

## Safety
Live cables (up to 380 V) and water mean a shock risk. Read section 8.5 of docs/design.md before any test with the robot.

## Contributing and license
Branch and pull request rules: [CONTRIBUTING.md](CONTRIBUTING.md). Code under the [MIT license](LICENSE).
