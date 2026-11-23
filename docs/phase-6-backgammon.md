# Phase 6 — Backgammon: dice, shots, races and the cube

```
edge-engine play backgammon                         # a game against the heuristic bot
edge-engine play backgammon -o bot=1ply             # a stronger, slower bot
edge-engine play backgammon -o mode=shots           # pip counts and shot counting
edge-engine play backgammon -o mode=cube            # bear-off chances and cube decisions
edge-engine lab backgammon                          # shot table, move counts, bear-off, cube
edge-engine lab backgammon -o train=1500            # train the TD network (about 25 s)
edge-engine play backgammon -o bot=td               # then play against it
```

You are X and move from 24 towards 1. The bot is O and moves from 1 towards 24. Choose a play by its number from the list, or type the moves (`24/18 13/8`).

---

## 1. The rules engine

The board is always stored from the side to move, so one move generator serves both players: it is turned round with `flip()` between turns. A legal play:
- enters checkers from the **bar** first (on point 25 − die, unless the opponent holds it with two or more);
- may not land on a point held by two or more opponent checkers, and **hits** a single opponent checker;
- **bears off** only when all 15 checkers are in the home board: with the exact number, or with a larger number from the highest occupied point;
- must use **as many dice as possible** (four for doubles), and if only one die can be used, the **larger** one if that is possible.

Different move orders that reach the same position count as one play. From the opening position the 21 rolls give 447 distinct plays (16 for 3-1, 75 for 2-2).

**Checking it.** A second move generator, written separately in the tests (a plain list of checker locations, every die order, the rules applied over finished sequences), must give exactly the same set of resulting positions. They agree on all 5,250 cases tested: 250 positions from random games × 21 rolls. Hand-made positions cover a closed board, the larger-die rule, the bear-off rules and the use-both-dice rule.

---

## 2. Shots

To count how many of the 36 rolls hit a blot, the game runs the opponent's real move generator for every roll and checks whether any legal play hits it. Points you hold block combination shots, and checkers on the bar have to enter first. With nothing in between, this reproduces the classic table:

| Distance | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Rolls that hit | 11 | 12 | 14 | 15 | 15 | 17 | 6 | 6 | 5 | 3 | 2 | 3 |

Two things to remember:
- **A direct shot (1-6 away) is hit by 11 rolls**, plus one or two for every smaller combination that also reaches it. So 6 away is the most dangerous (17).
- **From 7 away, only combinations hit**, so the chance falls off a cliff to 6 or fewer, and every point in between that you own removes some of them. Example: a blot 8 away is hit by 6-2, 5-3, 4-4 and 2-2 on an open board. If you hold the points 2 and 4 pips in front of the hitter, only 6-2 (playing the 2 first) and 5-3 are left: 4 rolls.

A useful fact: a specific number comes up on at least one die in 11 of 36 rolls (30.6%), and a roll moves 49/6 ≈ 8.17 pips on average, counting doubles.

---

## 3. The bots

| Bot | How it plays | Strength |
|---|---|---|
| random | any legal play | — |
| greedy (default) | the play with the best score on a hand-written evaluation | beats random in about 90% of games |
| 1ply | for each of its best few plays, averages the opponent's best reply over all 21 rolls | stronger, about a second per move |
| td | a neural network trained by self-play | beats the greedy bot in most games after 1,000-2,500 training games |

The evaluation scores: pip lead; each blot's exposure (the share of rolls that could hit it, weighted by how far back a hit sends it); home-board points and the 7-point; anchors in the opponent's home board; the longest prime; opponent checkers on the bar; checkers borne off.

**Your plays are scored against the engine's evaluation.** That is the engine's opinion, not exact equity, which can't be computed in the middle game. The exact parts of this module (shots, pip counts, bear-off chances, dead-cube decisions) are where the scoring is exact.

### TD learning

The `td` bot is a small version of Tesauro's TD-Gammon (1992). The network takes the position after a play (4 inputs per point per player, plus bar and borne-off counts: 196 numbers), has one hidden layer of 40 units, and outputs the chance that the side that just played wins. It plays both sides against itself. After each of its plays, its previous estimate is moved towards its new one (temporal difference, TD(0)); at the end, towards 1 for the winner and 0 for the loser.

With a learning rate of 0.3, nothing seems to happen for the first few hundred games. Then the network quickly learns to win almost every game against random play, and after 1,000-2,500 games it beats the hand-written bot in 55-82% of games. With a learning rate of 0.1 it had still not taken off after 1,500 games.

---

## 4. The doubling cube

Before rolling, a player may double the stakes. The opponent either **takes** (plays on for twice the stake, and owns the cube) or **drops** (loses the current stake).

**The take point.** Ignoring gammons and future cube use (a "dead cube"), with the doubler winning with probability p:

```
drop:  −1
take:  2·(1 − p) − 2·p = 2 − 4p   per original unit
take is right when 2 − 4p ≥ −1, i.e. when your chance 1 − p is at least 25%
```

**When to double (dead cube).** Not doubling is worth 2p − 1. Doubling is worth whichever is worse for you of 2·(2p − 1) (they take) and +1 (they drop). With a dead cube, doubling is right whenever you are the favourite, and it doubles your edge. In real play the cube is not dead: whoever owns it can redouble later, which is worth something. So players wait for a stronger position, and the usual doubling window in money play is about 70-78%. The cube is an **option**, and owning an option has value.

**Bear-off, exactly.** When both sides have all their checkers home and no contact is left, each side's number of rolls to finish has an exact distribution, computed by recursion over every roll (each roll played to minimise the expected number of rolls left). The chance the side on roll wins:

```
P(win) = Σ over n of  P(I need exactly n rolls) × P(they need more than n − 1)
```

Examples: one checker on the 6-point needs 1.25 rolls on average (9 rolls of 36 don't bear it off); two checkers on the 6-point finish in one roll only with 3-3, 4-4, 5-5 or 6-6.

**Long races: the 8-9-12 rule.** With pip counts L (leader) and T (trailer), the lead is (T − L)/L. Double at 8% or more, redouble at 9%, and the trailer should take up to 12%. It is a rule of thumb for long races, and the game says so.
