# Edge Engine

Edge Engine is a set of small games for practising probability, mental arithmetic, bet sizing and game theory.
While you play, it asks you to estimate something, such as your equity in a hand, the dealer's chance of busting or how much to bet.
Then it shows the correct value and how far off you were.
Answers are logged, so you can see which kinds of question you're slow on or keep getting wrong.
The engines, solvers and bots are written from scratch in Python, using only the standard library and numpy.
No real money is involved.

---

## How it works

```
Game state → you are asked a question → you answer (timed)
           → the truth function computes the real value
           → reveal: your answer vs the truth, with a short explanation
           → score + log → per-category stats
```

Questions can be point estimates ("what is your equity?"), decisions ("hit or stand?"), probability forecasts (scored with the Brier score), intervals ("give a 90% range") or speed drills.

---

## Games

| Phase | Module | Main skills | Status |
|---|---|---|---|
| 0 | Foundations (+ dice demo) | Seeded RNG, probability, scoring, logging | Done |
| 1 | Mental Maths Speed | Arithmetic speed and accuracy | Done |
| 2 | Coin Flip with an Edge | Bet sizing, Kelly criterion, risk of ruin | Done |
| 3 | Blackjack | Conditional probability, card counting | Done |
| 4 | Market Making | Pricing, spreads, adverse selection | Done |
| 5 | Poker | Game theory, EV, ranges | Done |
| 6 | Backgammon | Dice probability, the doubling cube | Done |
| 7 | Chess | Search, evaluation, calculation | Done |

### Phase 1 — Mental Maths Speed
Timed arithmetic in the style of trading-firm tests: two-minute sprints, an 80-questions-in-8-minutes test with −1 for wrong answers, and untimed practice. Nine categories: addition, subtraction, multiplication, division, decimals, fractions, percentages, estimation and odds (including pot odds). The question mix adapts to the categories you are slowest on or get wrong most often, using your history. Every answer gets a worked explanation, plus a technique tip when you were wrong or slow. See [how it works](docs/phase-1-mental-maths.md).

```
edge-engine play mental                     # sprint
edge-engine play mental -o mode=test        # 80 in 8
edge-engine play mental -o categories=odds  # one category
```

### Phase 2 — Coin Flip with an Edge
A biased coin (60% heads) and a $25 bankroll. You have an edge, but betting too much still loses money over time. Each bet is scored against the Kelly bet, and at the end your bankroll is compared with Kelly, half-Kelly and double-Kelly betting on the *same* flips, with a fan chart of 1,000 simulated runs at your average bet size. In the unknown-edge mode the bias is hidden and you have to estimate it as you play (Bayesian updating with a Beta prior). A lab command prints exact growth rates, mean and median outcomes, drawdown and ruin risk for any coin. See [the maths](docs/phase-2-kelly.md).

```
edge-engine play kelly                          # 50 flips of a 60% coin
edge-engine play kelly -o flips=300 -o cap=250  # the classic experiment
edge-engine play kelly -o mode=unknown          # hidden bias
edge-engine lab kelly                           # no input needed
```

### Phase 3 — Blackjack
Configurable rules (number of decks, S17/H17, 3:2 or 6:5 payouts, double after split, surrender). Basic strategy is computed by a from-scratch EV solver, and the computed 6-deck chart matches the published chart in every cell for both S17 and H17. Count mode asks for the Hi-Lo running count, true count and bet before each hand, and scores decisions against the EVs of the cards actually left, so count-based plays (the Illustrious 18 and Fab 4) count as right. A drill mode trains fast counting. Every decision is scored by the EV it gave up, and the session ends with your most expensive mistakes. See [the maths](docs/phase-3-blackjack.md).

```
edge-engine play blackjack                  # basic strategy
edge-engine play blackjack -o mode=count    # count, bet, play
edge-engine play blackjack -o mode=drill    # counting drill
edge-engine lab blackjack                   # chart, edge by count, deviation indices
```

### Phase 4 — Market Making
"Make me a market" on the sum of dice or of cards dealt without replacement. You quote a bid and an ask, traders deal against you, the items are revealed one at a time, and you re-quote. Some traders have peeked at the next item. Fair value, variance (with the without-replacement correction) and the full distribution are computed exactly. At the end your P&L is split exactly into spread earned, losses to informed traders (adverse selection) and luck. The lab simulates P&L against quote width, showing why the spread has to widen when more traders are informed. See [the maths](docs/phase-4-market-making.md).

```
edge-engine play market                     # 4 dice, 30% informed traders
edge-engine play market -o contract=cards   # card sum, no replacement
edge-engine lab market                      # statistics and width economics
```

