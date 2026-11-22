# Edge Engine — project guidelines

## Absolute rule: `local-brain/` is never pushed

The `local-brain/` folder and everything in it must **never** be committed or pushed to GitHub.
This is permanent. Do not ask about it, do not confirm it, just enforce it:

- `local-brain/` stays in `.gitignore`. Never use `git add -f` on it.
- Never copy its content into tracked files (README, docs, comments).
- Before any commit or push, check that nothing under `local-brain/` is staged.
- Local git hooks (`pre-commit`, `pre-push`) also block it — keep them in place.

## Build rules

- One game per phase. A phase is done only when the game, its tests and its docs are finished.
- The game "brains" (engines, solvers, truth functions) are written from scratch: Python standard library and numpy only.
- After each phase: write a teaching PDF in `local-brain/pdfs/` (private) and update `docs/log.md` (decisions, design, work done).
- `local-brain/` holds private files only. All project files (code, docs, plan, log) go outside it.
- Plan: `docs/action-plan.md`. Log: `docs/log.md`.
