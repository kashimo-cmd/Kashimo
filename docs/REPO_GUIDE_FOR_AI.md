# Guide for an AI assistant working on this repo

The owner pastes or attaches this file at the start of every chat. **Read it fully before writing any file or command.** It exists because earlier chats lost time to the mistakes listed in section 7.

## 1. Context
Kashimo: tracked inspection robot for an ACTIA cable gallery (IEEE IAS Challenge TSYP14, final deadline 12 Dec 2026). Raspberry Pi 5 on the robot, web dashboard on a PC. Repo: https://github.com/kashimo-cmd/Kashimo. Local clone: `C:\Users\User\Kashimo` (the only clone). The owner uses Windows CMD and pastes terminal output into chats.
You cannot push, cannot see the owner's disk, the Pi or the PC. You give files and exact commands, the owner runs them and pastes the output. Ask for the output before saying anything worked.

## 2. Read in this order
1. `README.md` (status table). 2. `docs/TASKS.md`. 3. `docs/design.md` section 0, section 4 (frozen contracts) and your task. 4. `docs/ARCHITECTURE.md`. 5. `docs/tasks/K<nn>.md` of the tasks you depend on (they list placeholders and open items).
`docs/design.md` is the single source of truth. Section 4 is frozen: implement it as written, report problems as DEVIATIONS.

## 3. Truth rules (judges check these)
- Never write "passed", "works" or give a measurement unless the owner pasted proof. Use the evidence levels in `docs/TESTING.md`: Target, Assumption, Simulated, Measured, Verified.
- Say what was **not run**: Pi hardware, real camera, real keyboard layouts, etc.
- No invented parts, prices, specs, ACTIA data or references. Unknown means `[CHECK]` or ask the owner.
- No secrets, tokens, model files, datasets, recordings or confidential ACTIA material in Git.
- No compliance or certification claims.

