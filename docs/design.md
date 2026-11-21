# Kashimo: design and build plan v4 (ACTIA gallery inspection robot)

IAS Challenge TSYP14, Phase 2 · v4.1 of 21 November 2026 · replaces v3 (v3 keeps the old conflict table C1-C39).
Tags: **[NEW]** v4 change · **[PICK]** option chosen · **[CALC]** my arithmetic · **[EST]** estimate, not verified · **[CHECK]** test before relying on it.

**v4 changes:** (1) AI runs **on the Pi 5**, not on the PC. (2) Dev on a 16 GB card, move to 32 GB later through Git. (3) AI is a plug-in: dummy detector now, real files later. (4) Dashboard = web page, design rules in section 7. (5) The file is split into tasks K01-K17, one task = one Claude prompt.
**v4.1 fixes:** site geometry (gallery 2+ m wide, slabs 0.5 m wide spanning it, faults = cuts, burns, water), body 300 x 200 x 100 mm under 3 kg, slab resolution 0.5 m, heading snap off by default, water and safety section 8.5.

---

## 0. RULES FOR THE AI READING THIS FILE

Prompt the user pastes: *"Read Kashimo_design_v4.md. Do task K05. Follow section 0."*

1. Do ONLY the named task. Read section 0, section 4 (contracts) and the sections the task lists. Nothing else.
2. Output = files made with `create_file` at the exact repo path under `/mnt/user-data/outputs/`, then `present_files`. Then ONE note, 8 lines max:
   `STATUS: DONE|PARTIAL` · `RUN: <command>` · `TEST: <real result, or NOT RUN>` · `DEVIATIONS: <none|list>` · `OPEN: <3 items max>`
3. No explanation, no recap of the spec, no README prose, no comments beyond one-line docstrings.
4. Section 4 contracts are **frozen**: names of messages, fields, keys, pins, constants, paths. If one looks wrong, implement it as written and list it under DEVIATIONS.
5. Everything must run on a PC with `HW_MODE=mock`. Parts that need the real Pi: mark `# CHECK ON PI`.
6. Size: 300 lines per file, 600 per task. If it will not fit: finish a working core, stop, list the rest in OPEN. Never output half-written files.
7. Python 3.11, asyncio. No library outside the stack in section 3.3.
8. Never write "passed" for a test you did not run.
9. UI tasks (K13-K15) also follow section 7. Anything that breaks section 7 is a failure.

---

## 1. TASKS

Order: A (base) then B (Pi) and C (PC) in parallel, then D. Tests T1-T21 are in section 9. Each task lists its output, its spec sections, and when it is done.

| ID | Task | Needs |
|---|---|---|
| K01 | Repo skeleton, config, setup.sh, systemd | none |
| K02 | Protocol module and constants | K01 |
| K03 | Fake Pi (lets you build the PC side with no robot) | K02 |
| K04 | Hardware layer with mock (`hw.py`) | K02 |
| K05 | Sensors: 3 ultrasonic, 2 encoders | K04 |
| K06 | Drive mixing, interlocks, STOP latch | K04 |
| K07 | Head (pan-tilt) and rod controllers | K04 |
| K08 | IMU and position (path map maths) | K04 |
| K09 | Controller main loop, WebSocket server, telemetry, events | K05-K08 |
| K10 | Video pipeline: ffmpeg, MediaMTX, SD recording | K01 |
| K11 | AI plug-in: detector interface, dummy, ONNX loader, rules, worker | K09 |
| K12 | PC server: relay, photo, screenshot, CSV | K02, K03 |
| K13 | Dashboard shell: tokens, layout, all states (static) | K12 |
| K14 | Dashboard logic: keys, commands, readouts, banners, video | K13 |
| K15 | Dashboard map and log panel | K14 |
| K16 | Pi tools: AI benchmark, calibration, data recorder, latency test | K09 |
| K17 | Deploy: migration, health check | K09 |

### K01 Repo skeleton
- Out: tree of 4.1 with stub files, `config/config.yaml` (4.2), `config/slabs.json` (`{"sample":true,"slab_width_m":0.5,"origin_m":0.0,"overrides":{}}`), `requirements-pi.txt`, `requirements-pc.txt`, `setup.sh` (Pi: apt, venv, pip, install units, make `runs/`), `systemd/kashimo-{mediamtx,video,controller,ai}.service`, `.gitignore` (`model/ runs/ *.db venv/ __pycache__/`), `README.md` 40 lines max (run in mock, run on Pi).
- Spec: 3, 4.1, 4.2.
- Done: `bash -n setup.sh` ok, `config.yaml` loads with `yaml.safe_load`.

### K02 Protocol
- Out: `common/protocol.py`, `common/constants.py`, `tests/test_protocol.py`.
- Do: every message of 4.5 as a dataclass, `encode(msg)->str`, `decode(str)->msg` with validation (unknown `t`, missing or wrong-type field = error). Constants from 4.3. Key map from 4.6.
- Done: pytest round-trips every message and rejects bad ones.

### K03 Fake Pi
- Out: `tools/fake_pi.py`, `tools/ws_smoke.py`.
- Do: WebSocket server on :8765 speaking 4.5. Watchdog 500 ms. Kinematics 0.25 m/s, pivot, producing s, x, y, yaw. Distances from a 30 m long, 2 m wide gallery (walls at y = -1 and +1 m, side distances computed from y and yaw, one optional 90 degree turn). Forward refused under 30 cm. Head 40 deg/s, LED, rod states (3 s moves), STOP latch. EVENTs kept in memory, replayed on SYNC. `ai="DUMMY"` with a fake ALERT_DEFECT every 20 s (generated JPG). HTTP `/alerts/*` and `/video.mjpg` (PC webcam 0, else a generated test pattern). Flags `--drop-link N`, `--no-imu`.
- Done: `ws_smoke.py` sends CONTROL and prints telemetry changing.

### K04 Hardware layer
- Out: `pi/controller/hw.py`, `tests/test_hw.py`.
- Do: class `HW`, `HW_MODE=mock|pi`. `motors(l,r)` (-1..1 to RPWM/LPWM), `motors_enable(bool)`, `pulse(sensor)->cm|None`, `encoder_counts()->(l,r)`, `led(bool)`, `servo(name,angle)` for pan|tilt|fold, `rssi()` (`iw dev wlan0 link`, mock -58), `imu_read()->(ax,ay,az,gx,gy,gz)` (smbus2, 0x68, mock = still), `cpu_temp()`, `cpu_load()`. Pi mode: gpiozero + lgpio, pins of 4.4. Mock mode records the last commands. On exit or exception: enable low, PWM 0.
- Spec: 4.4, 8.2. Done: mock tests, `motors_enable(False)` forces 0.

### K05 Sensors
- Out: `pi/controller/sensors.py`, `tests/test_sensors.py`.
- Do: 50 ms slots in the order F, L, F, R (one trigger at a time): front 10 Hz, sides 5 Hz. Median of last 3. No echo = `None`. Encoders: `distance_m = counts/20 x circumference x cal_factor`, signed from the commanded direction. `read()` returns `{fl,fc,fr,ds,left_m,right_m}`.
- Done: a spike is removed by the median; signed distance correct.

