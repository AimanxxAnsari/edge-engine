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

---

## 2026-11-22 — Phase 1: Mental Maths Speed

**[DECISION] D-012: one branch per phase, merged by pull request.** *Why:* CI runs before anything reaches `main`, each phase is one reviewable unit in the history, and a dead-end approach can be dropped by deleting the branch. No `develop`/`release` branches: that is team overhead.

**[DESIGN] Phase 1 design.**

*Categories and the truth function.* Nine categories: add, sub, mul, div, decimals, fractions, percent, estimation, odds. A generator draws the operands with the seeded RNG and stores them in `Question.params` (operands as strings such as `"0.3"` or `"3/4"`). A separate `solve(params)` computes the exact answer with `Fraction`. Generation and truth are separate functions, so the truth can be tested on its own.

| Category | Example | Target time | Tolerance |
|---|---|---|---|
| add | 347 + 486 | 5 s | exact |
| sub | 503 − 278 | 6 s | exact |
| mul | 47 × 8, 14 × 37 | 8 s | exact |
| div | 672 ÷ 8 | 8 s | exact |
| decimals | 0.3 × 0.7, 4.8 ÷ 0.6 | 10 s | exact |
| fractions | 3/4 + 1/6 | 15 s | 0.005 (so 3-decimal answers count) |
| percent | 15% of 240; 18 is what % of 72; change from 80 to 100 | 10 s | exact |
| estimation | 347 × 62, 8 214 ÷ 37 | 12 s | 2% of the answer |
| odds | 3 to 1 against → %; 20% → odds against; pot odds | 12 s | 0.5 percentage points (0.05 for odds) |

Percent answers are typed as plain numbers: for a percent question `25` and `25%` both mean 25.

*Modes.*
- **sprint**: 120 s, as many as you can, +1 per correct answer.
- **test**: 80 questions in 480 s, +1 correct, −1 wrong, 0 skipped (`s` skips).
- **practice**: 20 questions, no clock.

*The clock counts answering time only* (the sum of the time spent on each question). Reading the reveal and tips does not use up the clock. An answer that finishes after time has run out is logged (it is still practice data) but does not count towards the mode score.

*Adaptive sampling.* For each category c, with n answers, w wrong or skipped, and total time s against target T:

```
error rate  e = (w + 1) / (n + 2)            (Laplace smoothing)
time ratio  r = ((s + 2T) / (n + 2)) / T     (prior: two answers at the target time)
weight      raw = r · e
probability p = 0.75 · raw / Σ raw + 0.25 / C
```

With no data every category has e = 0.5 and r = 1, so the choice is uniform. The 25% uniform floor keeps every category in play. History from earlier sessions is loaded from SQLite and capped at the equivalent of 50 answers per category, so old results don't swamp new ones. Adaptive sampling can be turned off with `adaptive=false`.

*Tips.* Each question carries a general technique tip, shown only when the answer was wrong, skipped or slower than the target. The explanation (always shown) is a worked solution for those exact numbers.

**[DECISION] D-013: three small additions to the module contract.** `observe(state, question, score, seconds) → state` is called after each answer is scored, so a module can react to answers (clock, adaptive stats). `summary(state) → str` is printed at the end. `load_history(stats)` gives a module the logged per-category stats before a session. All three have no-op defaults, so the dice demo is unchanged. *Why:* the clock and adaptive sampling both need to see answers, and this is the smallest change that allows it without the module reading the terminal or the database itself.

**[DECISION] D-014: skippable questions.** `Question.skippable`; a skipped answer is stored as `null` with 0 points and `correct = NULL`, so it doesn't count in accuracy (accuracy is "right among attempted"). The adaptive weights do count skips as errors.

**[DECISION] D-015: module options from the command line** with `-o key=value` (for example `-o mode=test -o categories=odds,percent`), so the CLI does not need flags for every module.

