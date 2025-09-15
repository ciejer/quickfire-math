from typing import Tuple
from ..logic import generate_from_preset, is_commutative_op_key
from ..models import DrillTypeEnum

def next_prompt_from_preset(drill_type: DrillTypeEnum, preset: dict) -> Tuple[str, int, str]:
    return generate_from_preset(drill_type, preset)

def ok_against_avoid(new_prompt: str, avoid_prompt: str | None, avoid_pair_key: str | None) -> bool:
    if avoid_prompt and new_prompt == avoid_prompt:
        return False
    if avoid_pair_key and is_commutative_op_key(new_prompt) == avoid_pair_key:
        return False
    return True