### K06 Drive
- Out: `pi/controller/drive.py`, `tests/test_drive.py`.
- Do: `mix(fwd,turn)->(l,r)`: forward = both equal, forward+turn = curve (inner track 40 % of outer), turn alone = pivot. Speed target 0.25 m/s mapped by `drive.pwm_at_speed`. 0.3 s ramp. `check_interlocks()` per table 5.4. STOP latch. Returns a refusal text for the dashboard.
- Done: one test per interlock row.

### K07 Head and rod
- Out: `pi/controller/head.py`, `pi/controller/rod.py`, tests.
- Do: head integrates 40 deg/s at 50 ms (2 deg/step), clamp 0-180, holds on release, HOME at 60 deg/s, ignored unless rod UPRIGHT. Rod FOLDED to LIFTING to UPRIGHT to FOLDING to FOLDED, 30 deg/s, 5 s timeout gives ALERT_ROD, accepted only when robot stopped, head goes to FOLD_POSE before folding.
- Spec: 5.2. Done: state transitions and timeout tested.

### K08 IMU and position
- Out: `pi/controller/imu.py`, `pi/controller/position.py`, `tests/test_position.py`.
- Do: algorithm 5.6 steps 1-8 as pure functions fed with samples (no threads inside). `Position.update(ds, gyro_z, dt)`.
- Done: pivot adds 0 distance. Synthetic L-shaped run ends within 1 % of the true end point. Snap (when enabled, default off) applies within 25 degrees and not outside. Standstill corrects the bias. Tilt and bump thresholds fire.

### K09 Controller
- Out: `pi/controller/main.py`, `ws_server.py`, `telemetry.py`, `events.py`, `tests/test_controller.py`.
- Do: asyncio 50 ms loop wiring K04-K08. States MANUAL, STOPPED, LINK_LOST. Watchdog 500 ms. TELEMETRY 10 Hz. EVENTs stored in SQLite `robot.db`, replayed on SYNC. Slab from `slabs.json`. HTTP static `/alerts/`. Internal endpoints (4.5) for the AI worker. Link loss sets the latch.
- Spec: 4.5, 5.1-5.7. Done: `HW_MODE=mock` run plus `ws_smoke.py`. Test: no heartbeat gives motors off within 0.5 s.

### K10 Video
- Out: `pi/video/mediamtx.yml`, `pi/video/pipeline.sh`, `pi/video/prune.sh`, `tools/check_video.sh`.
- Do: ONE ffmpeg: V4L2 MJPEG 1280x720 15 fps in, output 1 = libx264 ultrafast zerolatency 2.5 Mbps to `rtsp://127.0.0.1:8554/cam`, output 2 = 2 fps full-size JPEG to `/run/kashimo/frames/latest.jpg` with `-update 1 -atomic_writing 1` (so the AI never decodes H.264). MediaMTX: WebRTC (WHEP) on 8889, RTSP on 8554, recording in 60 s segments. `prune.sh` deletes oldest segments above `rec_cap_gb`. `--test-source` uses a test pattern.
- Done: `bash -n`, ffmpeg command runs with `--test-source` on a PC.

### K11 AI plug-in
- Out: `pi/ai/detectors/base.py`, `dummy.py`, `onnx_det.py`, `pi/ai/rules.py`, `pi/ai/worker.py`, `tools/make_dummy_onnx.py`, `tests/test_ai.py`.
- Do: section 6.4. Dummy score = frame brightness change (fake but changes). ONNX loader reads `model/config.json`. Worker: 1 frame per 0.5 s, queue of 1, 2 threads, nice 10, skip gates, 3-in-a-row, 5 s cooldown, saves frame + heatmap, posts ALERT_DEFECT to the controller. `ai` status is `DUMMY` when the dummy runs.
- Done: rules tested with the dummy. `onnx_det` loads the dummy ONNX file and returns `(score, heatmap)`.

### K12 PC server
- Out: `pc/server/app.py`, `photo.py`, `screenshot.py`, `csvlog.py`, `tests/test_server.py`.
- Do: FastAPI + uvicorn. Serves `pc/web/`. Browser WebSocket `/ws` relays CONTROL and CMD to the Pi and fans out TELEMETRY and EVENT. **The server never creates heartbeats: only the browser does.** Pi client with auto-reconnect, SYNC(since_id) after reconnect. RTT from `hb_seq` and loss % over 10 s added to the stream sent to the browser. `POST /api/photo` (newest RTSP frame), `POST /api/screenshot` (mss), file names and CSV per 5.7, downloads alert images into `runs/<date_time>/alerts/`.
- Done: with `fake_pi`, `curl` photo and screenshot make files and a CSV line.

### K13 Dashboard shell
- Out: `pc/web/index.html`, `css/tokens.css`, `css/layout.css`, `css/components.css`.
- Do: static layout of 7.4 following section 7. States through `data-state` attributes. `?demo=<state>` loads fixtures to review: connected, disconnected, link-about-to-cut, link-lost, latched, obstacle-red, tilt, imu-calibrating, ai-dummy, led-off, rod-moving.
- Done: no console error, no horizontal overflow at 1366x768, 1920x1080 and 390 px wide. Screenshot them if a browser exists, else `NOT RUN`.

### K14 Dashboard logic
- Out: `pc/web/js/keys.js`, `link.js`, `whep.js`, `app.js`.
- Do: key rules 4.6 and 5.4, 100 ms CONTROL, hold-R ring, one-shot commands, every on-screen button equal to its key, readouts and banners from the table 5.4, video by WHEP with `video.mode=mjpeg` fallback.
- Done: against `fake_pi`, keys move the values. The pure part of `keys.js` has a test page or a node test.

### K15 Map and log
- Out: `pc/web/js/map.js`, `log.js`.
- Do: top-down SVG map from x, y, yaw, gallery outline (`gallery.width_m`, default 2.0), slab ticks every 0.5 m (label every 5th), pins (photo blue, alert orange, obstacle red, bump grey), pin click opens the picture or line, path length, straight distance to the hole, badges. Log list latest first.
- Done: runs on the `fake_pi` path.

### K16 Pi tools
- Out: `tools/bench_detector.py`, `record_normal.py`, `calib_encoders.py`, `calib_imu.py`, `latency_test.py`.
- Do: `bench_detector` loads a model folder and runs 100 frames, prints ONE JSON line: ms average and p95, RSS MB, CPU %, temperature, `vcgencmd get_throttled`. `--with-video` also reports the stream fps. `record_normal` saves 2 fps frames plus `pan,tilt,led` CSV (data for Stage B). `calib_encoders` drives 5 m, asks the measured distance, writes `cal_factor`. `calib_imu` 10 min still, drift report. `latency_test` command round trip.
- Done: each runs in mock or says why not.

### K17 Deploy
- Out: `tools/verify.py`, `tools/deploy_check.sh`, `docs/MIGRATION.md` (40 lines max).
- Do: steps of 3.2. `verify.py` prints a PASS/FAIL table: services active, camera found, I2C 0x68, GPIO libraries, disk free over 20 %, `model/` valid (detector loads), ports, time sync, EEPROM `PSU_MAX_CURRENT`.
- Done: runs on a PC and marks the Pi-only checks `SKIP`.

---

## 2. THE PROJECT

**Goal.** After a fault on the ACTIA cable gallery, locate it without anyone entering. Today: 2+ technicians, about 2 h, crawling, no record. Target: one operator, about 0.5 h, a log with slab numbers, only the faulty slab is lifted.

