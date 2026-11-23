# Phase 3 — Blackjack: basic strategy, counting and deviations

```
edge-engine play blackjack                          # basic strategy, 20 hands
edge-engine play blackjack -o mode=count            # running count, true count, bet, then play
edge-engine play blackjack -o mode=drill            # count a deck in batches, true-count conversions
edge-engine play blackjack -o h17=true -o payout=6:5 -o decks=2
edge-engine lab blackjack                           # chart, edge, dealer bust chances, indices
```

Decision keys: `h` hit, `s` stand, `d` double, `p` split, `r` surrender. Insurance: `t` take, `d` decline.

---

## 1. Rules

The default game is 6 decks, the dealer stands on soft 17 (S17), blackjack pays 3:2, double after split (DAS), late surrender, resplitting up to four hands (not aces), and 75% penetration. All of these can be changed with `-o`. The dealer **peeks** for blackjack when showing an ace or a ten, so every decision is made knowing the dealer does not have blackjack.

---

## 2. The EV solver

Every number in this module comes from one solver. It assumes cards are drawn independently from a fixed **composition** $`c = (c_1, \dots, c_{10})`$, where $`c_v`$ is the probability of value $`v`$ (1 is an ace, 10 is any ten-value card).

**Hands.** A hand is stored as its hard sum $`h`$ (aces counted as 1) and whether it holds an ace $`a`$. Its total is

```math
t(h, a) = \begin{cases} h + 10 & \text{if } a \text{ and } h + 10 \le 21 \quad (\text{a soft hand}) \\ h & \text{otherwise.} \end{cases}
```

**Dealer.** Starting from the upcard, the dealer draws until reaching 17 or more (and also hits soft 17 under H17). The distribution $`D`$ of the final total over $`\{17, 18, 19, 20, 21, \text{bust}\}`$ is a recursion:

```math
D(h, a) = \begin{cases} \text{point mass at } t(h, a) & \text{if the dealer stands} \\ \sum_{v=1}^{10} c_v\, Digl(h + v,\ a \lor [v = 1]\bigr) & \text{otherwise.} \end{cases}
```

**Peek.** With an ace up the hole card cannot be a ten, and with a ten up it cannot be an ace, so the first draw uses the composition with that value removed and renormalised, e.g. $`c'_v = c_v / (1 - c_{10})`$ for $`v \ne 10`$. Every decision is then correctly conditioned on "no dealer blackjack".

**Player.** With $`D_{17}, \dots, D_{21}, D_{\text{bust}}`$ the dealer's chances:

```math
\mathrm{Stand}(t) = D_{\text{bust}} + \sum_{d < t} D_d - \sum_{d > t} D_d \qquad (t \le 21; \text{ a bust hand is } -1),
```

```math
\mathrm{Hit}(h, a) = \sum_{v=1}^{10} c_v \max\Bigl(\mathrm{Stand}\bigl(t(h + v, a')\bigr),\ \mathrm{Hit}(h + v, a')\Bigr), \qquad a' = a \lor [v = 1],
```

```math
\mathrm{Double}(h, a) = 2 \sum_{v=1}^{10} c_v\, \mathrm{Stand}\bigl(t(h + v, a')\bigr), \qquad \mathrm{Surrender} = -\tfrac12 .
```

**Split.** Each hand starts with one card $`r`$ of the pair. Let $`A`$ be the value from the second cards that don't match, $`B`$ the value of keeping a matching card as an ordinary hand, and $`p = c_r`$. With resplitting, a matching card turns one hand into two, each worth the same $`x`$:

```math
x = A + p\,\max(B,\ 2x) \;\Longrightarrow\; x = \frac{A}{1 - 2p} \quad \text{when resplitting pays,} \qquad \mathrm{Split} = 2x .
```

Split aces get one card each, and ace-ten after a split is 21, not blackjack.

**The edge of a round.** Summing over the upcard $`u`$ and the player's two cards: a player blackjack pays the payout $`\beta`$ (1.5 at 3:2) unless the dealer also has one; otherwise a dealer blackjack costs one bet; otherwise the best action's EV:

