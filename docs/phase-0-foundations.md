# Phase 0 — Foundations: the maths behind the shared code

This page explains the maths used by `src/edge_engine/`: the random number generator, the probability helpers, the Monte Carlo runner and the scoring rules.

---

## 1. Random numbers: xoshiro256\*\*

Every game draws its randomness from `Rng`, so a session can be replayed from its seed.

**State and step.** The state is four 64-bit words $`s_0, s_1, s_2, s_3`$. Each step outputs

```math
\text{result} = \operatorname{rotl}(5\,s_1,\ 7) \times 9 \pmod{2^{64}}
```

and then mixes the state with shifts, XORs and one rotation:

```
t = s1 << 17
s2 ^= s0;  s3 ^= s1;  s1 ^= s2;  s0 ^= s3
s2 ^= t;   s3 = rotl(s3, 45)
```

Shifts, XORs and rotations are all linear over the two-element field $`\mathrm{GF}(2)`$, so the state update is a linear map $`s \mapsto A s`$ on 256 bits. The shift and rotation amounts are chosen so that every non-zero state is visited before any repeats:

```math
\text{period} = 2^{256} - 1 .
```

The multiply-by-5, rotate and multiply-by-9 ("star-star") scramble the output, so it passes statistical tests that the raw linear state fails.

**Seeding.** A small integer seed would give a state that is almost all zeros, and the all-zero state never changes ($`A \cdot 0 = 0`$). So the seed is first run through SplitMix64, which spreads it over all 256 bits.

**Integers without bias.** Taking $`x \bmod n`$ is biased unless $`n`$ is a power of two. With 3-bit numbers ($`0 \dots 7`$) and $`n = 3`$:

```math
P(0) = P(1) = \tfrac{3}{8}, \qquad P(2) = \tfrac{2}{8} .
```

`randbelow(n)` instead takes the top $`b`$ bits, where $`2^b`$ is the smallest power of two with $`2^b \ge n`$, and throws away values $`\ge n`$. Every accepted value then has the same probability. Each try succeeds with probability $`n / 2^b > \tfrac12`$, since $`2^b < 2n`$. The number of tries is geometric, so

```math
\mathbb{E}[\text{tries}] = \frac{2^b}{n} < 2 .
```

**Floats.** A double has a 53-bit mantissa, so `random()` uses the top 53 bits of the output $`x`$:

```math
u = \left\lfloor x / 2^{11} \right\rfloor \cdot 2^{-53} \in [0, 1),
```

one of $`2^{53}`$ evenly spaced values, never exactly 1.

**Shuffling.** Fisher–Yates: for $`i`$ from $`n-1`$ down to $`1`$, swap item $`i`$ with a uniformly chosen item in $`0 \dots i`$. Position $`n-1`$ gets any item with probability $`\tfrac1n`$, then position $`n-2`$ any remaining item with probability $`\tfrac1{n-1}`$, and so on, so every ordering has probability

```math
\frac{1}{n} \cdot \frac{1}{n-1} \cdots \frac{1}{2} = \frac{1}{n!} .
```

The tests check this with a chi-square test on all six orders of three items.

---

## 2. Counting and exact distributions

**n choose k.**

```math
\binom{n}{k} = \frac{n!}{k!\,(n-k)!}
```

Factorials get huge quickly, so the code uses the multiplicative form

```math
r_0 = 1, \qquad r_i = r_{i-1} \cdot \frac{n - k + i}{i} \quad (i = 1, \dots, k).
```

By induction $`r_i = \binom{n-k+i}{i}`$, which is an integer, so the division is always exact.

**Binomial.** $`X`$ counts the successes in $`n`$ independent trials, each a success with probability $`p`$:

```math
P(X = k) = \binom{n}{k} p^k (1-p)^{n-k}, \qquad \mathbb{E}[X] = np, \qquad \operatorname{Var}(X) = np(1-p).
```

Example: four heads in ten flips of a 60% coin is $`\binom{10}{4}\,0.6^4\,0.4^6 = 210 \times 0.6^4 \times 0.4^6 \approx 0.111`$.

**Hypergeometric.** $`X`$ counts the successes in $`n`$ draws *without* replacement from $`N`$ items, $`K`$ of which are successes:

```math
P(X = k) = \frac{\binom{K}{k}\binom{N-K}{n-k}}{\binom{N}{n}} .
```

Example: a 5-card hand with exactly one ace is $`\binom{4}{1}\binom{48}{4} / \binom{52}{5} \approx 0.299`$.

The mean is the same as with replacement. The variance is smaller:

```math
\mathbb{E}[X] = n\,\frac{K}{N}, \qquad
\operatorname{Var}(X) = n\,\frac{K}{N}\left(1 - \frac{K}{N}\right) \underbrace{\frac{N-n}{N-1}}_{\text{finite-population correction}} .
```

Drawing without replacement means each draw tells you something about the rest, so totals vary less. At $`n = N`$ (drawing everything) the correction is 0: there is no randomness left. This matters for card games and for market-making on hidden cards.

