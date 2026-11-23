# Phase 5 — Poker: game theory, hand strength and pot odds

```
edge-engine play poker                          # Kuhn poker against the equilibrium bot
edge-engine play poker -o bot=station           # ... against a calling station
edge-engine play poker -o mode=leduc            # Leduc Hold'em
edge-engine play poker -o mode=spots            # Hold'em spots: outs, equity, pot odds
edge-engine lab poker                           # CFR convergence, evaluator, equity
```

Keys: `k` check, `b` bet, `c` call, `f` fold, `r` raise.

---

## 1. Two small games that can be solved exactly

**Kuhn poker.** Three cards (J, Q, K), one each, ante 1. One betting round with a bet of 1: the first player checks or bets; facing a bet you call or fold. Harold Kuhn solved it in 1950.

**Leduc Hold'em.** Six cards (two each of J, Q, K), ante 1. Round one has bets of 2; then one public card is turned over; round two has bets of 4. At most a bet and a raise per round. A pair with the public card wins, otherwise the higher card; equal ranks split.

Both games are small: Kuhn has 12 information sets (what a player knows when acting) and Leduc 288. So an exact equilibrium can be computed, and every decision can be scored exactly.

**Value of a game.** A pair of strategies $`(\sigma_1, \sigma_2)`$ is a Nash equilibrium if neither player gains by changing alone. In a two-player zero-sum game every equilibrium gives the same expected payoff $`v`$ to the first player (the minimax theorem):

```math
v = \max_{\sigma_1} \min_{\sigma_2} u_1(\sigma_1, \sigma_2) = \min_{\sigma_2} \max_{\sigma_1} u_1(\sigma_1, \sigma_2) .
```

---

## 2. Counterfactual regret minimisation (CFR)

