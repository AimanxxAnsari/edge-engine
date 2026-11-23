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

Each technique is a small algebraic identity that turns one hard step into easier ones.

**Addition: left to right.** Split the second number by place value and keep one running total:

```math
347 + 486 = \bigl((347 + 400) + 80\bigr) + 6 = (747 + 80) + 6 = 827 + 6 = 833 .
```

**Subtraction: compensation.** For any convenient $`b'`$ (usually the next multiple of 10 above $`b`$):

```math
a - b = (a - b') + (b' - b), \qquad 503 - 278 = (503 - 280) + 2 = 225 .
```

**Multiplication: the distributive law.** Split one factor into tens and units:

```math
(10t + u)\,c = 10t\,c + u\,c, \qquad 47 \times 8 = 320 + 56 = 376, \qquad 14 \times 37 = 370 + 148 = 518 .
```

**Decimals: scale to whole numbers.** Multiply whole numbers and count the decimal places; for division the scale cancels:

```math
x \cdot y = \frac{(10^m x)(10^n y)}{10^{m+n}} \;\Rightarrow\; 0.3 \times 0.7 = \frac{3 \times 7}{10^2} = 0.21,
\qquad \frac{x}{y} = \frac{10^k x}{10^k y} \;\Rightarrow\; \frac{4.8}{0.6} = \frac{48}{6} = 8 .
```

**Fractions: the lowest common denominator** $`L = \mathrm{lcm}(b, d)`$:

```math
\frac{a}{b} + \frac{c}{d} = \frac{a\,(L/b) + c\,(L/d)}{L}, \qquad \frac34 + \frac16 = \frac{9 + 2}{12} = \frac{11}{12},
\qquad \frac{a}{b} \cdot \frac{c}{d} = \frac{ac}{bd} \ \text{(cancel first)} .
```

**Percent: build from 10%.** $`p\%`$ of $`n`$ is $`\frac{p}{100} n`$; 10% is a shift of the decimal point, so 15% of 240 is $`24 + 12 = 36`$. "18 is what % of 72" is $`18/72 = 0.25 = 25\%`$.

**Percentage change** is measured against the *starting* value $`x`$:

```math
\Delta\% = \frac{y - x}{x} \times 100, \qquad 80 \to 100: +25\%, \qquad 100 \to 80: -20\% .
```

It is not symmetric: a rise of $`r`$ followed by a fall of $`r`$ leaves $`(1+r)(1-r) = 1 - r^2 < 1`$ of the start.

**Estimation: round, then adjust.** Round one factor to a convenient $`a'`$ and correct exactly:

```math
a \times b = a' b - (a' - a)\,b, \qquad 347 \times 62 = 350 \times 62 - 3 \times 62 = 21\,700 - 186 = 21\,514 .
```

Rounding *both* factors is riskier, because relative errors add:

```math
\frac{(a + \delta_a)(b + \delta_b)}{ab} \approx 1 + \frac{\delta_a}{a} + \frac{\delta_b}{b} .
```

For division, find a round multiple first: $`8214 \div 37`$: $`37 \times 220 = 8140`$, and the remaining $`74 = 2 \times 37`$, so the answer is 222.

**Odds.**
- "$`a`$ to $`b`$ against" means $`a`$ losses for every $`b`$ wins: $`P(\text{win}) = \dfrac{b}{a + b}`$. So 5 to 2 against is $`2/7 \approx 28.6\%`$.
- A chance $`p`$ is odds of $`\dfrac{1 - p}{p}`$ to 1 against: 20% is $`0.8 / 0.2 = 4`$ to 1.
- **Pot odds.** Facing a bet $`B`$ into a pot $`P`$, calling puts in $`B`$ to win a final pot of $`P + 2B`$. With equity $`q`$:

```math
\mathrm{EV}(\text{call}) = q\,(P + 2B) - B \ge 0 \iff q \ge \frac{B}{P + 2B} .
```

A half-pot bet ($`B = P/2`$) needs 25%; a pot-sized bet ($`B = P`$) needs $`\tfrac13`$.

---

## 3. Modes and the clock

| Mode | Limit | Score |
|---|---|---|
| sprint | 120 s | +1 per correct answer |
| test | 80 questions or 480 s | +1 right, −1 wrong, 0 skipped |
| practice | 20 questions, no clock | +1 per correct answer |

**The clock counts answering time only:** the time between a question appearing and your answer. Reading the explanation and tip afterwards is free. An answer that finishes after time has run out is still saved (it is practice data), but it does not count towards the score.

**When to skip in test mode.** If you are right with probability $`p`$, answering is worth

```math
\mathbb{E}[\text{score}] = p \cdot (+1) + (1 - p) \cdot (-1) = 2p - 1,
```

and skipping is worth 0, so answer when $`p > \tfrac12`$. Time matters too: a skip that saves 20 seconds buys more questions you are confident about.

**Points per question.** Separately from the mode score, a correct answer taking $`t`$ seconds against a target $`T`$ earns

```math
\text{points} = \min\left(1, \frac{T}{t}\right),
```

so you get full points at or under the target time. Wrong and skipped answers earn 0.

---

## 4. Adaptive sampling

The next category is chosen at random, weighted towards your weak spots. For a category $`c`$ with $`n`$ answers, $`w`$ of them wrong or skipped, total time $`s`$ and target time $`T`$:

```math
e_c = \frac{w + 1}{n + 2}, \qquad
r_c = \frac{(s + 2T)/(n + 2)}{T}, \qquad
P(c) = 0.75\,\frac{r_c\,e_c}{\sum_{c'} r_{c'}\,e_{c'}} + \frac{0.25}{C},
```

where $`C`$ is the number of categories.

**Why the +1, +2 and 2T?** Without them, a category with one lucky answer would have an error rate of 0 and never come up again. The error rate is a Bayesian estimate: put a uniform prior on the true error rate $`\theta`$, i.e. $`\theta \sim \mathrm{Beta}(1, 1)`$. After $`w`$ errors in $`n`$ answers the posterior is $`\mathrm{Beta}(w + 1,\ n - w + 1)`$, whose mean is

```math
\mathbb{E}[\theta \mid \text{data}] = \frac{w + 1}{n + 2}
```

(Laplace's rule of succession). It starts every category at $`\tfrac12`$ and moves towards $`w/n`$ as answers come in. In the same way, the time ratio starts as if you had already answered twice at exactly the target time, so it begins at 1.

**Why multiply?** A category where you are both slow *and* wrong should come up most. Being twice as slow or twice as error-prone each doubles the weight $`r_c e_c`$.

**Why the 25% floor?** It keeps every category in the mix ($`P(c) \ge 0.25/C`$), so you don't lose skills you are already good at, and the estimates for strong categories keep getting updated.

**History.** Before a session, the stats from earlier sessions are loaded from the history database. Each category's history counts for at most 50 answers: if there are $`n > 50`$, then $`n`$, $`w`$ and $`s`$ are all scaled by $`50/n`$. A category you have improved on stops being over-weighted after a few dozen new answers.

Example: with fractions answered wrong and slowly, and everything else right and fast, the share of fraction questions climbs from $`\tfrac13`$ to above 60% within a few dozen questions (this is one of the tests).

---

## 5. Tips

Every answer gets a worked explanation for its exact numbers. A general technique tip is added when the answer was wrong, skipped, or slower than the category's target time.