**Site [FIXED v4.1].** One gallery 30+ m long, 2+ m wide, 1.5 m deep, possible 90 degree turns, random floor bumps, dry floor in the normal state. It is closed by concrete slabs **50 cm wide (along the gallery) and as long as the gallery is wide (2+ m)**, laid side by side: 60+ slabs per 30 m [CALC]. Under them: electrical cables, live up to 380 V (EMI). Faults to find: **cuts, burns, water ingress** (wet cable, standing water, LED reflections).

**Robot.** Small tracked robot, body 300 x 200 x 100 mm, under 3 kg, built from scratch (3D-printed), retractable handle inside the body [CHECK Q1]. The 50 cm slab hole is the size limit, not the gallery width. Hinged rod that folds flat, on it a 2-servo pan-tilt head carrying a USB camera and the white LED bar (they turn together). Raspberry Pi 5 4 GB is the only computer: it drives, streams video, records to SD and **runs the AI [NEW]**. Three ultrasonic sensors (front, left, right), two encoders, MPU6050. Battery. Wi-Fi to a router at the slab hole, PC wired to the router.

**Operation.** Manual, operator live at the PC. Nothing moves unless a key is held.

**Run**
1. **Setup.** Lift one slab (hole 0.5 m x the gallery width, 2+ m). Router at the hole, PC wired. Lower the robot by hand, rod folded. Nobody enters.
2. **Power on.** The Pi starts MediaMTX, the video pipeline, the controller and the AI worker. LED on, head at REST (90, 90), STOP latch off, rod assumed FOLDED, IMU calibrates 3 s (robot still on the floor).
3. **Dashboard** on the PC: live video (WebRTC about 0.2 s), obstacle distance, link strength, path map, state, alerts, on-screen keys.
4. **Rod.** Hold R for 1 s.
5. **Drive.** Z forward, S back, Q left, D right. Release = stop. A message every 100 ms is heartbeat plus held keys. No valid message for 500 ms = motors off. Front sensor refuses forward at 30 cm.
6. **Look.** Arrows aim camera + LED, H centres, L toggles LED.
7. **Evidence.** Enter = photo, P = screenshot, saved on the PC with slab and distance.
8. **AI (on the Pi) [NEW].** Looks at one frame every 0.5 s. A frame is scored only when LED is on, rod upright and still, head still. 3 flagged frames in a row give an alert (frame + heatmap + log line) pushed to the dashboard. The operator judges.
9. **Position and map.** Encoders = distance, gyro = turning. Along-axis distance divided by the 0.5 m slab width gives the slab number. Target plus or minus 2 slabs (1 m) [EST], goal plus or minus 1.
10. **Link lost [NEW].** Motors stop within 0.5 s, latch set. Recording **and the AI keep running**. Alerts are stored in `robot.db` and replayed to the PC when the link returns (SYNC). Operator presses Space to release.
11. **End.** Drive back, stop, hold R to fold, lift out. The report is the defect log, photos, screenshots.

**Time [CALC].** 30 m at 0.25 m/s = 2 min, 4 min round trip. 26 min left for aiming and photos in the 0.5 h target.

---

## 3. DEVELOPMENT WORKFLOW [NEW]

### 3.1 Now (16 GB card)
- Pi OS **Lite** 64-bit (Bookworm). Everything lives in one GitHub repo. The PC side and the GPIO code are built with `HW_MODE=mock` and `tools/fake_pi.py`, so no robot is needed to test.
- AI: the friend trains on his side. Until the real files arrive the dummy detector runs. Nothing else changes when they arrive (section 6.4).

### 3.2 Move to the 32 GB card
1. Back up the 16 GB card as an image (Win32DiskImager, or `dd`). Keep it.
2. Flash Pi OS Lite on the 32 GB card, enable SSH, set the fixed IP.
3. `git clone <repo> ~/kashimo && cd ~/kashimo && bash setup.sh`.
4. Copy the model folder: `scp -r model/ pi@<ip>:~/kashimo/model/` (the folder is not in Git).
5. `python tools/verify.py` must show all PASS.
Alternative: write the 16 GB image onto the 32 GB card (small to big works), then `raspi-config` and expand the filesystem.
Rule: nothing is configured by hand on the Pi. If it matters, it is in `setup.sh` or `config/config.yaml`.

### 3.3 Stack [PICK]
| Where | What |
|---|---|
| Pi OS | Raspberry Pi OS Lite 64-bit, Python 3.11, gpiozero + lgpio, smbus2, aiohttp or websockets, numpy, opencv-python-headless, onnxruntime |
| Video | USB camera, MJPEG in, one ffmpeg, MediaMTX (WebRTC out, RTSP, recording) |
| Pi to PC | WebSocket JSON, heartbeat 100 ms, watchdog 500 ms |
| Pi log | SQLite `robot.db` |
| PC | Python 3.11, FastAPI, uvicorn, websockets, opencv-python, mss |
| Dashboard | Plain HTML, CSS, JS. No framework, no build step, no CDN (works offline) |
| Tools | Git, pytest |

### 3.4 Pi 5 resource budget [NEW][EST, measure with K16]
| Resource | Fact | Consequence |
|---|---|---|
| CPU | 4 cores A76 2.4 GHz, no NPU, no usable GPU compute | AI runs on CPU, capped |
| Video | No hardware H.264 encoder: x264 uses 1-2 cores | AI gets 2 threads, low priority |
| RAM | 4 GB, about 2.5 GB free | AI process 1.5 GB or less. No swap on the SD card |
| Storage | SD card, slow random reads | Model loads once at start, runs from RAM |
| Heat | AI plus x264 throttles without cooling | Active cooler is mandatory |
| Power | AI adds about 2-3 W | Re-check runtime in T12 |
| Real-time | Motors use software PWM on the same CPU | Watchdog must never starve: AI is a separate low-priority process (S1 ESP32 removes the risk) |

Targets: AI 300 ms or less per frame, 1.5 GB or less, 2 cores or less, video stream stays at 15 fps (T2 with AI on).

---

## 4. CONTRACTS (frozen)

### 4.1 Repo tree
```
kashimo/
  common/      protocol.py  constants.py
  pi/
    controller/ main.py ws_server.py telemetry.py events.py hw.py sensors.py drive.py head.py rod.py imu.py position.py
    ai/         worker.py rules.py detectors/{base,dummy,onnx_det}.py
    video/      pipeline.sh mediamtx.yml prune.sh
  pc/
    server/     app.py photo.py screenshot.py csvlog.py
    web/        index.html css/{tokens,layout,components}.css js/{keys,link,whep,app,map,log}.js
  model/        (git-ignored) model.onnx bank.npy config.json model_card.md
  config/       config.yaml slabs.json
  tools/        fake_pi.py ws_smoke.py bench_detector.py record_normal.py calib_*.py latency_test.py verify.py check_video.sh make_dummy_onnx.py
  tests/  docs/  systemd/  runs/ (git-ignored)  setup.sh  requirements-{pi,pc}.txt  README.md
```

### 4.2 `config/config.yaml` keys
```
pi_ip, ws_port 8765, hw_mode mock|pi, video {mode webrtc|mjpeg, whep_url, rtsp_url, mjpeg_url, w 1280, h 720, fps 15, kbps 2500},
rec_cap_gb 8, drive {pwm_at_speed, inner_ratio 0.4, ramp_s 0.3},
odo {track_circumference_m, counts_per_rev 20, cal_factor 1.0},
imu {snap off, snap_window_deg 25, snap_straight_m 1.0},
ai {detector dummy|onnx, model_dir model, fps 2, threads 2, nice 10, roi [x,y,w,h], pose_gate_deg null, consecutive 3, cooldown_s 5},
gallery {width_m 2.0, length_m 30, slab_width_m 0.5},
slabs_file config/slabs.json
```

