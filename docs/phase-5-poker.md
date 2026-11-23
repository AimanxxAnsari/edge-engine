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

---

## 2. Counterfactual regret minimisation (CFR)

CFR plays the game against itself over and over. At every information set it keeps a **regret** for each action: how much better that action would have done than the current mix, weighted by how likely the opponent and chance were to lead there. The next strategy plays actions in proportion to their positive regret (*regret matching*).

```
regret(I, a) += Σ over deals in I of  opponent reach × chance × (value(a) − value(I))
strategy(I, a) ∝ max(regret(I, a), 0)
```

The **average** strategy over all iterations converges to a Nash equilibrium in two-player zero-sum games. This project uses **CFR+**: regrets are floored at zero after each update, the players update in turn, and later iterations count more in the average. It converges much faster than plain CFR.

**Implementation.** The tree is built once over public betting histories. Every node holds arrays over all deals (6 in Kuhn, 24 in Leduc once impossible deals are removed), so one pass with numpy updates every deal at once. 1,000 iterations of Leduc take under a second.

**Checking the answer.** A **best response** is the most a player can win against a fixed strategy: at each of their information sets, pick the action with the highest value summed over the deals they can't tell apart. **Exploitability** is the average of the two best-response values. It is zero exactly at an equilibrium, so it measures how far from solved a strategy is.

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
- **Moving first is worth −1/18 per hand** even with perfect play.
- **At equilibrium, the hands you mix with are indifferent.** Against the equilibrium bot, checking and bluffing a J have exactly the same value; that is what stops the opponent from exploiting either. The game says so when it happens, and counts both as right.

**Exploiting a weak opponent.** Against `bot=station` (always calls, never bets) the best play is to stop bluffing and bet your good hands. Against `bot=maniac` (always bets) you call down much lighter. In these modes your decisions are scored against the **best response to that bot**, so the equilibrium move is not always the best one. Over many hands, best-response play earns exactly +1/3 of a chip per hand against either bot (averaged over both seats), compared with 0 against the equilibrium.

---

## 4. Hand strength

The evaluator scores 5 to 7 cards in one pass. It counts ranks and suits, checks for a flush and a straight (including the wheel, A-2-3-4-5), and returns a number that sorts by category and then by the deciding ranks. Checks:
- All **2,598,960** five-card hands give the known counts: 40 straight flushes, 624 quads, 3,744 full houses, 5,108 flushes, 10,200 straights, 54,912 trips, 123,552 two pair, 1,098,240 pairs, 1,302,540 high cards.
- Seven-card category frequencies match the known counts out of 133,784,560 (chi-square test).
- For thousands of random 7-card hands, the direct score equals the best of the 21 five-card subsets.

---

## 5. Equity, outs and pot odds

**Equity** is your share of the pot if the hand were played to the end: wins plus half of ties. With both hands known it is exact: 990 possible boards from the flop, 44 from the turn. Monte Carlo is used preflop, with a standard error; aces beat kings about 82% of the time.

**Outs** are the cards that put you ahead. From the turn, equity is exactly outs ÷ unseen cards (if no card gives a tie). From the flop, the chance of hitting at least one of n outs in two cards is

```
1 − (U − n)/U × (U − n − 1)/(U − 1)
```

For a flush draw (9 outs, 47 unseen) that is 35.0%. The **rule of 2 and 4** (outs × 4% on the flop, × 2% on the turn) is a quick approximation: 36% for 9 outs.

**Pot odds.** Facing an all-in bet B into a pot P, you call B to win a final pot of P + 2B. Calling is profitable when

```
equity > B / (P + 2B)            EV(call) = equity × (P + 2B) − B
```

**Minimum defence frequency** answers the reverse question. If your opponent bets B into P with nothing, they risk B to win P, so they profit if you fold more than B/(P + B) of the time. You must continue with at least **P/(P + B)** of your hands. The same ratio, B/(P + B), is how often **your** bluff must work to break even.

The spot trainer deals Hold'em hands where you are behind and drawing, shows both hands, and asks for the outs, the equity, the pot odds, the call-or-fold decision, and either the MDF or the break-even bluff.
