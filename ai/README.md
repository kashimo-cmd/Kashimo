# AI

**Status: plug-in structure only. The trained model is not integrated and no AI metric is verified.**

## How it fits
- Runtime code: `pi/ai/` (detector interface, dummy, ONNX loader, rules, worker). Stubs today (K11).
- Contract: [design.md](../docs/design.md) 4.7 and 6.4. `config.yaml` selects `dummy` or `onnx`. The dummy's scores are test data and the dashboard says so.
- Model files go in `model/` on the Pi, copied with `scp`. They are **not in Git** (`.gitignore` blocks `model/`, `*.onnx`, `*.npy`, `*.pt`).

## Team's model (from the project conversations, not verified here)
- YOLO11n, 9 classes, input 416, output `[1, 13, 3549]`, about 33 ms per image on a PC (reported by the trainer).
- Recall on real photos was low (corrosion 0.625, water 0.75, others 0.25 or lower). Not ready to trust alerts.
- Needs an adapter `onnx_yolo.py` to the Detector contract (cut, burn, water only). Out-of-scope classes would raise false alerts.
- Keep the same 9 classes, order, 416 input and output shape for every new version.

## What belongs in this folder
| File | Purpose |
|---|---|
| `DATA_COLLECTION.md` | Rules for photographing staged defects (the Data Collection Guide) |
| `MODEL_CARD.md` | Version, data, classes, metrics, date, who trained it |
| `eval/` | Holdout and false-alarm results per model version (small CSV or Markdown) |
Add them when they exist. Do not commit datasets or weights.

## Rules
- Distinguish implemented from planned. Do not claim a detection rate without an `eval/` file.
- Staged defects on dead cables only. Never collect data near live power.
- Collect data with the final camera, LED and height.
