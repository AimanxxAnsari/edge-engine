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
- Without bundled GPL code there's no GPL obligation. Licence: see D-005.
- Testing libraries (pytest) are tooling, not "brain", so they're allowed.

**[DECISION] D-005: MIT licence.** *Why:* nothing GPL is bundled (engines are from scratch), so the simplest permissive licence works.

**[DECISION] D-006: terminal interface first.** Each game is playable in the terminal before any web front end. *Why:* keeps the focus on the engines and the maths; a web UI can be added later on top of the same Python code. Built with the standard library only.

**[WORK]** Created the repo: README (short description + a section per game), `.gitignore`, `CLAUDE.md`, and git hooks blocking `local-brain/`. Wrote `docs/action-plan.md` and this log, first inside `local-brain/`, then moved both to `docs/`: `local-brain/` is only for private files.

**[DECISION] D-007: repo is public.** Confirmed by the user.

---

## 2026-11-22 — Phase 0: Foundations

**[DESIGN] Phase 0 design.** Shared code that every game sits on. No game yet; a small dice demo module exercises the full loop.

*Layout.* `src/edge_engine/` (src layout, so tests run against the installed package, not the working folder). Modules:

| Module | Job |
|---|---|
| `rng` | Seeded generator, replayable from `(seed)` or a saved state |
| `prob` | n-choose-k, binomial, hypergeometric, Monte Carlo with standard error |
| `scoring` | Error measures and per-question scoring |
| `core` | `Question`, `Kind`, and the `GameModule` contract |
| `loop` | predict → reveal → score → log, independent of the terminal |
| `storage` | SQLite session and answer log, per-category stats |
| `terminal` | Answer parsing and the terminal front end |
| `modules/dice` | Demo module: two dice, four question kinds |

*RNG: xoshiro256\*\*.* 256 bits of state, 64-bit outputs, period 2^256 − 1, passes BigCrush, about ten lines of code. The seed is expanded into the four state words with SplitMix64, which is what the authors recommend (it guarantees a state that is not all zeros). Outputs are reduced to a range by rejection sampling on the top bits (no modulo bias). Floats use the top 53 bits: `(x >> 11) · 2^-53`, uniform on [0, 1). Python's `random` is not used anywhere, so a seed gives the same game on every Python version.

*Probability.* `n_choose_k` uses the multiplicative formula, `r = r·(n−k+i) // i`, which stays an exact integer at every step. Binomial and hypergeometric functions work with `Fraction` inputs, so tests can check exact values. Monte Carlo uses Welford's online mean and variance and reports `SE = s/√n`.

*Module contract.* `init(rng, config) → state`, `legal_actions(state)`, `apply(state, action) → state`, `is_terminal(state)`, `result(state)`, `questions(state)`, `truth(state, q)`, `explain(state, q)`. The state is whatever the game wants; the loop never looks inside it.

*Question kinds and scoring.*

| Kind | Answer | Error | Correct when | Points |
|---|---|---|---|---|
| point | number | \|a − t\| | error ≤ tolerance | 1 / 0 |
| decision | one of the choices; truth is EV per choice | EV lost = best EV − chosen EV | EV lost = 0 | 1 / 0 |
| probability (forecast) | p in [0, 1]; truth is the outcome 0/1 | Brier (p − o)² | — (not defined) | 1 − Brier |
| interval | (lo, hi) at level 1 − α | interval (Winkler) score | truth inside | 1 / 0 |
| speed | number | \|a − t\| | error ≤ tolerance | min(1, target/seconds) if correct, else 0 |

Forecast questions are about something that has not happened yet, so the loop scores them **after** the next action, against the new state. Everything else is scored straight away.

*Storage.* SQLite file at `~/.edge_engine/history.db` (override with `--db`). Tables `sessions(id, module, seed, config, started_at, ended_at)` and `answers(session_id, question_id, kind, category, prompt, answer, truth, error, points, correct, seconds, created_at)`. Answers and truths are stored as JSON.

**[DECISION] D-004: number left unused.** It was skipped by mistake on 22 Nov; kept empty so later IDs don't shift.

**[DECISION] D-008: xoshiro256\*\* seeded by SplitMix64.** *Why:* small, fast enough in pure Python, well tested, and it has published reference values to test against. PCG needs 128-bit multiplies, which are clumsier to read.

**[DECISION] D-009: no runtime dependencies yet.** Phase 0 needs only the standard library. numpy is added to `pyproject.toml` when the first module uses it. Dev tools: pytest, ruff.

**[DECISION] D-010: git hooks are tracked in `githooks/`** and turned on with `git config core.hooksPath githooks`, so the `local-brain/` block survives a fresh clone.

**[DECISION] D-011: forecasts resolve after the next action** (see the design above).

**[WORK] Phase 0 built.** Package `src/edge_engine/` with `rng`, `prob`, `scoring`, `core`, `loop`, `storage`, `terminal`, `cli` and the dice demo (`edge-engine play dice`). 60 tests, all passing; `ruff` clean. Checks include:
- xoshiro256\*\* and SplitMix64 against published reference outputs; seeded replay and state save/restore; chi-square tests on die rolls and on all six orders of a 3-item shuffle.
- `n_choose_k` against `math.comb` for n < 40; exact `Fraction` checks for binomial and hypergeometric; hypergeometric variance computed from the pmf equals the closed form.
- Monte Carlo on P(two dice ≥ 9) is within 4 SE of 10/36, and the reported SE matches √(p(1−p)/n).
- Full loop with a scripted perfect player, five rounds, 20 answers logged; forecasts are revealed after the roll; quitting mid-round drops the unresolved forecast and still closes the session.
- Terminal parsing of `0.25`, `1/4`, `25%`, intervals and choice prefixes; the CLI plays and prints per-category stats.

Other work: CI on GitHub Actions (Python 3.10–3.12, ruff + pytest); git hooks moved to tracked `githooks/` (tested in a throwaway repo: a commit with `local-brain/` is blocked); README updated (Getting started, layout, status, "Phase N" headings, "per-category stats" instead of "dashboard"); maths explainer `docs/phase-0-foundations.md`; private teaching PDF written.

*Bug found on the way:* `TerminalUI(input_fn=input)` bound `input` when the function was defined, so tests that patch `builtins.input` had no effect. It now looks `input`/`print` up at call time.
