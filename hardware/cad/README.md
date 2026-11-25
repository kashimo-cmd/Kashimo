# CAD

3D model of the robot (chassis, tracks, rod, head, mounts).

| Put here | Format |
|---|---|
| Printable parts | `stl/` one file per part (STL or 3MF) |
| Exchange model | `step/` full assembly as STEP, readable in any CAD |
| Renders for the README and report | `renders/` PNG, under 1 MB each |
| Native source (Fusion, SolidWorks, ...) | only if each file is under 50 MB. Otherwise attach it to a GitHub release and link it here |

Rules:
- Name files `part-name_vN.step`, bump N when the part changes. Keep a table below: part, version, date, who, printed or not.
- Dimensions that matter (body 300 x 200 x 100 mm, 0.5 m slab opening) must match [design.md](../../docs/design.md) 8.1. If CAD differs, say so in an issue and update the design.
- GitHub rejects files over 100 MB. No confidential ACTIA drawings.

## Parts table
none yet
