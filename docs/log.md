# Edge Engine — Decision, Design & Work Log

One combined log. Newest entries at the bottom of each section.
Tags: **[DECISION]** = a choice made and why · **[DESIGN]** = how something is built · **[WORK]** = what was done.

---

## 2026-11-22

**[WORK]** Reviewed the research notes (kept private). Checked the key numbers (Kelly growth rates, backgammon shot table, Kuhn equilibrium, flush-draw equity, card variance, Lichess formulas): all correct. Two small issues in the I18 table, §5.5: the "16 vs 10" index wording contradicts itself, and the "15 vs 10 surrender" row shows no actual deviation.

**[DECISION] D-001: `local-brain/` is never pushed.** It is listed in `.gitignore`, enforced by local `pre-commit` and `pre-push` hooks, and written into `CLAUDE.md` and Claude's memory as a permanent rule. *Why:* it holds private research notes and the per-phase teaching PDFs. Everything else (code, plan, this log) lives in the repo.

**[DECISION] D-002: one game per phase.** Phase 0 is foundations, then phases 1–7 are Mental Maths, Kelly, Blackjack, Market Making, Poker, Backgammon and Chess, in the report's order. After each phase: a teaching PDF in `local-brain/pdfs/` and an entry in this log. *Why:* finishing small modules completely beats having many half-built ones.

**[DECISION] D-003: the game brains are built from scratch (Python standard library + numpy).** No Stockfish, no poker evaluator package, no gnubg, no chess.js for the logic. *Why:* the learning and the portfolio value are in building the engines. *Consequences:*
- The language for the brains becomes **Python**, not TypeScript as in the report.
- The chess engine will be much weaker than Stockfish, so "game review" grades moves against our own engine. Stockfish may be used *only outside the app* as a test oracle, never shipped.
- Without bundled GPL code there's no GPL obligation. Licence still open (MIT vs GPL-3.0): **D-005, open**.
- Testing libraries (pytest) are tooling, not "brain", so they're allowed.

**[OPEN] D-006: the UI layer.** Options: (a) terminal UI first, then a web front end (React) talking to a small Python API, keeping all logic in Python; (b) Pyodide, running Python in the browser. Proposed: (a). Decide before the end of Phase 0.

**[WORK]** Created the repo: README (short description + a section per game), `.gitignore`, `CLAUDE.md`, and git hooks blocking `local-brain/`. Wrote `docs/action-plan.md` and this log, first inside `local-brain/`, then moved both to `docs/`: `local-brain/` is only for private files.

**[DECISION] D-007: repo is public.** Confirmed by the user.
