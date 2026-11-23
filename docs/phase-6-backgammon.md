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
- enters checkers from the **bar** first (on point $`25 - d`$ for a die $`d`$, unless the opponent holds it with two or more);
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
- **A direct shot ($`1 \le d \le 6`$) is hit by 11 rolls**, plus one or two for every smaller combination that also reaches it:

```math
\text{shots}(d) = \underbrace{11}_{\text{a die shows } d} + \#\bigl\{(i, j),\ i \ne j,\ i, j \ne d : i + j = d\bigr\} + \#\bigl\{k \text{ doubles} : d \in \{2k, 3k, 4k\}\bigr\} .
```

  For $`d = 6`$: 11, plus 5-1, 1-5, 4-2, 2-4, plus 3-3 and 2-2, giving 17, the most dangerous distance.
- **From 7 away, only combinations hit**, so the chance falls off a cliff to 6 or fewer, and every point in between that you own removes some of them. Example: a blot 8 away is hit by 6-2, 5-3, 4-4 and 2-2 on an open board. If you hold the points 2 and 4 pips in front of the hitter, only 6-2 (playing the 2 first) and 5-3 are left: 4 rolls.

Two useful facts. A specific number comes up on at least one die in

```math
1 - \left(\tfrac56\right)^2 = \tfrac{11}{36} \approx 30.6\% \ \text{of rolls,}
```

and a roll moves, on average, counting doubles (which move four times):

```math
\mathbb{E}[\text{pips}] = \tfrac{30}{36} \cdot 7 + \tfrac{6}{36} \cdot (4 \times 3.5) = \tfrac{35}{6} + \tfrac{14}{6} = \tfrac{49}{6} \approx 8.17 .
```

The **pip count** is the total distance your checkers must travel to bear off, $`\sum_{p} p \cdot n_p + 25 \cdot n_{\text{bar}}`$ where $`n_p`$ is the number of your checkers on point $`p`$; the start is 167 for each side.

---

## 3. The bots

| Bot | How it plays | Strength |
|---|---|---|
| random | any legal play | — |
| greedy (default) | the play with the best score on a hand-written evaluation | beats random in about 90% of games |
| 1ply | for each of its best few plays, averages the opponent's best reply over all 21 rolls | stronger, about a second per move |
| td | a neural network trained by self-play | beats the greedy bot in most games after 1,000-2,500 training games |

The evaluation is a weighted sum of features of the position after a play:

```math
E = 0.1\,\frac{\text{pip lead}}{10} - \sum_{\text{blots } b} \frac{\text{shots}(b)}{36}\left(\tfrac12 + \tfrac{p_b}{24}\right) + 0.25\,(\text{home points}) + 0.2\,[\text{7-point}] + 0.15\,(\text{anchors}) + 0.12\,(\text{longest prime}) + 0.35\,(\text{opponent on bar}) + 0.1\,(\text{borne off}),
```

where a blot on point $`p_b`$ costs more the further back a hit would send it. For speed, $`\text{shots}(b)`$ here is a quick count that ignores blocked points, and blots only count while there is contact. The **1-ply** bot takes the 6 best plays by $`E`$ and scores each by averaging, over the opponent's 36 rolls, the negative of the opponent's best reply:

```math
\text{value}(\text{play}) = \frac{1}{36} \sum_{\text{rolls } r} -\max_{\text{reply to } r} E(\text{reply}) .
```

**Your plays are scored against the engine's evaluation.** That is the engine's opinion, not exact equity, which can't be computed in the middle game. The exact parts of this module (shots, pip counts, bear-off chances, dead-cube decisions) are where the scoring is exact.

### TD learning

The `td` bot is a small version of Tesauro's TD-Gammon (1992). The network takes the position $`s`$ after a play, encoded as 196 numbers $`x(s)`$ (4 inputs per point per player, plus bar and borne-off counts). It has one hidden layer of 40 sigmoid units and outputs the chance that the side that just played wins:

