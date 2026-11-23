# Phase 2 — Coin Flip with an Edge: the maths of bet sizing

```
edge-engine play kelly                          # $25, a 60% coin, 50 flips
edge-engine play kelly -o flips=300 -o cap=250  # the classic experiment's setup
edge-engine play kelly -o mode=unknown          # the bias is hidden
edge-engine lab kelly                           # tables, simulations, fan chart
edge-engine lab kelly -o p=0.55 -o flips=100    # a different coin
```

Bets: `5` is \$5 on heads, `-5` is \$5 on tails, `20%` is 20% of your bankroll.

---

## 1. The setup

You start with \$25. A coin lands heads with probability $`p = 0.6`$ (write $`q = 1 - p`$), and you can bet any amount up to your bankroll at even money: win and you gain the stake, lose and you lose it. The edge is clearly yours. The question is **how much to bet**.

In 2016 Victor Haghani and Richard Dewey ran this experiment with 61 people, mostly finance students and professionals: \$25, a 60% coin, 30 minutes, winnings capped at \$250. About 30% went bust and the average payout was about \$91. Having an edge was not enough; the size of the bets decided the outcome.

---

## 2. The Kelly criterion

Bet a fixed fraction $`f`$ of your bankroll each time. Each win multiplies wealth by $`1 + f`$ and each loss by $`1 - f`$, so after $`n`$ bets with $`k`$ wins

```math
W_n = W_0\,(1 + f)^k\,(1 - f)^{n - k},
\qquad
\frac{1}{n} \ln \frac{W_n}{W_0} = \frac{k}{n} \ln(1 + f) + \frac{n - k}{n} \ln(1 - f) .
```

By the law of large numbers $`k/n \to p`$, so the long-run growth rate per bet is

```math
g(f) = p \ln(1 + f) + q \ln(1 - f), \qquad W_n \approx W_0\, e^{n\,g(f)} .
```

Maximising long-run wealth means maximising $`g`$: **the average of the logs, not the average of the outcomes.** Setting the derivative to zero,

```math
g'(f) = \frac{p}{1 + f} - \frac{q}{1 - f} = 0 \;\Longrightarrow\; p(1 - f) = q(1 + f) \;\Longrightarrow\; f^* = p - q = 2p - 1,
```

and $`g''(f) = -\dfrac{p}{(1+f)^2} - \dfrac{q}{(1-f)^2} < 0`$, so this is a maximum: the **Kelly fraction**. If a win pays $`b`$ times the stake, $`g(f) = p\ln(1 + bf) + q\ln(1 - f)`$ and

```math
f^* = \frac{bp - q}{b} \qquad \text{("edge over odds")}.
```

For $`p = 0.6`$, $`f^* = 0.2`$: bet 20% of whatever you have now, and $`g(0.2) = 0.6 \ln 1.2 + 0.4 \ln 0.8 \approx 0.0201`$ per flip.

| Fraction $`f`$ | × Kelly | $`g(f)`$ per flip | Comment |
|---|---|---|---|
| 0.05 | 0.25 | 0.0088 | very safe, slow |
| 0.10 | 0.5 | 0.0150 | 75% of the best growth, much smaller swings |
| 0.20 | 1 | 0.0201 | the maximum |
| 0.30 | 1.5 | 0.0148 | same growth as ~0.1, far bigger swings |
| 0.39 | 1.95 | 0 | growth is zero |
| 0.40 | 2 | −0.0024 | **you shrink on average despite the edge** |
| 1.00 | — | $`-\infty`$ | one tails and you are out |

**The shape of $`g`$.** Expanding $`\ln(1 \pm f)`$ to second order, $`g(f) \approx (p - q) f - \tfrac12 f^2 = f^* f - \tfrac12 f^2`$. Writing $`f = c\,f^*`$:

```math
g(c f^*) \approx \tfrac12 (f^*)^2\, c\,(2 - c) = g(f^*)\, c\,(2 - c) .
```

Half Kelly ($`c = \tfrac12`$) keeps $`\tfrac34`$ of the growth; double Kelly ($`c = 2`$) gets zero. The variance of the log-growth rises with $`f^2`$, so over-betting costs far more than under-betting by the same amount. That is why many professionals bet half Kelly or less: their estimate of $`p`$ is never exact.

**Maximising expected wealth is a trap.** $`\mathbb{E}[W_1] = W_0\,(1 + f(2p - 1))`$ rises with $`f`$, so maximising expected wealth means going all-in every time: $`\mathbb{E}[W_n] = W_0 \cdot 1.2^n`$, while $`P(\text{still alive after } n) = 0.6^n \to 0`$. The mean is carried by a single, vanishingly unlikely path.

---

## 3. The mean misleads; the median doesn't

Your final wealth depends only on the number of wins $`k \sim \mathrm{Binomial}(n, p)`$, and it rises with $`k`$, so everything can be computed exactly:

```math
\mathbb{E}[W_n] = W_0\,\bigl(1 + f(2p - 1)\bigr)^n,
\qquad
\mathrm{median}(W_n) = W_0\,(1+f)^{k_{\text{med}}}(1-f)^{n - k_{\text{med}}},
```

```math
P(W_n < x\,W_0) = \sum_{k \,:\, (1+f)^k (1-f)^{n-k} < x} \binom{n}{k} p^k q^{n-k} .
```

(A monotone function maps the median of $`k`$ to the median of $`W_n`$, but not the mean to the mean.)

