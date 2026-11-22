# Phase 1 — Mental Maths Speed: how it works

```
edge-engine play mental                              # 120-second sprint
edge-engine play mental -o mode=test                 # 80 questions in 8 minutes, +1 / −1
edge-engine play mental -o mode=practice             # 20 questions, no clock
edge-engine play mental -o categories=odds,percent   # only some categories
edge-engine play mental -o adaptive=false            # every category equally often
edge-engine stats --module mental                    # where you are slow or wrong
```

Type `s` to skip a question and `q` to stop.

---

## 1. Question categories

| Category | Examples | Target | Counts as right |
|---|---|---|---|
| add | 347 + 486 | 5 s | exact |
| sub | 503 − 278 | 6 s | exact |
| mul | 47 × 8, 14 × 37 | 8 s | exact |
| div | 672 ÷ 8 | 8 s | exact |
| decimals | 0.3 × 0.7, 4.8 ÷ 0.6, 4.58 + 6.1 | 10 s | exact |
| fractions | 3/4 + 1/6, 5/6 × 7/10 | 15 s | within 0.005 |
| percent | 15% of 240; 18 is what % of 72; from 80 to 100 | 10 s | exact |
| estimation | 347 × 62, 8214 ÷ 37 | 12 s | within 2% |
| odds | 5 to 2 against → %; 20% → odds; pot odds | 12 s | within 0.5 points (0.05 for odds) |

Fractions can be typed as `11/12` or as a decimal. Percent answers are plain numbers: `25` and `25%` mean the same.

**Generation and truth are separate.** A generator picks operands with the seeded RNG and stores them in the question (`{"op": "+", "a": "3/4", "b": "1/6"}`). A separate function, `solve`, computes the exact answer from those operands using fractions. The generators are written so the answers come out clean: divisions come out whole, and percent questions have whole-number inputs. `solve` does not rely on that, so the tests can check it on its own.

---

## 2. Techniques the explanations use

**Addition: left to right.** 347 + 486 → 347 + 400 = 747, + 80 = 827, + 6 = 833. You keep one running total instead of carrying digits.

**Subtraction: round and add back.** 503 − 278 → 503 − 280 = 223, then add back 2 → 225.

**Multiplication: split one factor.** 47 × 8 = 40 × 8 + 7 × 8 = 320 + 56 = 376. For a teen times a two-digit number: 14 × 37 = 10 × 37 + 4 × 37 = 370 + 148 = 518.

**Decimals: drop the points.** 0.3 × 0.7 → 3 × 7 = 21, two decimal places → 0.21. For division, scale both numbers by the same power of 10: 4.8 ÷ 0.6 = 48 ÷ 6 = 8.

**Fractions: lowest common denominator.** 3/4 + 1/6 → LCD 12 → 9/12 + 2/12 = 11/12.

**Percent: build from 10%.** 10% of 240 is 24, 5% is 12, so 15% is 36. "18 is what % of 72" is 18/72 = 0.25 = 25%. Percentage change is always measured against the *starting* value: 80 → 100 is +25%, but 100 → 80 is −20%.

**Estimation: round, then adjust.** 347 × 62 → 350 × 62 = 21,700, then subtract 3 × 62 = 186 → 21,514. For division, find a round multiple first: 8214 ÷ 37 → 37 × 220 = 8140, and the remaining 74 is 2 more 37s → 222.

**Odds.**
- "a to b against" means you win b times out of a + b: 5 to 2 against → 2/7 ≈ 28.6%.
- A chance p is odds of (1 − p)/p to 1 against: 20% → 0.8/0.2 = 4 to 1.
- **Pot odds:** facing a bet B into a pot P, you call B to win a final pot of P + 2B, so you need equity of at least B / (P + 2B). A half-pot bet (50 into 100) needs 50/200 = 25%; a pot-sized bet (100 into 100) needs 100/300 = 1/3.

---

## 3. Modes and the clock

| Mode | Limit | Score |
|---|---|---|
| sprint | 120 s | +1 per correct answer |
| test | 80 questions or 480 s | +1 right, −1 wrong, 0 skipped |
| practice | 20 questions, no clock | +1 per correct answer |

**The clock counts answering time only:** the time between a question appearing and your answer. Reading the explanation and tip afterwards is free. An answer that finishes after time has run out is still saved (it is practice data), but it does not count towards the score.

**When to skip in test mode.** With +1 / −1 scoring, answering is worth it when your chance of being right p satisfies p − (1 − p) > 0, which means p > 1/2. Skipping scores 0, but it also saves time for questions you can answer.

**Points per question.** Separately from the mode score, each correct answer earns `min(1, target / seconds)` points, so you get full points at or under the target time. Wrong and skipped answers earn 0.

---

## 4. Adaptive sampling

The next category is chosen at random, weighted towards your weak spots. For each category, with n answers, w of them wrong or skipped, total time s, and target time T:

```
error rate   e = (w + 1) / (n + 2)
time ratio   r = ((s + 2T) / (n + 2)) / T
weight       raw = r × e
probability  p = 0.75 × raw / (sum of raw) + 0.25 / (number of categories)
```

**Why the +1, +2 and 2T?** Without them, a category with one lucky answer would have an error rate of 0 and never come up again. The `(w + 1)/(n + 2)` form (Laplace's rule of succession) starts every category at 1/2 and moves towards the true rate as answers come in. In the same way, the time ratio starts as if you had already answered twice at exactly the target time.

**Why multiply?** A category where you are both slow *and* wrong should come up most. Being twice as slow or twice as error-prone each doubles the weight.

**Why the 25% floor?** It keeps every category in the mix, so you don't lose skills you are already good at, and the estimates for strong categories keep getting updated.

**History.** Before a session, the stats from earlier sessions are loaded from the history database. Each category's history counts for at most 50 answers (scaled down proportionally), so a category you have improved on stops being over-weighted after a few dozen new answers.

Example: with fractions answered wrong and slowly, and everything else right and fast, the share of fraction questions climbs from 1/3 to above 60% within a few dozen questions (this is one of the tests).

---

## 5. Tips

Every answer gets a worked explanation for its exact numbers. A general technique tip is added when the answer was wrong, skipped, or slower than the category's target time.
