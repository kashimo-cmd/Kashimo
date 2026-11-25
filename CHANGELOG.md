# Changelog

Format: [Keep a Changelog](https://keepachangelog.com). Versions are Git tags.

## [Unreleased]
### Added
- Documentation set: ARCHITECTURE, USER_MANUAL, TASKS, TESTING, IMPACT, phase 2 notes, REPO_GUIDE_FOR_AI.
- `hardware/` (BOM, pin map, power), `results/` (empty result log and test report template), `ai/`, `media/`.
- CHANGELOG.md, CITATION.cff.

### Fixed
- `docs/tasks/K14.md`: test count corrected to 178 passed, 2 skipped.

## [0.2.0-pre] K04-K08 (merged, untagged)
- K04 hardware layer (mock and Pi modes), K05 sensors, K06 drive and interlocks, K07 head and rod, K08 IMU and position. Tested on a PC with fake hardware only. Not run on the Pi.

## [0.1.0] - 2026-11-25
First tagged state: PC-side software complete up to K14.
### Added
- K01 repo skeleton, config, setup.sh, systemd units, CI (pytest in mock mode).
- K02 protocol messages, constants, key map. K03 fake Pi and WebSocket smoke test.
- K00 Pi first-boot guide and probe. K10 video pipeline and MediaMTX config (not run on the real Pi).
- K12 PC server: relay, photo, screenshot, CSV.
- K13 dashboard shell. K14 dashboard logic (keys, link banners, readouts, WHEP/MJPEG video).
- Phase 1 poster in `docs/phase1/`.
### Not done
- K09, K11, K15, K16, K17 were stubs at this tag.