The code returns `Fraction`s, so the tests check exact values, not floating-point approximations.

---

## 3. Monte Carlo and standard error

When an exact answer is too hard, simulate: run the trial $`n`$ times and average,

```math
\bar X = \frac{1}{n} \sum_{i=1}^{n} X_i .
```

$`\bar X`$ is itself random. If one trial has standard deviation $`\sigma`$, estimated by the sample standard deviation $`s`$, its spread is the **standard error**

```math
\operatorname{SD}(\bar X) = \frac{\sigma}{\sqrt{n}} \approx \mathrm{SE} = \frac{s}{\sqrt n}, \qquad
\text{95\% interval} \approx \bar X \pm 1.96\,\mathrm{SE} .
```

To halve the error you need four times as many trials.

For an event with probability $`p`$, one trial is 0 or 1, so

```math
\sigma^2 = p(1-p), \qquad \mathrm{SE} = \sqrt{\frac{p(1-p)}{n}} .
```

With $`p = 10/36`$ and $`n = 20\,000`$, $`\mathrm{SE} \approx 0.0032`$.

**Welford's update.** Computing the variance as $`\overline{x^2} - \bar x^2`$ subtracts two nearly equal numbers and loses precision. Welford's method updates the mean $`m`$ and the sum of squared deviations $`M_2`$ one value at a time:

```math
\delta = x_i - m_{i-1}, \qquad m_i = m_{i-1} + \frac{\delta}{i}, \qquad M_{2,i} = M_{2,i-1} + \delta\,(x_i - m_i), \qquad s^2 = \frac{M_{2,n}}{n-1} .
```

---

## 4. Scoring

Each question kind is scored differently.

| Kind | Error | Points |
|---|---|---|
| point | $`\lvert a - t \rvert`$ | 1 if within tolerance, else 0 |
| speed | $`\lvert a - t \rvert`$ | if right: $`\min(1,\ T / \text{seconds})`$ for a target time $`T`$; else 0 |
| decision | EV lost $`= \max_c \mathrm{EV}(c) - \mathrm{EV}(\text{yours})`$ | 1 if no EV lost, else 0 |
| probability | Brier $`(p - o)^2`$ | $`1 - \text{Brier}`$ |
| interval | interval score $`S_\alpha`$ (below) | 1 if the truth is inside, else 0 |

**Brier score.** For a forecast $`p`$ of an event with outcome $`o`$ (1 = happened, 0 = didn't), the score is $`(p - o)^2`$. It is a *proper* scoring rule: if the true chance is $`q`$, your expected score

```math
\mathbb{E}[(p - o)^2] = q(1-p)^2 + (1-q)p^2
```

has derivative $`2(p - q)`$, so it is lowest exactly at $`p = q`$. Shading your forecast in either direction can only make it worse on average. Putting $`p = q`$ back in gives the best possible average,

```math
\min_p \mathbb{E}[(p - o)^2] = q(1-q),
```

which is why a 50/50 event can never score better than 0.25.

**Interval score (Winkler).** For a central interval $`[l, u]`$ at level $`1 - \alpha`$ and truth $`y`$:

```math
S_\alpha(l, u; y) = (u - l) + \frac{2}{\alpha}\,(l - y)\,\mathbf{1}[y < l] + \frac{2}{\alpha}\,(y - u)\,\mathbf{1}[y > u] .
```

Narrow intervals score well, but a miss costs $`2/\alpha`$ per unit, which is 20 per unit for a 90% interval. Like the Brier score it is proper: you do best by giving your honest $`\alpha/2`$ and $`1 - \alpha/2`$ quantiles (the 5% and 95% points for a 90% interval). Over many questions, the share of intervals that contain the truth (the hit rate) should be close to $`1 - \alpha`$. If it is well below, you are overconfident.

**EV lost.** In a decision, the question is not whether you won the hand but how much expected value your choice gave up compared with the best choice. This separates decision quality from luck.

---

## 5. The loop

```
state → questions → you answer (timed)
      → truth(state, question) → score → reveal + log
      → action → new state
      → forecasts are scored against the new state
```

Forecast questions are about something that has not happened yet, such as "will this roll be at least 9?". They are scored after the next action, once the outcome is known.

The **dice demo** (`edge-engine play dice`) uses all of this. Each round a target $`k`$ is drawn and two dice are rolled. The number of ways to roll a sum $`s`$ is

```math
\#\{s\} = 6 - \lvert s - 7 \rvert \quad (2 \le s \le 12), \qquad
P(\text{sum} \ge k) = \frac{1}{36} \sum_{s=k}^{12} \bigl(6 - \lvert s - 7 \rvert\bigr) .
```

An even-money bet on it has

```math
\mathrm{EV} = p \cdot (+1) + (1-p) \cdot (-1) = 2p - 1,
```

so you should take it exactly when $`p > \tfrac12`$, which means $`k \le 7`$ ($`P(\ge 7) = 21/36`$, $`P(\ge 8) = 15/36`$).
