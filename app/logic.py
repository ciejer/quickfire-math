"""Core question generation and formatting logic."""
from __future__ import annotations

import random
from typing import Tuple
from .models import UserSettings

# Problem is (prompt_str, correct_answer, tts_text)
Problem = Tuple[str, int, str]


def _tts_for(op: str, a: int, b: int, ans: int) -> str:
    words = {
        "addition": f"{a} plus {b} equals {ans}",
        "subtraction": f"{a} minus {b} equals {ans}",
        "multiplication": f"{a} times {b} equals {ans}",
        "division": f"{a} divided by {b} equals {ans}",
    }
    return words[op]


def _sym_bounds(lo: int, hi: int) -> tuple[int, int]:
    if lo > hi:
        lo, hi = hi, lo
    return lo, hi


def _rand(a: int, b: int) -> int:
    a, b = _sym_bounds(a, b)
    return random.randint(a, b)


def generate_problem(op: str, s: UserSettings) -> Problem:
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
        max_q = max(1, min(12, s.div_dividend_max // divisor))
        quotient = _rand(1, max_q)
        dividend = divisor * quotient
        ans = quotient
        return (f"{dividend} ÷ {divisor}", ans, _tts_for(op, dividend, divisor, ans))

    raise ValueError("Unsupported op")


def human_settings(op: str, s: UserSettings) -> str:
    if op == "addition":
        return f"Add: {s.add_min}–{s.add_max}"
    if op == "subtraction":
        return f"Subtract: {s.sub_min}–{s.sub_max}"
    if op == "multiplication":
        return f"Multiply: A {s.mul_a_min}–{s.mul_a_max}, B {s.mul_b_min}–{s.mul_b_max}"
    if op == "division":
        q_hi = min(12, s.div_dividend_max // max(1, s.div_divisor_min))
        return f"Divide: divisor {s.div_divisor_min}–{s.div_divisor_max}, quotient ≤ {q_hi}"
    return ""