**[WORK] Phase 1 built.** Package `src/edge_engine/modules/mental/`: `questions.py` (nine generators, `solve`, worked explanations, tips), `adaptive.py` (category weights), `module.py` (`MentalMaths`, modes sprint / test / practice). Core changes: `observe`, `summary` and `load_history` hooks (D-013); `Question.tip` and `Question.skippable` (D-014); `Rng.weighted_index`; the loop stops as soon as `observe` ends the game; CLI `-o key=value` (D-015) with option errors reported before a session is logged. 109 tests (49 new), all passing; ruff clean. New checks include:
- `solve` against 16 hand-worked answers (including pot odds for half-pot and pot-sized bets).
- 300 draws per category: whole positive answers for integer arithmetic, exact division, no trivial ×10 multiplications, short exact decimals, odds always "against" and in lowest terms.
- Adaptive weights: uniform with no data; slow + wrong > no data > fast + right; time and errors each raise the weight; the floor holds; sampling matches the probabilities (chi-square); history is capped at 50 answers.
- A simulated player who is slow and wrong on fractions sees fractions rise from about a third to over 60% of questions.
- Modes: a sprint at 2 s per answer gives exactly 60 questions; a late answer is logged but not counted; test mode scores +1/−1/0 and stops at 80; practice ignores time.

*Changes made after trying it:* multiples of 10 dropped from ×1-digit questions (30 × 7 is too easy); odds questions are always "against" and reduced (no "2 to 4 against"); repeating percentages shown as "≈ 66.67" instead of "200/3"; estimation explanations rewritten as "round, then adjust", since rounding both numbers was often more than 2% off (730 × 60 against 39,930).

*Left for later:* history is all-time (capped), not weighted by date; difficulty within a category is fixed. Both can be added without changing the contract.

---

## 2026-11-22 — Phase 2: Coin Flip with an Edge (Kelly)

**[DESIGN] Phase 2 design.**

*The game.* You start with $25 and bet on a biased coin, even money, for a fixed number of flips (default 50; `-o flips=300` for the full classic setup). Each flip you type a bet: `5` is $5 on heads, `-5` is $5 on tails, `20%` is 20% of your bankroll. The bet is the question: it is scored against the Kelly bet, the module records it through `observe`, and the "flip" action settles it. This needs no change to the loop.

*Modes.*
- **classic:** p = 0.6, known. Optional cap (`-o cap=250`): wealth stops at the cap, as in the original experiment.
- **unknown:** p is drawn from a Beta(5, 5) prior (mean 0.5, sd ≈ 0.15) and hidden. You must learn the bias from the flips; every 10 flips you are asked for your estimate of P(heads).

*Truth functions.*

| Quantity | Formula |
|---|---|
| Kelly fraction (net odds b) | f* = (b·p − q)/b; even money: 2p − 1 |
| Growth per flip | g(f) = p·ln(1 + b·f) + q·ln(1 − f) (signed f: negative = tails) |
| Mean final wealth | W0·(1 + f·(b·p − q))^N |
| Median / P(finish below x·W0) | exact: final wealth depends only on the number of wins k ~ Binomial(N, p) and rises with k |
| Kelly bet with a cap | min(f*·W, cap − W): never bet more than you need to reach the cap (a heuristic; the exact capped optimum needs dynamic programming and is out of scope) |
| Kelly bet with unknown p | posterior Beta(a + heads, b + tails); f = 2m − 1 with m the posterior mean. For one even-money bet, expected log wealth depends on p only through E[p], so this is exact for the next bet. |
| Drawdown (continuous approximation) | P(ever falling to x·W0) ≈ x^(2/c − 1) when betting c × Kelly |
| Gambler's ruin, fixed-size bets | (q/p)^(W0/bet), no time limit |

*Questions.*
- Before the first flip (classic mode): "Which fraction maximises growth?" (point, ±0.01) and "If you bet 30% every flip, what is the chance you finish below $25?" (point, ±0.05; exact binomial).
- Every flip: the bet (point; truth = Kelly bet; right if within 5% of bankroll). The explanation shows your growth rate against Kelly's.
- Unknown mode, every 10 flips: P(heads) estimate (point, truth = posterior mean, ±0.03).

