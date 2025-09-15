from typing import List, Dict, Any, Set
import re
from datetime import datetime, timedelta
from sqlmodel import select
from ..storage import get_session
from ..models import DrillResult, DrillAward

def fetch_results_with_stars(uid: int, limit: int = 25) -> tuple[list[DrillResult], set[int]]:
    with get_session() as s:
        results: List[DrillResult] = s.exec(
            select(DrillResult)
            .where(DrillResult.user_id == uid)
            .order_by(DrillResult.created_at.desc())
            .limit(limit)
        ).all()
        res_ids = [r.id for r in results]
        star_ids: Set[int] = set()
        if res_ids:
            rows = s.exec(
                select(DrillAward.drill_result_id)
                .where(DrillAward.drill_result_id.in_(res_ids))
                .where(DrillAward.award_type == "star")
            ).all()
            for row in rows:
                if isinstance(row, (list, tuple)):
                    star_ids.add(int(row[0]))
                else:
                    star_ids.add(int(row))
    return results, star_ids

def build_feed_items(results: List[DrillResult], star_ids: Set[int]) -> list[dict[str, Any]]:
    items = []
    for r in results:
        m = re.match(r"^\[L(\d+)\]\s+(.*)$", r.settings_snapshot or "")
        level_num = int(m.group(1)) if m else None
        label_part = m.group(2) if m else (r.settings_snapshot or "")
        score_num = None
        ms = re.search(r"Score\s+(\d+)\s*/\s*(\d+)", label_part)
        if ms:
            score_num = f"{ms.group(1)}/{ms.group(2)}"
            label_part = re.sub(r"\s*•\s*Score\s+\d+\s*/\s*\d+\s*", " ", label_part).strip()
        items.append({
            "ts": r.created_at.isoformat(),
            "drill_type": r.drill_type.value,
            "level": level_num,
            "label": label_part,
            "score": score_num,
            "time_ms": r.elapsed_ms,
            "star": (r.id in star_ids),
        })
    return items

def today_counts(uid: int, tz_offset_min: int) -> Dict[str, Any]:
    local_now = datetime.utcnow() - timedelta(minutes=tz_offset_min)
    local_start = datetime(local_now.year, local_now.month, local_now.day)
    local_end = local_start + timedelta(days=1)
    start_utc = local_start + timedelta(minutes=tz_offset_min)
    end_utc = local_end + timedelta(minutes=tz_offset_min)

    with get_session() as s:
        q = s.exec(
            select(DrillResult)
            .where(DrillResult.user_id == uid)
            .where(DrillResult.created_at >= start_utc)
            .where(DrillResult.created_at < end_utc)
        )
        rows = q.all()
    counts: Dict[str, Any] = {"total": len(rows), "addition": 0, "subtraction": 0, "multiplication": 0, "division": 0}
    for r in rows:
        counts[r.drill_type.value] += 1
    return counts
