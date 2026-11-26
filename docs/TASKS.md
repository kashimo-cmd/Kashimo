# Task map

Master list of tasks K00-K17. Details of each task: section 1 of [design.md](design.md). Per-task cards: `docs/tasks/`.
Status is what `main` contains on 25 Nov 2026 (after PR #14). IN PROGRESS = done by the team in a branch or chat but not pushed or merged: files on `main` are still one-line stubs. Change the row to DONE only after the merge. "Real robot" means run on the physical Pi or robot.

| ID | Task | Status | Evidence in repo | Real robot |
|---|---|---|---|---|
| K00 | Pi first boot and probe | DONE | `docs/PI_FIRST_BOOT.md`, `tools/pi_probe.sh` | probe output not recorded |
| K01 | Skeleton, config, setup.sh, systemd | DONE | whole tree, CI | setup.sh not run on a Pi |
| K02 | Protocol and constants | DONE | `common/`, `tests/test_protocol.py` | n/a |
| K03 | Fake Pi | DONE | `tools/fake_pi.py`, `tests/test_fake_pi.py` | n/a |
| K10 | Video pipeline | DONE (PC) | `pi/video/`, `tools/check_video.sh` | **NOT RUN** |
| K12 | PC server | DONE | `pc/server/`, `tests/test_server.py` | n/a |
| K13 | Dashboard shell | DONE | `pc/web/` | n/a |
| K14 | Dashboard logic | DONE | `pc/web/js/`, `docs/tasks/K14.md`, `tests/*.mjs` | no real Pi, no AZERTY test (T13) |
| K15 | Map and log panel | DONE | `pc/web/js/map.js`, `log.js`, `docs/tasks/K15.md`, `tests/map.test.mjs`, `tests/log.test.mjs` | no real Pi, no gallery turn, no Edge or Firefox |
| K04 | Hardware layer | DONE (PC, fake HW) | `pi/controller/hw.py`, `tests/test_hw.py`, `docs/tasks/K04.md` | **NOT RUN** |
| K05 | Sensors | DONE (PC, fake HW) | `sensors.py`, `tests/test_sensors.py`, `docs/tasks/K05.md` | **NOT RUN** |
| K06 | Drive | DONE (PC, fake HW) | `drive.py`, `tests/test_drive.py`, `docs/tasks/K06.md` | **NOT RUN** |
| K07 | Head and rod | DONE (PC, fake HW) | `head.py`, `rod.py`, tests, `docs/tasks/K07.md` | **NOT RUN** |
| K08 | IMU and position | DONE (PC, fake HW) | `imu.py`, `position.py`, tests, `docs/tasks/K08.md` | **NOT RUN** |
| K09 | Controller main loop | DONE (PC, mock HW) | `main.py`, `ws_server.py`, `telemetry.py`, `events.py`, tests, `docs/tasks/K09.md` | **NOT RUN** |
| K11 | AI plug-in | IN PROGRESS, not merged | `pi/ai/` | no model integrated |
| K16 | Pi tools | IN PROGRESS, not merged | `tools/bench_detector.py`, `calib_*.py`, `latency_test.py`, `record_normal.py` | no |
| K17 | Deploy and verify | IN PROGRESS, not merged | `tools/verify.py` | waits for the 32 GB card |

Order (design v4.2): done A and V, then C (K12-K15), then B (K04-K09), then D (K11, K16, K17).
Update this table in the same pull request that finishes a task.
