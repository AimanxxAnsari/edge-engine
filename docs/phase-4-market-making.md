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

"Make me a market" is a standard trading-interview exercise. Here the contract settles at the sum of $`n`$ hidden items: dice, or cards dealt without replacement. Each round you give a **bid** $`b`$ (the price you will buy at) and an **ask** $`a`$ (the price you will sell at). Several traders arrive and each trades one lot if your price suits them. Then one item is revealed, and you quote again. After the last reveal the contract settles at the sum $`S`$.

Each round you are also asked for the fair value, the standard deviation, and your P&L marked at the current fair value $`F`$:

```math
\text{mark-to-market} = \text{cash} + \text{position} \times F .
```

In the first round you price a binary option: the chance the sum reaches some level, $`P(S \ge x)`$, read off the exact distribution.

---

## 2. Fair value and uncertainty

**Dice.** One die has

```math
\mathbb{E}[X] = \frac{1 + \dots + 6}{6} = 3.5, \qquad
\mathbb{E}[X^2] = \frac{91}{6}, \qquad
\mathrm{Var}(X) = \frac{91}{6} - \frac{49}{4} = \frac{35}{12} \approx 2.92 .
```

Independent dice add means and variances, so with $`m`$ dice still hidden

```math
F = \text{(sum shown)} + 3.5\,m, \qquad \mathrm{Var}(S \mid \text{shown}) = \frac{35}{12}\,m .
```

The sum of 4 dice has fair value 14 and sd $`\sqrt{35/3} \approx 3.42`$. If the first die shows a 6, fair value jumps to $`6 + 3 \times 3.5 = 16.5`$, and the sd falls to $`\sqrt{35/4} \approx 2.96`$.

**Cards without replacement.** One card from a full deck (A = 1 … K = 13) has mean 7 and variance $`(13^2 - 1)/12 = 14`$. Each card you see changes what is left. Let the $`R`$ unseen cards have mean $`\mu`$ and population variance $`\sigma^2`$, with $`m`$ of them hidden in the contract. Then

```math
F = \text{(sum shown)} + m\,\mu, \qquad
\mathrm{Var} = m\,\sigma^2\,\frac{R - m}{R - 1} .
```

**Where the correction comes from.** For draws without replacement, $`\mathrm{Var}(\sum X_i) = m\sigma^2 + m(m-1)\,\gamma`$, where $`\gamma = \mathrm{Cov}(X_i, X_j)`$. Drawing all $`R`$ cards gives a fixed total, so the variance must be zero at $`m = R`$:

```math
0 = R\sigma^2 + R(R-1)\,\gamma \;\Longrightarrow\; \gamma = -\frac{\sigma^2}{R - 1} \;\Longrightarrow\;
\mathrm{Var} = m\sigma^2\left(1 - \frac{m-1}{R-1}\right) = m\sigma^2\,\frac{R - m}{R - 1} .
```

The covariance is negative: a high card makes the next one slightly more likely to be low, so the sum varies less than $`m`$ independent draws would. Three cards from a full deck: $`3 \times 14 \times \tfrac{49}{51} \approx 40.4`$ instead of 42.

**The full distribution.** For dice it is a repeated convolution, $`P_m(s) = \tfrac16 \sum_{f=1}^{6} P_{m-1}(s - f)`$. For cards, count the ways to choose $`m`$ physical cards with each total: taking $`j`$ of the $`c_v`$ cards of value $`v`$ can be done in $`\binom{c_v}{j}`$ ways and adds $`jv`$ to the sum. Building the table over all values and dividing by $`\binom{R}{m}`$ gives the exact distribution:

```math
P(S = s) = \frac{1}{\binom{R}{m}} \sum_{\substack{j_1 + \dots + j_{13} = m \\ \sum_v j_v v = s}} \ \prod_{v=1}^{13} \binom{c_v}{j_v} .
```

The tests check every formula against listing all outcomes, including all 22,100 three-card hands.

---

## 3. Who you are trading with

| Trader | Its value of the contract | When it trades |
|---|---|---|
| Noise | $`F + U`$, with $`U`$ uniform on $`[-\sigma, \sigma]`$ | buys if its value is above your ask, sells if below your bid |
| Informed | $`G = \mathbb{E}[S \mid \text{shown},\ x]`$, having seen the next item $`x`$ | only when your quote is wrong relative to $`G`$ |

For dice, $`G = F + (x - 3.5)`$. For cards, $`G = \text{(shown)} + x + (m - 1)\,\mu'`$, where $`\mu'`$ is the mean of the unseen cards once $`x`$ is removed.