CFR plays the game against itself over and over. At every information set $`I`$ it keeps a **regret** for each action $`a`$: how much better that action would have done than the current mix $`\sigma^t`$, weighted by how likely the opponent and chance were to lead there (the *counterfactual* reach $`\pi_{-i}`$, which leaves out the player's own probabilities):

```math
r^T(I, a) = \sum_{t=1}^{T} \sum_{h \in I} \pi_{-i}^{\sigma^t}(h)\,\Bigl(v_i^{\sigma^t}(h \cdot a) - v_i^{\sigma^t}(h)\Bigr) .
```

The next strategy plays actions in proportion to their positive regret (*regret matching*), uniformly if none is positive:

```math
\sigma^{T+1}(I, a) = \frac{\max\bigl(r^T(I, a),\, 0\bigr)}{\sum_{a'} \max\bigl(r^T(I, a'),\, 0\bigr)} .
```

The **average** strategy over all iterations converges to a Nash equilibrium in two-player zero-sum games, because the total regret is bounded by the sum of these per-information-set regrets, and each grows only like $`\sqrt{T}`$. This project uses **CFR+**, which converges much faster:

```math
r^{t}(I, a) \leftarrow \max\Bigl(0,\ r^{t-1}(I, a) + \Delta^t(I, a)\Bigr), \qquad
\bar\sigma^T \propto \sum_{t=1}^{T} t \cdot \pi_i^{\sigma^t}(I)\, \sigma^t(I, \cdot) .
```

Regrets are floored at zero after every update (so an action that was bad early can recover quickly), the players update in turn, and iteration $`t`$ counts with weight $`t`$ in the average.

**Implementation.** The tree is built once over public betting histories. Every node holds arrays over all deals (6 in Kuhn, 24 in Leduc once impossible deals are removed), so one pass with numpy updates every deal at once. 1,000 iterations of Leduc take under a second.

**Checking the answer.** A **best response** is the most a player can win against a fixed strategy: at each of their information sets, pick the action with the highest value summed over the deals they can't tell apart. **Exploitability** is the average of the two best-response values:

```math
\varepsilon(\sigma) = \frac{1}{2}\Bigl(\max_{\sigma_1'} u_1(\sigma_1', \sigma_2) + \max_{\sigma_2'} u_2(\sigma_1, \sigma_2')\Bigr) \ \ge 0 .
```

It is zero exactly at an equilibrium, so it measures how far from solved a strategy is.

| Game | Iterations | Value (first player) | Exploitability |
|---|---|---|---|
| Kuhn | 100 | −0.05558 | 0.0012 |
| Kuhn | 3,000 | **−0.05556 = −1/18** | 0.00004 |
| Leduc | 100 | −0.0846 | 0.013 |
| Leduc | 1,500 | **−0.0856** | 0.00013 |

Both match the published game values. The best-response code is itself checked by brute force: in Kuhn, each player has 64 pure strategies, and the best of them always equals the computed best response.

---

## 3. What equilibrium play looks like (Kuhn)

The first player's equilibria form a family with one free parameter α between 0 and 1/3:

| Situation | Equilibrium | Found by CFR (α = 0.223) |
|---|---|---|
| First player bets J (a bluff) | α | 0.223 |
| First player bets K | 3α | 0.668 |
| First player bets Q | never | 0.000 |
| First player calls a bet with Q | α + 1/3 | 0.556 |
| Second player bets J after a check | 1/3 | 0.333 |
| Second player calls a bet with Q | 1/3 | 0.334 |

Two lessons:
- **Moving first is worth $`-\tfrac{1}{18}`$ per hand** even with perfect play.
- **At equilibrium, the hands you mix with are indifferent.** Against the equilibrium bot, checking and bluffing a J have exactly the same value; that is what stops the opponent from exploiting either. The game says so when it happens, and counts both as right.

**Indifference, worked through.** The second player holds a Q and faces a bet. The first player bets K with probability $`3\alpha`$ and J with probability $`\alpha`$ (never Q), so given a bet

```math
P(\text{bluff} \mid \text{bet}) = \frac{\alpha}{\alpha + 3\alpha} = \frac14 .
```

Calling risks 1 more chip to win a pot of 3 (two antes and the bet), compared with folding:

```math
\mathrm{EV}(\text{call}) - \mathrm{EV}(\text{fold}) = \tfrac14 \cdot 3 - \tfrac34 \cdot 1 = 0 .
```

The Q is exactly indifferent, for every $`\alpha`$, which is why the equilibrium is free to call with it only part of the time.

**Exploiting a weak opponent.** Against `bot=station` (always calls, never bets) the best play is to stop bluffing and bet your good hands. Against `bot=maniac` (always bets) you call down much lighter. In these modes your decisions are scored against the **best response to that bot**, so the equilibrium move is not always the best one. Over many hands, best-response play earns exactly +1/3 of a chip per hand against either bot (averaged over both seats), compared with 0 against the equilibrium.

---

## 4. Hand strength

The evaluator scores 5 to 7 cards in one pass. It counts ranks and suits, checks for a flush and a straight (including the wheel, A-2-3-4-5), and returns a number that sorts by category and then by the deciding ranks. Checks:
- All $`\binom{52}{5} = 2{,}598{,}960`$ five-card hands give the known counts, each of which can be derived by counting:

| Hand | Count | How to count it |
|---|---|---|
| Straight flush | 40 | $`10 \times 4`$ (10 high cards, 4 suits) |
| Four of a kind | 624 | $`13 \times 48`$ |
| Full house | 3,744 | $`13\binom{4}{3} \times 12\binom{4}{2}`$ |
| Flush | 5,108 | $`4\binom{13}{5} - 40`$ |
| Straight | 10,200 | $`10 \times 4^5 - 40`$ |
| Three of a kind | 54,912 | $`13\binom{4}{3} \times \binom{12}{2} \times 4^2`$ |
| Two pair | 123,552 | $`\binom{13}{2}\binom{4}{2}^2 \times 44`$ |
| One pair | 1,098,240 | $`13\binom{4}{2} \times \binom{12}{3} \times 4^3`$ |
| High card | 1,302,540 | $`\bigl(\binom{13}{5} - 10\bigr)(4^5 - 4)`$ |

- Seven-card category frequencies match the known counts out of 133,784,560 (chi-square test).
- For thousands of random 7-card hands, the direct score equals the best of the 21 five-card subsets.

---

## 5. Equity, outs and pot odds

**Equity** is your share of the pot if the hand were played to the end, averaged over every way the board can finish:

```math
\text{equity} = P(\text{win}) + \tfrac12 P(\text{tie}) .
```

With both hands known it is exact: $`\binom{45}{2} = 990`$ possible boards from the flop, 44 from the turn. Monte Carlo is used preflop, with a standard error $`\sqrt{p(1-p)/n}`$; aces beat kings about 82% of the time.

**Outs** are the cards that put you ahead. From the turn, with $`n`$ outs among $`U`$ unseen cards, equity is exactly $`n/U`$ (if no card gives a tie). From the flop, the chance of hitting at least one out in two cards is one minus the chance of missing twice:

```math
P(\text{hit}) = 1 - \frac{U - n}{U} \cdot \frac{U - n - 1}{U - 1} .
```

For a flush draw (9 outs, 47 unseen) that is $`1 - \tfrac{38}{47} \cdot \tfrac{37}{46} \approx 35.0\%`$. The **rule of 2 and 4** ($`4n\%`$ on the flop, $`2n\%`$ on the turn) is a quick approximation: 36% for 9 outs. It drops the $`n^2`$ term, so it overstates big draws: 15 outs gives 60% by the rule but 54.1% exactly.

**Pot odds.** Facing an all-in bet $`B`$ into a pot $`P`$, you call $`B`$ to win a final pot of $`P + 2B`$. With equity $`q`$:

```math
\mathrm{EV}(\text{call}) = q\,(P + 2B) - B \ \ge 0 \iff q \ge \frac{B}{P + 2B} .
```

**Minimum defence frequency** answers the reverse question. If your opponent bets $`B`$ into $`P`$ with nothing and you fold a share $`\phi`$ of the time, the bluff is worth

```math
\mathrm{EV}(\text{bluff}) = \phi P - (1 - \phi) B > 0 \iff \phi > \frac{B}{P + B} .
```

So you must continue with at least $`\text{MDF} = \dfrac{P}{P + B}`$ of your hands. The same ratio, $`\dfrac{B}{P + B}`$, is how often **your** bluff must work to break even.

The spot trainer deals Hold'em hands where you are behind and drawing, shows both hands, and asks for the outs, the equity, the pot odds, the call-or-fold decision, and either the MDF or the break-even bluff.
