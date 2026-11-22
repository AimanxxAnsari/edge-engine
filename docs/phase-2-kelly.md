# Phase 2 — Coin Flip with an Edge: the maths of bet sizing

```
edge-engine play kelly                          # $25, a 60% coin, 50 flips
edge-engine play kelly -o flips=300 -o cap=250  # the classic experiment's setup
edge-engine play kelly -o mode=unknown          # the bias is hidden
edge-engine lab kelly                           # tables, simulations, fan chart
edge-engine lab kelly -o p=0.55 -o flips=100    # a different coin
```

Bets: `5` is $5 on heads, `-5` is $5 on tails, `20%` is 20% of your bankroll.

---

## 1. The setup

You start with $25. A coin lands heads with probability p = 0.6, and you can bet any amount up to your bankroll at even money: win and you gain the stake, lose and you lose it. The edge is clearly yours. The question is **how much to bet**.

In 2016 Victor Haghani and Richard Dewey ran this experiment with 61 people, mostly finance students and professionals: $25, a 60% coin, 30 minutes, winnings capped at $250. About 30% went bust and the average payout was about $91. Having an edge was not enough; the size of the bets decided the outcome.

---

## 2. The Kelly criterion

Bet a fixed fraction f of your bankroll each time. After n bets with k wins:

```
W_n = W_0 · (1 + f)^k · (1 − f)^(n − k)
```

Taking logs and dividing by n, the growth per bet tends to

```
g(f) = p · ln(1 + f) + q · ln(1 − f)        (q = 1 − p)
```

Setting the derivative to zero, `p/(1 + f) − q/(1 − f) = 0`, gives the **Kelly fraction**

```
f* = p − q = 2p − 1                          (even money)
f* = (b·p − q) / b                           (a win pays b times the stake)
```

For p = 0.6, f* = 0.2: bet 20% of whatever you have now.

| Fraction | × Kelly | g(f) per flip | Comment |
|---|---|---|---|
| 0.05 | 0.25 | 0.0088 | very safe, slow |
| 0.10 | 0.5 | 0.0150 | 75% of the best growth, much smaller swings |
| 0.20 | 1 | 0.0201 | the maximum |
| 0.30 | 1.5 | 0.0148 | same growth as ~0.1, far bigger swings |
| 0.39 | 1.95 | 0 | growth is zero |
| 0.40 | 2 | −0.0024 | **you shrink on average despite the edge** |
| 1.00 | — | −∞ | one tails and you are out |

Near the top, g is roughly a parabola: `g(c·f*) ≈ g(f*) · c · (2 − c)`. Half Kelly keeps 75% of the growth; double Kelly gets zero. Over-betting costs far more than under-betting by the same amount, which is why many professionals bet half Kelly or less: their estimate of p is never exact.

**Why it works.** Every bet multiplies your wealth, so what matters is the *average of the logs*, not the average of the outcomes. Betting to maximise the expected *wealth* means going all-in every time (expected wealth 1.2× per flip), and that ends at zero with probability 1.

---

## 3. The mean misleads; the median doesn't

Your final wealth depends only on the number of wins k, and k is Binomial(n, p). So everything can be computed exactly.

```
mean      E[W_n] = W_0 · (1 + f·(2p − 1))^n
median    the wealth at the median k (wealth rises with k)
P(W_n < x·W_0) = sum of the binomial probabilities of the k that end below x·W_0
```

For 300 flips from $25 at full Kelly, the mean is about $3.2 million but the median is about $10,500. At double Kelly the mean is $266 billion while the median is $12, below the start. A few astronomically lucky runs inflate the mean; the median is what a typical player gets. `edge-engine lab kelly` prints this table for any coin.

Even at full Kelly, the chance of ending 300 flips below the start is about 4%. After only 100 flips it is about 18%.

---

## 4. Drawdowns and ruin

**Proportional betting never goes broke** (you always keep 1 − f of what you have), but it can fall a long way. A continuous-time approximation for the chance of *ever* falling to a fraction x of the start, when betting c × Kelly:

```
P(ever reaching x·W_0) ≈ x^(2/c − 1)
```

At full Kelly (c = 1) that is x itself: a 50% chance of halving at some point, and a 10% chance of falling to a tenth. At half Kelly it is x³: 12.5% for halving. The simulation in the lab agrees closely (it is a little lower, because the game is finite and the coin is discrete).

**Fixed-size bets can go broke.** Betting $b each time from W_0, with no time limit, the classic gambler's-ruin result is

```
P(ruin) = (q/p)^(W_0 / b)
```

With $5 bets from $25 that is (0.4/0.6)⁵ ≈ 13%, even with a 60% coin. With $10 bets you can survive only 2 net losses, giving 44%.

---

## 5. The cap

With a $250 cap, wealth above the cap is worthless. The game uses a simple rule: Kelly, but never bet more than you need to reach the cap. The exact best strategy with a cap and a fixed number of flips needs dynamic programming over every bankroll and every flip left, and is not part of this phase.

---

## 6. Unknown bias: Bayesian Kelly

In `mode=unknown` the coin's bias p is drawn from a **Beta(5, 5)** distribution (centred on 0.5, usually between 0.25 and 0.75) and hidden. After h heads and t tails the posterior is Beta(5 + h, 5 + t), with mean

```
m = (5 + h) / (10 + h + t)
```

The prior acts like 5 heads and 5 tails you have "already seen", which pulls early estimates towards 0.5.

**Kelly with an uncertain p uses the mean.** For the next bet,

```
E[ log W ] = E[p]·ln(1 + f) + (1 − E[p])·ln(1 − f)
```

so the best fraction is `2m − 1`. The bet does not change what you learn (you see the flip either way), so betting this way at every flip also maximises the expected log of the *final* wealth. The game compares you with this Bayes-Kelly player, with a Bayes half-Kelly player, and with an "oracle" that knows p.

---

## 7. How the game scores you

| Question | When | Truth | Right if |
|---|---|---|---|
| Kelly fraction | start (classic) | 2p − 1 | within 0.01 |
| P(finish below start betting 30%) | start (classic) | exact binomial | within 0.05 |
| Your bet | every flip | the Kelly bet in dollars | within 5% of your bankroll |
| P(heads) estimate | every 10 flips (unknown) | posterior mean | within 0.03 |

After each flip the game shows your growth rate against Kelly's. At the end it shows the final bankrolls of the comparison strategies **on the same flips**, which takes luck out of the comparison, plus a fan chart of 1,000 simulated runs at your average bet size.
