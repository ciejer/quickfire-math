"""Generation + simplified star rule + helpers."""
from __future__ import annotations
import random
from collections import defaultdict
from typing import Dict, List, Tuple, Any

from .models import DrillTypeEnum

def _rand(a: int, b: int) -> int:
    if a > b: a, b = b, a
    return random.randint(a, b)

def _choose(seq):
    return random.choice(seq)

# ----------------- Generation from presets -----------------
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

# ----------------- Metrics -----------------
def compute_first_try_metrics(qlog: List[dict]) -> dict:
    attempts_by_prompt: Dict[str, List[dict]] = defaultdict(list)
    for e in qlog:
        attempts_by_prompt[e["prompt"]].append(e)

    total_items = 0
    first_try_correct = 0

    for prompt, attempts in attempts_by_prompt.items():
        attempts.sort(key=lambda x: x["started_at"])
        if not attempts:
            continue
        total_items += 1
        first = attempts[0]
        if first["correct"]:
            first_try_correct += 1

    acc = (first_try_correct / total_items) if total_items else 0.0
    return {
        "items": total_items,
        "first_try_correct": first_try_correct,
        "acc": acc,
    }

# ----------------- Star rule (simplified) -----------------
def star_decision(metrics: dict, total_time_ms: int, target_time_sec: float) -> tuple[bool, dict]:
    """
    Gates:
      - Accuracy >= A(level)  (A varies by level in thresholds_for_level)
      - Total time <= personalised target_time_sec (locked at level start)
    """
    # accuracy gates vary slowly by level — mirror levels.thresholds_for_level for A-only
    # We keep it simple by using a tiered accuracy that scales with item count
    items = metrics.get("items", 20) or 20
    if items <= 10:
        A = 0.8
    elif items <= 20:
        A = 0.85
    else:
        A = 0.9

    exp = {"A": A, "acc": metrics["acc"], "target_sec": target_time_sec}
    if metrics["acc"] < A:
        exp["why"] = "accuracy_below_gate"; return False, exp

    if (total_time_ms / 1000.0) > float(target_time_sec):
        exp["why"] = "too_slow"; return False, exp

    exp["why"] = "ok"; return True, exp

# ----------------- Commutative duplicate helper -----------------
def is_commutative_op_key(prompt: str) -> str | None:
    """
    Returns a key like '×:4,6' or '+:3,9' for commutative ops, else None.
    """
    import re
    m = re.match(r"^\s*(\d+)\s*([+\u00D7])\s*(\d+)\s*$", prompt)  # + or ×
    if not m: return None
    a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
    lo, hi = sorted((a, b))
    return f"{op}:{lo},{hi}"
