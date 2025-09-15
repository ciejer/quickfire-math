from typing import Optional
import json
from datetime import datetime
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlmodel import select
from ..deps import templates
from ..utils.session import get_user_id
from ..utils.progress import level_info
from ..utils.stars import need_hint_text
from ..utils.feedback import friendly_fail_message
from ..utils.next_problem import next_prompt_from_preset, ok_against_avoid
from ..storage import get_session
from ..models import DrillTypeEnum, DrillResult, DrillQuestion, UserProgress, DrillAward
from ..levels import thresholds_for_level, clamp_level, level_label
from ..logic import compute_first_try_metrics, star_decision, levelup_decision

router = APIRouter()

@router.post("/start", response_class=HTMLResponse)
def start_drill(request: Request, drill_type: DrillTypeEnum = Form(...)):
    uid = get_user_id(request)
    if not uid:
        raise HTTPException(403)
    lvl, lbl, preset = level_info(uid, drill_type)
    p, ans, tts = next_prompt_from_preset(drill_type, preset)
    return templates.TemplateResponse("drill.html", {
        "request": request, "drill_type": drill_type.value,
        "target_count": 20, "first_prompt": p, "first_answer": ans, "first_tts": tts,
        "settings_human": lbl
    })

@router.post("/next")
def next_problem(
    request: Request,
    drill_type: DrillTypeEnum = Form(...),
    avoid_prompt: Optional[str] = Form(default=None),
    avoid_pair: Optional[str] = Form(default=None),
):
    uid = get_user_id(request)
    if not uid:
        raise HTTPException(403)
    _, _, preset = level_info(uid, drill_type)

    last = avoid_prompt
    last_pair = avoid_pair
    for _ in range(16):
        p, ans, tts = next_prompt_from_preset(drill_type, preset)
        if ok_against_avoid(p, last, last_pair):
            return JSONResponse({"prompt": p, "answer": ans, "tts": tts})
    return JSONResponse({"prompt": p, "answer": ans, "tts": tts})

@router.post("/finish")
def finish_drill(
    request: Request,
    drill_type: DrillTypeEnum = Form(...),
    elapsed_ms: int = Form(...),
    settings_human: str = Form(...),
    question_count: int = Form(20),
    score: int = Form(0),
    qlog: str = Form("[]"),
):
    uid = get_user_id(request)
    if not uid:
        raise HTTPException(403)

    with get_session() as s:
        prog = s.exec(select(UserProgress).where(
            UserProgress.user_id == uid, UserProgress.drill_type == drill_type
        )).first()
        if not prog:
            _, _, _, _, TMAX = thresholds_for_level(1)
            prog = UserProgress(user_id=uid, drill_type=drill_type, level=1, target_time_sec=TMAX)
            s.add(prog); s.commit(); s.refresh(prog)

        level_at = int(prog.level)
        snapshot = f"[L{level_at}] {settings_human} • Score {score}/{question_count}"
        rec = DrillResult(
            user_id=uid, drill_type=drill_type,
            settings_snapshot=snapshot, question_count=question_count, elapsed_ms=elapsed_ms,
        )
        s.add(rec); s.commit(); s.refresh(rec)

        try:
            logs = json.loads(qlog)
        except Exception:
            logs = []
        for e in logs:
            try:
                started = datetime.fromisoformat(str(e.get("started_at")).replace("Z",""))
            except Exception:
                started = datetime.utcnow()
            s.add(DrillQuestion(
                drill_result_id=rec.id, drill_type=drill_type,
                a=int(e.get("a", 0)), b=int(e.get("b", 0)), prompt=str(e.get("prompt","")),
                correct_answer=int(e.get("correct_answer",0)), given_answer=int(e.get("given_answer",0)),
                correct=bool(e.get("correct", False)), started_at=started, elapsed_ms=int(e.get("elapsed_ms",0)),
            ))
        s.commit()

        metrics = compute_first_try_metrics(logs)

        tts = getattr(prog, "target_time_sec", None)
        if not tts:
            _, _, _, _, TMAX = thresholds_for_level(prog.level)
            tts = TMAX

        star, exp = star_decision(metrics, elapsed_ms, float(tts))

        awards = []
        if star:
            awards.append(("star", "⭐ Star earned"))

        if prog.best_time_ms is None or elapsed_ms < prog.best_time_ms:
            prog.best_time_ms = elapsed_ms
            awards.append(("pb_time", "🏁 New best time"))
        if prog.best_acc is None or metrics["acc"] > (prog.best_acc or 0):
            prog.best_acc = metrics["acc"]
            awards.append(("pb_acc", "🎯 New best accuracy"))

        sr_before = prog.stars_recent or ""
        did_level_up = levelup_decision(sr_before, star)
        prog.stars_recent = (sr_before + ("1" if star else "0"))[-6:]

        new_level_label = ""
        if did_level_up:
            prev_best_sec = (prog.best_time_ms or elapsed_ms) / 1000.0
            next_level = clamp_level(drill_type, prog.level + 1)
            lbl_next = level_label(drill_type, next_level).lower()
            if prog.level == 1 and "recap" in lbl_next:
                next_level = clamp_level(drill_type, next_level + 1)
            _, _, _, _, TMAX = thresholds_for_level(next_level)
            next_target = min(TMAX, prev_best_sec * 1.5)
            prog.level = next_level
            prog.last_levelup_at = datetime.utcnow()
            try:
                prog.target_time_sec = int(round(next_target))
            except Exception:
                pass
            new_level_label = level_label(drill_type, next_level)
            prog.best_time_ms = None
            prog.best_acc = None
            prog.stars_recent = ""
            awards.append(("level_up", f"⬆️ Level up to {new_level_label}"))

        new_level_val = int(prog.level)
        star_bool = bool(star)
        levelup_bool = bool(did_level_up)
        fail_msg = "" if star_bool else friendly_fail_message(metrics, float(tts), exp.get("why",""), question_count)

        s.add(prog); s.commit()
        for (t, text) in awards:
            s.add(DrillAward(drill_result_id=rec.id, award_type=t, payload=text))
        s.commit()

    return JSONResponse({
        "ok": True,
        "star": star_bool,
        "level_up": levelup_bool,
        "new_level": new_level_val,
        "new_level_label": new_level_label,
        "awards": [a for _, a in awards],
        "fail_msg": fail_msg,
        "need_hint": need_hint_text(sr_before, star),
    })