By default 30% of traders are informed, and you are never told which is which until the end. At your position limit (±5 lots) the side that would push you past it is withdrawn.

---

## 4. The economics of width

**Against noise traders only,** a market $`F \pm h`$ trades on each side with probability

```math
P(F + U > F + h) = \frac{\sigma - h}{2\sigma}
```

and earns $`h`$ each time, so the expected profit per trader is

```math
\pi(h) = 2 \cdot h \cdot \frac{\sigma - h}{2\sigma} = \frac{h(\sigma - h)}{\sigma},
\qquad \pi'(h) = \frac{\sigma - 2h}{\sigma} = 0 \;\Longrightarrow\; h^* = \frac{\sigma}{2},\quad \pi(h^*) = \frac{\sigma}{4} .
```

The best market is **one standard deviation wide**. Narrower trades more often but earns less each time; wider earns more each time but rarely trades. At $`h = \sigma`$ nobody trades at all.

**Informed traders** trade exactly when $`|G - F| > h`$, and each trade costs you the gap between their value and your price. Averaged over the next item $`x`$:

```math
\mathbb{E}[\text{informed P\&L}] = -\,\mathbb{E}_x\bigl[\max(0,\ |G - F| - h)\bigr] .
```

For 4 dice quoted $`F \pm 1`$ that is $`-\tfrac16 \sum_{x=1}^{6} \max(0, |x - 3.5| - 1) = -\tfrac46`$ per informed trader. With an informed share $`\alpha`$, the expected profit per trader is $`(1 - \alpha)\,\pi(h) + \alpha \cdot \mathbb{E}[\text{informed P\&L}]`$. The tighter you quote, the more often informed traders can hit you, so the best width moves out. The lab simulates P&L per game against width (4 dice, 4 traders a round):

| Informed | Best half-width | Expected P&L per game |
|---|---|---|
| 0% | 0.5 sd | about +10.4 |
| 20% | about 0.6 sd | about +6.9 |
| 40% | about 0.6 sd | about +3.8 |

At 40% informed, a market 0.1 sd wide loses about 5 per game. That is the core of real market making: **your spread has to pay for the traders who know more than you.**

**Inventory.** If you are long, both your prices should move down. A lower bid makes it less likely you buy more, and a lower ask makes it more likely you sell. You keep the same width while drifting towards a flat position.

---

## 5. Where the P&L came from

For each trade, with $`s = +1`$ if you bought and $`-1`$ if you sold, price $`p`$, public fair value $`F`$ at that moment, the trader's own value $`G`$ (equal to $`F`$ for a noise trader) and the final settlement $`S`$:

```math
\underbrace{s(S - p)}_{\text{P\&L}} = \underbrace{s(F - p)}_{\text{spread}} + \underbrace{s(G - F)}_{\text{adverse selection}} + \underbrace{s(S - G)}_{\text{luck}} .
```

- **Spread:** what you earned against fair value when you traded. Positive whenever you bought below fair or sold above it.
- **Adverse selection:** what informed traders knew that you didn't. Zero for noise trades, and negative for informed trades against a market centred on fair value.
- **Luck:** how the remaining hidden items fell after that. Since $`G`$ is the conditional mean of $`S`$ given what the trader knew (which includes everything you knew), $`\mathbb{E}[S - G] = 0`$: luck averages out.

The three parts **add up exactly**, because the middle terms cancel. Summed over all trades, the total also equals your final cash plus position $`\times\, S`$. The game keeps prices as exact fractions, and the tests check the equality with no tolerance over many random games. The end-of-game summary also splits P&L by trader type, which shows directly how much informed traders cost you and whether your spread paid for it.

---

## 6. How the game scores you

| Question | Truth | Right if |
|---|---|---|
| Chance the sum reaches a level (round 1) | $`P(S \ge x)`$ from the exact distribution | within 0.03 |
| Fair value | $`\mathbb{E}[S \mid \text{shown}]`$ | within 0.05 |
| Standard deviation | $`\sqrt{\mathrm{Var}(S \mid \text{shown})}`$ | within 10% |
| P&L marked at fair value | cash + position $`\times F`$ | within 0.5 |
| Your market | fair value $`F`$ | $`b \le F \le a`$; tighter scores better |

The market's error is the interval score with $`\alpha = 0.5`$, $`(a - b) + 4\,\bigl(\text{distance of } F \text{ outside } [b, a]\bigr)`$, so tight markets centred on fair value score best. It is scored on being centred and tight, not on the P&L of one game, which is mostly luck. The breakdown and the lab show the long-run economics.
