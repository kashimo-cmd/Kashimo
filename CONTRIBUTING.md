# Contributing

`docs/design.md` is the single source of truth. Read its section 0 before writing code.

## Rules
- `main` is protected. Nobody pushes to it: every change is a pull request.
- One task = one branch = one pull request. Branch names: `k05-sensors`, `fix/watchdog-timeout`, `docs/bom`.
- Commit messages follow Conventional Commits: `feat(k05): median filter`, `fix(drive): refuse forward under 30 cm`, `docs: ...`, `test: ...`, `chore: ...`, `ci: ...`.
- Merge by squash, after CI is green and one teammate approved.
- Section 4 contracts are frozen. If one looks wrong, open an issue, do not change it silently.
- Python 3.11, asyncio, only the libraries of section 3.3. Max 300 lines per file.
- Everything must run on a PC with `HW_MODE=mock`. Pi-only code is marked `# CHECK ON PI`.
- Never commit model files, recordings, databases, passwords or keys (`.gitignore` blocks the usual ones).
- Never write that a test passed if you did not run it.

## Workflow
```
git switch main && git pull
git switch -c k05-sensors
python -m pytest
git push -u origin k05-sensors
```
Then open a pull request. The template lists what to fill in.

## Ownership
`.github/CODEOWNERS` lists who reviews which folder. Each sub-team owns its folders.
