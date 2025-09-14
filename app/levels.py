from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Sequence, Dict, Any, Tuple
from .models import DrillTypeEnum


@dataclass(frozen=True)
class LevelPreset:
    label: str              # kid-friendly, shown in UI
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


# -------- Multiplication: ~18 levels, 1–2 tables at a time
def mul_levels() -> Sequence[LevelPreset]:
    lvls: list[LevelPreset] = []
    # L1..L4: A 1–5, introduce 2..5
    for t in [2, 3, 4, 5]:
        lvls.append(LevelPreset(f"{t} times table, up to 5", {"a_min":1,"a_max":5,"b_set":[t]}))
    # L5..L10: A 1–9, build out to 9
    lvls += [
        LevelPreset("2 & 3 times tables, up to 9", {"a_min":1,"a_max":9,"b_set":[2,3]}),
        LevelPreset("4 & 5 times tables, up to 9", {"a_min":1,"a_max":9,"b_set":[4,5]}),
        LevelPreset("6 times table, up to 9", {"a_min":1,"a_max":9,"b_set":[6]}),
        LevelPreset("7 times table, up to 9", {"a_min":1,"a_max":9,"b_set":[7]}),
        LevelPreset("8 times table, up to 9", {"a_min":1,"a_max":9,"b_set":[8]}),
        LevelPreset("9 times table, up to 9", {"a_min":1,"a_max":9,"b_set":[9]}),
    ]
    # L11..L15: A 1–12, add 10..12
    lvls += [
        LevelPreset("2–4 times tables, up to 12", {"a_min":1,"a_max":12,"b_set":[2,3,4]}),
        LevelPreset("5–6 times tables, up to 12", {"a_min":1,"a_max":12,"b_set":[5,6]}),
        LevelPreset("7–8 times tables, up to 12", {"a_min":1,"a_max":12,"b_set":[7,8]}),
        LevelPreset("9–10 times tables, up to 12", {"a_min":1,"a_max":12,"b_set":[9,10]}),
        LevelPreset("11–12 times tables, up to 12", {"a_min":1,"a_max":12,"b_set":[11,12]}),
    ]
    # L16..L18: mixed
    lvls += [
        LevelPreset("All times tables to 12", {"a_min":1,"a_max":12,"b_set":list(range(1,13))}),
        LevelPreset("All times tables (harder)", {"a_min":1,"a_max":12,"b_set":list(range(1,13)), "bias_hard": True}),
        LevelPreset("Times tables mastery", {"a_min":1,"a_max":12,"b_set":list(range(1,13)), "bias_hard": True}),
    ]
    return lvls


# -------- Addition/Subtraction: gradual ranges + carry/borrow mix
def add_levels() -> Sequence[LevelPreset]:
    return [
        LevelPreset("Sums 0–10 (easy)", {"min":0,"max":10,"carry_bias":0.2}),
        LevelPreset("Sums 0–20", {"min":0,"max":20,"carry_bias":0.4}),
        LevelPreset("Sums 0–50 (trickier)", {"min":0,"max":50,"carry_bias":0.6}),
        LevelPreset("Sums 0–100", {"min":0,"max":100,"carry_bias":0.6}),
        LevelPreset("Sums 0–200 (fast)", {"min":0,"max":200,"carry_bias":0.7}),
    ]


def sub_levels() -> Sequence[LevelPreset]:
    return [
        LevelPreset("Take-aways 0–10 (easy)", {"min":0,"max":10,"borrow_bias":0.2}),
        LevelPreset("Take-aways 0–20", {"min":0,"max":20,"borrow_bias":0.4}),
        LevelPreset("Take-aways 0–50 (trickier)", {"min":0,"max":50,"borrow_bias":0.6}),
        LevelPreset("Take-aways 0–100", {"min":0,"max":100,"borrow_bias":0.6}),
        LevelPreset("Take-aways 0–200 (fast)", {"min":0,"max":200,"borrow_bias":0.7}),
    ]


def div_levels() -> Sequence[LevelPreset]:
    # mirror multiplication, focus on quotient bands
    return [
        LevelPreset("÷ by 2 (answers 1–5)", {"divisor_set":[2], "q_min":1,"q_max":5}),
        LevelPreset("÷ by 3 (answers 1–5)", {"divisor_set":[3], "q_min":1,"q_max":5}),
        LevelPreset("÷ by 4–5 (answers 1–9)", {"divisor_set":[4,5], "q_min":1,"q_max":9}),
        LevelPreset("÷ by 6–7 (answers 1–9)", {"divisor_set":[6,7], "q_min":1,"q_max":9}),
        LevelPreset("÷ by 8–9 (answers 1–9)", {"divisor_set":[8,9], "q_min":1,"q_max":9}),
        LevelPreset("÷ by 10–12 (answers 1–12)", {"divisor_set":[10,11,12], "q_min":1,"q_max":12}),
        LevelPreset("Mixed ÷1–12 (answers 1–12)", {"divisor_set":list(range(1,13)), "q_min":1,"q_max":12}),
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