### Phase 5 — Poker
A from-scratch CFR+ solver finds the equilibrium of Kuhn poker (value −1/18, inside Kuhn's known family of mixed strategies) and Leduc Hold'em (value −0.0856), checked by exact best-response calculations. You can play both games against the equilibrium bot or against exploitable bots; each decision is scored against the best response to the bot you face, so you learn when to mix and when to exploit. A from-scratch hand evaluator (checked on all 2,598,960 five-card hands) and an exact equity calculator power a Hold'em spot trainer for outs, equity, pot odds, call-or-fold, minimum defence frequency and bluff break-even. See [the maths](docs/phase-5-poker.md).

```
edge-engine play poker                    # Kuhn poker against the equilibrium
edge-engine play poker -o mode=leduc      # Leduc Hold'em
edge-engine play poker -o mode=spots      # Hold'em spots
edge-engine lab poker                     # CFR convergence, evaluator, equity
```

### Phase 6 — Backgammon
A full rules engine (bar, blocks, hits, bearing off, the use-as-many-dice-as-possible and larger-die rules, gammons and backgammons), checked against an independent second move generator. Shot counting uses the real move generator, so blocked points count, and reproduces the classic 1-12 table. Play a game against a hand-written bot, a 1-ply search bot or a small TD-learning network trained by self-play. Drill pip counts and shots. Learn the cube with exact bear-off winning chances, the 25% take point and the 8-9-12 race rule. See [the maths](docs/phase-6-backgammon.md).

```
edge-engine play backgammon                  # a game against the bot
edge-engine play backgammon -o mode=shots    # pip counts and shots
edge-engine play backgammon -o mode=cube     # bear-off chances and cube decisions
edge-engine lab backgammon -o train=1500     # train the TD network
```

### Phase 7 — Chess
A from-scratch move generator (0x88 board, make/undo, Zobrist hashing, FEN, SAN, PGN) that matches the published perft counts for the six standard test positions. An alpha-beta engine with iterative deepening, a transposition table, quiescence search, a check extension and piece-square evaluation. Play it, with every move scored as win% lost. Drill board vision and mate-in-one puzzles with exact answers. Review any PGN with the Lichess win% and accuracy formulas and openly documented move classes. See [the maths](docs/phase-7-chess.md).

```
edge-engine play chess                    # play White against the engine
edge-engine play chess -o mode=drills     # board vision and mate in one
edge-engine lab chess -o pgn=game.pgn     # perft, engine checks, game review
```

---

## Getting started

Requires Python 3.10 or later and numpy.

```
git clone https://github.com/AimanxxAnsari/edge-engine.git
cd edge-engine
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
git config core.hooksPath githooks
```

```
edge-engine list                         # available modules
edge-engine play mental                  # mental maths sprint
edge-engine play kelly                   # bet sizing on a biased coin
edge-engine lab kelly                    # Kelly tables and simulations
edge-engine play blackjack               # basic strategy (mode=count to count cards)
edge-engine play market                  # make a market on a sum of dice
edge-engine play poker                   # Kuhn poker (mode=leduc, mode=spots)
edge-engine play backgammon              # a game of backgammon (mode=shots, mode=cube)
edge-engine play chess                   # play the chess engine (mode=drills)
edge-engine play dice --seed 7           # play; the same seed replays the same session
edge-engine stats                        # per-category results, slowest first
pytest                                   # run the tests (--runslow for the long ones)
```

Answers can be typed as `0.25`, `1/4` or `25%`. Type `s` to skip (where allowed) and `q` to stop. Module options are passed with `-o key=value`. History is saved to `~/.edge_engine/history.db` (change it with `--db`, or turn it off with `--no-log`).

## Project layout

```
src/edge_engine/
  rng.py        seeded xoshiro256** generator
  prob.py       n-choose-k, binomial, hypergeometric, Monte Carlo with standard error
  scoring.py    Brier score, interval score, EV lost, speed score
  core.py       question kinds and the module contract
  loop.py       predict → reveal → score → log
  storage.py    SQLite history
  terminal.py   terminal front end
  modules/      one file (or package) per game: dice (demo), mental, kelly, blackjack, market,
                poker, backgammon, chess
docs/           plan, log and a maths explainer per phase
```

## Status

All eight phases are done: foundations, Mental Maths Speed, Coin Flip with an Edge, Blackjack, Market Making, Poker, Backgammon and Chess. Everything runs in the terminal. The maths behind each phase is explained in `docs/`:

| Phase | Explainer |
|---|---|
| 0 | [Foundations](docs/phase-0-foundations.md) |
| 1 | [Mental Maths Speed](docs/phase-1-mental-maths.md) |
| 2 | [Coin Flip with an Edge](docs/phase-2-kelly.md) |
| 3 | [Blackjack](docs/phase-3-blackjack.md) |
| 4 | [Market Making](docs/phase-4-market-making.md) |
| 5 | [Poker](docs/phase-5-poker.md) |
| 6 | [Backgammon](docs/phase-6-backgammon.md) |
| 7 | [Chess](docs/phase-7-chess.md) |

Decisions and work done are recorded in [docs/log.md](docs/log.md), and the plan with each phase's "done when" checks in [docs/action-plan.md](docs/action-plan.md).

## Licence

MIT. See [LICENSE](LICENSE).
