from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Sequence, Dict, Any, Tuple
from .models import DrillTypeEnum


@dataclass(frozen=True)
class LevelPreset:
    label: str
    params: Dict[str, Any]  # generation parameters (type-specific)


# Thresholds vary by broad band. Returns (A, CAP, DELTA, HM, TMAX_seconds)
def thresholds_for_level(level: int) -> Tuple[float, float, float, int, int]:
    if level <= 2:
        return (0.75, 10.0, 0.10, 2, 10*60)
    elif level <= 4:
        return (0.85, 8.0, 0.12, 2, 8*60)
    elif level <= 6:
        return (0.90, 6.0, 0.15, 1, 6*60)
    else:
        return (0.95, 4.5, 0.18, 1, 5*60)


# -------- Multiplication: ~18 levels, adding 1–2 tables at a time
def mul_levels() -> Sequence[LevelPreset]:
    lvls: list[LevelPreset] = []
    # L1..L4: A 1–5, introduce single tables 2..5
    for t in [2,3,4,5]:
        lvls.append(LevelPreset(f"L{len(lvls)+1}: ×{t} (A 1–5)", {"a_min":1,"a_max":5,"b_set":[t]}))
    # L5..L10: A 1–9, introduce 2..9 over a few bundles
    lvls += [
        LevelPreset(f"L{len(lvls)+1}: ×2,×3 (A 1–9)", {"a_min":1,"a_max":9,"b_set":[2,3]}),
        LevelPreset(f"L{len(lvls)+1}: ×4,×5 (A 1–9)", {"a_min":1,"a_max":9,"b_set":[4,5]}),
        LevelPreset(f"L{len(lvls)+1}: ×6 (A 1–9)", {"a_min":1,"a_max":9,"b_set":[6]}),
        LevelPreset(f"L{len(lvls)+1}: ×7 (A 1–9)", {"a_min":1,"a_max":9,"b_set":[7]}),
        LevelPreset(f"L{len(lvls)+1}: ×8 (A 1–9)", {"a_min":1,"a_max":9,"b_set":[8]}),
        LevelPreset(f"L{len(lvls)+1}: ×9 (A 1–9)", {"a_min":1,"a_max":9,"b_set":[9]}),
    ]
    # L11..L15: A 1–12, bring in 10..12 in small groups
    lvls += [
        LevelPreset(f"L{len(lvls)+1}: ×2–4 (A 1–12)", {"a_min":1,"a_max":12,"b_set":[2,3,4]}),
        LevelPreset(f"L{len(lvls)+1}: ×5–6 (A 1–12)", {"a_min":1,"a_max":12,"b_set":[5,6]}),
        LevelPreset(f"L{len(lvls)+1}: ×7–8 (A 1–12)", {"a_min":1,"a_max":12,"b_set":[7,8]}),
        LevelPreset(f"L{len(lvls)+1}: ×9–10 (A 1–12)", {"a_min":1,"a_max":12,"b_set":[9,10]}),
        LevelPreset(f"L{len(lvls)+1}: ×11–12 (A 1–12)", {"a_min":1,"a_max":12,"b_set":[11,12]}),
    ]
    # L16..L18: full mix 1–12, then weighted harder
    lvls += [
        LevelPreset(f"L{len(lvls)+1}: Mixed ×1–12", {"a_min":1,"a_max":12,"b_set":list(range(1,13))}),
        LevelPreset(f"L{len(lvls)+1}: Mixed ×1–12 (harder)", {"a_min":1,"a_max":12,"b_set":list(range(1,13)), "bias_hard": True}),
        LevelPreset(f"L{len(lvls)+1}: Mastery ×1–12", {"a_min":1,"a_max":12,"b_set":list(range(1,13)), "bias_hard": True}),
    ]
    return lvls


# -------- Addition/Subtraction: gradual ranges + carry/borrow mix
def add_levels() -> Sequence[LevelPreset]:
    return [
        LevelPreset("L1: 0–10 (no-carry bias)", {"min":0,"max":10,"carry_bias":0.2}),
        LevelPreset("L2: 0–20 (some carry)", {"min":0,"max":20,"carry_bias":0.4}),
        LevelPreset("L3: 0–50 (carry common)", {"min":0,"max":50,"carry_bias":0.6}),
        LevelPreset("L4: 0–100 (carry common)", {"min":0,"max":100,"carry_bias":0.6}),
        LevelPreset("L5: 0–200 (carry frequent)", {"min":0,"max":200,"carry_bias":0.7}),
    ]


def sub_levels() -> Sequence[LevelPreset]:
    return [
        LevelPreset("L1: 0–10 (no-borrow bias)", {"min":0,"max":10,"borrow_bias":0.2}),
        LevelPreset("L2: 0–20 (some borrow)", {"min":0,"max":20,"borrow_bias":0.4}),
        LevelPreset("L3: 0–50 (borrow common)", {"min":0,"max":50,"borrow_bias":0.6}),
        LevelPreset("L4: 0–100 (borrow common)", {"min":0,"max":100,"borrow_bias":0.6}),
        LevelPreset("L5: 0–200 (borrow frequent)", {"min":0,"max":200,"borrow_bias":0.7}),
    ]


def div_levels() -> Sequence[LevelPreset]:
    # mirror multiplication, focusing on quotient bands
    return [
        LevelPreset("L1: ÷ by 2 (q 1–5)", {"divisor_set":[2], "q_min":1,"q_max":5}),
        LevelPreset("L2: ÷ by 3 (q 1–5)", {"divisor_set":[3], "q_min":1,"q_max":5}),
        LevelPreset("L3: ÷ by 4–5 (q 1–9)", {"divisor_set":[4,5], "q_min":1,"q_max":9}),
        LevelPreset("L4: ÷ by 6–7 (q 1–9)", {"divisor_set":[6,7], "q_min":1,"q_max":9}),
        LevelPreset("L5: ÷ by 8–9 (q 1–9)", {"divisor_set":[8,9], "q_min":1,"q_max":9}),
        LevelPreset("L6: ÷ by 10–12 (q 1–12)", {"divisor_set":[10,11,12], "q_min":1,"q_max":12}),
        LevelPreset("L7: Mixed ÷1–12 (q 1–12)", {"divisor_set":list(range(1,13)), "q_min":1,"q_max":12}),
    ]


LEVELS: dict[DrillTypeEnum, list[LevelPreset]] = {
    DrillTypeEnum.multiplication: list(mul_levels()),
    DrillTypeEnum.addition: list(add_levels()),
    DrillTypeEnum.subtraction: list(sub_levels()),
    DrillTypeEnum.division: list(div_levels()),
}


def clamp_level(drill_type: DrillTypeEnum, level: int) -> int:
    maxl = len(LEVELS[drill_type])
    return max(1, min(level, maxl))


def level_label(drill_type: DrillTypeEnum, level: int) -> str:
    lvl = LEVELS[drill_type][clamp_level(drill_type, level)-1]
    return lvl.label


def get_preset(drill_type: DrillTypeEnum, level: int) -> dict:
    lvl = LEVELS[drill_type][clamp_level(drill_type, level)-1]
    return lvl.params.copy()
