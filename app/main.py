from __future__ import annotations

import os, secrets, random, json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import select

from .storage import init_db, get_session
from .models import (
    User, UserSettings, DrillResult, DrillQuestion,
    DrillTypeEnum, AdminConfig, UserProgress, DrillAward
)
from .levels import get_preset, clamp_level, level_label
from .logic import generate_from_preset, compute_first_try_metrics, ewma_update, star_decision, levelup_decision

APP_NAME = "Quickfire Math"
app = FastAPI(title=APP_NAME)
BASE_DIR = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

_WORDS = ["tui","kiwi","pohutukawa","harbour","beach","waka","kauri","ponga","kepler","southern","albatross","river","island","koru","pounamu","sunrise","sunset","storm","mist","summit","spark","ember","glow","forest","valley","ocean","rimu","totara","manuka","harakeke","kumara","tuatara","alpine","peak","fern","swift","clever","brave","steady","calm","bright","kind","solid","focused","nimble"]
def _gen_pwd() -> str: return f"{random.choice(_WORDS)}-{random.choice(_WORDS)}-{secrets.randbelow(100)}"

@app.on_event("startup")
def startup():
    init_db()
    with get_session() as s:
        cfg = s.exec(select(AdminConfig)).first()
        if not cfg or not cfg.admin_password_plain:
            pwd = _gen_pwd()
            if not cfg: cfg = AdminConfig(admin_password_plain=pwd); s.add(cfg)
            else: cfg.admin_password_plain = pwd
            s.commit()
            print(f"[Quickfire] Admin password (generated): {pwd}")
        else:
            print(f"[Quickfire] Admin password: {cfg.admin_password_plain}")

def get_user_id(request: Request) -> Optional[int]:
    v = request.cookies.get("uid")
    return int(v) if v and v.isdigit() else None

def ensure_progress_rows(uid: int):
    with get_session() as s:
        for dt in DrillTypeEnum:
            prog = s.exec(select(UserProgress).where(UserProgress.user_id == uid, UserProgress.drill_type == dt)).first()
            if not prog:
                prog = UserProgress(user_id=uid, drill_type=dt, level=1)
                s.add(prog)
        s.commit()

def level_info(uid: int, dt: DrillTypeEnum) -> tuple[int,str,dict]:
    ensure_progress_rows(uid)
    with get_session() as s:
        prog = s.exec(select(UserProgress).where(UserProgress.user_id == uid, UserProgress.drill_type == dt)).first()
    lvl = clamp_level(dt, prog.level if prog else 1)
    return lvl, level_label(dt, lvl), get_preset(dt, lvl)

# Pages

@app.get("/", response_class=HTMLResponse)
def login(request: Request):
    with get_session() as s:
        users = list(s.exec(select(User)).all())
    return templates.TemplateResponse("login.html", {"request": request, "users": users, "app_name": APP_NAME})

@app.post("/login")
def do_login(user_id: int = Form(...)):
    resp = RedirectResponse(url="/home", status_code=303)
    resp.set_cookie("uid", str(user_id), max_age=60 * 60 * 24 * 365, samesite="lax")
    return resp

@app.post("/user/add")
def user_add(display_name: str = Form(...)):
    name = (display_name or "").strip()
    if not name:
        return RedirectResponse("/", status_code=303)
    with get_session() as s:
        u = User(display_name=name)
        s.add(u); s.commit(); s.refresh(u)
        s.add(UserSettings(user_id=u.id))
        s.commit()
        new_id = u.id
    ensure_progress_rows(new_id)
    resp = RedirectResponse(url="/home", status_code=303)
    resp.set_cookie("uid", str(new_id), max_age=60 * 60 * 24 * 365, samesite="lax")
    return resp

@app.get("/home", response_class=HTMLResponse)
def home(request: Request):
    uid = get_user_id(request)
    if not uid: return RedirectResponse("/")
    ensure_progress_rows(uid)
    with get_session() as s:
        user = s.get(User, uid)
        drills = s.exec(
            select(DrillResult)
            .where(DrillResult.user_id == uid)
            .order_by(DrillResult.created_at.desc())
            .limit(20)
        ).all()
    return templates.TemplateResponse("home.html", {
        "request": request, "user": user, "drills": drills
    })

