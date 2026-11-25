# Hardware

Robot engineering data. **Nothing here has been built or measured yet** unless a file says so.

| File | Content | Status |
|---|---|---|
| [BOM.md](BOM.md) | Parts, owned or bought, budget | provisional, prices from design.md and invoices |
| [PINMAP.md](PINMAP.md) | Pi 5 GPIO assignment | design, [CHECK] on the real Pi |
| [POWER.md](POWER.md) | Power tree and safety notes | design |
| CAD, schematics, wiring photos | none yet | add here as `cad/`, `schematics/` when they exist |

## Robot summary (design values, [design.md](../docs/design.md) 8.1)
- Body 300 x 200 x 100 mm, under 3 kg, 3D-printed (PETG), tracks. Must pass a 0.5 m slab opening [CHECK].
- Hinged rod (about 25 cm) with a 2-servo pan-tilt head, USB camera and white LED bar.
- Raspberry Pi 5 4 GB with active cooler. 3 ultrasonic sensors, 2 encoders, MPU6050 IMU.
- Open choice: motors with built-in encoders (design.md Q1, S4).

## Rules
- Mark every value as measured or [EST]/[CALC]/[CHECK] as in design.md.
- Keep large CAD or photos out of Git if over a few MB. Link them instead.
- No ACTIA confidential drawings in this repo.