### 4.3 Constants
| Name | Value |
|---|---|
| OBSTACLE_CM | 30 |
| DRIVE_SPEED | 0.25 m/s |
| LOOP_S / TELEM_HZ | 0.05 / 10 |
| HEARTBEAT_S / WATCHDOG_S / WARN_S | 0.1 / 0.5 / 0.3 |
| HEAD_RATE / HOME_RATE | 40 / 60 deg/s |
| REST / FOLD_POSE | (90, 90) / measured on the prototype |
| ROD_RATE / ROD_TIMEOUT | 30 deg/s / 5 s |
| IMU_RATE / GYRO_CAL_S | 100 Hz / 3 s |
| SNAP_STRAIGHT / SNAP_WINDOW | 1.0 m (no turn above 3 deg/s) / 25 deg (snap is OFF by default, see 5.6) |
| TILT_WARN / TILT_ALERT | 25 / 35 deg |
| BUMP_G | 0.5 g above rest |
| STANDSTILL | gyro under 1 deg/s, accel within 0.03 g of 1 g, no encoder count for 1 s |
| ROD_HOLD_S | 1.0 (PC side) |
| Colours of front distance | green above 60, orange 30-60, red under 30; ">200", "--" no echo [EST] |
| Link bars | -60 dBm or better 4, -70 3, -80 2, worse 1 [EST]. Delay orange above 200 ms. Loss orange above 5 % |

### 4.4 Pin map (Pi 5, BCM) [CHECK]
| Function | GPIO |
|---|---|
| Servo pan / tilt (hardware PWM) | 12 / 13 |
| Servo rod fold | 19 [CHECK PWM on Pi 5, else software PWM] |
| Motor L fwd / rev (BTS7960 RPWM / LPWM) | 17 / 27 |
| Motor R fwd / rev | 22 / 23 |
| Motor enable (all R_EN, L_EN), 10 k pull-down | 24 |
| HC-SR04 left trig / echo | 5 / 6 |
| HC-SR04 front trig / echo | 16 / 20 |
| HC-SR04 right trig / echo | 21 / 26 |
| Encoder left / right | 4 / 25 |
| LED gate (MOSFET) | 18 |
| I2C SDA / SCL (MPU6050 0x68) | 2 / 3 |
Echo pins go through a divider (1 k series, 2 k to ground). Encoders on 3.3 V.

### 4.5 Messages
JSON over WebSocket `ws://<pi_ip>:8765/ws`. Every message: `{"t":TYPE,"seq":int,"ts":float,...}`.

**PC to Pi**
| t | Fields | When |
|---|---|---|
| CONTROL | `drive:{fwd:-1\|0\|1, turn:-1\|0\|1}`, `head:{pan:-1\|0\|1, tilt:-1\|0\|1}` | every 100 ms (this is the heartbeat) |
| CMD | `cmd: HEAD_HOME \| LED \| ROD \| STOP \| START` | one shot |
| SYNC | `since_id:int` | after (re)connect, Pi replays EVENTs with id above it |

**Pi to PC**
| t | Fields |
|---|---|
| TELEMETRY (10 Hz) | `state` (MANUAL\|STOPPED\|LINK_LOST), `latch`, `hb_seq`, `fc fl fr` (cm or null), `s x y yaw`, `slab`, `pan tilt`, `led`, `rod` (FOLDED\|LIFTING\|UPRIGHT\|FOLDING), `pitch roll`, `imu` (CALIBRATING\|OK\|UNCERTAIN\|LOST), `rssi_dbm`, `cpu_temp cpu_load`, `ai` (OFF\|DUMMY\|RUNNING\|PAUSED_LED\|PAUSED_MOTION\|NO_MODEL), `ai_ms`, `rec`, `refusal` (text or null) |
| EVENT | `id`, `kind` (ALERT_OBSTACLE\|ALERT_ROD\|ALERT_TILT\|BUMP\|ALERT_DEFECT\|LINK_LOST\|LINK_BACK), `s x y slab pan tilt`, `data` |

`ALERT_DEFECT.data` = `{score, frame:"/alerts/000012.jpg", heat:"/alerts/000012_heat.jpg", detector:"dummy|<name>"}`. Files are served by the Pi at `http://<pi_ip>:8765/alerts/...`.

**Internal (127.0.0.1 only, controller to AI worker)**
- `GET /internal/state` returns `{pan, tilt, led, rod, moving, head_moving, s, slab}`.
- `POST /internal/event` (AI posts an ALERT_DEFECT, the controller stores it and broadcasts it).
- `POST /internal/ai_status` (AI posts `{ai, ai_ms}`).

**Ports.** 8765 controller, 8889 WebRTC (WHEP `http://<pi_ip>:8889/cam/whep`), 8554 RTSP (`rtsp://<pi_ip>:8554/cam`), 8080 PC dashboard.

### 4.6 Keys (AZERTY labels, physical positions via `event.code`)
| Function | Key | `event.code` | Behaviour |
|---|---|---|---|
| Forward | Z | KeyW | hold, refused under 30 cm |
| Backward | S | KeyS | hold, blind |
| Left / Right | Q / D | KeyA / KeyD | hold, with Z = curve, alone = pivot |
| Head left-right / up-down | arrows | ArrowLeft/Right/Up/Down | hold = 40 deg/s, release = stays |
| Centre head | H | KeyH | one press |
| LED | L | KeyL | one press, toggles |
| Photo | Enter | Enter | one press |
| Screenshot | P | KeyP | one press |
| Rod up / fold | R | KeyR | hold 1 s, only when stopped |
| STOP / release | Space | Space | press = STOP (latched), again = release |
Rules: held-key set sent every 100 ms. All released or window blur = zero speed in the next message. Z+S and Q+D cancel. Auto-repeat ignored. Space, Enter and arrows must not scroll or click a focused button. Every key has an on-screen button of the same name, lit while pressed. Must work with the Arabic layout active (T13).

### 4.7 AI detector contract
```
class Detector:
    def load(self, model_dir: str) -> None
    def score(self, frame_bgr: np.ndarray) -> tuple[float, np.ndarray]   # score >= 0, heatmap float32 HxW in 0..1
    name: str
```
Input: BGR frame 1280x720. Cropping to `roi` and resizing is done inside `score` from `model/config.json`.
`model/config.json`: `{"name","input_size":[w,h],"mean":[..],"std":[..],"roi":[x,y,w,h],"threshold":float,"score_scale":float,"backbone","bank_file":"bank.npy"|null,"anomalib_version"}`. `model/model.onnx` must run on CPU with onnxruntime. `model/model_card.md`: data used, AUROC, F1, ms on the PC.

---

## 5. BEHAVIOUR SPEC