```math
V(s) = \mathrm{sig}\bigl(w_2 \cdot \mathrm{sig}(W_1 x(s) + b_1) + b_2\bigr), \qquad \mathrm{sig}(z) = \frac{1}{1 + e^{-z}} .
```

It plays both sides against itself, always choosing the play with the highest $`V`$. After each of its plays, its previous estimate $`V(s)`$ is moved towards its new one $`V(s')`$ (temporal difference, TD(0)):

```math
\theta \leftarrow \theta + \alpha\,\bigl(V(s') - V(s)\bigr)\,\nabla_\theta V(s) ;
```

at the end of the game, towards 1 for the winner and 0 for the loser. The gradient is ordinary back-propagation through the two sigmoid layers, checked against finite differences in the tests.

With a learning rate of 0.3, nothing seems to happen for the first few hundred games. Then the network quickly learns to win almost every game against random play, and after 1,000-2,500 games it beats the hand-written bot in 55-82% of games. With a learning rate of 0.1 it had still not taken off after 1,500 games.

---

## 4. The doubling cube

Before rolling, a player may double the stakes. The opponent either **takes** (plays on for twice the stake, and owns the cube) or **drops** (loses the current stake).

**The take point.** Ignoring gammons and future cube use (a "dead cube"), with the doubler winning with probability $`p`$, the taker's values per original unit are

```math
\text{drop} = -1, \qquad \text{take} = 2(1 - p) - 2p = 2 - 4p,
\qquad \text{take} \iff 2 - 4p \ge -1 \iff 1 - p \ge \tfrac14 .
```

**When to double (dead cube).** For the doubler,

```math
\mathrm{EV}(\text{no double}) = 2p - 1, \qquad
\mathrm{EV}(\text{double}) = \min\bigl(\underbrace{2(2p - 1)}_{\text{they take}},\ \underbrace{+1}_{\text{they drop}}\bigr),
```

since the opponent picks whichever is worse for you. With a dead cube, doubling beats not doubling exactly when $`p > \tfrac12`$, and it doubles your edge. In real play the cube is not dead: whoever owns it can redouble later, which is worth something. So players wait for a stronger position, and the usual doubling window in money play is about 70-78%. The cube is an **option**, and owning an option has value.

**Bear-off, exactly.** When both sides have all their checkers home and no contact is left, each side's number of rolls to finish has an exact distribution. For a position $`h`$ (the checkers on points 1-6), with $`a_n(h) = P(\text{exactly } n \text{ rolls})`$:

```math
a_0(\varnothing) = 1, \qquad a_n(h) = \sum_{\text{rolls } r} \frac{w_r}{36}\, a_{n-1}\bigl(h_r^*\bigr),
\qquad h_r^* = \arg\min_{\text{plays of } r} \mathbb{E}[\text{rolls left}],
```

where $`w_r`$ is 1 for doubles and 2 otherwise. The side on roll wins if it finishes in $`n`$ rolls while the other has not finished in $`n - 1`$:

```math
P(\text{win}) = \sum_{n \ge 1} a_n(\text{mine}) \Bigl(1 - \sum_{m < n} a_m(\text{theirs})\Bigr) .
```

Examples: one checker on the 6-point fails to come off only with 1-1, 1-2, 2-1, 1-3, 3-1, 1-4, 4-1, 2-3, 3-2 (9 rolls), so it needs $`1 + \tfrac{9}{36} = 1.25`$ rolls on average. Two checkers on the 6-point finish in one roll only with 3-3, 4-4, 5-5 or 6-6 ($`\tfrac{4}{36}`$).

**Long races: the 8-9-12 rule.** With pip counts $`L`$ (leader) and $`T`$ (trailer), the lead is

```math
\text{lead} = \frac{T - L}{L} .
```

Double at 8% or more, redouble at 9%, and the trailer should take up to 12%. It is a rule of thumb for long races, and the game says so.
