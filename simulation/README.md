# Simulation

Proof-of-concept simulations that are not part of the robot's runtime code.

| Folder | Content |
|---|---|
| `proteus/` | Proteus project (`.pdsprj`) and exports: schematic PDF, screenshots of the running simulation |
| `scenarios/` | Other simulations if any, with a README on how to run them |

Rules:
- Say what the simulation shows and what it does **not** show (a Proteus run proves the circuit idea, not the real robot). Evidence level: Simulated ([docs/TESTING.md](../docs/TESTING.md)).
- Always export a PDF of the schematic and a PNG of the result next to the project file, so judges need not install Proteus. Note the Proteus version.
- A simulated number is never reported as measured.
- The software PoC that already exists is the fake Pi (`tools/fake_pi.py`), see [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).

## Simulations
none yet