### 5.1 Controller (manual only in v1)
States: MANUAL, STOPPED (latch), LINK_LOST. Rod states in 4.5. Every 50 ms: read sensors, encoders, IMU, last CONTROL, commands.
1. **Init.** Enable low, head to REST at 30 deg/s, LED on, rod FOLDED (assumed: a hobby servo has no feedback), s = 0, latch off, IMU calibrating.
2. **Watchdog.** No valid CONTROL for 500 ms: enable low, state LINK_LOST, latch on, EVENT LINK_LOST. When it returns: EVENT LINK_BACK, the operator presses Space.
3. **Drive.** Held keys mixed into track speeds (K06). Obstacle under 30 cm in front: forward refused, EVENT ALERT_OBSTACLE once per approach.
4. **Head.** Held keys move pan and tilt (K07). HOME = REST at 60 deg/s. The LED is on the head so it follows.
5. **LED.** Toggles GPIO 18.
6. **Rod.** FOLDED to LIFTING (fold servo up, head to REST) to UPRIGHT. UPRIGHT to FOLDING (head to FOLD_POSE, servo down) to FOLDED. Accepted only when stopped. 5 s timeout stops the servo and sends ALERT_ROD.
7. **STOP / START.** Space sets / releases the latch. Head, LED, photo and screenshot work while latched.

### 5.2 Optional, NOT in v1
AUTO-STEP (drive 1.0 m, stop, 25-position scan, serpentine, 41 s per cycle) and obstacle WAITING_FOR_GUIDANCE. No key, mouse button only. Not a task.

### 5.3 Slab log
- `slabs.json`: `{slab_width_m 0.5, origin_m, overrides}`. Slab number = floor((a - origin_m) / slab_width_m) + 1, along-axis distance a = x (yaw 0 = along the gallery). x is robust to heading drift (error enters as cos), y is not.
- CSV columns: `timestamp, slab_no, distance_m, x_m, y_m, pan, tilt, score, class, frame_file, heatmap_file, delayed`. One slab = 0.5 m. Expect plus or minus 2 slabs (1 m) from the position estimate [EST]. The operator can confirm by counting slab joints on the ceiling (S8).
- Photo file name: `photo_0001_slab07_d12.4m_p090_t090.jpg` in `runs/<date_time>/photos/`, plus a line in `photos.csv`. Screenshot: `shot_0001_HHMMSS.png`.
- Recording: SD, 60 s segments, capped by `rec_cap_gb`. With AI on the Pi there is no "delayed" re-analysis unless the AI was off; keep the `delayed` column.

### 5.4 Interlocks and banners (dashboard and Pi must agree)
| Situation | Result |
|---|---|
| Front under 30 cm | Z refused, red banner. S, Q, D work |
| No message 300 ms | Orange "link about to cut" |
| No message 500 ms | Motors off, latch on, red "LINK LOST", Space after return |
| Latch on | Drive refused. Head, LED, photo, screenshot work |
| R while moving | Refused: "stop first" |
| Rod moving or folded | Drive refused while moving. Head keys ignored. Photo works |
| LED off | Badge "LED OFF: image dark, AI paused" |
| Tilt above 25 / 35 deg | Orange TILT / red banner and ALERT_TILT |
| IMU calibrating or lost | Drive refused while calibrating. Lost: map stops turning, red "IMU LOST" |
| AI `DUMMY` | Badge "AI: TEST DETECTOR, scores are not real" |
| AI `NO_MODEL` | Badge "AI: no model loaded" |
| Pi disconnected | Whole panel greyed, last values marked stale, controls disabled |

**Obstacle readout.** Big number = front sensor only (median of 3, 10 Hz). Left and right are small: distance to each wall (about 1 m if centred in a 2 m gallery), shown for lateral position, not for collision.

### 5.5 Link strength
Three values: dBm from the Pi (`iw dev wlan0 link`), delay in ms (PC measures the round trip of `hb_seq`), loss % (gaps in TELEMETRY over the last 10 s). Thresholds in 4.3, set from T4 and T15.

### 5.6 Position and path map
| Part | Job | Limit |
|---|---|---|
| Encoders x2 | path length s | tracks slip a little |
| Gyro | heading | drifts, corrected |
| Accelerometer | standstill, tilt, bumps | NOT position: 5 mg error gives about 88 m after 60 s [CALC] |

1. Boot, robot still: average gyro z for 3 s = bias. Drive refused. If it moves, restart the 3 s.
2. Every 10 ms: `yaw += (gz - bias) x dt`. Yaw 0 = direction when lowered [CHECK Q13].
3. Every 50 ms: `ds` = mean of both tracks, signed by commanded direction, x cal_factor. `x += ds cos(yaw)`, `y += ds sin(yaw)`, `s += ds`. A pivot gives ds = 0.
4. Standstill: pull the bias slowly toward the gyro reading.
5. **Heading snap** (switch, default OFF [v4.1]): after 1.0 m driven with no turn above 3 deg/s, set yaw to the nearest multiple of 90 degrees if within 25 degrees [EST]. A 2 m wide gallery does not force the robot parallel to a wall, so a straight run does not prove yaw = 0: enable only if the operator keeps to one wall. Optional later (S15): wall-parallel correction from a side sensor, yaw error = atan(change in wall distance / distance driven) [EST]. While no correction is applied the badge "heading uncertain" shows.
6. Tilt from gravity, low-pass. Bump = 0.5 g above rest, EVENT BUMP with s, x, y.
7. Telemetry carries x, y, yaw, s, pitch, roll, imu.
Accuracy [EST]: along-axis x about 1 m over 30 m (heading error enters as cos, so it is small). Lateral y drifts with the gyro: 5 degrees/min over the 2 min drive = about 10 degrees, so y can be off by up to about 5 m at 30 m [CALC] and the map can show the robot outside the walls. Treat y as a sketch (S15 fixes it with the side sensors). x and the slab number matter.

### 5.7 Coverage and faults [NEW][CHECK Q4]
- The gallery is 2+ m wide. Walls do not guide the robot, and cables may lie anywhere across the floor or along the walls. The operator picks the line: centre with the head scanning both sides, or along a wall. Every photo and alert logs x and y.
- Cut and burn: damaged insulation, discolouration, exposed conductor. Water ingress: wet cable, standing water, damp patch, LED reflection. Water also changes the whole image (reflections, wet-looking floor), so expect AI false alarms and test them (T24).
- The robot must survive a wet floor (8.5).

---

## 6. AI (on the Pi 5) [NEW]

### 6.1 Task and method
- Flag normal or defect with a heatmap. Faults to find: cuts, burns, water ingress. Class names only if ACTIA confirms them later. Water changes the whole image (reflections, wet floor): see Stage C and T24.
- Method: **PatchCore** (Roth et al., CVPR 2022): stores patches of normal images, flags patches unlike any stored one. No defect labels needed. Known weak point: false alarms (0.55 false-positive rate in the cable benchmark of the AI sheet). Counter: fixed light, ROI crop, threshold from a normal run, 3-in-a-row, cooldown.
- Training is NOT done on the Pi. The friend fits the model on a PC, exports it, and the Pi only runs it.

### 6.2 Models to compare (benchmark on the Pi with K16, then pick one)
| # | Model | Why |
|---|---|---|
| 1 | PatchCore, ResNet18 (layer2+3), coreset 1-10 % | Same method as the AI team, about 4x lighter than WideResNet50 [EST] |
| 2 | EfficientAD-S (Batzner et al., WACV 2024) | Built for low latency. Fallback if 1 is too slow |
| 3 | PatchCore, WideResNet50 | Reference only. Expect about 2-4 fps on the Pi [EST] |
Runtime: ONNX Runtime on CPU, backbone INT8 if accuracy holds, bank float16, nearest-neighbour by numpy or faiss-cpu. Optional upgrade if all fail: Hailo-8L AI Kit (outside budget).
Acceptance on the **Pi** (K16 numbers, not PC numbers): 300 ms or less per frame, 1.5 GB or less RAM, 2 cores, video stays 15 fps.

