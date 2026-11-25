# User manual (operator)

**Status: draft.** The robot is not built and the controller is not written. Sections marked [PC NOW] work today with the fake Pi. Sections marked [ROBOT LATER] describe the intended operation and have not been run on hardware.

## 1. Safety first
- Cables in the gallery are live up to 380 V and water can be present. Do not touch the robot while it is wet or inside the gallery. Ask ACTIA safety whether the line is de-energised before any inspection ([design.md](design.md) 8.5).
- Nobody enters the gallery during the search.
- Hold-to-move: releasing all keys stops the robot. Space is the emergency stop.

## 2. Start the dashboard on a PC [PC NOW]
1. Install Python 3.11+, then in the repo folder: `pip install -r requirements-pc.txt`.
2. No robot: terminal 1 `python tools/fake_pi.py --no-webcam`, terminal 2 `python -m pc.server.app --video mjpeg`.
3. Open http://127.0.0.1:8080. Press Ctrl+F5 after an update.
4. Look at example states with `?demo=<state>` (for example `?demo=disconnected`). Demo values are not live data.

## 3. Set up at the gallery [ROBOT LATER]
1. Lift one slab (opening 0.5 m by the gallery width). Place the router at the opening, connect the PC by cable.
2. Lower the robot by hand, rod folded, facing along the gallery.
3. Power on. Wait for the IMU calibration (3 s, robot still). Dashboard shows Connected.

## 4. Keys (physical positions, work on AZERTY and Arabic layouts)
| Action | Key | Behaviour |
|---|---|---|
| Forward / back | Z / S | Hold. Forward refused under 30 cm |
| Left / right | Q / D | Hold. Alone = pivot, with Z = curve |
| Head | Arrow keys | Hold to move, release to stay |
| Centre head | H | |
| LED on/off | L | |
| Photo | Enter | Saved on the PC |
| Screenshot | P | Saved on the PC |
| Rod up / fold | R | Hold 1 s, only when stopped |
| Stop / release | Space | First press stops (latch), second releases |
Every key also has an on-screen button.

## 5. Reading the screen
| You see | Meaning | Do |
|---|---|---|
| Red "LINK LOST" | No message for 500 ms, motors off | Wait for the link, press Space to release |
| Orange "link about to cut" | No message for 300 ms | Stop moving |
| "Front under 30 cm" | Forward refused | Reverse or turn |
| "LED OFF: image dark, AI paused" | LED off | Press L |
| "AI: TEST DETECTOR" | Dummy AI, scores are not real | Do not trust alerts |
| "AI: no model loaded" | No model file | Copy `model/` to the Pi |
| Whole panel grey, values struck through | Pi disconnected, values are old | Check Wi-Fi, power |
| `--` with no strike-through | No data received yet | Wait |

## 6. Run procedure [ROBOT LATER]
Rod up (R), drive with Z/S/Q/D, aim the head, photograph suspect spots (Enter). An AI alert (3 flagged frames in a row) shows frame and heatmap: you decide. At the end drive back, fold the rod (R), lift the robot out. The report is the defect log, photos and screenshots.

## 7. Troubleshooting
| Problem | Check |
|---|---|
| Page shows struck-through dashes | Server and fake Pi must run from the same repo folder. Ctrl+F5 |
| No video | Start the server with `--video mjpeg` for the fake Pi. On the Pi: `tools/check_video.sh` |
| Keys do nothing | Click the page once. Check the Pi is Connected and the latch is off |
