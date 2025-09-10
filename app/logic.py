"""Core question generation and formatting logic."""

from __future__ import annotations

import random
from typing import Literal, Tuple

from .models import UserSettings, DrillType

# Problem is (prompt_str, correct_answer, tts_text)
Problem = Tuple[str, int, str]


def _tts_for(op: DrillType, a: int, b: int, ans: int) -> str:
    """Return a human‑readable spoken phrase for the operation."""
    words = {
        "addition": f"{a} plus {b} equals {ans}",
        "subtraction": f"{a} minus {b} equals {ans}",
        "multiplication": f"{a} times {b} equals {ans}",
        "division": f"{a} divided by {b} equals {ans}",
    }
    return words[op]


def _sym_bounds(lo: int, hi: int) -> Tuple[int, int]:
    """Ensure min and max are in the right order."""
    if lo > hi:
        lo, hi = hi, lo
    return lo, hi


def _rand(a: int, b: int) -> int:
    """Random integer between inclusive bounds (order independent)."""
    a, b = _sym_bounds(a, b)
    return random.randint(a, b)


def generate_problem(op: DrillType, s: UserSettings) -> Problem:
    """Generate a new problem for the given operation and user settings."""
    if op == "addition":
        a, b = _rand(s.add_min, s.add_max), _rand(s.add_min, s.add_max)
        ans = a + b
        return (f"{a} + {b}", ans, _tts_for(op, a, b, ans))
    if op == "subtraction":
        a, b = _rand(s.sub_min, s.sub_max), _rand(s.sub_min, s.sub_max)
        if a < b:
            a, b = b, a
        ans = a - b
        return (f"{a} − {b}", ans, _tts_for(op, a, b, ans))
    if op == "multiplication":
        a = _rand(s.mul_a_min, s.mul_a_max)
        b = _rand(s.mul_b_min, s.mul_b_max)
        ans = a * b
        return (f"{a} × {b}", ans, _tts_for(op, a, b, ans))
    if op == "division":
        divisor = _rand(s.div_divisor_min, s.div_divisor_max) or 1
        max_q = max(1, s.div_dividend_max // divisor)
        quotient = _rand(1, max_q)
        dividend = divisor * quotient
        ans = quotient
        return (f"{dividend} ÷ {divisor}", ans, _tts_for(op, dividend, divisor, ans))
    raise ValueError("Unsupported op")


def human_settings(op: DrillType, s: UserSettings) -> str:
    """Produce a brief summary of the settings for display."""
    if op == "addition":
        return f"Add: {s.add_min}–{s.add_max}"
    if op == "subtraction":
        return f"Subtract: {s.sub_min}–{s.sub_max}"
    if op == "multiplication":
        return f"Multiply: A {s.mul_a_min}–{s.mul_a_max}, B {s.mul_b_min}–{s.mul_b_max}"
    if op == "division":
        return f"Divide: dividend ≤ {s.div_dividend_max}, divisor {s.div_divisor_min}–{s.div_divisor_max}"
    return ""