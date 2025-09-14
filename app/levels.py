from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence, Dict, Any, Tuple
from .models import DrillTypeEnum

@dataclass(frozen=True)
class LevelPreset:
    label: str
    params: Dict[str, Any]

def thresholds_for_level(level: int) -> Tuple[float, float, float, int, int]:
    if level <= 2:
        return (0.75, 10.0, 0.10, 2, 10*60)
    elif level <= 6:
        return (0.85, 8.0, 0.12, 2, 8*60)
    elif level <= 12:
        return (0.90, 6.0, 0.15, 1, 6*60)
    else:
        return (0.95, 4.5, 0.18, 1, 5*60)

# Multiplication with “recap” in-between levels (favouring the newly introduced table)
def mul_levels() -> Sequence[LevelPreset]:
    lvls: list[LevelPreset] = []
    introduced = []
    def recap_label() -> str:
        # friendly label like “2–4 times tables, up to 9 (recap)”
        if not introduced: return "Times tables recap"
        lo, hi = min(introduced), max(introduced)
        mid = "–".join(str(x) for x in ([lo, hi] if hi-lo>1 else [lo,hi]))
        return f"{mid} times tables, up to 9 (recap)"
    # Introduce 2..5 (A 1–5), with recap after each
    for t in [2,3,4,5]:
        introduced.append(t)
        lvls.append(LevelPreset(f"{t} times table, up to 5", {"a_min":1,"a_max":5,"b_set":[t]}))
        lvls.append(LevelPreset(f"{t} + recap, up to 5", {"a_min":1,"a_max":5,"b_set":introduced.copy(), "recap_focus":[t], "recap_weight":0.7}))
    # Extend to 9, single-table intro + recap
    for t in [6,7,8,9]:
        introduced.append(t)
        lvls.append(LevelPreset(f"{t} times table, up to 9", {"a_min":1,"a_max":9,"b_set":[t]}))
        lvls.append(LevelPreset(recap_label(), {"a_min":1,"a_max":9,"b_set":introduced.copy(), "recap_focus":[t], "recap_weight":0.65}))
    # Extend to 12 in grouped intros + recap
    blocks = ([10],[11],[12])
    for block in blocks:
        introduced.extend(block)
        human = " & ".join(f"{b}" for b in block)
        lvls.append(LevelPreset(f"{human} times table, up to 12", {"a_min":1,"a_max":12,"b_set":block}))
        lvls.append(LevelPreset("All tables recap (favours new)", {"a_min":1,"a_max":12,"b_set":introduced.copy(), "recap_focus":block, "recap_weight":0.6}))
    # Mastery sets
    lvls += [
        LevelPreset("All times tables to 12", {"a_min":1,"a_max":12,"b_set":list(range(1,13))}),
        LevelPreset("All times tables (harder)", {"a_min":1,"a_max":12,"b_set":list(range(1,13)), "bias_hard": True}),
    ]
    return lvls

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