### 6.3 Data and stages
| Stage | Data | Goal |
|---|---|---|
| A | MVTec AD "cable" (224 normal, 58 normal + 92 defect test), then CableInspect-AD (4,798 images, 7 defect types). Both CC BY-NC-SA, fine for the challenge | Build the pipeline, pick the model, report AUROC, F1, false positives. Looks nothing like the gallery |
| B | Own normal footage from the mock gallery with the real camera, LED, rod, pan-tilt (use `tools/record_normal.py`) | **Final memory bank.** A model fitted only on internet pixels calls the whole gallery abnormal |
| C | Staged defects on a mock cable in the mock gallery: cut, burn mark, **water spray and a puddle** | Threshold (99th percentile of a held-out normal run), final metrics |
If ACTIA gives real normal photos, they replace Stage B. If a YOLO-format cable-defect dataset appears: YOLO nano with NCNN, about 67-94 ms per image on the Pi 5 (vendor numbers, CPU only) [CHECK].

### 6.4 Plug-in design (this is how the AI "arrives later")
1. Everything around the model is real from day one: frame grab, skip gates, 3-in-a-row, cooldown, alert files, dashboard badge, SQLite event, SYNC replay.
2. `config.yaml: ai.detector = dummy` runs `dummy.py` (fake score from frame brightness, dashboard shows "TEST DETECTOR").
3. When the friend's files arrive: copy them into `model/`, set `ai.detector: onnx`, restart the AI service. **No code change.**
4. If `model/` is missing or invalid, the worker reports `NO_MODEL` and does not alert. It never falls back silently to the dummy.
5. Worker loop:
   - Read `/run/kashimo/frames/latest.jpg` every 0.5 s. Queue of 1: a late frame is dropped, never queued.
   - `GET /internal/state`. **Skip** (status `PAUSED_LED` / `PAUSED_MOTION`) when LED off, rod not UPRIGHT, rod moving, or head moving, or for 0.4 s after any movement (T_SETTLE).
   - If `pose_gate_deg` is set: score only when pan and tilt are within that many degrees of a fitted pose (the bank was fitted on 25 poses) [CHECK].
   - `score()`. Alert when score > threshold for `consecutive` frames, then `cooldown_s`.
   - Save the frame and the heatmap, POST ALERT_DEFECT, POST ai_status with `ai_ms`.
6. Process: `nice 10`, 2 threads (`OMP_NUM_THREADS=2`, onnxruntime intra-op 2).

### 6.5 Friend's tasks (not Claude tasks)
| ID | Task | Deliverable |
|---|---|---|
| F1 | Stage A: fit candidates 1-3 on MVTec cable, report AUROC, F1, ms on his PC CPU | one table |
| F2 | Export each to ONNX, run with `onnxruntime` on CPU, compare scores with the original model | max absolute difference |
| F3 | Package one `model/` folder per candidate following 4.7 | folders + `model_card.md` |
| F4 | Edris runs `tools/bench_detector.py` on the Pi for each folder | JSON lines, pick one |
| F5 | Stage B refit on mock-gallery footage, then Stage C threshold and metrics | final `model/` |
Git: the friend works on a branch of the same repo (code only). Model files go to Edris by file transfer, not through Git.

### 6.6 Metrics [TEAM TARGET]
Recall, precision, F1, AUROC, false alarms per 30 m run, ms per frame **on the Pi**, slab error.

---

## 7. DASHBOARD DESIGN [NEW] (K13, K14, K15)

### 7.1 Interface choice: web page, not an app [PICK]
| Option | Video | Keys | Effort | Verdict |
|---|---|---|---|---|
| **Web page** served by the PC Python server (plain HTML, CSS, JS) | WebRTC built into the browser, about 0.2 s | `event.code` gives physical keys, works with any layout | Lowest. Nothing to install, same on Windows or Linux, edited and tested by Git | **Chosen** |
| Desktop app (PyQt, Electron, Tauri) | RTSP via OpenCV or GStreamer, 0.5-1 s, or an embedded web view (= the same page in a wrapper) | Fine | Packaging, an .exe, more code per task | No |
| OpenCV or pygame window | OK | OK | Fast to code, cannot be made a clean professional UI | No |
Weak points of the web page: needs window focus, and the tab can be closed. Safe either way (watchdog stops the robot). For an app feel without an app: launch `chrome --app=http://localhost:8080` (or Edge), no code change.
No framework, no build step, no CDN, no web fonts from the internet: the PC may be offline at the gallery.

### 7.2 Product identity
Robotics operations console. The video is the main thing. Information is dense, precise and readable at a glance, on a 13-inch AZERTY laptop, possibly in daylight. It is **not** a SaaS analytics dashboard and not a marketing page. Name: the text "KASHIMO" in the header, no logo.

### 7.3 Tokens (`css/tokens.css`) [CHECK contrast with a tool]
| Token | Value |
|---|---|
| `--bg` / `--surface` / `--surface-2` / `--border` | #121518 / #1A1E22 / #22272C / #323840 |
| `--text` / `--text-2` | #E8EBEE / #A3ADB7 |
| `--accent` (focus, selection) | #4FA3E0 |
| `--ok` / `--warn` / `--err` | #46C28B / #E9A93B / #F2594C |
| Font | `system-ui, "Segoe UI", sans-serif`. Numbers: `ui-monospace, "Cascadia Mono", Consolas, monospace` with `tabular-nums` |
| Sizes | 12 labels (caps, spaced) / 14 body / 16 values / 20 titles / 48 big distance |
| Spacing | 4, 8, 12, 16, 24 only |
| Radius | 2 px panels, 4 px buttons and inputs. No pills |
| Elevation | none: 1 px borders and dividers, no shadows, no gradients, no blur |
| Icons | none, except one inline-SVG set with 1.5 px strokes if a control needs it. No emoji |
| Motion | 120 ms colour transitions on state change. The R-hold ring is functional. `prefers-reduced-motion` disables the rest |
Status is never colour only: always a text label and a shape (`● OK`, `▲ WARN`, `■ FAULT`).

### 7.4 Layout (one page, no scrolling at 1366x768)
```
+------------------------------------------------------------------+
| KASHIMO   STATE: MANUAL   LED: ON   ROD: UPRIGHT   AI: ...  [STOP]|
+--------------------------------------------+---------------------+
|                                            | OBSTACLE AHEAD      |
|                                            |  87 cm   L 11  R 12 |
|                 LIVE VIDEO                 | LINK ||||. -58 dBm  |
|                                            |      35 ms   0 %    |
|                                            | Pan 90 Tilt 90      |
|                                            | Slab 07  12.4 m     |
|                                            | Pitch 2  Roll 0     |
|                                            | MAP (top view)      |
+--------------------------------------------+---------------------+
| ALERTS / LOG (latest first)                | [Photo] [Screenshot]|
+------------------------------------------------------------------+
| ZQSD drive | arrows head | H centre | L led | R rod | Space stop |
+------------------------------------------------------------------+
```
Right column = rows separated by 1 px rules, NOT a stack of cards. Tablet and phone: video on top, readouts below, key bar hidden (touch buttons stay).