```math
\text{edge} = \sum_{u} c_u \sum_{\text{hands}} P(\text{hand}) \Bigl[ \mathbf{1}_{\text{BJ}}\,(1 - d_u)\,\beta + \mathbf{1}_{\text{no BJ}} \bigl( -d_u + (1 - d_u) \max_{\text{action}} \mathrm{EV} \bigr) \Bigr],
```

where $`d_u`$ is the chance the dealer has blackjack with upcard $`u`$.

**Compositions.**

| Model | Used for |
|---|---|
| Infinite deck: 1/13 per value, 4/13 for tens | the edge, the dealer table |
| A fresh shoe minus the known cards (your cards, the upcard), averaged over every two-card hand that makes a total | basic strategy |
| The cards you have not seen yet | count mode: decisions that depend on the count |
| The average shoe at a true count | the edge by count, deviation indices |

---

## 3. Basic strategy, computed and checked

The computed 6-deck chart **matches the published 4–8 deck chart in every cell**, for both S17 and H17. The six cells where H17 differs are all reproduced: double 11 vs A; surrender 15 vs A, 17 vs A and 8-8 vs A; double soft 18 vs 2 and soft 19 vs 6. `edge-engine lab blackjack` prints the chart for any rules.

The infinite-deck model gets every cell right except two soft doubles, A2 vs 5 and A4 vs 4. There the EV difference between doubling and hitting is only 0.7% and 0.1% of a bet, and removing your own cards from a real shoe tips the balance. That is why basic strategy here uses the finite shoe.

Patterns worth remembering:
- Stand on 12–16 against 2–6 (except hit 12 vs 2 and 3), and hit them against 7–A. The dealer busts 35–42% of the time showing 2–6, and 17–26% showing 7–A.
- Always split aces and eights; never split tens or fives.
- Double 11 against everything but an ace (S17), and 10 against 2–9.

With perfect basic strategy the house edge is about **0.42%**. Paying 6:5 instead of 3:2 changes only the blackjack payout, so the difference is exact:

```math
\Delta = (1.5 - 1.2) \times P(\text{player BJ}) \times P(\text{no dealer BJ}) = 0.3 \times \frac{2 \cdot 4}{169} \times \left(1 - \frac{2 \cdot 4}{169}\right) \approx 1.35\% .
```

---

## 4. Counting: Hi-Lo

| Cards | Value |
|---|---|
| 2, 3, 4, 5, 6 | +1 |
| 7, 8, 9 | 0 |
| 10, J, Q, K, A | −1 |

The **running count** is the sum over every card seen since the shuffle. The dealer's hole card counts only once it is turned over. Hi-Lo is **balanced**: per deck, $`5 \times 4 = 20`$ cards count $`+1`$ and $`16 + 4 = 20`$ count $`-1`$, so

```math
\sum_{\text{deck}} \text{value} = 0 \quad\Longrightarrow\quad \text{RC}_{\text{seen}} + \text{RC}_{\text{unseen}} = 0 .
```

Whatever you have seen, the unseen cards count exactly minus your running count, so a high running count means the cards still to come are rich in tens and aces.

The **true count** divides by the decks left:

```math
\text{TC} = \frac{\text{RC}}{\text{unseen cards} / 52} .
```

A running count of +6 means much more with one deck left (TC +6) than with six (TC +1).

**The average shoe at a true count.** A true count of $`t`$ means high cards exceed low cards by $`t`$ per deck. Keeping 52 cards per deck splits that half and half, so per deck there are

```math
20 + \tfrac{t}{2} \ \text{high cards (tens and aces)}, \qquad 20 - \tfrac{t}{2} \ \text{low cards (2-6)}, \qquad 12 \ \text{neutral (7-9)},
```

each spread evenly within its group. The solver uses this shoe for the edge by count and for the deviation indices.

**Why high cards help the player.** More blackjacks, which pay 3:2 to you but only 1:1 to the dealer. Doubles land on tens more often. And the dealer, who must hit 12–16, busts more often. In the solver's average shoe, each +1 of true count adds about **+0.56%** to the player's edge: from −0.42% at TC 0 to about +0.15% at TC +1 and +1.9% at TC +4.

