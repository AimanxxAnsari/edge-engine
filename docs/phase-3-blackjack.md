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

Every number in this module comes from one solver. It assumes cards are drawn independently from a fixed **composition**: a probability for each value, ace to ten.

**Dealer.** Starting from the upcard, the dealer draws until reaching 17 or more (and also hits soft 17 under H17). A recursion over (hard sum, has an ace) gives the probability of finishing on 17, 18, 19, 20, 21 or bust. With peek, the hole card is drawn as if it cannot complete a blackjack.

**Player.**
- *Stand:* win if the dealer busts or ends lower, push if equal, lose if higher.
- *Hit:* take a card, then do whichever of hit or stand is better, recursively.
- *Double:* twice the stake, exactly one more card, then stand.
- *Surrender:* lose half the bet, −0.5.
- *Split:* each hand starts with one card of the pair. Let A be the value from non-matching second cards, B the value of keeping a matching card as a pair, and p the chance of a matching card. With resplitting, each hand is worth x = A + p·max(B, 2x), so x = A / (1 − 2p) when resplitting pays. Split aces get one card each, and ace-ten after a split is 21, not blackjack.

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

With perfect basic strategy the house edge is about **0.42%**. Paying 6:5 instead of 3:2 for blackjack costs another 0.3 × P(blackjack) ≈ **1.4%**.

---

## 4. Counting: Hi-Lo

| Cards | Value |
|---|---|
| 2, 3, 4, 5, 6 | +1 |
| 7, 8, 9 | 0 |
| 10, J, Q, K, A | −1 |

The **running count** is the sum over every card seen since the shuffle. The dealer's hole card counts only once it is turned over. Hi-Lo is **balanced**: a full deck sums to zero, so a high running count means the cards still to come are rich in tens and aces.

The **true count** divides by the decks left: TC = RC / (unseen cards / 52). A running count of +6 means much more with one deck left (TC +6) than with six (TC +1).

**Why high cards help the player.** More blackjacks, which pay 3:2 to you but only 1:1 to the dealer. Doubles land on tens more often. And the dealer, who must hit 12–16, busts more often. In the solver's average shoe, each +1 of true count adds about **+0.56%** to the player's edge: from −0.42% at TC 0 to about +0.15% at TC +1 and +1.9% at TC +4.

**Bet spread.** Bet 1 unit at TC ≤ 1, then 2, 4, 6 and 8 units at TC 2, 3, 4 and 5+ (floor of the true count). The edge rises with the count, and Kelly says to bet in proportion to the edge, as in Phase 2.

---

## 5. Count-based changes to basic strategy

At high counts some plays change: stand on 16 vs 10, take insurance, double 10 vs 10. Don Schlesinger's **Illustrious 18** and **Fab 4** (surrenders) list the most valuable changes with their **index**: make the change when the true count is at least the index.

**Insurance** is the clearest case. It pays 2:1 if the hole card is a ten, so it is worth it when more than one card in three is a ten. In the average shoe that happens at TC ≈ +3.1, against the published +3.

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
| Insurance | dealer shows an ace | 0.5·(3p − 1) with p = chance the hole card is a ten |
| Bust chance if you hit | strategy mode, two-card hard 12–16 | share of cards that bust you |
| Running count, true count, bet | count mode, before each hand | Hi-Lo of the seen cards; RC / decks left; the spread |
| Running count after a batch | drill mode | the count so far; the deck ends at 0 |
| True count conversion | drill mode, every third batch | RC / decks |

At the end: net units, EV lost (total and per 100 hands), and the three most expensive mistakes.