### 7.5 Design rules (mandatory for the AI doing K13-K15)
You act as a senior product designer and frontend engineer. The interface must look like a skilled human designed it for this product, not like a generic AI-generated site.
1. **Understand first.** Product = live robot control. Priorities: product identity, usability, hierarchy, consistency, craft, accessibility, responsiveness. A pretty UI that is hard to use fails. A usable UI that looks like a template also fails.
2. **No AI slop** unless the product needs it: purple-blue gradients, glassmorphism, glowing borders, floating blobs, 3D illustrations, rounded cards everywhere, identical repeated cards, oversized hero headings, big empty space, pill buttons, decorative badges, shadows on everything, decorative icons, gratuitous animation, fake stats, fake testimonials, empty marketing copy. Do not swap one fashionable look for another.
3. **Design system first.** Use only the tokens of 7.3. No one-off values. One font family plus the mono for numbers. Consistent radius, spacing, icon style.
4. **Real layout.** Table for records, list for sequences, cards only for real grouping. Do not put everything in a card. The control panel must not look like an analytics dashboard.
5. **Hierarchy.** The user sees at once: where they are, the video, the obstacle distance, whether the link is alive, what they can press. Strong colour only for warnings, errors and the focus ring.
6. **Everything works.** No decorative control. Every button, key, banner and toggle has an action, a visible response, a result and an error response. No success message unless it really succeeded (a photo is "saved" only after the server confirms the file).
7. **All states.** Initial, loading, connected, disconnected, stale values, running, latched, warning, critical, disabled, hover, focus, active, empty log. Show real values apart from test values: the dummy AI and `?demo=` data must be labelled and never look live.
8. **Real content.** Domain words (slab, path length, latch, heading, link). No lorem ipsum, no invented numbers. Short natural labels. Sample data is labelled "sample".
9. **Responsive.** Laptop first. Check 1366x768, 1920x1080, tablet, 390 px. No horizontal overflow, clipped text, overlap or unreachable control. Adapt the layout, do not just shrink it.
10. **Accessible (WCAG 2.2 AA).** 4.5:1 text contrast, 3:1 large text. Status not by colour alone. Visible focus. Semantic elements, labelled controls, full keyboard operation, touch targets of 40 px or more on touch buttons. Reduced motion respected.
11. **Motion has a purpose:** state change, feedback, loading. Nothing floats, bounces or delays an action.
12. **Finish.** Aligned baselines, fixed control heights, text truncation with a tooltip, consistent terms, useful empty states, scroll only inside the log.

**Process:** (1) audit what exists, (2) apply the tokens, (3) implement with reusable CSS classes, no new dependency, (4) QA: every control, every state in `?demo=`, every width, keyboard only, console errors, (5) anti-slop review. Answer these 10 questions before finishing, fix any "no": could this belong to any other app? Does it look like a robot console? Any needless gradient, shadow, card or decoration? Is the hierarchy obvious in 2 seconds? Density right? Built for the real workflow? Does everything work? All states covered? Coherent at every width? Does it look designed, not generated?

---

## 8. HARDWARE REFERENCE

### 8.1 Mechanical [CHECK Q1]
| Item | Value |
|---|---|
| Gallery / hole | 30+ m x 2+ m x 1.5 m deep / one lifted slab = 0.5 m x gallery width (2+ m) |
| Robot | body 300 x 200 x 100 mm, under 3 kg, camera about 0.40 m above floor with the rod up. Must pass the 0.5 m hole with margin (lower it flat or on its side) [CHECK Q1] |
| Pivot | free in a 2 m wide gallery (the 50 cm corridor limit of v3 is gone). The limit is the 0.5 m hole: test with a cardboard dummy first |
| Chassis | built from scratch, 3D-printed PETG, tracks (kit or printed). Sealed electronics box (8.5). Foil lining on the motor compartment, grounded at one point, Pi Wi-Fi corner outside it. Retractable handle inside the body |
| Rod | rigid aluminium 8 mm, about 25 cm, hinged at the base, one 10 kg-cm metal-gear servo, stop blocks at both ends, 90 degrees at 30 deg/s. Torque 3 kg-cm needed [CALC][EST], 3x margin |
| Head | 2 micro servos (MG90S) pan-tilt bracket, camera + LED bar fixed on it, 100 g or less together, slack loops for cables |
| Handling | two low handles over the centre of gravity [CHECK a person can place it by hand at 1.5 m deep] |

### 8.2 Electrical
```
3S LiPo (9.9-12.6 V) - XT60 - fuse 15 A - switch -+- BTS7960 L - motor L
 (low-voltage alarm on balance lead)              +- BTS7960 R - motor R
                                                  +- LED bar via MOSFET (12 V, up the rod)
                                                  +- Buck A 5.1 V >=5 A - Pi 5, BTS logic, HC-SR04 x3
                                                  +- Buck B 5-6 V 5 A - servos only (+1000 uF)
```
- Star ground at the battery minus. Two bucks so servo and motor noise cannot reset the Pi.
- Pi 5 on a non-PD supply: set `PSU_MAX_CURRENT=5000` in the EEPROM [CHECK]. Libraries: gpiozero + lgpio (RPi.GPIO and pigpio do not work on Pi 5).
- Safe state in hardware: all R_EN and L_EN tied to GPIO 24 with a 10 k pull-down. Pi crashed or booting = motors off.
- 100 nF across each motor, ferrite on each motor pair, twisted motor wires, away from camera and signal. 16 AWG power, 22-24 AWG logic.
- MPU6050 on 3.3 V I2C, screwed flat to the chassis plate near the centre, away from motors and 12 V wires, NOT on the rod. Axes marked, z up. No magnetometer (380 V cables and rebar).
- Camera on a USB 2.0 port (USB 3 noise hurts 2.4 GHz Wi-Fi) [CHECK].
- Runtime [CALC][EST]: about 43 W, 44 Wh pack x 80 % = 35 Wh, about 49 min (4000 mAh) or 61 min (5000 mAh). Add 2-3 W for the AI. Measure in T12.
- Wi-Fi: router at the hole, antennas into the gallery, PC wired, Pi fixed IP with auto-reconnect, band chosen by T4. If T4 fails, USB Wi-Fi adapter with external antenna (25-40 TND).

### 8.3 Parts and budget (TND, with VAT)
**Owned and used:** Pi 5 4 GB 507.00, USB camera 8MP 26.00, HC-SR04 x3 14.40 (invoice 2B Trading 2026-05083, 21/10/2026). Owned, not on the robot: PSU, 2 spare cameras, 1 spare HC-SR04, jumpers.
**Bought from the Hardware sheet (234-242):** 2 motors 37GB-550 12 V 96, 2 BTS7960 40-48, 2 encoders HC-020K 28, SD card 38, LED bar 32. **SD card is now 32 GB** (was 128 GB; enough, see 5.3).
**Missing parts [EST] (409-700):** chassis 0 (3D-printed, filament from the same source), 3S LiPo 60-90, charger 60-90 (skip if owned), LiPo alarm 5-8, Buck A 18-35, Buck B 10-18, 2 MG90S 24-30, pan-tilt bracket 8-15, rod 5-10, router 60-120 (borrow), Ethernet 5, Pi cooler 12-20, fuse + switch 8-15, connectors 8-12, passives 5-8, MOSFET 3-5, ferrites 6-10, perfboard 8-12, enclosure 15-30, hardware 10-15, fold servo 15-30, hinge 5-10, MPU6050 9-12.
**Totals [CALC]:** owned items free = 593-842. Charger and router borrowed = 473-632, **fits 750**. Owned items counted = 1,140-1,389, impossible. Q2 decides. Motors and encoders are being re-chosen for the lighter body (S4), so these totals are provisional.

