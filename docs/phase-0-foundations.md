# Phase 0 — Foundations: the maths behind the shared code

This page explains the maths used by `src/edge_engine/`: the random number generator, the probability helpers, the Monte Carlo runner and the scoring rules.

---

## 1. Random numbers: xoshiro256\*\*

Every game draws its randomness from `Rng`, so a session can be replayed from its seed.

**State and step.** The state is four 64-bit words `s0..s3`. Each step outputs

```
result = rotl(s1 · 5, 7) · 9          (all arithmetic mod 2^64)
```

and then mixes the state with shifts, XORs and one rotation:

```
t = s1 << 17
s2 ^= s0;  s3 ^= s1;  s1 ^= s2;  s0 ^= s3
s2 ^= t;   s3 = rotl(s3, 45)
```

The state update is linear over GF(2) and has period 2^256 − 1. The `* 5`, rotate and `* 9` ("star-star") scramble the output so it passes statistical tests that the raw linear state fails.

**Seeding.** A small integer seed would give a state that is almost all zeros, and the all-zero state is a fixed point. So the seed is first run through SplitMix64, which spreads it over all 256 bits.

**Integers without bias.** `x mod n` is biased unless n is a power of two: with 3-bit numbers (0..7) and n = 3, the values 0 and 1 come up three times out of eight, but 2 only twice. `randbelow(n)` instead takes the top `b` bits, where 2^b is the smallest power of two ≥ n, and throws away values ≥ n. Since 2^b < 2n, each try succeeds with probability above 1/2, so on average fewer than two tries are needed.

**Floats.** A double has a 53-bit mantissa, so `random()` uses the top 53 bits: `(x >> 11) · 2^-53`. Every value is a multiple of 2^-53 in [0, 1).

**Shuffling.** Fisher-Yates: for i from n−1 down to 1, swap item i with a uniformly chosen item in 0..i. Each of the n! orders has probability exactly 1/n!. The tests check this with a chi-square test on all six orders of three items.

---

## 2. Counting and exact distributions

**n choose k.** `C(n, k) = n! / (k! (n−k)!)`. Factorials get huge quickly, so the code uses the multiplicative form

```
r = 1
for i in 1..k:  r = r · (n − k + i) / i
```

After step i, `r = C(n − k + i, i)`, which is an integer, so the division is always exact.

**Binomial.** n independent trials, each a success with probability p:

```
P(X = k) = C(n, k) · p^k · (1 − p)^(n−k)
```

Example: four heads in ten flips of a 60% coin is `210 · 0.6^4 · 0.4^6 ≈ 0.111`.

**Hypergeometric.** k successes in n draws *without* replacement from N items, K of which are successes:

```
P(X = k) = C(K, k) · C(N − K, n − k) / C(N, n)
```

Example: a 5-card hand with exactly one ace is `C(4,1) · C(48,4) / C(52,5) ≈ 0.299`.

The mean is the same as with replacement, `n·K/N`. The variance is smaller:

```
Var = n · (K/N) · (1 − K/N) · (N − n)/(N − 1)
```

The last factor is the *finite-population correction*. Drawing without replacement means each draw tells you something about the rest, so totals vary less. This matters for card games and for market-making on hidden cards.

The code returns `Fraction`s, so the tests check exact values, not floating-point approximations.

---

## 3. Monte Carlo and standard error

When an exact answer is too hard, simulate: run the trial n times and average. The average X̄ is itself random. Its spread is the **standard error**

```
SE = s / √n
```

where s is the sample standard deviation of one trial. To halve the error you need four times as many trials. A 95% confidence interval is about `X̄ ± 1.96 · SE`.

For an event with probability p, one trial is 0 or 1, so `s² = p(1 − p)` and `SE = √(p(1−p)/n)`. With p = 10/36 and n = 20 000, SE ≈ 0.0032.

**Welford's update.** Computing the variance as `mean(x²) − mean(x)²` subtracts two nearly equal numbers and loses precision. Welford's method updates the mean and the sum of squared deviations one value at a time:

```
delta = x − mean
mean += delta / i
m2   += delta · (x − mean)
variance = m2 / (n − 1)
```

---

## 4. Scoring

Each question kind is scored differently.

| Kind | Error | Points |
|---|---|---|
| point | \|answer − truth\| | 1 if within tolerance, else 0 |
| speed | \|answer − truth\| | if right: 1 at or under the target time, then target / seconds |
| decision | EV lost = best EV − EV of your choice | 1 if no EV lost, else 0 |
| probability | Brier score (p − o)² | 1 − Brier |
| interval | interval score | 1 if the truth is inside, else 0 |

**Brier score.** For a forecast p of an event with outcome o (1 = happened, 0 = didn't), the score is `(p − o)²`. It is a *proper* scoring rule: if the true chance is q, your expected score `q(1 − p)² + (1 − q)p²` is lowest at p = q. Shading your forecast in either direction can only make it worse on average. The best possible average is `q(1 − q)`, which is why a 50/50 event can never score better than 0.25.

**Interval score (Winkler).** For a central interval [lo, hi] at level 1 − α:

```
score = (hi − lo) + (2/α) · (lo − truth)   if truth < lo
                  + (2/α) · (truth − hi)   if truth > hi
```

Narrow intervals score well, but a miss costs 2/α per unit, which is 20 per unit for a 90% interval. Like the Brier score, it is proper: you do best by giving your honest 5% and 95% points. Over many questions, the share of intervals that contain the truth (the hit rate) should be close to the stated level. If it is well below, you are overconfident.

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

The **dice demo** (`edge-engine play dice`) uses all of this. Each round a target k is drawn and two dice are rolled. The number of ways to roll a sum s is `6 − |s − 7|` for s from 2 to 12, so `P(sum ≥ k)` is a sum of those counts over 36. An even-money bet on it has `EV = p·(+1) + (1 − p)·(−1) = 2p − 1`, so you should take it exactly when p > 1/2, which means k ≤ 7.
