"""Question generation + star/level evaluation."""
from __future__ import annotations
import random
from collections import defaultdict
from typing import Dict, List, Tuple, Any

from .models import DrillTypeEnum
from .levels import thresholds_for_level  # <-- FIX: bring thresholds into this module


# -------------- Generation from presets

def _rand(a: int, b: int) -> int:
    if a > b: a, b = b, a
    return random.randint(a, b)

def _choose(seq):
    return random.choice(seq)

def generate_from_preset(drill_type: DrillTypeEnum, preset: Dict[str, Any]) -> Tuple[str, int, str]:
    """Return (prompt, answer, tts)."""
    if drill_type == DrillTypeEnum.multiplication:
        a = _rand(preset["a_min"], preset["a_max"])
        b = _choose(preset["b_set"])
        if preset.get("bias_hard"):
            # light weighting towards larger factors
            if random.random() < 0.5:
                a = max(a, _rand(max(preset["a_min"], 6), preset["a_max"]))
                b = max(b, _choose([7,8,9,10,11,12]))
        ans = a * b
        return (f"{a} × {b}", ans, f"{a} times {b} equals {ans}")

    if drill_type == DrillTypeEnum.addition:
        lo, hi = preset["min"], preset["max"]
        a, b = _rand(lo, hi), _rand(lo, hi)
        # encourage carrying sometimes
        if random.random() < preset.get("carry_bias", 0.0):
            # try to force a carry in ones column for 2-digit numbers
            a = max(10, _rand(10, max(10, hi)))
            b = max(10, _rand(10, max(10, hi)))
            while (a % 10) + (b % 10) < 10 and random.random() < 0.8:
                a = _rand(10, max(10, hi))
                b = _rand(10, max(10, hi))
        ans = a + b
        return (f"{a} + {b}", ans, f"{a} plus {b} equals {ans}")

    if drill_type == DrillTypeEnum.subtraction:
        lo, hi = preset["min"], preset["max"]
        a, b = _rand(lo, hi), _rand(lo, hi)
        if a < b: a, b = b, a
        # encourage borrowing sometimes
        if random.random() < preset.get("borrow_bias", 0.0) and a >= 10 and b >= 10:
            while (a % 10) >= (b % 10) and random.random() < 0.8:
                a = _rand(max(10, lo), hi)
                b = _rand(max(10, lo), hi)
                if a < b: a, b = b, a
        ans = a - b
        return (f"{a} − {b}", ans, f"{a} minus {b} equals {ans}")

    if drill_type == DrillTypeEnum.division:
        divs = preset["divisor_set"]
        d = _choose(divs) or 1
        q = _rand(preset["q_min"], preset["q_max"])
        dividend = d * q
        ans = q
        return (f"{dividend} ÷ {d}", ans, f"{dividend} divided by {d} equals {ans}")

    raise ValueError("Unsupported drill type")


# -------------- Metrics + star rule

def compute_first_try_metrics(qlog: List[dict]) -> dict:
    """
    qlog entries: {prompt,a,b,correct_answer,given_answer,correct,started_at,elapsed_ms}
    We consider the first attempt of each unique prompt; if it's correct => counts to ACC and TPQ.
    HARD mistakes = number of prompts with >=2 wrong attempts before first correct (or 2 wrong total if never correct).
    """
    attempts_by_prompt: Dict[str, List[dict]] = defaultdict(list)
    for e in qlog:
        attempts_by_prompt[e["prompt"]].append(e)

    total_items = 0
    first_try_correct = 0
    tpq_sum_ms = 0
    hard_mistakes = 0

    for prompt, attempts in attempts_by_prompt.items():
        # order by started_at just in case
        attempts.sort(key=lambda x: x["started_at"])
        if not attempts:
            continue
        total_items += 1
        first = attempts[0]
        if first["correct"]:
            first_try_correct += 1
            tpq_sum_ms += int(first.get("elapsed_ms", 0))
        # hard mistake = two wrong before first correct (or two wrong total if never correct)
        wrong_before_correct = 0
        for a in attempts:
            if a["correct"]:
                break
            wrong_before_correct += 1
        if wrong_before_correct >= 2:
            hard_mistakes += 1

    acc = (first_try_correct / total_items) if total_items else 0.0
    tpq_ms = (tpq_sum_ms / first_try_correct) if first_try_correct else None
    return {
        "items": total_items,
        "acc": acc,
        "tpq_ms": tpq_ms,
        "hard_mistakes": hard_mistakes,
    }


def ewma_update(old: float | None, new: float, alpha: float = 0.25) -> float:
    if old is None:
        return new
    return alpha * new + (1 - alpha) * old


def star_decision(level: int, metrics: dict, total_time_ms: int, ewma_tpq_ms: float | None) -> Tuple[bool, dict]:
    """
    Return (star_bool, explanation_dict).
    Gates:
      - Accuracy >= A(level)
      - Speed: TPQ <= CAP(level)  OR  (TPQ <= EWMA_TPQ * (1 - DELTA(level)))
      - Hard mistakes <= HM(level)
      - total_time <= TMAX(level)
    """
    A, CAP, DELTA, HM, TMAX = thresholds_for_level(level)
    exp: dict[str, str | float | int | None] = {
        "A": A, "CAP": CAP, "DELTA": DELTA, "HM": HM, "TMAX": TMAX,
        "acc": metrics["acc"], "tpq_ms": metrics["tpq_ms"], "hard_mistakes": metrics["hard_mistakes"],
    }

    # Accuracy gate
    if metrics["acc"] < A:
        exp["why"] = "accuracy_below_gate"
        return False, exp

    # Time cap (whole drill)
    if total_time_ms > TMAX * 1000:
        exp["why"] = "over_total_time_cap"
        return False, exp

    # Hard mistakes
    if metrics["hard_mistakes"] > HM:
        exp["why"] = "too_many_hard_mistakes"
        return False, exp

    # Speed gate: if no tpq (0 first-try correct), fail
    tpq_ms = metrics["tpq_ms"]
    if tpq_ms is None:
        exp["why"] = "no_first_try_correct"
        return False, exp

    abs_ok = (tpq_ms / 1000.0) <= CAP
    imp_ok = False
    if ewma_tpq_ms is not None:
        imp_ok = tpq_ms <= ewma_tpq_ms * (1.0 - DELTA)

    if not (abs_ok or imp_ok):
        exp["why"] = "too_slow"
        return False, exp

    exp["why"] = "ok"
    return True, exp


def levelup_decision(stars_recent: str, this_star: bool) -> bool:
    """
    Level up when:
      - >=3 stars in last 5 (including this drill), AND
      - >=2 stars in last 3 (including this drill), AND
      - this_star is True (latest drill a star)
    """
    s = (stars_recent + ("1" if this_star else "0"))[-5:]
    last5 = s.count("1")
    last3 = s[-3:].count("1")
    return this_star and (last5 >= 3) and (last3 >= 2)