@app.post("/start", response_class=HTMLResponse)
def start_drill(request: Request, drill_type: DrillTypeEnum = Form(...)):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    lvl, lbl, preset = level_info(uid, drill_type)
    p, ans, tts = generate_from_preset(drill_type, preset)
    return templates.TemplateResponse("drill.html", {
        "request": request, "drill_type": drill_type.value,
        "target_count": 20,
        "first_prompt": p, "first_answer": ans, "first_tts": tts,
        "settings_human": lbl
    })

@app.post("/next")
def next_problem(request: Request, drill_type: DrillTypeEnum = Form(...)):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    _, _, preset = level_info(uid, drill_type)
    p, ans, tts = generate_from_preset(drill_type, preset)
    return JSONResponse({"prompt": p, "answer": ans, "tts": tts})

@app.post("/finish")
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
    if not uid: raise HTTPException(403)

    with get_session() as s:
        rec = DrillResult(
            user_id=uid, drill_type=drill_type, settings_snapshot=f"{settings_human} • Score {score}/{question_count}",
            question_count=question_count, elapsed_ms=elapsed_ms,
        )
        s.add(rec); s.commit(); s.refresh(rec)

        try:
            logs = json.loads(qlog)
        except Exception:
            logs = []

        for e in logs:
            s.add(DrillQuestion(
                drill_result_id=rec.id, drill_type=drill_type,
                a=int(e.get("a", 0)), b=int(e.get("b", 0)), prompt=str(e.get("prompt","")),
                correct_answer=int(e.get("correct_answer",0)), given_answer=int(e.get("given_answer",0)),
                correct=bool(e.get("correct", False)),
                started_at=datetime.fromisoformat(e.get("started_at").replace("Z","")),
                elapsed_ms=int(e.get("elapsed_ms",0)),
            ))
        s.commit()

        prog = s.exec(select(UserProgress).where(UserProgress.user_id == uid, UserProgress.drill_type == drill_type)).first()
        if not prog:
            prog = UserProgress(user_id=uid, drill_type=drill_type, level=1)
            s.add(prog); s.commit(); s.refresh(prog)

        metrics = compute_first_try_metrics(logs)
        star, exp = star_decision(prog.level, metrics, elapsed_ms, prog.ewma_tpq_ms)

        if metrics["tpq_ms"] is not None:
            prog.ewma_tpq_ms = ewma_update(prog.ewma_tpq_ms, float(metrics["tpq_ms"]))
        prog.ewma_acc = ewma_update(prog.ewma_acc, float(metrics["acc"]))

        awards: list[tuple[str,str]] = []
        if star:
            awards.append(("star", "⭐ Star earned"))
        if prog.best_time_ms is None or elapsed_ms < prog.best_time_ms:
            prog.best_time_ms = elapsed_ms
            awards.append(("pb_time", "🏁 New best time"))
        if prog.best_acc is None or metrics["acc"] > prog.best_acc:
            prog.best_acc = metrics["acc"]
            awards.append(("pb_acc", "🎯 New best accuracy"))

        # push this drill's star into history
        sr_before = prog.stars_recent
        sr_after = (prog.stars_recent + ("1" if star else "0"))[-6:]
        prog.stars_recent = sr_after

        # decide level-up using history *before* appending this drill
        did_level_up = levelup_decision(sr_before, star)
        if did_level_up:
            prog.level = clamp_level(drill_type, prog.level + 1)
            prog.last_levelup_at = datetime.utcnow()
            # reset per-level progress for the new level
            prog.best_time_ms = None
            prog.best_acc = None
            prog.stars_recent = ""       # <---- reset stars for new level
            prog.ewma_tpq_ms = None      # <---- reset EWMA for new level
            prog.ewma_acc = None
            awards.append(("level_up", f"⬆️ Level up to {level_label(drill_type, prog.level)}"))

        s.add(prog); s.commit()

        for (t, text) in awards:
            s.add(DrillAward(drill_result_id=rec.id, award_type=t, payload=text))
        s.commit()

    return JSONResponse({
        "ok": True,
        "star": star,
        "level_up": did_level_up,
        "new_level": prog.level,
        "awards": [a for _, a in awards],
        "explain": {"need": "Earn 3 of your last 5 stars to level up."},
    })
