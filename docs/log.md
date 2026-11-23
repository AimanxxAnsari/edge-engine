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

---

## 2026-11-23 — Phase 3: Blackjack

**[DESIGN] Phase 3 design.**

*Rules* (all settable): decks (6), S17 or H17, blackjack 3:2 or 6:5, double after split, late surrender, resplitting (not aces), penetration 75%. The dealer peeks for blackjack (US rules), so every decision is evaluated given that the dealer does not have blackjack.

*EV solver* (`ev.py`). Cards are drawn independently from a fixed composition: the probability of each value 1–10.
- Dealer: recursion over (hard sum, has ace) → probability of 17, 18, 19, 20, 21, bust. The hole card is drawn conditioned on "no blackjack" when the upcard is an ace or a ten.
- Player: stand compares with the dealer distribution; hit is a recursion over (hard sum, has ace) taking the better of hit and stand after each card; double = 2 × (one card, then stand); surrender = −0.5.
- Split: per-hand value x = A + p·max(B, 2x), where A covers non-matching second cards, B keeps a matching card as a pair, and p is the chance of a matching card. Solving gives x = A / (1 − 2p) when resplitting pays. Split aces get one card each, and 21 on them is not a blackjack. This is the unlimited-resplit approximation; casinos usually stop at four hands, which changes very little.
- Three compositions: **infinite deck** (1/13 each, 4/13 tens); a **fresh shoe minus the known cards** (the player's cards and the dealer's upcard), averaged over every two-card hand that makes a total, which is how published "total-dependent" charts are built; and the **unseen cards** of the actual shoe, for count-dependent decisions.
- `comp_at_true_count(tc)`: per deck, 20 + tc/2 high cards and 20 − tc/2 low cards, spread evenly within each group. This is the average shoe at a given Hi-Lo true count.

*Checks before building the game:*
- The 6-deck table matches the published 4–8 deck basic-strategy chart (S17, DAS, late surrender) in every cell, and the H17 table matches in every cell including the six H17 changes (11 vs A, 15 vs A, 17 vs A, A7 vs 2, A8 vs 6, 8-8 vs A). The infinite-deck table differs only in two knife-edge soft doubles (A2 vs 5, A4 vs 4: EV margins 0.007 and 0.001), which is why the finite-shoe model is the default.
- Computed deviation indices against Schlesinger's Illustrious 18 and Fab 4 (*Blackjack Attack*): all 22 within 1.2 true counts, most within 0.5 (3 decks left, all two-card hands averaged).

*Hi-Lo.* 2–6 count +1, 7–9 count 0, tens and aces count −1. The running count covers the cards the player has **seen**: the dealer's hole card counts only once it is turned over. True count = RC / decks of unseen cards. The bet spread uses the floor of the true count: TC ≤ 1 → 1 unit, 2 → 2, 3 → 4, 4 → 6, 5 or more → 8.

*Modes.*
- **strategy:** decisions only, scored against EVs for a fresh shoe minus the visible cards (basic strategy).
- **count:** before each hand, the running count, the true count and the bet; decisions are scored against EVs for the actual unseen cards, so count-based deviations count as right. The explanation names the published index when there is one.
- **drill:** batches of cards with a timed running-count question each, plus true-count conversions ("RC +11, 2.5 decks left").

*Questions.* Each decision is a `decision` question whose truth is the EV of every legal action, so the error is the EV lost. Insurance is a decision (take / decline) whenever the dealer shows an ace, with truth from the exact chance that the hole card is a ten. In strategy mode, the first decision on a hard 12–16 also asks for the bust chance if you hit (exact from the composition). Keys: `h` hit, `s` stand, `d` double, `p` split, `r` surrender.

*End of session:* net units, EV lost (total and per 100 hands), decision accuracy and the three most expensive mistakes.

*Lab:* `edge-engine lab blackjack` prints the computed chart, the player's edge for the rules, the edge by true count, dealer bust chances by upcard, and computed against published deviation indices.

**[DECISION] D-021: scored against EVs, with the published indices as teaching aids.** In count mode the truth is the EV of each action for the actual unseen cards, which is more precise than any index table. The published indices are shown in the explanations, and the tests use them to check the solver.

**[DECISION] D-022: decision shortcuts.** `params["keys"]` maps single letters to choices, because "s" could mean stand, split or surrender.

**[DECISION] D-023: mutable game state for blackjack.** A round has a shoe, several split hands and a dealer, and the state moves through stages (bet, insurance, decision). The state object is updated in place and returned, which the loop allows (it only threads the state through). Phases 1 and 2 keep their immutable states.

**[WORK] Phase 3 built.** Package `src/edge_engine/modules/blackjack/`: `cards.py` (cards, hand totals, the shoe with a cut card, rules, Hi-Lo values), `ev.py` (dealer outcomes with peek; stand, hit, double, split with resplitting, surrender; the edge of a round; the compositions), `strategy.py` (chart codes, the total-dependent table, rendering), `count.py` (running and true count, bet spread, the published Illustrious 18 and Fab 4), `module.py` (`Blackjack`: strategy, count and drill modes), `lab.py` (`edge-engine lab blackjack`). Terminal: decision shortcut keys (D-022). 187 tests (52 new), all passing in under 5 s; ruff clean.

