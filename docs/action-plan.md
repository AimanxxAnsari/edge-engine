# Edge Engine — Action Plan

*Created 22 Nov 2026. One game per phase. A phase is finished only when every item in its "Done when" list is ticked.*

## The routine for every phase

1. **Design**: write the phase's design entry in `docs/log.md`: rules, the maths behind the truth function, data structures and open questions.
2. **Engine**: write the "brain" from scratch (standard library + numpy only), with unit tests against known values.
3. **Trainer**: add the predict → reveal → score questions on top of the engine.
4. **Terminal interface**: make the game playable in the terminal.
5. **Docs**: add a maths explainer in `docs/` (public) for the module.
6. **Push**: commit to GitHub (nothing from `local-brain/`, ever).
7. **Teach** (private): write `local-brain/pdfs/phase-N-<name>.pdf`, a teaching document covering what was built, how the code works, why each design choice was made, the maths, and exercises to check understanding.
8. **Log**: add the work-log entry and any new decisions to `docs/log.md`.

---

## Phase 0 — Foundations

Not a game, but every game depends on it.

- Repo structure, packaging, test runner, linting, CI (GitHub Actions).
- `core`: the module contract (`init`, `legal_actions`, `apply`, `is_terminal`, `result`, `questions`, `truth`, `explain`).
- `rng`: a seeded generator written from scratch (e.g. xoshiro256** or PCG), so games can be replayed and shared.
- `prob`: n-choose-k, binomial, hypergeometric, and a Monte Carlo runner that reports standard error.
- `scoring`: absolute error, Brier score, interval hit rate, EV lost, speed score.
- `storage`: a session/answer log (SQLite from the standard library).

**Done when:** a dummy module runs through the whole predict → reveal → score → log loop, and the RNG and probability tests pass.

Status (22 Nov 2026): **done.**
- [x] Design entry in docs/log.md
- [x] Engine + tests
- [x] Trainer (questions / truth / explain), via the dice demo
- [x] Terminal interface
- [x] docs/ explainer (`docs/phase-0-foundations.md`)
- [x] Pushed (local-brain check passed)
- [x] Teaching PDF in local-brain/pdfs/
- [x] Work-log entry in docs/log.md

## Phase 1 — Mental Maths Speed

- Question generators: + − × ÷, fractions/percentages, decimals, estimation, odds conversion.
- Modes: 120-second sprint; 80-in-8 simulator (+1/−1).
- Per-category timing log, and adaptive weighting (time × error rate).
- Tips shown after slow or wrong answers.

**Done when:** both modes are playable, stats are logged per category, and adaptive sampling is tested.

Status (22 Nov 2026): **done** (branch `phase-1-mental-maths`).
- [x] Design entry in docs/log.md
- [x] Engine + tests
- [x] Trainer (questions / truth / explain)
- [x] Terminal interface
- [x] docs/ explainer (`docs/phase-1-mental-maths.md`)
- [x] Pushed (local-brain check passed)
- [x] Teaching PDF in local-brain/pdfs/
- [x] Work-log entry in docs/log.md

## Phase 2 — Coin Flip with an Edge (Kelly)

- Classic Haghani–Dewey setup ($25, p = 0.6, cap optional).
- Kelly / half-Kelly comparison paths on the *same* flips; growth-rate function g(f).
- Unknown-edge mode with a Beta prior (Bayesian updating, written by hand).
- Fan chart from 1,000 simulated runs; risk of ruin.

**Done when:** the tests reproduce f* = 0.2 and g(0.1), g(0.2), g(0.4) from the research notes, and the simulations agree with the exact values within standard error.

Status (22 Nov 2026): **done** (branch `phase-2-kelly`).
- [x] Design entry in docs/log.md
- [x] Engine + tests
- [x] Trainer (questions / truth / explain)
- [x] Terminal interface
- [x] docs/ explainer (`docs/phase-2-kelly.md`)
- [x] Pushed (local-brain check passed)
- [x] Teaching PDF in local-brain/pdfs/
- [x] Work-log entry in docs/log.md

## Phase 3 — Blackjack

- Shoe, rules config (decks, S17/H17, 3:2 vs 6:5, DAS, surrender, penetration).
- Basic strategy computed by our own recursive EV solver (infinite deck, then composition-dependent).
- Hi-Lo trainer: running count, true count, bet spread; I18 + Fab 4 deviations (verified against a source).
- EV-lost review per decision.

**Done when:** the computed basic strategy matches a published chart, and a full deck counts to 0 (property test).

Status (23 Nov 2026): **done** (branch `phase-3-blackjack`).
- [x] Design entry in docs/log.md
- [x] Engine + tests
- [x] Trainer (questions / truth / explain)
- [x] Terminal interface
- [x] docs/ explainer (`docs/phase-3-blackjack.md`)
- [x] Pushed (local-brain check passed)
- [x] Teaching PDF in local-brain/pdfs/
- [x] Work-log entry in docs/log.md

## Phase 4 — Market Making

