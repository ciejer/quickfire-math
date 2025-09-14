"""Question generation + star/level evaluation."""
from __future__ import annotations
import random
from collections import defaultdict
from typing import Dict, List, Tuple, Any

from .models import DrillTypeEnum
from .levels import thresholds_for_level

def _rand(a: int, b: int) -> int:
    if a > b: a, b = b, a
    return random.randint(a, b)

def _choose(seq):
    return random.choice(seq)

# ----------------- Generation from presets (with recap bias) -----------------
def _choose_with_bias(full_list: list[int], focus: list[int], weight_focus: float = 0.6) -> int:
    if not focus:
        return _choose(full_list)
    if random.random() < weight_focus:
        return _choose(focus)
    return _choose(full_list)

def generate_from_preset(drill_type: DrillTypeEnum, preset: Dict[str, Any]) -> Tuple[str, int, str]:
    """Return (prompt, answer, tts)."""
    if drill_type == DrillTypeEnum.multiplication:
        a = _rand(preset["a_min"], preset["a_max"])
        b_list = list(preset["b_set"])
        b_focus = list(preset.get("recap_focus", []))
        b = _choose_with_bias(b_list, b_focus, float(preset.get("recap_weight", 0.6)))
        if preset.get("bias_hard"):
            if random.random() < 0.5:
                a = max(a, _rand(max(preset["a_min"], 6), preset["a_max"]))
                if b < 7:
                    b = _choose([7,8,9,10,11,12])
        if random.random() < 0.5:
            a, b = b, a
        ans = a * b
        return (f"{a} × {b}", ans, f"{a} times {b} equals {ans}")

    if drill_type == DrillTypeEnum.addition:
        lo, hi = preset["min"], preset["max"]
        a, b = _rand(lo, hi), _rand(lo, hi)
        if random.random() < preset.get("carry_bias", 0.0):
            a = max(10, _rand(10, max(10, hi)))
            b = max(10, _rand(10, max(10, hi)))
            while (a % 10) + (b % 10) < 10 and random.random() < 0.8:
                a = _rand(10, max(10, hi))
                b = _rand(10, max(10, hi))
        if random.random() < 0.5:
            a, b = b, a
        ans = a + b
        return (f"{a} + {b}", ans, f"{a} plus {b} equals {ans}")

    if drill_type == DrillTypeEnum.subtraction:
        lo, hi = preset["min"], preset["max"]
        a, b = _rand(lo, hi), _rand(lo, hi)
        if a < b: a, b = b, a
        if random.random() < preset.get("borrow_bias", 0.0) and a >= 10 and b >= 10:
            while (a % 10) >= (b % 10) and random.random() < 0.8:
                a = _rand(max(10, lo), hi)
                b = _rand(max(10, lo), hi)
                if a < b: a, b = b, a
        ans = a - b
        return (f"{a} − {b}", ans, f"{a} minus {b} equals {ans}")

    if drill_type == DrillTypeEnum.division:
        divs = list(preset["divisor_set"])
        focus = list(preset.get("recap_focus", []))
        d = _choose_with_bias(divs, focus, float(preset.get("recap_weight", 0.6)))
        q = _rand(preset["q_min"], preset["q_max"])
        dividend = d * q
        ans = q
        return (f"{dividend} ÷ {d}", ans, f"{dividend} divided by {d} equals {ans}")

    raise ValueError("Unsupported drill type")

# ----------------- Metrics + star rule -----------------
def compute_first_try_metrics(qlog: List[dict]) -> dict:
    attempts_by_prompt: Dict[str, List[dict]] = defaultdict(list)
    for e in qlog:
        attempts_by_prompt[e["prompt"]].append(e)

    total_items = 0
    first_try_correct = 0
    tpq_sum_ms = 0
    hard_mistakes = 0

    for prompt, attempts in attempts_by_prompt.items():
        attempts.sort(key=lambda x: x["started_at"])
        if not attempts:
            continue
        total_items += 1
        first = attempts[0]
        if first["correct"]:
            first_try_correct += 1
            tpq_sum_ms += int(first.get("elapsed_ms", 0))
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
        "first_try_correct": first_try_correct,
        "acc": acc,
        "tpq_ms": tpq_ms,
        "hard_mistakes": hard_mistakes
    }

def ewma_update(old: float | None, new: float, alpha: float = 0.25) -> float:
    if old is None: return new
    return alpha * new + (1 - alpha) * old

def star_decision(level: int, metrics: dict, total_time_ms: int, ewma_tpq_ms: float | None) -> Tuple[bool, dict]:
    A, CAP, DELTA, HM, TMAX = thresholds_for_level(level)
    exp = {"A":A, "CAP":CAP, "DELTA":DELTA, "HM":HM, "TMAX":TMAX,
           "acc":metrics["acc"], "tpq_ms":metrics["tpq_ms"], "hard_mistakes":metrics["hard_mistakes"]}
    if metrics["acc"] < A: exp["why"]="accuracy_below_gate"; return False, exp
    if total_time_ms > TMAX * 1000: exp["why"]="over_total_time_cap"; return False, exp
    if metrics["hard_mistakes"] > HM: exp["why"]="too_many_hard_mistakes"; return False, exp

    tpq_ms = metrics["tpq_ms"]
    if tpq_ms is None and metrics.get("items", 0) > 0:
        tpq_ms = total_time_ms / metrics["items"]  # fallback
    if tpq_ms is None: exp["why"] = "no_first_try_timing"; return False, exp

    abs_ok = (tpq_ms / 1000.0) <= CAP
    imp_ok = (ewma_tpq_ms is not None) and (tpq_ms <= ewma_tpq_ms * (1.0 - DELTA))
    if not (abs_ok or imp_ok): exp["why"]="too_slow"; return False, exp

    exp["why"]="ok"; return True, exp

def levelup_decision(stars_recent: str, this_star: bool) -> bool:
    s = (stars_recent + ("1" if this_star else "0"))[-5:]
    last5 = s.count("1")
    last3 = s[-3:].count("1")
    return this_star and (last5 >= 3) and (last3 >= 2)