The "Done when" checks:
- The computed 6-deck chart equals the published S17 chart in all 340 cells, and the H17 chart (S17 with its six known changes) in all 340 cells.
- The full deck counts to 0: for 20 shuffled shoes cut at a random point, the count of the seen cards plus the count of the rest is 0; and the count drill ends every deck at 0.

Other checks: the infinite-deck chart differs from the published one only at A2 vs 5 and A4 vs 4; the dealer's bust chance showing a 6 agrees with a 40,000-hand simulation within 4 SE; H17 lowers the dealer's chance of 17 and raises busts; the house edge is 0.42%, and 6:5 costs exactly 0.3 × P(blackjack) × P(no dealer blackjack) ≈ 1.39%; the edge rises with the true count by 0.4–0.7% per count; insurance and all 21 published deviations are reproduced within 1.25 true counts. On a stacked shoe: blackjack pays 1.5 (or 1.2 at 6:5), dealer blackjack takes one bet, insurance pays 2:1, doubling, splitting eights with a double after the split, split aces with one card each (21 is not a blackjack), surrender, and H17 against S17 on the same cards. The hole card is not counted until shown; the bust-chance and insurance truths are checked against hand counts of the remaining cards; the bet answer sets the stake; a perfect player loses 0 EV over 150 hands in both modes.

*Found while building:*
- The first true-count composition gave aces and the 7–9 group a weight of 1 instead of 4 per deck, so the insurance index came out at 0. It was caught by comparing with the published +3.
- The previous hand's result was cleared before it was shown, so a blackjack on the first hand never appeared. It is now kept separately.
- Two of my test expectations were wrong (95 tens left, not 94; a script that returned only the answer); the code was right.

*Left for later:* exact composition-dependent EVs (drawing without replacement inside the recursion), the 4-hand resplit limit inside the EV, a bankroll curve with risk of ruin, and H17 deviation indices.

---

## 2026-11-23 — Phase 4: Market Making

**[DESIGN] Phase 4 design.**

*The contract.* A hidden quantity that settles at the sum of n items: dice (independent, 1–6) or cards (A = 1 … K = 13, dealt from one deck without replacement). Default: 4 items. The items are revealed one per round. Before each reveal you quote a two-sided market (bid, ask) and bots trade one lot at a time against it. After the last reveal the contract settles at the sum.

*Exact statistics* (`contract.py`, all with `Fraction`):

| | Dice, m hidden | Cards, m hidden from R unseen |
|---|---|---|
| Fair value | revealed + 3.5·m | revealed + m·μ, μ = mean of the unseen cards |
| Variance | m · 35/12 | m·σ²·(R − m)/(R − 1), σ² = population variance of the unseen cards |
| Distribution | convolution of m dice | dynamic programme over card values: ways to pick m cards with each sum, using C(count, k) per value, over C(R, m) |

The unseen cards include the hidden items, since from the player's view they are a random sample of what is left. (R − m)/(R − 1) is the finite-population correction: drawing without replacement makes the sum vary less.

*Bots* (one lot each; several per round; each is informed with probability α, default 0.3):
- **Noise trader:** values the contract at fair + U(−sd, sd). Buys at your ask if its value is above it, sells at your bid if below.
- **Informed trader:** has peeked at the next item to be revealed. Its value G = revealed + peeked + (m − 1)·(mean of the unseen cards without the peeked one). Trades only when your quote is wrong relative to G.
- At your position limit (default ±5), the side that would push you past it is pulled.

Against noise traders, a half-width h earns h per trade, and the chance of a trade on each side falls as (sd − h)/(2·sd), so very wide markets trade rarely. Informed traders trade exactly when you are wrong, so narrow markets lose to them. The best width is in between and grows with α. The lab measures this by simulation.

*Quote rules.* Bid below ask, and at most 2 standard deviations wide (`-o max_width=` in sds), so you can't avoid trading by quoting an absurd market.

*P&L breakdown (exact).* For trade i with sign s (+1 you bought, −1 you sold), price p, public fair value F at the time, trader's value G (= F for noise traders) and settlement S:

```
s·(S − p) = s·(F − p)  +  s·(G − F)  +  s·(S − G)
  P&L         spread     adverse selection   luck
```

The three parts telescope, so their sums add up to the total P&L exactly, which is the phase's test.

*Questions per round:* fair value (±0.05); standard deviation (±10%); from round 2, your P&L marked at the new fair value (±0.5); the quote (interval: right if fair value is inside your market; the error is an interval score with α = 0.5, so tight markets around fair value score best). Round 1 also asks for the chance the sum reaches a threshold (a binary option, priced exactly from the distribution, ±0.03).

