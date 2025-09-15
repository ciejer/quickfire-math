from typing import Dict
from sqlmodel import select
from ..storage import get_session
from ..models import DrillTypeEnum, UserProgress
from ..levels import thresholds_for_level, clamp_level, level_label, get_preset
from .stars import need_hint_text

def ensure_progress_rows(uid: int) -> None:
    with get_session() as s:
        for dt in DrillTypeEnum:
            prog = s.exec(select(UserProgress).where(
                UserProgress.user_id == uid, UserProgress.drill_type == dt
            )).first()
            if not prog:
                _, _, _, _, TMAX = thresholds_for_level(1)
                s.add(UserProgress(user_id=uid, drill_type=dt, level=1, target_time_sec=TMAX))
        s.commit()

def level_info(uid: int, dt: DrillTypeEnum) -> tuple[int, str, dict]:
    ensure_progress_rows(uid)
    with get_session() as s:
        prog = s.exec(select(UserProgress).where(
            UserProgress.user_id == uid, UserProgress.drill_type == dt
        )).first()
    lvl = clamp_level(dt, prog.level if prog else 1)
    return lvl, level_label(dt, lvl), get_preset(dt, lvl)

def progress_payload(uid: int) -> Dict[str, dict]:
    ensure_progress_rows(uid)
    out: Dict[str, dict] = {}
    with get_session() as s:
        for dt in DrillTypeEnum:
            prog = s.exec(select(UserProgress).where(
                UserProgress.user_id == uid, UserProgress.drill_type == dt
            )).first()
            if not prog:
                out[dt.value] = {
                    "level": 1, "label": level_label(dt, 1),
                    "last5": "", "ready_if_star": False,
                    "need_msg": "Get 3 of your last 5 stars to level up"
                }
            else:
                sr = (prog.stars_recent or "")[-5:]
                out[dt.value] = {
                    "level": prog.level,
                    "label": level_label(dt, prog.level),
                    "last5": sr,
                    "ready_if_star": False,
                    # On dashboard, do not include a hypothetical current drill
                    "need_msg": need_hint_text(sr, None),
                }
    return out
