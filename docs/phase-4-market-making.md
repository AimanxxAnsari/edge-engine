# Phase 4 — Market Making: fair value, width and adverse selection

```
edge-engine play market                           # the sum of 4 dice, 30% informed flow
edge-engine play market -o contract=cards         # 4 cards (A=1 … K=13), no replacement
edge-engine play market -o informed=0.5 -o bots=6 # more traders, more of them informed
edge-engine lab market                            # statistics, P&L against quote width
```

Type a market as two prices: `12.5 15.5` or `12.5@15.5` (bid, then ask).

---

## 1. The game

"Make me a market" is a standard trading-interview exercise. Here the contract settles at the sum of n hidden items: dice, or cards dealt without replacement. Each round you give a **bid** (the price you will buy at) and an **ask** (the price you will sell at). Several traders arrive and each trades one lot if your price suits them. Then one item is revealed, and you quote again. After the last reveal the contract settles at the sum.

Each round you are also asked for the fair value, the standard deviation, and your P&L marked at the current fair value. In the first round you price a binary option: the chance the sum reaches some level.

---

## 2. Fair value and uncertainty

**Dice.** With m dice still hidden:

```
fair value = (sum shown) + 3.5·m
variance   = m · 35/12            (one die: mean 3.5, variance 35/12 ≈ 2.92)
```

The sum of 4 dice has fair value 14 and sd √(11.67) ≈ 3.42. If the first die shows a 6, fair value jumps to 6 + 3·3.5 = 16.5, and the sd falls to 2.96.

**Cards without replacement.** One card from a full deck (A = 1 … K = 13) has mean 7 and variance (13² − 1)/12 = 14. Each card you see changes what is left. With R unseen cards of mean μ and (population) variance σ², and m of them hidden in the contract:

```
fair value = (sum shown) + m·μ
variance   = m·σ²·(R − m)/(R − 1)
```

The factor (R − m)/(R − 1) is the **finite-population correction**. Drawing without replacement means a high card makes the next one slightly more likely to be low, so the sum varies less than m independent draws would. Three cards from a full deck: 3·14·49/51 ≈ 40.4 instead of 42.

**The full distribution.** For dice it is a convolution. For cards, a dynamic programme counts the ways to choose m physical cards with each total (C(4, k) ways to take k cards of a value), divided by C(R, m). The tests check every formula against listing all outcomes, including all 22,100 three-card hands.

---

## 3. Who you are trading with

| Trader | What it knows | When it trades |
|---|---|---|
| Noise | Nothing: values the contract at fair ± up to one sd, at random | When its value is above your ask (it buys) or below your bid (it sells) |
| Informed | Has seen the next item: values it at fair + (item − its expected value) | Only when your quote is wrong relative to that value |

By default 30% of traders are informed, and you are never told which is which until the end. At your position limit (±5 lots) the side that would push you past it is withdrawn.

---

## 4. The economics of width

Against **noise traders only**, a half-width h means each side trades with chance (sd − h)/(2·sd) and earns h. The expected profit per trader is

```
2 · h · (sd − h)/(2·sd) = h·(sd − h)/sd,
```

which is largest at **h = sd/2: a market one standard deviation wide**. Narrower trades more often but earns less each time; wider earns more each time but rarely trades. At h = sd nobody trades at all.

**Informed traders** trade exactly when you are wrong, and each trade costs you the gap between their value and your price. The tighter you quote, the more often they can do this. The lab simulates P&L per game against width (4 dice, 4 traders a round):

| Informed | Best half-width | Expected P&L per game |
|---|---|---|
| 0% | 0.5 sd | about +10.4 |
| 20% | about 0.6 sd | about +6.9 |
| 40% | about 0.6 sd | about +3.8 |

At 40% informed, a market 0.1 sd wide loses about 5 per game. That is the core of real market making: **your spread has to pay for the traders who know more than you.**

**Inventory.** If you are long, both your prices should move down. A lower bid makes it less likely you buy more, and a lower ask makes it more likely you sell. You keep the same width while drifting towards a flat position.

---

## 5. Where the P&L came from

For each trade (s = +1 if you bought, −1 if you sold) at price p, with public fair value F at that moment, the trader's own value G (equal to F for a noise trader) and the final settlement S:

```
s·(S − p)  =  s·(F − p)  +  s·(G − F)  +  s·(S − G)
   P&L          spread      adverse selection     luck
```

- **Spread:** what you earned against fair value when you traded. Positive whenever you bought below fair or sold above it.
- **Adverse selection:** what informed traders knew that you didn't. Zero for noise trades, and negative for informed trades against a market centred on fair value.
- **Luck:** how the remaining hidden items fell after that.

The three parts **add up exactly**, because the terms telescope. The game keeps prices as exact fractions, and the tests check the equality with no tolerance over many random games. The end-of-game summary also splits P&L by trader type, which shows directly how much informed traders cost you and whether your spread paid for it.

---

## 6. How the game scores you

| Question | Truth | Right if |
|---|---|---|
| Chance the sum reaches a level (round 1) | exact distribution | within 0.03 |
| Fair value | E[sum given what's shown] | within 0.05 |
| Standard deviation | from the variance above | within 10% |
| P&L marked at fair value | cash + position × fair value | within 0.5 |
| Your market | fair value | fair value is inside your market; tighter scores better |

The market is scored on being centred and tight, not on the P&L of one game, which is mostly luck. The breakdown and the lab show the long-run economics.