### 8.4 Sensors
Front HC-SR04: stops forward at 30 cm, big dashboard number. Left, right: distance to each wall (about 1 m if centred), small numbers, lateral position. HC-020K x2: distance for the map. MPU6050: heading, standstill, tilt, bumps. **No rear sensor:** reverse is blind, go slowly (S12).

### 8.5 Water and electrical safety [NEW][CHECK with ACTIA]
- Water can be present when a cable is faulty. Electronics box sealed to about IP54 [EST] (gasket, cable glands), camera and LED behind a window, connectors above the floor, body clearance above 2 cm of water [EST].
- Ultrasonic sensors read a water surface as a floor: the front distance can be wrong over standing water. Treat readings over water as unreliable (T24).
- Live cables up to 380 V plus water plus a conductive chassis is a shock risk for the person lifting the robot out. Ask ACTIA whether the line is de-energised during the inspection (Q15). If not: plastic chassis and handle, no exposed metal, nobody touches the robot until it is dry. I am not a safety engineer: ACTIA safety must confirm.

---

## 9. TESTS (mock gallery 2 m wide, 30 m, slabs marked every 0.5 m, turns and bumps)
| ID | What | Target |
|---|---|---|
| T1 | AI ms per frame **on the Pi**, with video and controller running (K16) | 300 ms or less, 1.5 GB or less |
| T2 | Video delay, WebRTC and RTSP, clock on screen, 30 samples, **AI on** | WebRTC 0.5 s or less, stream 15 fps |
| T3 | Command round trip and watchdog stop time | 0.2 s or less, stop within 0.5 s |
| T4 | Packet loss and signal at 30 m with turns, 2.4 vs 5 GHz | loss under 1 % |
| T5 | Slab error: 10 objects at marked slabs (0.5 m), 5 m calibration run | within plus or minus 2 slabs, goal 1 [EST] |
| T6 | Cut the link mid-run: recording complete, AI alerts replayed after SYNC | 0 frames and 0 alerts lost |
| T7 | Full run time | 0.5 h or less |
| T8 | Camera sharpness at 20-40 cm, light on | cable details readable |
| T9 | Rod vibration blur after a move, T_SETTLE 0.4 / 0.6 / 0.8 s | sharp frame |
| T10 | Turn in place, cross the 2 m width and drive back straight, boards 2 m apart | heading holds, no jam |
| T11 | Lowering the 300 x 200 x 100 mm body through a 50 cm opening by hand | fits with margin |
| T12 | Battery runtime at full load **with AI** | 40 min or more |
| T13 | Every key on the real AZERTY laptop, also Arabic layout, no numpad | 12 functions work |
| T14 | Obstacle readout at 10, 30, 60, 100, 200 cm vs ruler, colours, stop at 30 | within 2 cm [EST] |
| T15 | Link bars: dBm, delay, loss at 5, 10, 20, 30 m and after turns | bars drop before the 500 ms cut |
| T16 | Rod: 50 fold and lift cycles, hold on bumps, time | no slip, no stall, under 5 s |
| T17 | Photo and screenshot, 20 each, names, CSV line | saved within 1 s |
| T18 | Key to motion delay, Space to motors off | 0.2 s or less |
| T19 | Path map on L and U courses, 30 m, snap on and off, vs tape | end within 1 m, turns within 5 degrees [EST] |
| T20 | IMU drift: still 10 min, 5 reboots, motors on | under 5 deg/min after calibration [EST] |
| T21 | Ramps 10, 20, 30 degrees vs protractor, a known bump 10 times | tilt within 3 degrees, bump 9 of 10 [EST] |
| T22 | CPU temperature and throttling over a 30 min run with AI [NEW] | no throttling (`vcgencmd get_throttled` = 0x0) |
| T23 | Watchdog under AI load: AI at 100 % on 2 cores, link cut [NEW] | motors off within 0.5 s |
| T24 | Water: 1-2 cm of water and a wet cable on the mock gallery: traction, sealing, front sensor, lens droplets, AI scores [NEW] | no leak, not stuck, AI behaviour recorded |
| T25 | Coverage: from the centre line, does the head see both walls and the floor at readable detail (T8 sharpness) [NEW] | decides the driving line (5.7) |

---

## 10. QUESTIONS
1. **Body:** this file now uses 300 x 200 x 100 mm, under 3 kg, built from scratch. Motors with built-in encoders are not chosen yet: send the model and I update 4.4, 8.2 and 8.3.
2. Does the Pi 5 (507 TND) count against the 750 TND? If yes the budget cannot be met.
3. Where is the hole: end or middle of the gallery? Dead end? Any turns, how many?
4. Where exactly are the cables across the 2 m width (floor, walls, trays, trench)? Fixes the driving line, rod height and camera angles (5.7).
5. Are all slabs exactly 0.5 m wide? Thickness and weight? (`slabs.json` assumes a uniform 0.5 m.)
6. Exact USB camera model: UVC, MJPEG 720p, focus type, lens angle?
7. Is the LED bar strobe-only? If yes buy a plain 12 V white strip.
8. Tracks: kit or printed? Track width and sprocket size for the 300 x 200 mm body?
9. LiPo charger and router to borrow?
10. Laptop and OS running the dashboard (screenshot tool, keyboard layout)?
11. Rod folds forward or backward, allowed folded height?
12. All turns exactly 90 degrees? The heading snap assumes it.
13. Robot faces along the first straight part when lowered?
14. Which model does the friend's F1 table pick, and on which PC specs?
15. Is the line de-energised during the inspection? Is the floor ever wet, how deep when water gets in?

## 11. SUGGESTIONS (not applied)
| # | Idea | Why |
|---|---|---|
| S1 | ESP32-S3 (owned) as motor, servo, encoder coprocessor over USB serial | Real-time PWM, survives a Pi or AI overload. Check poster R4 |
| S2 | BH1750 beside the camera | Log light level (PatchCore needs constant light) |
| S3 | ACS712 + ADS1115 current sensing | Stuck detection |
| S4 | Motors with built-in Hall encoders | No disc on a track sprocket |
| S5 | Lowering strap and light tether | Safer at 1.5 m, recover a stuck robot |
| S6 | INA219 battery monitor with automatic stop | Protects the LiPo |
| S7 | Log temperature and smoke (DHT11, MQ-2) | Impact report |
| S8 | Count slab joints on the ceiling (0.5 m apart) with the head tilted up | Confirms the slab number by eye, corrects the position |
| S10 | Mock gallery from boards at 50 cm, dummy first | Validates size before buying |
| S11 | PatchCore flags, YOLO names the defect | If labels are found |
| S12 | Spare HC-SR04 at the back | Reverse is blind |
| S13 | Beep when front distance drops under 30 cm | Operator watches the video, not the number |
| S14 | USB SSD or high-endurance SD for recording | Less SD wear [NEW] |
| S15 | Use left + right ultrasonic distances as lateral position y and as a wall-parallel heading check | Gyro y can drift about 5 m by 30 m [CALC], the walls are only about 1 m away [NEW] |
