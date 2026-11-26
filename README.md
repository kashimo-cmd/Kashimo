# Kashimo

[![CI](https://github.com/kashimo-cmd/Kashimo/actions/workflows/ci.yml/badge.svg)](https://github.com/kashimo-cmd/Kashimo/actions/workflows/ci.yml)

Tracked robot for safe inspection of live cable galleries (IEEE IAS Challenge TSYP14, partner ACTIA). A Raspberry Pi 5 drives, streams video and runs the AI. One operator works from a web dashboard on a PC.
Problem: the gallery is 30+ m long, cables are live up to 380 V, and two or more technicians crawl in to search a fault (about 2 h, ACTIA estimate). Details: [docs/phase2](docs/phase2/README.md).

**Status (25 Nov 2026):** PC software (protocol, fake Pi, server, dashboard to K15) and the Pi controller K04-K09 are done and tested on a PC only. K11, K16, K17 are not merged. Nothing is run on the real Pi or robot, and there are no measured results yet. Per-task status: [docs/TASKS.md](docs/TASKS.md).

## Docs
[Index](docs/README.md) · [Design and contracts](docs/design.md) · [Architecture](docs/ARCHITECTURE.md) · [User manual](docs/USER_MANUAL.md) · [Testing](docs/TESTING.md) · [Hardware](hardware/README.md) · [Results](results/README.md) · [AI guide for assistants](docs/REPO_GUIDE_FOR_AI.md)

## Run in mock mode (PC, no robot)
Python 3.11 or newer.
```
python -m venv venv
venv\Scripts\activate        (Linux/macOS: source venv/bin/activate)
pip install -r requirements-pc.txt
python -m pytest
```
Terminal 1: `python tools/fake_pi.py --no-webcam`. Terminal 2: `python -m pc.server.app --video mjpeg`. Browser: http://127.0.0.1:8080. Code reads `HW_MODE=mock`.

## Run on the Pi
Raspberry Pi OS Lite 64-bit **Bookworm** (Python 3.11): in Imager choose Raspberry Pi OS (other), Legacy 64-bit Lite. `setup.sh` refuses Trixie.
```
git clone https://github.com/kashimo-cmd/Kashimo.git ~/kashimo
cd ~/kashimo && bash setup.sh
```
`model/` is not in Git: copy it with `scp`. First boot: [docs/PI_FIRST_BOOT.md](docs/PI_FIRST_BOOT.md).

## Layout
`common/` `pi/` `pc/` `config/` `tools/` `tests/` `systemd/` code · `hardware/` `simulation/` `results/` `media/` `ai/` `docs/` evidence and documentation.

## Safety, contributing, license
Live cables and water mean a shock risk: read section 8.5 of [docs/design.md](docs/design.md) before any robot test. Nothing is certified.
[CONTRIBUTING.md](CONTRIBUTING.md) · [MIT license](LICENSE) · [CITATION.cff](CITATION.cff) · [CHANGELOG.md](CHANGELOG.md)