**Bet spread.** With $`\tau = \lfloor \text{TC} \rfloor`$:

```math
\text{bet} = \begin{cases} 1 & \tau \le 1 \\ 2,\ 4,\ 6 & \tau = 2,\ 3,\ 4 \\ 8 & \tau \ge 5 \end{cases} \ \text{units.}
```

The edge rises with the count (about 0.56% per true count here), and Kelly says to bet in proportion to the edge, as in Phase 2.

---

## 5. Count-based changes to basic strategy

At high counts some plays change: stand on 16 vs 10, take insurance, double 10 vs 10. Don Schlesinger's **Illustrious 18** and **Fab 4** (surrenders) list the most valuable changes with their **index**: make the change when the true count is at least the index.

**Insurance** is the clearest case. It costs half your bet and pays 2:1 if the hole card is a ten. With $`p = P(\text{ten})`$ among the unseen cards, per unit of your main bet:

```math
\mathbb{E}[\text{insurance}] = \tfrac12 \bigl( 2p - (1 - p) \bigr) = \tfrac12 (3p - 1) > 0 \iff p > \tfrac13 .
```

In the average shoe that happens at TC ≈ +3.1, against the published +3.

**Finding an index.** For a play with the deviation $`D`$ and the basic play $`B`$, the index is the true count where the margin changes sign:

```math
\text{index} = \min \bigl\{ t : \mathrm{EV}_t(D) - \mathrm{EV}_t(B) > 0 \bigr\},
```

with the EVs computed in the average shoe at true count $`t`$, averaged over the two-card hands that make the total.

The lab computes each index by finding the true count where the change becomes the better play, in an average shoe with 3 of 6 decks left. Computed against published:

| Play | Computed | Published | | Play | Computed | Published |
|---|---|---|---|---|---|---|
| Insurance | +3.1 | +3 | | 9 vs 7 double | +2.7 | +3 |
| 16 vs 10 stand | +1.2 | 0 | | 16 vs 9 stand | +5.8 | +5 |
| 15 vs 10 stand | +4.3 | +4 | | 13 vs 2 stand | −1.4 | −1 |
| 10,10 vs 5 split | +5.1 | +5 | | 12 vs 4 stand | −0.7 | 0 |
| 10,10 vs 6 split | +4.8 | +4 | | 12 vs 5 stand | −2.2 | −2 |
| 10 vs 10 double | +3.7 | +4 | | 12 vs 6 stand | −1.7 | −1 |
| 12 vs 3 stand | +1.0 | +2 | | 13 vs 3 stand | −2.8 | −2 |
| 12 vs 2 stand | +2.7 | +3 | | 14 vs 10 surrender | +3.4 | +3 |
| 11 vs A double | +0.8 | +1 | | 15 vs 10 surrender | 0.0 | 0 |
| 9 vs 2 double | +0.1 | +1 | | 15 vs 9 surrender | +2.3 | +2 |
| 10 vs A double | +3.6 | +4 | | 15 vs A surrender | +1.9 | +1 |

All are within 1.25 of the published index, and most within 0.5. The published values come from large simulations of real shoes with whole-number true counts, so small gaps are expected. 16 vs 10 is the most sensitive: it depends on which cards make the 16 and on how deep into the shoe you are.

In **count mode**, decisions are scored against the EVs for the cards you have actually not seen yet, so a correct count-based change scores as right, and the explanation names the published index.

---

## 6. What the game asks

| Question | When | Truth |
|---|---|---|
| Hit / stand / double / split / surrender | every decision | EV of each action; error = EV lost |
| Insurance | dealer shows an ace | $`\tfrac12(3p - 1)`$ with $`p`$ = chance the hole card is a ten |
| Bust chance if you hit | strategy mode, two-card hard 12–16 | $`\sum_{v \ge 22 - t} c_v`$ for a hard total $`t`$ |
| Running count, true count, bet | count mode, before each hand | Hi-Lo of the seen cards; RC / decks left; the spread |
| Running count after a batch | drill mode | the count so far; the deck ends at 0 |
| True count conversion | drill mode, every third batch | RC / decks |

At the end: net units, EV lost (total and per 100 hands), and the three most expensive mistakes.