*Same-flip comparison.* Shadow bankrolls (Kelly, half Kelly and double Kelly; in unknown mode Bayes-Kelly, Bayes half-Kelly and an oracle that knows p) are settled on the same coin flips as you. This takes luck out of the comparison.

*End of session.* Final bankrolls for you and the shadows, the coin's real bias, and a fan chart of 1,000 simulated runs at your average bet fraction.

*Lab.* `edge-engine lab kelly` prints, for a range of fractions: g(f), mean, median, P(finish below start), simulated drawdown risk with SE beside the approximation, a fan chart, and fixed-bet ruin. No input needed.

Money is kept in whole cents (integers), so no rounding drift builds up over 300 flips.

**[DECISION] D-016: the bet is a question, not an action.** The loop's actions are a short list of strings, and a bet is a number. Making the bet a scored question that `observe` records keeps the loop unchanged and gets bet sizing scored and logged for free.

**[DECISION] D-017: numeric answer ranges.** `params["min"]` / `params["max"]` make the terminal reject out-of-range answers (you can't bet more than you have), and `params["pct_base"]` makes `20%` mean 20% of that base.

**[DECISION] D-018: `edge-engine lab <name>`** for non-interactive analysis (tables, simulations, charts), kept outside the game contract.

**[DECISION] D-019: still no numpy.** 1,000 runs × 300 flips in pure Python takes well under a second, and the RNG has to be our own anyway.

**[DECISION] D-020: `observe` also receives the answer:** `observe(state, question, answer, score, seconds)`. This changes D-013. *Why:* the bet is the answer, and the module has to know the amount to settle it. The mental maths module only needed the score, so it simply ignores the new argument.

**[WORK] Phase 2 built.** Package `src/edge_engine/modules/kelly/`: `kmath.py` (Kelly fraction, g(f), zero-growth root, exact mean / median / P(below) from the binomial, drawdown approximation, gambler's ruin, Beta posterior and sampler), `sim.py` (paths, drawdown and fixed-bet ruin frequencies with SE, quantiles, text fan chart), `module.py` (`CoinFlip`, classic and unknown modes), `lab.py` (`edge-engine lab kelly`). Core and CLI: `observe` gets the answer (D-020); numeric answer ranges and `%`-of-bankroll input (D-017); dollar display; `lab` command (D-018); the summary now prints before the final "Session finished" line. 135 tests (26 new), all passing in under 2 s; ruff clean.

The "Done when" checks:
- f* = 0.2; g(0.1) = 0.0150, g(0.2) = 0.0201 and g(0.4) ≈ −0.0025 as in the research notes. The exact value of the last is −0.002447, so the notes round it up; the test allows ±0.00006 and also checks the formula itself.
- Simulation against exact: mean log growth per flip at f = 0.1, 0.2, 0.4 (within 4 SE of g); P(finish below start) at f = 0.3; mean final wealth at f = 0.1; fixed $5 bets against (q/p)⁵.

Other checks: mean, median and P(below) against brute force over all 2¹⁰ flip sequences; the Beta sampler's mean and variance; a perfect player's bankroll equals the Kelly shadow's to the cent; bets settle correctly on heads and tails; the cap ends the game and limits the Kelly bet; going all-in and losing ends the game; in unknown mode the estimate question comes every 10 flips and a perfect player matches Bayes-Kelly; a seed replays the session exactly.

*Changes made after trying it:* means of millions and billions are shown as `$3.22M` so the lab table fits; the fan chart's axis labels are aligned and the start row is labelled; the bet prompt shows a dollar hint instead of the probability hint; the summary's "Kelly growth" now uses the favoured side when the coin favours tails (it showed −0.24).

*Left for later:* the exact capped optimum (dynamic programming), variable-odds and multiple-bet modes.
