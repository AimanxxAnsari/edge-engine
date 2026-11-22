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
           → score + log → progress dashboard
```

Questions can be point estimates ("what is your equity?"), decisions ("hit or stand?"), probability forecasts (scored with the Brier score), intervals ("give a 90% range") or speed drills.

---

## Games

| Phase | Game | Main skills | Status |
|---|---|---|---|
| 0 | Foundations | Architecture, seeded RNG, scoring | Planned |
| 1 | Mental Maths Speed | Arithmetic speed and accuracy | Planned |
| 2 | Coin Flip with an Edge | Bet sizing, Kelly criterion, risk of ruin | Planned |
| 3 | Blackjack | Conditional probability, card counting | Planned |
| 4 | Market Making | Pricing, spreads, adverse selection | Planned |
| 5 | Poker | Game theory, EV, ranges | Planned |
| 6 | Backgammon | Dice probability, the doubling cube | Planned |
| 7 | Chess | Search, evaluation, calculation | Planned |

### 1. Mental Maths Speed
Timed arithmetic sprints in the style of trading-firm tests: two-minute sprints, an 80-questions-in-8-minutes simulator with penalties for wrong answers, and drills on fractions, percentages and odds conversion. Difficulty adapts to the question types that slow you down the most.

### 2. Coin Flip with an Edge
A biased coin (for example 60% heads) and a bankroll. You have an edge, but betting too much still loses money over time. Your bankroll is compared with Kelly and half-Kelly betting on the *same* flips, and there is a mode where you have to estimate the coin's bias as you play.

### 3. Blackjack
Configurable rules (number of decks, S17/H17, 3:2 or 6:5 payouts) and basic strategy computed from exact expected values. Includes a Hi-Lo counting trainer with running and true count, count-based strategy changes, and a review of how much EV each mistake cost.

### 4. Market Making
"Make me a market" on dice sums and hidden cards. You quote a bid and an ask, bots trade against you, information comes out one piece at a time and you re-quote. Some bots know more than you do. You learn fair value, spread width, skewing your inventory and adverse selection.

### 5. Poker
Moves from Kuhn poker (3 cards, fully solved) to Leduc Hold'em to heads-up Hold'em. A from-scratch CFR solver finds the optimal mixed strategies, and the trainer drills outs, equity, pot odds, minimum defence frequency and thinking in ranges.

### 6. Backgammon
A full rules engine, shot counting (how many of the 36 rolls hit a blot), pip-count drills and the doubling cube: when to double and when to take. A heuristic bot comes first, then a self-trained evaluator.

### 7. Chess
A from-scratch engine with move generation, alpha-beta search and position evaluation, plus a game-review mode that converts evaluations to win% and rates each move. No hidden information or dice, so it covers calculation and evaluation.

---

## Status

Early development. Games run in the terminal first. Each game is built end to end (engine, trainer, tests, docs) before the next one starts.

## Licence

MIT. See [LICENSE](LICENSE).
