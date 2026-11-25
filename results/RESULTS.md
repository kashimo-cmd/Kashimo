# Results log

Status: NOT RUN = no measurement exists. Update a row only with a link to a report file.

| ID | What | Target | Can run now? | Status | Report |
|---|---|---|---|---|---|
| T1 | AI ms per frame on the Pi | 300 ms or less, 1.5 GB or less | dummy only | NOT RUN | |
| T2 | Video delay, 30 samples | WebRTC 0.5 s or less, 15 fps | after K10 on the Pi | NOT RUN | |
| T3 | Command round trip, watchdog stop | 0.2 s, stop within 0.5 s | needs K09 | NOT RUN | |
| T4 | Packet loss at 30 m | under 1 % | needs router | NOT RUN | |
| T5 | Slab error | within 2 slabs, goal 1 | needs robot | NOT RUN | |
| T6 | Link cut, nothing lost | 0 lost | needs K09 | NOT RUN | |
| T7 | Full run time | 0.5 h or less | needs robot | NOT RUN | |
| T8 | Camera sharpness 20-40 cm | readable detail | after K10 | NOT RUN | |
| T9 | Rod vibration blur | sharp frame | needs robot | NOT RUN | |
| T10 | Turn and cross 2 m width | no jam | needs robot | NOT RUN | |
| T11 | Body through 50 cm opening | fits | needs body | NOT RUN | |
| T12 | Battery runtime with AI | 40 min or more | needs robot | NOT RUN | |
| T13 | Keys on AZERTY and Arabic layout | 12 functions | yes (PC, fake Pi) | NOT RUN | |
| T14 | Obstacle readout vs ruler | within 2 cm | needs sensors | NOT RUN | |
| T15 | Link bars vs distance | bars drop before cut | needs router | NOT RUN | |
| T16 | Rod 50 cycles | no slip | needs robot | NOT RUN | |
| T17 | Photo and screenshot, 20 each | saved within 1 s | yes (PC, fake Pi) | NOT RUN | |
| T18 | Key to motion delay | 0.2 s or less | needs K09 | NOT RUN | |
| T19 | Path map on L and U courses | end within 1 m | needs robot | NOT RUN | |
| T20 | IMU drift | under 5 deg/min | needs IMU | NOT RUN | |
| T21 | Ramps and bumps | tilt within 3 deg | needs robot | NOT RUN | |
| T22 | CPU temperature, throttling, 30 min | `get_throttled` = 0x0 | after K10 | NOT RUN | |
| T23 | Watchdog under AI load | off within 0.5 s | needs K09, K11 | NOT RUN | |
| T24 | Water on the mock gallery | no leak, not stuck | needs robot | NOT RUN | |
| T25 | Coverage of walls and floor | readable | needs robot | NOT RUN | |

Automated PC tests (not T-tests): simulated only. Last totals recorded in task cards: 178 passed + 2 skipped at K14, 195 at K04. Current total on `main`: not recorded yet.