For 300 flips from \$25 at full Kelly, the mean is about \$3.2 million but the median is about \$10,500. At double Kelly the mean is \$266 billion while the median is \$12, below the start. A few astronomically lucky runs inflate the mean; the median is what a typical player gets. `edge-engine lab kelly` prints this table for any coin.

**Ending below the start.** Betting a fraction $`f`$ for $`n`$ flips, you finish below the start when

```math
(1+f)^k (1-f)^{n-k} < 1 \iff k < n\,\frac{\ln\bigl(1/(1-f)\bigr)}{\ln\bigl((1+f)/(1-f)\bigr)} .
```

At $`f = 0.3`$ that threshold is $`0.576\,n`$, barely below the expected $`0.6\,n`$ heads, which is why even a favourable coin leaves you below the start about 30% of the time after 100 flips. Even at full Kelly, the chance of ending 300 flips below the start is about 4%; after only 100 flips it is about 18%.

---

## 4. Drawdowns and ruin

**Proportional betting never goes broke** (you always keep $`1 - f`$ of what you have), but it can fall a long way. In the continuous limit, log-wealth is a Brownian motion with drift $`\mu_f`$ and variance $`s^2`$ per unit time, and the chance of ever falling by $`L`$ in log terms is $`e^{-2\mu_f L / s^2}`$. Betting $`c`$ times Kelly makes $`2\mu_f / s^2 = 2/c - 1`$, so with $`L = \ln(1/x)`$:

```math
P(\text{ever falling to } x\,W_0) \approx x^{\,2/c - 1} .
```

At full Kelly ($`c = 1`$) that is $`x`$ itself: a 50% chance of halving at some point, and a 10% chance of falling to a tenth. At half Kelly it is $`x^3`$: 12.5% for halving. The simulation in the lab agrees closely (it is a little lower, because the game is finite and the coin is discrete).

**Fixed-size bets can go broke.** Betting a fixed amount is a random walk. Let $`r_u`$ be the chance of ever going broke from $`u`$ bets' worth of bankroll. Then

```math
r_u = p\,r_{u+1} + q\,r_{u-1}, \qquad r_0 = 1, \qquad r_\infty = 0 .
```

Trying $`r_u = \lambda^u`$ gives $`p\lambda^2 - \lambda + q = 0`$, with roots $`1`$ and $`q/p`$; the bounded solution is

```math
P(\text{ruin}) = \left(\frac{q}{p}\right)^{u} .
```

With \$5 bets from \$25 ($`u = 5`$) that is $`(0.4/0.6)^5 \approx 13\%`$, even with a 60% coin. With \$10 bets you can survive only 2 net losses ($`u = 2`$), giving 44%.

---

## 5. The cap

With a \$250 cap $`K`$, wealth above the cap is worthless. The game uses a simple rule: Kelly, but never bet more than you need to reach the cap,

```math
\text{bet} = \min\bigl(f^* W,\ K - W\bigr) .
```

The exact best strategy with a cap and $`n`$ flips left is a dynamic programme over every bankroll,

```math
V_n(w) = \max_{0 \le b \le w} \bigl( p\,V_{n-1}(w + b) + q\,V_{n-1}(w - b) \bigr),
```

which is not part of this phase.

---

## 6. Unknown bias: Bayesian Kelly

In `mode=unknown` the coin's bias $`p`$ is drawn from a $`\mathrm{Beta}(5, 5)`$ distribution (centred on 0.5, standard deviation about 0.15) and hidden. The Beta family is *conjugate* to coin flips: after $`h`$ heads and $`t`$ tails,

```math
\text{posterior} \propto p^{4 + h}(1 - p)^{4 + t} \;\Longrightarrow\; \mathrm{Beta}(5 + h,\ 5 + t), \qquad m = \mathbb{E}[p \mid \text{data}] = \frac{5 + h}{10 + h + t} .
```

The prior acts like 5 heads and 5 tails you have "already seen", which pulls early estimates towards 0.5.

**Kelly with an uncertain $`p`$ uses the mean.** For the next bet, averaging over your uncertainty,

```math
\mathbb{E}\bigl[p \ln(1 + f) + (1 - p)\ln(1 - f)\bigr] = m \ln(1 + f) + (1 - m) \ln(1 - f),
```

so the best fraction is $`2m - 1`$. Over the whole game $`\ln W_n = \ln W_0 + \sum_t \ln(1 + f_t X_t)`$ is a *sum*, and your bet does not change what you learn (you see the flip either way), so choosing each $`f_t`$ to maximise its own term also maximises the expected log of the *final* wealth. The game compares you with this Bayes-Kelly player, with a Bayes half-Kelly player, and with an "oracle" that knows $`p`$.

---

## 7. How the game scores you

| Question | When | Truth | Right if |
|---|---|---|---|
| Kelly fraction | start (classic) | $`2p - 1`$ | within 0.01 |
| $`P`$(finish below start betting 30%) | start (classic) | exact binomial | within 0.05 |
| Your bet | every flip | the Kelly bet in dollars | within 5% of your bankroll |
| $`P`$(heads) estimate | every 10 flips (unknown) | posterior mean $`m`$ | within 0.03 |

After each flip the game shows your growth rate against Kelly's. At the end it shows the final bankrolls of the comparison strategies **on the same flips**, which takes luck out of the comparison, plus a fan chart of 1,000 simulated runs at your average bet size.
