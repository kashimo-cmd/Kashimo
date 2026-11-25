# Testing and validation

## Evidence levels (use these words, nothing else)
| Level | Meaning |
|---|---|
| **Target** | A number we want (poster, design.md). Not evidence |
| **Assumption** | Design value, tagged [EST] or [CALC] in design.md |
| **Simulated** | Produced on a PC with mock hardware or the fake Pi |
| **Measured** | Real run on the real hardware, with a file in [results/](../results/) |
| **Verified** | Measured and meets the target, reviewed by a teammate |

A result without a file in `results/` is not reported anywhere (README, report, slides).

## Automated tests (PC, mock mode)
`python -m pytest` runs `tests/`: protocol, fake Pi, PC server, dashboard JS (Node tests run if `node` is installed), skeleton checks. Recorded runs (task cards): K14 178 passed and 2 skipped (Windows). K04 card: 195 passed. K05 card: its 16 tests were run with a stand-in runner, not real pytest. Run `python -m pytest` on `main` and write the real total here. CI runs the same in mock mode on Linux with Python 3.11.
These prove software logic only. They prove nothing about the robot.

## Hardware and system tests T1-T25
Definitions and targets: [design.md](design.md) section 9. Which can run now: section 9.1. Status and links: [results/RESULTS.md](../results/RESULTS.md).
Each run uses [results/TEMPLATE_TEST_REPORT.md](../results/TEMPLATE_TEST_REPORT.md) and is saved as `results/T<id>_<YYYY-MM-DD>.md`, with raw data (CSV, photos) next to it if small.

## Targets from the poster (not verified)
| Target | Test | Status |
|---|---|---|
| Position within plus or minus 1 slab (design expects plus or minus 2 first) | T5, T19 | not run |
| Packet loss under 1 % at 30 m | T4, T15 | not run |
| Full inspection about 0.5 h | T7 | not run |
| No person enters during a fault search | T7 | not run |
| Prototype budget 750 TND | [hardware/BOM.md](../hardware/BOM.md) | open question Q2 |

## Rules
- Never write "passed" for a test that was not run.
- Record failures too. A failed test is a result.
- State the limits: where, how many samples, which hardware, which software commit.
