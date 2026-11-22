"""Question generators, the exact truth function, worked explanations and tips.

A generator draws operands and returns a JSON-friendly params dict. `solve(params)`
computes the exact answer as a Fraction, independently of how the operands were chosen.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from math import gcd, lcm
from typing import Any

from ...rng import Rng

Params = dict[str, Any]

SYMBOLS = {"+": "+", "-": "−", "*": "×", "/": "÷"}


# --- exact answers ----------------------------------------------------------


def F(x: Any) -> Fraction:
    """'3/4', '0.3', '12' or an int -> Fraction."""
    return Fraction(str(x))


def solve(p: Params) -> Fraction:
    """The exact answer to a question, from its params alone."""
    op = p["op"]
    if op in SYMBOLS:
        a, b = F(p["a"]), F(p["b"])
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        return a / b
    if op == "pct_of":  # p% of n
        return F(p["pct"]) * F(p["n"]) / 100
    if op == "what_pct":  # a is what % of b
        return F(p["a"]) / F(p["b"]) * 100
    if op == "pct_change":  # from x to y, in %
        x, y = F(p["x"]), F(p["y"])
        return (y - x) / x * 100
    if op == "odds_to_pct":  # a to b against -> chance of winning in %
        a, b = F(p["a"]), F(p["b"])
        return b / (a + b) * 100
    if op == "pct_to_odds":  # chance p% -> odds of X to 1 against
        q = F(p["pct"]) / 100
        return (1 - q) / q
    if op == "pot_odds":  # equity needed to call, in %
        pot, bet = F(p["pot"]), F(p["bet"])
        return bet / (pot + 2 * bet) * 100
    raise ValueError(f"unknown op {op!r}")


def tolerance(p: Params, truth: Fraction) -> float:
    """Allowed absolute error for this question."""
    if "rel_tol" in p:
        return float(abs(truth) * F(p["rel_tol"]))
    return float(p.get("tol", 0))


def fmt(x: Fraction) -> str:
    """Integers as integers, short decimals as decimals, else 'p/q (≈ d)'."""
    if x.denominator == 1:
        return str(x.numerator)
    d = x.denominator
    while d % 2 == 0:
        d //= 2
    while d % 5 == 0:
        d //= 5
    if d == 1:  # terminating decimal
        s = f"{float(x):.6f}".rstrip("0").rstrip(".")
        if F(s) == x:
            return s
    return f"{x.numerator}/{x.denominator} (≈ {float(x):.4f})"


def approx(x: Fraction) -> str:
    """'= 25', '= 12.5' when exact and short, else '≈ 66.67'."""
    shown = fmt(x)
    return f"= {shown}" if "/" not in shown else f"≈ {float(x):.2f}"


def _n(x: Any) -> str:
    """Operand as shown in a prompt."""
    return fmt(F(x)) if "/" not in str(x) else str(x)


# --- prompts ----------------------------------------------------------------


def prompt(p: Params) -> str:
    op = p["op"]
    if op in SYMBOLS:
        lead = "Estimate (within 2%): " if p.get("rel_tol") else ""
        return f"{lead}{_n(p['a'])} {SYMBOLS[op]} {_n(p['b'])}"
    if op == "pct_of":
        return f"{_n(p['pct'])}% of {_n(p['n'])}"
    if op == "what_pct":
        return f"{_n(p['a'])} is what percent of {_n(p['b'])}?"
    if op == "pct_change":
        return f"From {_n(p['x'])} to {_n(p['y'])}: percentage change? (negative for a fall)"
    if op == "odds_to_pct":
        return f"Odds of {p['a']} to {p['b']} against. Chance of winning, in %?"
    if op == "pct_to_odds":
        return f"A {_n(p['pct'])}% chance is odds of X to 1 against. X?"
    if op == "pot_odds":
        return (
            f"The pot is {p['pot']} and your opponent bets {p['bet']}. "
            "What equity (in %) do you need to call?"
        )
    raise ValueError(f"unknown op {op!r}")


# --- worked explanations ----------------------------------------------------


def _place_parts(b: int) -> list[int]:
    """347 -> [300, 40, 7] (zeros dropped)."""
    digits = str(b)
    parts = [int(d) * 10 ** (len(digits) - i - 1) for i, d in enumerate(digits)]
    return [x for x in parts if x] or [0]


def explain(p: Params) -> str:
    op, ans = p["op"], solve(p)
    cat = p["cat"]
    if cat == "add":
        a, b = int(p["a"]), int(p["b"])
        steps, total = [], a
        for part in _place_parts(b):
            total += part
            steps.append(f"+ {part} = {total}")
        return f"{a} " + ", ".join(steps) + "."
    if cat == "sub":
        a, b = int(p["a"]), int(p["b"])
        up = -(-b // 10) * 10
        if up == b:
            return f"{a} − {b} = {ans}."
        return f"Round {b} up to {up}: {a} − {up} = {a - up}, then add back {up - b}: {ans}."
    if cat == "mul":
        a, b = int(p["a"]), int(p["b"])
        big, small = (a, b) if b < 10 else (b, a)
        if small < 10:
            t, u = big // 10 * 10, big % 10
            if u == 0:
                return f"{t // 10} × {small} = {t // 10 * small}, then add a zero: {ans}."
            return (
                f"{big} × {small} = {t}×{small} + {u}×{small} = {t * small} + {u * small} = {ans}."
            )
        t, u = small // 10 * 10, small % 10  # teen x two-digit: split the teen
        return f"{small} × {big} = {t}×{big} + {u}×{big} = {t * big} + {u * big} = {ans}."
    if cat == "div":
        return f"{p['a']} ÷ {p['b']} = {ans}. Check: {ans} × {p['b']} = {p['a']}."
    if cat == "decimals":
        a, b = F(p["a"]), F(p["b"])
        if op == "*":
            da, db = _decimals(p["a"]), _decimals(p["b"])
            ia, ib = int(a * 10**da), int(b * 10**db)
            return (
                f"Drop the points: {ia} × {ib} = {ia * ib}; "
                f"{da + db} decimal place(s) in total → {fmt(ans)}."
            )
        if op == "/":
            scale = 10 ** max(_decimals(p["a"]), _decimals(p["b"]))
            return f"Multiply both by {scale}: {fmt(a * scale)} ÷ {fmt(b * scale)} = {fmt(ans)}."
        return f"Line up the points: {_n(p['a'])} {SYMBOLS[op]} {_n(p['b'])} = {fmt(ans)}."
    if cat == "fractions":
        a, b = F(p["a"]), F(p["b"])
        if op == "*":
            return f"Tops × tops, bottoms × bottoms: {a} × {b} = {fmt(ans)}."
        d = lcm(a.denominator, b.denominator)
        na, nb = a.numerator * d // a.denominator, b.numerator * d // b.denominator
        sign = "+" if op == "+" else "−"
        return f"Common denominator {d}: {na}/{d} {sign} {nb}/{d} = {fmt(ans)}."
    if op == "pct_of":
        n = F(p["n"])
        return f"10% of {fmt(n)} is {fmt(n / 10)}, so {_n(p['pct'])}% is {fmt(ans)}."
    if op == "what_pct":
        return f"{_n(p['a'])} / {_n(p['b'])} = {fmt(F(p['a']) / F(p['b']))} {approx(ans)}%."
    if op == "pct_change":
        x, y = F(p["x"]), F(p["y"])
        return f"Change / start = {fmt(y - x)} / {fmt(x)} {approx(ans)}%."
    if op in ("*", "/") and cat == "estimation":
        a, b = int(p["a"]), int(p["b"])
        band = f"within 2% means ±{float(abs(ans)) * 0.02:,.1f}"
        if op == "*":
            ra = round(a, -1)
            diff = a - ra
            sign = "+" if diff >= 0 else "−"
            return (
                f"Round {a} to {ra}: {ra} × {b} = {ra * b:,}, then {sign} {abs(diff)} × {b} "
                f"= {abs(diff) * b:,} → {a * b:,}. Anything {band} counts."
            )
        q2 = _round_sig(a // b, 2) or 1
        rest = a - b * q2
        return (
            f"{b} × {q2} = {b * q2:,}; the remaining {rest:,} is about {rest / b:.1f} more "
            f"{b}s, so ≈ {float(ans):,.1f}; {band}."
        )
    if op == "odds_to_pct":
        a, b = p["a"], p["b"]
        return f"{a} to {b} against: you win {b} times in {a + b}, so {b}/{a + b} {approx(ans)}%."
    if op == "pct_to_odds":
        q = F(p["pct"])
        return f"Lose {fmt(100 - q)}, win {fmt(q)}: {fmt(100 - q)}/{fmt(q)} {approx(ans)} to 1."
    if op == "pot_odds":
        pot, bet = int(p["pot"]), int(p["bet"])
        total = pot + 2 * bet
        return (
            f"You call {bet} to win a final pot of {total} ({pot} + {bet} + your {bet}): "
            f"{bet}/{total} {approx(ans)}%."
        )
    raise ValueError(f"unknown question {p!r}")


def _decimals(s: Any) -> int:
    s = str(s)
    return len(s.split(".")[1]) if "." in s else 0


def _round_sig(x: int, sig: int) -> int:
    """Round to `sig` significant figures."""
    digits = len(str(abs(x)))
    factor = 10 ** max(digits - sig, 0)
    return int(round(x / factor) * factor)


# --- generators -------------------------------------------------------------


def gen_add(rng: Rng) -> Params:
    return {"op": "+", "a": rng.randint(100, 999), "b": rng.randint(100, 999)}


def gen_sub(rng: Rng) -> Params:
    a = rng.randint(200, 999)
    return {"op": "-", "a": a, "b": rng.randint(100, a - 1)}


def gen_mul(rng: Rng) -> Params:
    if rng.random() < 0.7:
        a = rng.randint(12, 98)
        a += a % 10 == 0  # skip multiples of 10: 30 x 7 is too easy
        return {"op": "*", "a": a, "b": rng.randint(3, 9)}
    return {"op": "*", "a": rng.randint(11, 19), "b": rng.randint(12, 99)}


def gen_div(rng: Rng) -> Params:
    d, q = rng.randint(3, 12), rng.randint(12, 99)
    return {"op": "/", "a": d * q, "b": d}


def gen_decimals(rng: Rng) -> Params:
    kind = rng.randbelow(3)
    if kind == 0:  # 0.3 x 0.7, 4.6 x 0.8
        return {
            "op": "*",
            "a": fmt(F(rng.randint(2, 99)) / 10),
            "b": fmt(F(rng.randint(2, 9)) / 10),
        }
    if kind == 1:  # 4.8 / 0.6 = 8
        d, q = rng.randint(2, 9), rng.randint(2, 12)
        return {"op": "/", "a": fmt(F(d * q) / 10), "b": fmt(F(d) / 10)}
    a, b = F(rng.randint(100, 999)) / 100, F(rng.randint(10, 99)) / 10
    op = rng.choice("+-")
    if op == "-" and b > a:
        a, b = b, a
    return {"op": op, "a": fmt(a), "b": fmt(b)}


DENOMINATORS = (2, 3, 4, 5, 6, 8, 10, 12)


def _proper_fraction(rng: Rng) -> Fraction:
    d = rng.choice(DENOMINATORS)
    while True:
        f = Fraction(rng.randint(1, d - 1), d)
        if f.denominator == d:  # already in lowest terms
            return f


def gen_fractions(rng: Rng) -> Params:
    a, b = _proper_fraction(rng), _proper_fraction(rng)
    op = rng.choice("+-*")
    if op == "-" and b > a:
        a, b = b, a
    if op == "-" and a == b:
        op = "+"
    return {"op": op, "a": str(a), "b": str(b), "tol": "0.005"}


PCTS = ("1", "2.5", "5", "10", "12.5", "15", "20", "25", "30", "40", "45", "60", "75", "120")


def gen_percent(rng: Rng) -> Params:
    kind = rng.randbelow(3)
    if kind == 0:
        return {"op": "pct_of", "pct": rng.choice(PCTS), "n": 20 * rng.randint(1, 40)}
    if kind == 1:
        while True:
            b = rng.choice((20, 25, 40, 50, 60, 80, 120, 150, 200, 250, 400, 500))
            pct = F(rng.choice(PCTS))
            a = pct * b / 100
            if a.denominator == 1:
                return {"op": "what_pct", "a": int(a), "b": b, "unit": "percent"}
    while True:
        x = rng.choice((40, 50, 60, 80, 120, 150, 200, 250, 400))
        change = rng.choice((-50, -40, -25, -20, -10, 10, 20, 25, 30, 50, 75, 100, 150))
        y = F(x) * (100 + change) / 100
        if y.denominator == 1:
            return {"op": "pct_change", "x": x, "y": int(y), "unit": "percent"}


def gen_estimation(rng: Rng) -> Params:
    if rng.random() < 0.5:
        return {"op": "*", "a": rng.randint(101, 999), "b": rng.randint(11, 99), "rel_tol": "0.02"}
    return {"op": "/", "a": rng.randint(1000, 9999), "b": rng.randint(11, 99), "rel_tol": "0.02"}


def gen_odds(rng: Rng) -> Params:
    kind = rng.randbelow(3)
    if kind == 0:
        while True:  # odds against (a > b), in lowest terms: 3 to 1, 5 to 2, 7 to 4
            a, b = rng.randint(2, 9), rng.randint(1, 4)
            if a > b and gcd(a, b) == 1:
                break
        return {"op": "odds_to_pct", "a": a, "b": b, "unit": "percent", "tol": "0.5"}
    if kind == 1:
        pct = rng.choice(("10", "12.5", "20", "25", "40", "50", "60", "75"))
        return {"op": "pct_to_odds", "pct": pct, "tol": "0.05"}
    pot = rng.choice((60, 120, 180, 240, 300))
    frac = F(rng.choice(("1/4", "1/3", "1/2", "2/3", "3/4", "1")))
    return {"op": "pot_odds", "pot": pot, "bet": int(pot * frac), "unit": "percent", "tol": "0.5"}


@dataclass(frozen=True)
class Category:
    name: str
    target: float  # seconds for full points
    tip: str
    make: Callable[[Rng], Params]


CATEGORIES: dict[str, Category] = {
    c.name: c
    for c in (
        Category("add", 5, "Add from the left: hundreds, then tens, then units.", gen_add),
        Category(
            "sub",
            6,
            "Round the number you subtract up to a multiple of 10, subtract, then add back.",
            gen_sub,
        ),
        Category(
            "mul",
            8,
            "Split one number into tens and units and multiply each part (47×8 = 40×8 + 7×8).",
            gen_mul,
        ),
        Category(
            "div",
            8,
            "Run the times table backwards; halve both numbers first if they are even.",
            gen_div,
        ),
        Category(
            "decimals",
            10,
            "Drop the decimal points, work in whole numbers, then put the points back.",
            gen_decimals,
        ),
        Category(
            "fractions",
            15,
            "For + and −, use the lowest common denominator; for ×, cancel before multiplying.",
            gen_fractions,
        ),
        Category(
            "percent",
            10,
            "10% moves the decimal point; build other percentages from 10%, 5% and 1%.",
            gen_percent,
        ),
        Category(
            "estimation",
            12,
            "Round to a number that is easy to work with, then adjust for what you rounded.",
            gen_estimation,
        ),
        Category(
            "odds",
            12,
            "a to b against = b wins in a + b. A chance p is (1 − p)/p to 1 against. "
            "Pot odds: call / (pot + bet + call).",
            gen_odds,
        ),
    )
}


def make_params(rng: Rng, category: str) -> Params:
    p = CATEGORIES[category].make(rng)
    p["cat"] = category
    return p