## 4. Where files go
| Thing | Path |
|---|---|
| Shared protocol, constants | `common/` |
| Robot code | `pi/controller/`, `pi/ai/`, `pi/video/` |
| PC server, dashboard | `pc/server/`, `pc/web/` (css, js) |
| Dev and Pi tools, fake Pi | `tools/` |
| Tests | `tests/` (pytest, Node tests `*.test.mjs`) |
| Config, systemd units | `config/`, `systemd/` |
| Parts, pins, power | `hardware/` |
| Measured results (one file per run) | `results/` (+ row in `results/RESULTS.md`) |
| Task cards | `docs/tasks/K<nn>.md` |
| Photos, diagrams, screenshots | `media/` |
| CAD (STL, STEP, renders) | `hardware/cad/` |
| Proteus project and exports | `simulation/proteus/` |
| Report (editable + PDF) | `docs/report/` |
| Slides (editable + PDF) | `docs/presentation/` |
| Big files (over 50 MB), videos, model weights | NOT in Git: GitHub release asset or external link, listed in the folder README |
| AI notes, model card | `ai/` (weights are NOT in Git: `scp` to `model/` on the Pi) |
Do not create new top-level folders. Do not rename `pi/`, `pc/`, `common/`. Max 300 lines per code file. `README.md` max 40 lines (enforced by `tests/test_k01.py`): details go in `docs/`, never in the README. Do not edit or weaken existing tests to make them pass. Python 3.11 syntax only (CI and the Pi run 3.11, the owner's PC may run newer). Everything must run with `HW_MODE=mock`; Pi-only code is marked `# CHECK ON PI`.

## 5. How to deliver a task
Deliver **one zip in repo layout**: paths inside the zip are the paths in the repo (`pi/controller/rod.py`, `tests/test_rod.py`, `docs/tasks/K07.md`). Never loose files. The owner extracts with `tar -xf`, which creates missing folders.
Every task zip contains:
1. The code and its tests.
2. `docs/tasks/K<nn>.md` (Did, Files, Run, Tested, Not run, Open items, placeholders to CHECK ON PI).
3. The changed row in `docs/TASKS.md` (IN PROGRESS to DONE) and the status row in `README.md`.
4. A line under `## [Unreleased]` in `CHANGELOG.md`.
If a task changes behaviour described in `docs/ARCHITECTURE.md` or `docs/USER_MANUAL.md`, update those too.
Then reply with exactly: `STATUS: DONE|PARTIAL`, `RUN:`, `TEST:` (real result or NOT RUN), `DEVIATIONS:`, `OPEN:`. Then the commands.

## 6. Git commands: the template you must follow
Rules: one task = one branch = one pull request. `main` is protected. Branch first, extract second. Use explicit file paths in `git add` (never `git add -A` or `.`, the folder may hold stray files). No placeholders such as `N` or `<number>` or `DESIGNFILE`: every command must run exactly as written. Do not chain commands after one that can fail without telling the owner to stop and paste the output.

Pre-flight (always first):
```
cd /d C:\Users\User\Kashimo
git status
git switch main
git branch --set-upstream-to=origin/main main
git pull
```
`git status` must say "nothing to commit". If not, the owner pastes it and you decide. Do not continue on a dirty tree.

Work:
```
git switch -c k09-controller
tar -xf "%USERPROFILE%\Downloads\K09.zip"
git status
python -m pytest -q
```
Stop here. The owner pastes `git status` and the pytest result. Check that only the expected files changed and that pytest has no failures, then give:
```
git add <each file path from git status, one per path>
git commit -m "feat(k09): controller main loop"
git push -u origin k09-controller
gh pr create --fill
gh pr checks --watch
gh pr merge --squash --delete-branch
git switch main
git pull
git log --oneline -3
```
Success means: `git log` shows the new commit on `main` and the files are no longer stubs on GitHub. A pull request from a branch with no commits ("No commits between main and ...") means the `git add` or `git commit` failed: look at the output, do not retry blindly.
If `gh pr merge` refuses for a missing approval, merge in the browser after a teammate approves. If `gh` shows `TLS handshake timeout`, retry. If `git rebase` or `git pull` reports a conflict, stop and ask for the output.
Commit messages: `feat(k09): ...`, `fix(drive): ...`, `docs: ...`, `test: ...`, `chore: ...`, `ci: ...`.

## 7. Mistakes that already happened (do not repeat)
| Mistake | Rule |
|---|---|
| `copy` into `docs\tasks` that did not exist, then `git add` failed on the bad path and nothing was committed | Deliver a zip and `tar -xf`. Folders get created |
| The PR failed with "No commits between main and branch" | Verify `git status` before `git add`, and check the commit exists (`git log --oneline -2`) before `gh pr create` |
| Files edited while on `main`, then carried into other branches | Always `git switch -c` before extracting files |
| `git pull` failed: no tracking information | `git branch --set-upstream-to=origin/main main` (pre-flight) |
| Literal `N` typed as PR number | Use `gh pr merge --squash --delete-branch` without a number, from the task branch |
| `Closes #12` when no issues exist | The PR template uses `Task: K__`. Do not reference issues that do not exist |
| Placeholder `DESIGNFILE` left in a command | No placeholders |
| `files.txt` and `log.txt` lying in the repo folder | Keep them outside the repo (they are in `.gitignore`). Explicit `git add` paths |
| Tests written without ever running against the real module | Say it in `TEST:` and the task card. The owner runs real pytest before the push |
| Claims in docs that were never measured | Section 3 |

## 8. After merge: getting it onto the Pi
Only after `main` is updated and CI is green:
```
cd ~/kashimo
git pull
bash setup.sh
python tools/verify.py
```
`setup.sh` needs Raspberry Pi OS Bookworm (Python 3.11). Model files: `scp -r model pi@<pi-ip>:~/kashimo/` (they are not in Git). Pi results (probe output, benchmarks, T-tests) go into `results/` through a normal pull request. Never edit code directly on the Pi; if you must, commit on a branch and push from there.
Back up the SD card image before big changes.

## 9. Tasks not merged yet (K09, K11, K15, K16, K17): where each lands
On `main` these files are one-line stubs. The task's own output replaces them.
| Task | Replaces or adds | Tests | Also update |
|---|---|---|---|
| K09 controller | `pi/controller/main.py`, `ws_server.py`, `telemetry.py`, `events.py` (uses K04-K08 as in `docs/tasks/K04-K08.md`) | `tests/test_controller.py` | `docs/ARCHITECTURE.md` |
| K11 AI plug-in | `pi/ai/detectors/base.py`, `dummy.py`, `onnx_det.py`, `pi/ai/rules.py`, `worker.py`; YOLO adapter `onnx_yolo.py` | `tests/test_ai.py` | `ai/README.md` |
| K15 map and log | `pc/web/js/map.js`, `log.js`, only the needed lines in `index.html` and `css/` | `tests/*.test.mjs` | `docs/USER_MANUAL.md` |
| K16 Pi tools | `tools/bench_detector.py`, `calib_encoders.py`, `calib_imu.py`, `latency_test.py`, `make_dummy_onnx.py`, `record_normal.py` | `tests/test_tools.py` | `results/` only when run on the Pi |
| K17 deploy and verify | `tools/verify.py`, `setup.sh`, `systemd/*.service` | | `README.md` run section |
Merge them one at a time. Before pushing the next one: `git fetch`, `git rebase origin/main`, re-run pytest.
Carry-overs (all CHECK ON PI): `odo.track_circumference_m` value, `drive.pwm_at_speed` placeholder (K16 calibrates it), K07 `FOLD_POSE` and servo angles, K08 IMU axis signs, K10 video never run on the Pi.

## 10. Releases
After a milestone: update `CHANGELOG.md` (move Unreleased to a version), `git tag -a v0.2.0 -m "text"`, `git push origin v0.2.0`, then create a GitHub release from the tag. Tag the final submission state.

## 11. Style
Professional technical English. Short sentences. Relative links between docs. No decoration, no filler, no invented claims. Reply to the owner without yapping: files, status lines, commands.