- Dice/card contracts; exact mean/variance (including the without-replacement correction).
- Sequential reveal and re-quote; inventory limits and skew.
- Bots: uninformed, informed, mixed flow.
- P&L breakdown: spread vs luck vs adverse selection.

**Done when:** a full round is playable against mixed flow, and the P&L breakdown adds up exactly.

Status (23 Nov 2026): **done** (branch `phase-4-market-making`).
- [x] Design entry in docs/log.md
- [x] Engine + tests
- [x] Trainer (questions / truth / explain)
- [x] Terminal interface
- [x] docs/ explainer (`docs/phase-4-market-making.md`)
- [x] Pushed (local-brain check passed)
- [x] Teaching PDF in local-brain/pdfs/
- [x] Work-log entry in docs/log.md

## Phase 5 — Poker

- Kuhn poker + our own CFR solver (must reach game value −1/18).
- Leduc Hold'em + CFR / Monte Carlo CFR.
- Hand evaluator (5 and 7 cards, from scratch), Monte Carlo equity calculator.
- Heads-up Hold'em with rule-based bots; trainer for outs, equity, pot odds and MDF.

**Done when:** CFR converges on Kuhn and Leduc, the evaluator passes exhaustive or known-count tests, and equity agrees with exact enumeration.

Status (23 Nov 2026): **done** (branch `phase-5-poker`), with Hold'em as a spot trainer; full multi-street Hold'em against rule-based bots is deferred (D-027).
- [x] Design entry in docs/log.md
- [x] Engine + tests
- [x] Trainer (questions / truth / explain)
- [x] Terminal interface
- [x] docs/ explainer (`docs/phase-5-poker.md`)
- [x] Pushed (local-brain check passed)
- [x] Teaching PDF in local-brain/pdfs/
- [x] Work-log entry in docs/log.md

## Phase 6 — Backgammon

- Rules engine: full legal move generation, bar, bearing off, gammons and backgammons.
- Shot counter (must reproduce the 1–12 table), pip counts.
- Heuristic bot with 1-ply search over 21 rolls; then a small TD-learning network in numpy.
- Cube trainer (take point, 8-9-12 rule).

**Done when:** move generation passes perft-style counts, the shot table is reproduced, and the bot beats a random player.

Status (23 Nov 2026): **done** (branch `phase-6-backgammon`).
- [x] Design entry in docs/log.md
- [x] Engine + tests
- [x] Trainer (questions / truth / explain)
- [x] Terminal interface
- [x] docs/ explainer (`docs/phase-6-backgammon.md`)
- [x] Pushed (local-brain check passed)
- [x] Teaching PDF in local-brain/pdfs/
- [x] Work-log entry in docs/log.md

## Phase 7 — Chess

- Board representation (bitboards or 0x88), legal move generation, FEN/PGN.
- Alpha-beta, iterative deepening, transposition table, quiescence; hand-written evaluation.
- Game review: eval → win% → accuracy (Lichess formulas), move classification.

**Done when:** perft numbers match the standard reference positions, and the engine plays legal, sensible games and reviews a PGN.

Status (23 Nov 2026): **done** (branch `phase-7-chess`).
- [x] Design entry in docs/log.md
- [x] Engine + tests
- [x] Trainer (questions / truth / explain)
- [x] Terminal interface
- [x] docs/ explainer (`docs/phase-7-chess.md`)
- [x] Pushed (local-brain check passed)
- [x] Teaching PDF in local-brain/pdfs/
- [x] Work-log entry in docs/log.md

---

## Phase 8 — Learning modes (added 23 Nov 2026)

- Training wheels (`--wheels`) for every game: the answer, explanation and tip before each question; answers judged before they count; practice logged separately.
- Game hooks `lesson()` and `judge()`; game-specific feedback for the coin flip, market making and backgammon.
- Claude tutor (`--tutor`): explains the engines' exact numbers. In scored modes it never sees the answer before you commit, and assisted answers are marked.

**Done when:** every game runs with `--wheels`; the tutor never receives the answer in scored modes before the commit (tested); assisted answers are stored; the tutor is optional (games work without it) and its tests never call the API.

Status (23 Nov 2026): **done** (8a: branch `phase-8-training-wheels`; 8b: branch `phase-8b-tutor`).
- [x] Design entry in docs/log.md
- [x] Engine + tests
- [x] Trainer (questions / truth / explain)
- [x] Terminal interface
- [x] docs/ explainer (`docs/phase-8-learning.md`)
- [x] Pushed (local-brain check passed)
- [x] Teaching PDF in local-brain/pdfs/
- [x] Work-log entry in docs/log.md

---

## Phase checklist template

- [ ] Design entry in docs/log.md
- [ ] Engine + tests
- [ ] Trainer (questions / truth / explain)
- [ ] Terminal interface
- [ ] docs/ explainer
- [ ] Pushed (local-brain check passed)
- [ ] Teaching PDF in local-brain/pdfs/
- [ ] Work-log entry in docs/log.md