*End of round:* the settlement value, every trade (who, side, price, fair value, the informed trader's view) and the breakdown into spread, adverse selection and luck, including by trader type.

*Lab:* exact statistics for dice and card sums, with and without replacement; simulated P&L per game against quote width and informed share, split into spread income and adverse selection.

**[DECISION] D-024: P&L in exact fractions.** Prices are converted to `Fraction` (a typed 9.3 becomes 93/10), so the breakdown can be tested for exact equality rather than closeness.

**[DECISION] D-025: the quote is scored on fair value and width, not on profit.** Profit in a single game is mostly luck. Being centred on fair value and not too wide is the skill; the breakdown at the end shows how the economics played out.

**[DECISION] D-026: interval answers can have a maximum width** (`params["max_width"]`), checked when typed.

**[WORK] Phase 4 built.** Package `src/edge_engine/modules/market/`: `contract.py` (fair value, variance with the finite-population correction, the exact distribution for dice and cards, the informed trader's value), `bots.py` (noise and informed traders, the position limit, `run_round`, the exact P&L breakdown), `module.py` (`MarketMaking`), `lab.py` (`edge-engine lab market`). Terminal: interval answers with a maximum width and `@` as a separator (D-026). 231 tests (44 new), all passing in under 5 s; ruff clean.

The "Done when" checks:
- A full game against mixed flow: a scripted player who answers correctly and quotes fair ± sd/2 completes all four rounds with every answer right, and the summary shows the settlement, the trades and the breakdown.
- The breakdown adds up exactly: over 25 random games (dice and cards, 40% informed, random off-centre quotes), spread + adverse + luck equals the total P&L as fractions, the total equals cash + position × settlement, noise trades have zero adverse selection, and noise + informed totals equal the whole.

Other checks: the distribution, fair value and variance against brute-force enumeration (dice, and cards with some revealed); the three-card variance over all 22,100 hands equals 3·14·49/51; the research notes' figures (10.5 and 8.75 for 3 dice, 7 and 14 for one card, ≈ 40.4 for three cards); the informed value equals the conditional mean; at half-width sd/2 noise traders trade with probability 1/2 (simulated within 4 SE); informed traders never trade against a market containing their value and always trade against one that doesn't; the position limit holds.

*Found while building:* my first informed-trader test said a peeked 6 makes 4 dice worth 17.5; it is 6 + 3·3.5 = 16.5, and the code was right. The lab's first, coarse grid of widths did not show informed traders widening the best market, so I added finer widths before stating it: the best half-width moves from 0.5 sd to about 0.6 sd for both dice and cards.

*Left for later:* several related contracts at once (sum, maximum, product) with consistency checks, Fermi-estimate markets, quotes for more than one lot, and an inventory-aware "fair" quote to score skew against.

---

## 2026-11-23 — Phase 5: Poker

**[DESIGN] Phase 5 design.**

*Games for the solver.*
- **Kuhn poker:** cards J, Q, K; ante 1; one betting round, bet size 1. Actions: p (check or fold), b (bet or call).
- **Leduc Hold'em** (Southey et al., 2005): cards J, J, Q, Q, K, K; ante 1; two rounds with bet sizes 2 and 4, at most a bet and a raise per round; one public card after round 1. A pair with the public card wins, else the higher card; equal ranks split. Actions: c (check or call), r (bet or raise), f (fold).

Cards are tracked by rank, with exact deal weights for card removal (Leduc: P(c1) = 1/3, P(c2 | c1) = (2 − [c2 = c1])/5, P(public | c1, c2) = (2 − [p = c1] − [p = c2])/4), giving 6 deals for Kuhn and 27 for Leduc.

*CFR solver* (`cfr.py`). The game tree is built once over public betting histories. Every node holds numpy arrays over all deals: chance weight, both players' reach, the info-set index of the player to act, and the payoff at terminals. One iteration of **CFR+** is a forward pass (reach probabilities under the current strategy), a backward pass (expected values), then regret updates `r(I, a) += Σ over deals in I of (opponent reach × chance) × (v(child a) − v(node))`, clipped at zero. Strategies come from regret matching on the positive regrets. The average strategy is weighted linearly by iteration, which is what makes CFR+ converge fast.

*Checking convergence.* A **best response** pass against a fixed strategy: at each of the responder's info sets, pick the action with the highest counterfactual value summed over the deals in that info set. Exploitability = (BR value of player 1 + BR value of player 2) / 2; it is 0 exactly at a Nash equilibrium. Kuhn must reach the game value −1/18 with near-zero exploitability, and its strategy must fall in Kuhn's one-parameter family (bet J with α, K with 3α, call a bet with Q with α + 1/3). Leduc must reach low exploitability.

*Hand evaluator* (`evaluator.py`). One pass over 5 to 7 cards: rank counts, suit counts, flush and straight checks (including the wheel A-2-3-4-5), giving a score that sorts category first, then the relevant ranks. Seven-card hands are evaluated directly, not as 21 five-card subsets. Checks: all 2,598,960 five-card hands give the known category counts (a slow test, run in CI), seven-card category frequencies against the known counts out of 133,784,560 by sampling, and tie-break cases.

*Equity* (`equity.py`). Exact enumeration of the remaining board for two known hands (990 boards from the flop, 44 from the turn), and Monte Carlo with standard error for preflop or against a random hand. Ties count half.

*Modes.*
- **kuhn / leduc:** play against a bot. The bot is the CFR equilibrium (default), or an exploitable style (`bot=station` always calls, `bot=maniac` always bets). Each of your decisions is scored against the **best-response value** of each action against that bot's actual strategy, given your card and what you have seen. So the truth is what beats *this* opponent, and against the exploitable bots the best play is not the equilibrium play.
- **spots:** Hold'em situations with both hands shown (an all-in): outs for the next card, equity to the river (exact), pot odds, call or fold (EV = equity × final pot − call), minimum defence frequency, and the break-even bluff frequency. The explanations compare the rule of 2 and 4 with the exact answer.

*Lab:* CFR convergence for Kuhn and Leduc (exploitability and value against iterations), the Kuhn strategy against theory, seven-card category frequencies, and some equity matchups.

**[DECISION] D-027: Hold'em as a spot trainer this phase; full multi-street play against rule-based bots deferred.** Every scored decision in this project has an exact truth. In a full Hold'em hand against a heuristic bot there isn't one: the best action depends on the bot's whole future strategy and range. Spots where both hands are shown have exact answers, while Kuhn and Leduc give the "play against a bot, scored exactly" experience. A heads-up limit Hold'em game against rule-based bots is recorded as follow-up work.

**[DECISION] D-028: numpy for the solver.** Vectorising each tree node over all deals keeps a CFR iteration on Leduc to a few milliseconds in Python. numpy is now a runtime dependency (D-009 said it would be added when first used).

**[DECISION] D-029: slow tests are opt-in.** `@pytest.mark.slow` tests (the exhaustive 5-card count) are skipped locally unless `--runslow` is given; CI always runs them.

**[DECISION] D-030: Phase 5 is stacked on the Phase 4 branch**, because PR #4 was still open. Its PR is retargeted to `main` once PR #4 is merged.

**[WORK] Phase 5 built.** Package `src/edge_engine/modules/poker/`: `games.py` (Kuhn and Leduc rules, deal weights by rank), `cfr.py` (tree over public histories with per-deal numpy arrays; forward and backward passes, CFR+, best response, exploitability), `evaluator.py` (5-7 card scores), `equity.py` (exact enumeration, Monte Carlo, outs, two-card hit chance), `module.py` (`Poker`: kuhn, leduc and spots modes; equilibrium, station and maniac bots), `lab.py` (`edge-engine lab poker`). Scoring: decision questions accept a tolerance, so EVs within it count as tied. numpy is now a runtime dependency (D-028), and a `slow` marker with `--runslow` is added; CI runs everything (D-029). 260 tests pass in about 10 s, plus the slow exhaustive test (8 s); ruff clean.

The "Done when" checks:
- **CFR converges.** Kuhn reaches −1/18 within 0.0005 with exploitability under 0.0002, and its strategy falls inside Kuhn's family (K bet = 3α, Q call = α + 1/3, second player's bluff and call 1/3). Leduc: exploitability decreases across checkpoints to under 0.0005, and the value is −0.0856, the published figure. Tree sizes match the literature: 12 and 288 information sets.
- **The evaluator** gives the known counts for all 2,598,960 five-card hands, the known seven-card frequencies by chi-square, and the same score as the best of 21 subsets for 3,000 random seven-card hands, plus ordering, kicker and two-trips cases.
- **Equity** from Monte Carlo agrees with exact enumeration within 4 SE on four spots; the two players' shares always sum to 1; from the turn, equity equals outs/44 exactly.

Other checks: the best response equals the best of all 64 pure strategies in Kuhn (against uniform and equilibrium opponents); Leduc rules (legal actions, raise cap, round change, contributions, payoffs); a perfect player is right on every decision in all three modes; over 600 hands, best-response play against the station and maniac bots earns its computed value (+1/3 per hand) within 0.15; the best play differs by bot (never bluff the station, call the maniac with a Q).

*Found while building:*
- Against the equilibrium bot, mixed actions differ only by CFR's rounding (0.0004 chips), so a correct bluff was marked wrong. Decisions now have a tie tolerance, and the explanation says when actions are indifferent, which is the point of a mixed equilibrium.
- Two of my test expectations were wrong (a full house that also held a pair of aces; a "maniac" value I wrote into the docs before computing it, +0.42, when it is +1/3); the code was right in both.

*Left for later:* heads-up Hold'em against rule-based bots (D-027), Monte Carlo CFR for bigger games, a 13×13 range grid for range questions, and win-rate variance tools.

---

## 2026-11-23 — Phase 6: Backgammon

**[DESIGN] Phase 6 design.**

*Board* (`board.py`). Always stored from the side to move: 24 points (index 0 = that player's 1-point), positive numbers are the mover's checkers and negative the opponent's, plus both bars and both borne-off counts. The mover always moves from 24 towards 1 and off; `flip()` turns the board round for the other player. Start: 2 on the 24-point, 5 on the 13, 3 on the 8, 5 on the 6 (167 pips each).

*Moves.* A single checker move with die d: from the bar first (entering on point 25 − d, if the opponent has fewer than two there); otherwise from any point to a point that is not blocked (two or more opponent checkers); landing on a single opponent checker hits it. Bearing off is allowed only when all 15 checkers are in the home board: with the exact die, or with a larger die from the highest occupied point. A play uses as many dice as possible (four for doubles). If only one die can be used, it must be the larger one when possible. Plays that reach the same position count once.

*Checking the move generator* ("perft-style"). A second, deliberately simple generator (absolute board, a list of 15 checker positions per side, every rule checked directly, every die order tried) must produce the same set of resulting positions for every roll over hundreds of positions from random games. Depth-1 and depth-2 counts from the opening are recorded. Hand-made cases cover: a closed board (no entry), the larger-die rule, the bear-off rules, hitting from the bar, and doubles that cannot all be played.

*Shots.* The number of the 36 rolls that hit a given blot is counted with the real move generator for the opponent, so blocked points and bar rules are taken into account. With an empty board in between it must give the classic table: 11, 12, 14, 15, 15, 17, 6, 6, 5, 3, 2, 3 for distances 1-12.

*Bots* (`bots.py`):
- **random:** any legal play.
- **heuristic (0-ply):** the play whose resulting position scores best on a hand-written evaluation: pip lead, exposure of blots (the number of rolls that could hit each, weighted by how far back a hit sends it), made home points and the bar point, anchors, the longest prime, opponent checkers on the bar, and checkers off.
- **1-ply:** for each candidate, average over the opponent's 21 distinct rolls of their best reply under the same evaluation.
- **td:** a small neural network (198 inputs in Tesauro's encoding, 40 hidden units) trained by temporal-difference learning in self-play, with numpy. `edge-engine lab backgammon -o train=N` trains it and saves the weights under `~/.edge_engine/`.

*Bear-off and the cube* (`bearoff.py`). With all checkers in the home board and no contact, each side's number of rolls to finish is a distribution, computed exactly by recursion (each roll is played to minimise expected rolls) and cached. P(the player on roll wins) = Σₙ P(on roll needs exactly n) × P(other needs more than n − 1). This is the standard one-sided method: exact under minimum-expected-rolls play, which is very close to the best play for winning chances.

Cube decisions use the dead-cube, money-play maths (no gammons in a bear-off where both sides have borne off):
- No double: 2p − 1.
- Double: the opponent picks the smaller of take, 2(2p − 1), and drop, +1.
- Take when the doubler's chance is at most 75% (the 25% take point).

The explanations also cover why owning the cube moves the real decisions (the doubling window of roughly 70-78%). For longer races the **8-9-12 rule** is used: lead = (trailer's pips − leader's pips) / leader's pips; double at 8% or more, redouble at 9%, take up to 12%. These questions are marked as rule-of-thumb answers.

*Modes.*
- **play:** a game against a bot. Each of your plays is a decision scored against the engine's evaluation. That is the engine's opinion, not exact equity, and is labelled so. When you leave a blot you are asked how many rolls hit it (exact).
- **shots:** positions from random games: pip counts, and how many rolls hit your blot.
- **cube:** bear-off positions (exact winning chances; double? take?) and races (8-9-12 rule).

**[DECISION] D-031: checker play is scored against the engine's evaluation, not exact equity.** Backgammon equity is not computable exactly in the middle game. The scores are honest about being an engine's opinion. The exact parts (shots, pip counts, bear-off chances, dead-cube decisions) carry the teaching.

**[DECISION] D-032: the TD network is optional.** Training takes minutes in pure Python, so it is a lab command with saved weights, not part of the default game. Its test is marked slow.

**[WORK] Phase 6 built.** Package `src/edge_engine/modules/backgammon/`: `board.py` (positions from the side to move, `flip`, pips, legal plays, results, a text board), `shots.py` (hitting rolls by the real move generator, the open-board table), `bots.py` (evaluation, random, greedy 0-ply, 1-ply, `play_game`), `bearoff.py` (exact one-sided distributions, win chances, dead-cube values, the 8-9-12 rule), `td.py` (196-40-1 network, gradient, TD(0) self-play training, save and load), `module.py` (`Backgammon`: play, shots, cube), `lab.py` (`edge-engine lab backgammon`, optional training). Terminal: long decision lists show "a number from 1 to n" and only the best play in the reveal. 282 tests pass in about 16 s, plus the slow ones (exhaustive five-card count, TD training); ruff clean.

The "Done when" checks:
- **Perft-style move counts:** the fast generator and an independent reference generator give identical sets of resulting positions for all 21 rolls in 250 positions from random games (5,250 cases), and for the opening (447 plays in total; 16 for 3-1). Hand-made positions check the closed board, the larger-die rule, the bear-off rules (including bearing off from the highest point with a larger die) and the use-both-dice rule.
- **The shot table** 11, 12, 14, 15, 15, 17, 6, 6, 5, 3, 2, 3 is reproduced by the move generator; blocked points and bar entry are tested separately.
- **The bot beats random:** the heuristic bot wins at least 30 of 40 games (it won 37 of 40 in the lab and about 90% in general). The TD network, trained for 1,000 self-play games, wins at least 32 of 40 (slow test).

Other checks: bear-off expectations by hand (1.25 rolls for one checker on the 6-point; 4/36 to clear two from the 6-point in one roll), the bear-off win chance against a 3,000-game simulation under the same policy (within 4 SE), cube values (take and drop equal at 75%; with a dead cube, doubling beats not doubling exactly when p > 50%), the 8-9-12 rule, the TD gradient against finite differences, a TD update moves the estimate towards its target, and full sessions in all three modes.

*Found while building:*
- At a learning rate of 0.1 the TD network had not started to learn after 1,500 games; at 0.3 it learns within 1,000 for every seed tried, and beats the heuristic bot in 55-82% of games after 1,000-2,500. The default is 0.3.
- A turn with exactly one legal play produced a "choice" of one option; forced plays are now made automatically.
- Five of my own test expectations were wrong and the generator right: a roll stored as (1, 3), a bear-off with two legal results, a position where both dice could not be used, a 6-2 that still hits by playing the 2 first, and 14 (not 12) rolls entering from the bar onto a blot on the 3-point.

*Left for later:* a live-cube model (cube ownership, gammons) and cube decisions inside play mode, Keith count, rollouts for middle-game positions, and a "which play leaves the fewest shots" question.

---

## 2026-11-23 — Phase 7: Chess

**[DESIGN] Phase 7 design.**

*Board* (`board.py`). A 0x88 board: 128 squares, of which the 64 with `square & 0x88 == 0` are real, so "off the board" is a single bit test. Pieces are signed ints (white positive: pawn 1 … king 6). The board also tracks the side to move, castling rights (4 bits, cleared by a mask whenever a king or rook square is touched), the en passant square, the move clocks, both king squares, and a Zobrist hash (random 64-bit keys from our RNG, updated with each move). Moves are packed ints (from, to, promotion, flags).

*Legal moves.* Generate pseudo-legal moves (pawn pushes, double pushes, captures, en passant, promotions to four pieces, knight and king steps, sliding rays, castling through empty and unattacked squares), then make each one and reject it if the mover's king is attacked; undo restores everything from a stack. FEN in and out; SAN out (disambiguation, `x`, `=Q`, `+`, `#`, `O-O`) and in (matched against the legal moves); a PGN reader that skips headers, comments, variations and annotation marks.

*Perft* (the "Done when" check). Counting all legal move sequences to a fixed depth must match the published numbers for the standard test positions (chessprogramming.org): the start position, "Kiwipete" and positions 3-6, which between them exercise castling (including through check), en passant (including the pinned case), promotions and checks. Fast depths run in every test; deeper ones are a slow test.

*Engine* (`engine.py`). Negamax with alpha-beta pruning; iterative deepening; a transposition table keyed by the Zobrist hash (depth, score, bound, best move); quiescence search over captures with stand-pat; move ordering (table move first, then captures by most valuable victim / least valuable attacker, killer moves, history scores); mate scores that prefer shorter mates; draws by the fifty-move rule, repetition and insufficient material. Evaluation: material (100/320/330/500/900), piece-square tables (the "simplified evaluation function"), a king table that blends from middle game to endgame by remaining material, and +30 for the bishop pair.

*Game review* (`review.py`), with the formulas Lichess publishes:

```
win%     = 50 + 50 × (2 / (1 + e^(−0.00368208 × centipawns)) − 1)
accuracy = 103.1668 × e^(−0.04354 × (win% before − win% after)) − 3.1669
```

Each position of the game is searched once. A move's "before" is the best score in its position and its "after" is the negated score of the next position, both for the player who moved. Mates count as ±10,000 centipawns. Classes, by win% lost: **Best** (the engine's own move), **Excellent** < 2, **Good** < 5, **Inaccuracy** < 10, **Mistake** < 15, **Blunder** ≥ 15. The 5/10/15 thresholds equal Lichess's 0.1/0.2/0.3 on its −1 to +1 winning-chances scale. Game accuracy is the plain mean of move accuracies (Lichess blends weighted and harmonic means; ours is simpler, and says so).

*Modes.*
- **play:** a game against the engine. Each of your moves is a decision scored by the engine (each legal move searched to the set depth), labelled as the engine's opinion. The end of the game shows the review of your moves and the game in PGN.
- **drills:** board vision with exact answers. How many legal moves a given piece has; the material balance; how many checking moves the side to move has; mate-in-one puzzles from a built-in set, each verified by exhaustive search in the tests.

*Lab:* the perft table, the engine on the mate puzzles, and the review of a game (a built-in public-domain miniature, Morphy's "Opera Game" of 1858, or any PGN file with `-o pgn=path`).

**[DECISION] D-033: 0x88 mailbox rather than bitboards.** Python ints make bitboards possible, but 0x88 is easier to read and to get right, and perft correctness matters more than speed here.

**[DECISION] D-034: the engine is weak and says so.** Pure-Python search reaches about 3-4 plies in a few seconds, far below Stockfish. Reviews and move scores are labelled as this engine's opinion at the stated depth. Stockfish is never bundled (D-003).

**[WORK] Phase 7 built.** Package `src/edge_engine/modules/chess/`: `board.py` (0x88 board, pseudo-legal generation, make/undo stack, Zobrist hashing, legal moves and captures, outcomes, FEN, SAN in and out, PGN reader and writer, perft), `engine.py` (evaluation with piece-square tables and a blended king table; negamax alpha-beta, iterative deepening, transposition table, quiescence, check extension, move ordering; per-move scoring), `review.py` (Lichess win% and accuracy, move classes, game review and its table, the Opera Game), `module.py` (`Chess`: play and drills), `lab.py` (`edge-engine lab chess`). Terminal: a typed answer that exactly matches a choice or key wins before case-insensitive matching (so `bxc3` and `Bxc3` stay different), and questions can give their own hint. 313 tests pass in about 22 s, plus 8 slow ones; ruff clean.

The "Done when" checks:
- **Perft:** all six standard positions match the published counts at depths 1-3 in every run and at depth 4 in the slow test (start, Kiwipete, positions 3-6; about 10.5 million positions in 23 s). They matched on the first run.
- **Legal, sensible games:** the engine finds every built-in mate in one (each puzzle is also checked exhaustively to have a mate), a mate in two with two rooks, and wins a hanging queen. In games against random moves every engine move is legal, and it is ahead by at least 5 points of material, or has won, by move 30.
- **PGN review:** the Opera Game parses (33 plies, queenside castling, checks and mate) and is reviewed; the final Rd8# and the queen sacrifice Qb8+ are classed Best; a PGN file given with `-o pgn=` is reviewed by the lab.

Other checks: incremental Zobrist hash against recomputation and undo after every legal move in 15 random games; FEN round trips; SAN round trips (SAN and UCI) for every legal move in 10 random positions; castling SAN, promotions, file and rank disambiguation; en passant removes the right pawn; castling rights after a rook move; no castling through an attacked square; checkmate, stalemate, insufficient material, fifty-move rule, threefold repetition; PGN with comments, variations and annotation marks; the Lichess formulas (50% at 0 cp, symmetry, 63.6 and 40.0 accuracy for 10- and 20-point drops) and the class thresholds; full trainer sessions.

*Found while building:*
- Before the check extension, the engine could not see a mate just past its horizon: before 16.Qb8+ in the Opera Game it gave 45% instead of a forced mate, because mates were only detected inside the main search. Searching one more ply when in check fixed it, at almost no cost.
- Typing a move that wasn't legal gave the message "choose a number from 1 to 28", which is wrong for chess; questions can now supply their own hint and error text.
- One test position of mine was illegal (Black already in check with White to move); the code was right.

*Left for later:* a stronger engine (null-move pruning, late-move reductions, better evaluation), "find the best move" puzzles from your own blunders, an evaluation-graph view, and the Lichess game-accuracy weighting.

---

## 2026-11-23 — Phase 8: Training wheels and a Claude tutor

**[DECISION] D-035: Phase 8 adds a learning layer across all seven games, in two parts.** 8a, training wheels: a learning mode that shows the answer before you act. 8b, a Claude tutor that answers questions about the current position, built on 8a. *Why:* the scored modes test you; there was no mode for learning a game you don't know yet. Requested by the user.

**[DECISION] D-036: scored modes stay predict-then-reveal.** Training wheels is a separate mode with a separate log, so it never affects scores, stats or the adaptive question mix. In scored modes the tutor (8b) may give a hint that does not reveal the answer before you commit, and such answers are logged as "assisted"; full explanations come after the reveal. *Why:* the research notes' "crutch problem": seeing answers before committing stops you learning, so it must be a deliberate choice.

**[DESIGN] 8a, training wheels.** `edge-engine play <game> --wheels`.
- **Before each question:** the truth (the same exact truth function as the scored mode), the worked explanation and the technique tip, plus any extra teaching the game adds through a new optional hook, `lesson(state, question)`.
- **After you type an answer, before it counts:** what it would score against the truth, plus game-specific feedback from a second optional hook, `judge(state, question, answer)`. Examples: the growth rate of your proposed bet in the coin flip, how many shots your chosen backgammon play leaves, the expected profit of your quote against noise traders. If the answer is not right you may keep it (Enter) or type another; nothing is played until you confirm.
- **Forecast questions** (about an outcome that hasn't happened yet) never show their outcome in advance.
- **Separate log:** sessions are logged under `<game>:wheels`, so `edge-engine stats` shows practice separately and the mental-maths adaptive weights never see it.
- **Time:** modules receive `wheels=True` in their config, so they can drop time pressure (mental maths becomes untimed).

Both hooks have empty defaults, so a game gets the generic behaviour without any changes.

**[WORK] 8a built: training wheels.** `--wheels` on `edge-engine play`. The loop passes each question an `Aid` (truth, explanation, lesson, and a judge that scores an answer before it counts); forecasts carry no truth. Wheels sessions are logged as `<game>:wheels`. New optional hooks `lesson` and `judge` on the game contract. The terminal shows `learn:` lines before asking, and after an answer shows `check:` lines; a wrong answer, or any answer with game feedback, can be kept with Enter or replaced. Game-specific parts:
- Mental maths: untimed (a fixed 20 or the given number of questions).
- Coin flip: your bet's growth rate against Kelly's, with a warning when an over-bet shrinks you despite the edge.
- Market making: the exact expected profit per trader of your quote. For noise traders, the chance each side trades times the edge; for informed traders, averaged over every value the next item could take; then mixed by the informed share.
- Backgammon: the engine's top three plays with the shots each leaves, and the same for your choice.

The other games use the generic aid, whose explanations already carry the useful numbers (blackjack and poker EVs with chart and equilibrium hints, chess top moves). 321 tests pass (8 new); ruff clean.

Checks: the aid carries the truth for every question except forecasts; wheels sessions are logged separately and do not reach the adaptive history; a sprint under wheels runs the fixed 20 questions; the market judge matches the formula by hand (noise profit h(sd − h)/sd at a centred half-width h; informed loss −4/6 per trader against a ±1 quote on 4 dice); the terminal shows the lesson first and supports keeping, changing and comparing answers; the CLI flag and stats rows.

*Found while trying it:* a correct answer with useful feedback (a market quote's economics) was accepted immediately, so you could not compare widths. Answers with feedback now always offer "keep or try another".

**[DESIGN] 8b, the Claude tutor.** `--tutor` on `edge-engine play`; type `?` or `? question` at any prompt.
- **Grounding:** each request carries the screen, the question and its choices, and recent reveals. In training wheels it also carries the exact answer, explanation and lesson. The system prompt (cached) holds the tutor's rules and the game's public `docs/` explainer. The rules say every number must come from the game data or be simple arithmetic on it.
- **Scored modes:** the answer is never sent before the player commits ("Answer: HIDDEN"); the tutor is told to hint at the method; an answer given after a hint is marked *assisted* in the reveal, the summary and the history file (new `assisted` column, added automatically to old history files).
- **API:** the official `anthropic` SDK as an optional extra (`.[tutor]`, CI installs it); `claude-opus-5-5` by default (`--tutor-model`), effort low, streaming, the system prompt cached, the server-side refusal fallback on (`fallbacks: "default"`), a short rolling conversation (12 exchanges). Token use and an estimated cost are shown at the end. Credentials come from `ANTHROPIC_API_KEY` or an `ant auth login` profile and are never logged.
- **Failures never break a game:** missing package, credentials, network or a refusal show a one-line message and the game carries on.

**[DECISION] D-037: the tutor is a teaching layer, not a brain.** All truths stay in the from-scratch engines (D-003); Claude explains them. That keeps the project's rule intact and keeps the tutor's numbers right.

**[DECISION] D-038: tests never call the API.** A fake client records each request, so the tests check exactly what would be sent (e.g. no answer in scored mode) at no cost.

**[WORK] 8b built.** `src/edge_engine/tutor.py` (context, rules, request, streaming, usage and cost, error messages); the loop accepts an optional "assisted" flag from the ask function and stores it; the terminal handles `?`, passes reveals to the tutor and marks assisted answers; CLI flags `--tutor` and `--tutor-model`; `docs/phase-8-learning.md`. 331 tests pass (10 new); ruff clean.

Checks (fake client): in a scored session the request says the answer is hidden and does not contain it, the answer is marked assisted (in the results and in the database), and later answers are not; in training wheels the exact answer and explanation are sent and nothing is marked assisted; the request uses `claude-opus-5-5`, low effort, the refusal fallback and a cached system prompt that holds the rules and the docs explainer and nothing from `local-brain/`; the conversation and reveals carry over to the next question; cost arithmetic against the price table; credential and network errors and refusals give a message without breaking the game or marking the answer assisted; the tutor-off message; old history files gain the new column; the CLI end to end.

*Not checked here:* a live call to the API. No credentials were available in this environment, so the first real run will be the user's own; the request shape follows the current SDK (2.12) and its documentation.

*Found while building:* adding the assisted flag changed `ask` to return three values, which broke four existing tests that unpacked two; they now unpack three. My first fake client streamed words without their spaces; the tutor code was right.

---

## 2026-11-23 — Documentation: formulas in the README and every explainer

**[WORK] Typeset maths across the docs.** Each game section in the README now carries its key formula. The explainers for phases 0-8 have their formulas written as maths, inline `` $`…`$ `` and display ` ```math ` blocks, both of which GitHub typesets, plus derivations that had only been described in words. Examples: modulo bias and expected tries; the Fisher–Yates product; binomial moments; the Brier minimum; the identities behind each mental-maths technique; the Kelly first- and second-order conditions and the $`c(2-c)`$ parabola; the gambler's-ruin recurrence; the blackjack solver's recursions and split equation; the finite-population correction derived from the covariance; CFR and CFR+ updates and exploitability; counting derivations of all nine five-card categories; the shot-count formula; the TD update; 0x88, Zobrist and alpha-beta; the review formulas. Currency in prose is escaped (`\$`) so it is never read as maths. Every file was rendered with GitHub's own Markdown API to check that the maths is recognised and no price is swallowed. The README's games table lost its phase and status columns, and the Status section was removed at the user's request; a link to the foundations explainer moved to "How it works".

**[DECISION] D-039 (correction): the cost of 6:5 blackjack is 1.35%, not 1.39%.** The exact value is $`0.3 \times \tfrac{8}{169} \times (1 - \tfrac{8}{169}) = 0.01353`$; the explainer and the Phase 3 teaching PDF had used 0.98 instead of 0.953 for P(no dealer blackjack), and the test's tolerance (±0.0005 around 0.0139) was loose enough to pass either. Found while writing the formula out in full. The explainer and PDF are corrected, and the test now checks 0.01353 to ±0.00001. Earlier log entries that quote 1.39% are left as written.

*Checked while writing:* every worked number in the new formulas against the code or a direct calculation (the poker hand counts all reproduce 2,598,960 exactly; the backgammon shot formula gives 11, 12, 14, 15, 15, 17; the evaluation weights and the 6,200 phase constant match the code; the market-judge formula matches `quote_economics`).

**[WORK] Maths fix: no `\operatorname`.** GitHub's maths renderer refuses `\operatorname` ("The following macros are not allowed: operatorname"), which the explainers used 22 times (Var, SD, Cov, lcm, median, perft, legal, rotl, sig). All are now `\mathrm{…}`, which renders the same, and the one `\mathbin` became plain spacing. Reported by the user.
