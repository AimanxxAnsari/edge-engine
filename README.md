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

Questions can be point estimates ("what is your equity?"), decisions ("hit or stand?"), probability forecasts (scored with the Brier score), intervals ("give a 90% range") or speed drills. A forecast $`p`$ of an event that turns out as $`o \in \{0, 1\}`$ scores

```math
\text{Brier} = (p - o)^2 ,
```

which is lowest on average when $`p`$ is your honest probability. The scoring rules and the random number generator are explained in [the foundations](docs/phase-0-foundations.md).

---

## Games

| Module | Main skills |
|---|---|
| Foundations (+ dice demo) | Seeded RNG, probability, scoring, logging |
| Mental Maths Speed | Arithmetic speed and accuracy |
| Coin Flip with an Edge | Bet sizing, Kelly criterion, risk of ruin |
| Blackjack | Conditional probability, card counting |
| Market Making | Pricing, spreads, adverse selection |
| Poker | Game theory, EV, ranges |
| Backgammon | Dice probability, the doubling cube |
| Chess | Search, evaluation, calculation |

### Phase 1 — Mental Maths Speed
Timed arithmetic in the style of trading-firm tests: two-minute sprints, an 80-questions-in-8-minutes test with −1 for wrong answers, and untimed practice. Nine categories: addition, subtraction, multiplication, division, decimals, fractions, percentages, estimation and odds (including pot odds). The question mix adapts to the categories you are slowest on or get wrong most often, using your history. Every answer gets a worked explanation, plus a technique tip when you were wrong or slow. A category with $`n`$ answers, $`w`$ of them wrong, taking $`s`$ seconds in total against a target of $`T`$ per question, is picked in proportion to

```math
\underbrace{\frac{w+1}{n+2}}_{\text{error rate}} \times \underbrace{\frac{(s + 2T)/(n+2)}{T}}_{\text{time ratio}} ,
```

mixed with a 25% uniform share so every category keeps appearing. See [how it works](docs/phase-1-mental-maths.md).

```
edge-engine play mental                     # sprint
edge-engine play mental -o mode=test        # 80 in 8
edge-engine play mental -o categories=odds  # one category
```

### Phase 2 — Coin Flip with an Edge
A biased coin (60% heads) and a \$25 bankroll. You have an edge, but betting too much still loses money over time. Each bet is scored against the Kelly bet, and at the end your bankroll is compared with Kelly, half-Kelly and double-Kelly betting on the *same* flips, with a fan chart of 1,000 simulated runs at your average bet size. In the unknown-edge mode the bias is hidden and you have to estimate it as you play (Bayesian updating with a Beta prior). A lab command prints exact growth rates, mean and median outcomes, drawdown and ruin risk for any coin. Betting a fraction $`f`$ of your bankroll on a coin that wins with probability $`p`$ (and $`q = 1 - p`$) grows it by

```math
g(f) = p \ln(1 + f) + q \ln(1 - f) \quad \text{per flip, which peaks at the Kelly fraction} \quad f^* = p - q = 2p - 1 .
```

See [the maths](docs/phase-2-kelly.md).

```
edge-engine play kelly                          # 50 flips of a 60% coin
edge-engine play kelly -o flips=300 -o cap=250  # the classic experiment
edge-engine play kelly -o mode=unknown          # hidden bias
edge-engine lab kelly                           # no input needed
```

### Phase 3 — Blackjack
Configurable rules (number of decks, S17/H17, 3:2 or 6:5 payouts, double after split, surrender). Basic strategy is computed by a from-scratch EV solver, and the computed 6-deck chart matches the published chart in every cell for both S17 and H17. Count mode asks for the Hi-Lo running count, true count and bet before each hand, and scores decisions against the EVs of the cards actually left, so count-based plays (the Illustrious 18 and Fab 4) count as right. A drill mode trains fast counting. Every decision is scored by the EV it gave up, and the session ends with your most expensive mistakes. The Hi-Lo count turns into a true count, and insurance pays only when tens are common enough:

```math
\text{TC} = \frac{\text{running count}}{\text{unseen cards} / 52}, \qquad \mathbb{E}[\text{insurance}] = \tfrac12\,(3\,P(\text{ten}) - 1) > 0 \iff P(\text{ten}) > \tfrac13 .
```

See [the maths](docs/phase-3-blackjack.md).

```
edge-engine play blackjack                  # basic strategy
edge-engine play blackjack -o mode=count    # count, bet, play
edge-engine play blackjack -o mode=drill    # counting drill
edge-engine lab blackjack                   # chart, edge by count, deviation indices
```

### Phase 4 — Market Making
"Make me a market" on the sum of dice or of cards dealt without replacement. You quote a bid and an ask, traders deal against you, the items are revealed one at a time, and you re-quote. Some traders have peeked at the next item. Fair value, variance (with the without-replacement correction) and the full distribution are computed exactly. At the end your P&L is split exactly into spread earned, losses to informed traders (adverse selection) and luck. The lab simulates P&L against quote width, showing why the spread has to widen when more traders are informed. For each trade ($`s = +1`$ if you bought, $`-1`$ if you sold) at price $`p`$, with fair value $`F`$ at the time, the trader's own value $`G`$ and settlement $`S`$:

```math
\underbrace{s(S - p)}_{\text{P\&L}} = \underbrace{s(F - p)}_{\text{spread}} + \underbrace{s(G - F)}_{\text{adverse selection}} + \underbrace{s(S - G)}_{\text{luck}} .
```

See [the maths](docs/phase-4-market-making.md).

```
edge-engine play market                     # 4 dice, 30% informed traders
edge-engine play market -o contract=cards   # card sum, no replacement
edge-engine lab market                      # statistics and width economics
```

### Phase 5 — Poker
A from-scratch CFR+ solver finds the equilibrium of Kuhn poker (value −1/18, inside Kuhn's known family of mixed strategies) and Leduc Hold'em (value −0.0856), checked by exact best-response calculations. You can play both games against the equilibrium bot or against exploitable bots; each decision is scored against the best response to the bot you face, so you learn when to mix and when to exploit. A from-scratch hand evaluator (checked on all 2,598,960 five-card hands) and an exact equity calculator power a Hold'em spot trainer for outs, equity, pot odds, call-or-fold, minimum defence frequency and bluff break-even. Facing a bet $`B`$ into a pot $`P`$:

```math
\text{equity needed to call} = \frac{B}{P + 2B}, \qquad \text{minimum defence frequency} = \frac{P}{P + B}, \qquad \text{bluff break-even} = \frac{B}{P + B} .
```

See [the maths](docs/phase-5-poker.md).

```
edge-engine play poker                    # Kuhn poker against the equilibrium
edge-engine play poker -o mode=leduc      # Leduc Hold'em
edge-engine play poker -o mode=spots      # Hold'em spots
edge-engine lab poker                     # CFR convergence, evaluator, equity
```

### Phase 6 — Backgammon
A full rules engine (bar, blocks, hits, bearing off, the use-as-many-dice-as-possible and larger-die rules, gammons and backgammons), checked against an independent second move generator. Shot counting uses the real move generator, so blocked points count, and reproduces the classic 1-12 table. Play a game against a hand-written bot, a 1-ply search bot or a small TD-learning network trained by self-play. Drill pip counts and shots. Learn the cube with exact bear-off winning chances, the 25% take point and the 8-9-12 race rule. If the doubler wins with probability $`p`$, dropping costs 1 and taking is worth $`2(1-p) - 2p`$, so

```math
\text{take} \iff 2 - 4p \ge -1 \iff 1 - p \ge \tfrac14 .
```

See [the maths](docs/phase-6-backgammon.md).

```
edge-engine play backgammon                  # a game against the bot
edge-engine play backgammon -o mode=shots    # pip counts and shots
edge-engine play backgammon -o mode=cube     # bear-off chances and cube decisions
edge-engine lab backgammon -o train=1500     # train the TD network
```

### Phase 7 — Chess
A from-scratch move generator (0x88 board, make/undo, Zobrist hashing, FEN, SAN, PGN) that matches the published perft counts for the six standard test positions. An alpha-beta engine with iterative deepening, a transposition table, quiescence search, a check extension and piece-square evaluation. Play it, with every move scored as win% lost. Drill board vision and mate-in-one puzzles with exact answers. Review any PGN with the Lichess win% and accuracy formulas and openly documented move classes:

```math
\text{win\%}(c) = 50 + 50\left(\frac{2}{1 + e^{-0.00368208\,c}} - 1\right), \qquad \text{accuracy} = 103.1668\, e^{-0.04354\,\Delta} - 3.1669 ,
```

where $`c`$ is the evaluation in centipawns and $`\Delta`$ the win% a move gave up. See [the maths](docs/phase-7-chess.md).

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
pip install -e ".[dev]"          # add ,tutor for the Claude tutor
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

## Training wheels

Add `--wheels` to any game to learn it instead of being tested on it:

```
edge-engine play blackjack --wheels
edge-engine play chess --wheels
```

Before each question you see the answer, how it is worked out and the technique tip. After you type an answer you see what it would score, plus game-specific feedback (your bet's growth rate, your quote's expected profit per trader, the shots your backgammon play leaves). Then you keep it or try another before anything is played. Nothing is timed, and practice is logged separately (as `<game>:wheels`), so it never changes your stats or the adaptive question mix.

## Claude tutor

The tutor is part of the terminal games. Add `--tutor` to any game, then type `?` or `? your question` at any prompt:

```
pip install -e ".[tutor]"
export ANTHROPIC_API_KEY=...         # or: ant auth login
edge-engine play poker --tutor
edge-engine play blackjack --wheels --tutor
```

Claude explains the numbers the game's own engines computed and is told never to invent its own. In training wheels it explains everything, including the answer. In scored modes it is never sent the answer before you commit: it hints at the method, and the answer is marked *assisted*. Requests go to Anthropic's API and contain the screen, the question and the game's public explainer from `docs/`. The session summary shows the token use and an estimated cost. Without the package or a key, every game works as before. Details: [docs/phase-8-learning.md](docs/phase-8-learning.md).

## Web app (in progress)

A browser version with real visuals is being built beside the terminal games, for personal use: run locally, or on a small AWS setup (pages on S3 and CloudFront, the Python server on EC2): card tables, chess and backgammon boards you can click, the Kelly bankroll and fan charts, and a market-making order ladder. The terminal games stay as they are, and both use the same engines and history. The Claude tutor stays in the terminal only.

The groundwork is done: a game can now be played one answer at a time (`Session` in `loop.py`), which a web page needs, and the terminal plays through the same code.

## Project layout

```
src/edge_engine/
  rng.py        seeded xoshiro256** generator
  prob.py       n-choose-k, binomial, hypergeometric, Monte Carlo with standard error
  scoring.py    Brier score, interval score, EV lost, speed score
  core.py       question kinds and the module contract
  loop.py       predict → reveal → score → log, as a step-by-step Session
  storage.py    SQLite history
  terminal.py   terminal front end
  tutor.py      the optional Claude tutor
  modules/      one file (or package) per game: dice (demo), mental, kelly, blackjack, market,
                poker, backgammon, chess
docs/           plan, log and a maths explainer per phase
```

## Licence

MIT. See [LICENSE](LICENSE).
