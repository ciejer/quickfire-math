from __future__ import annotations

import os, secrets, random, json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import select

from .storage import init_db, get_session
from .models import (
    User, UserSettings, DrillResult, DrillQuestion,
    DrillTypeEnum, AdminConfig, UserProgress, DrillAward
)
from .levels import get_preset, clamp_level, level_label, LEVELS
from .logic import generate_from_preset, compute_first_try_metrics, ewma_update, star_decision, levelup_decision

APP_NAME = "Quickfire Math"
app = FastAPI(title=APP_NAME)
BASE_DIR = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# --- Admin password
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

# ---- Helpers

def ensure_progress_rows(uid: int):
    """Ensure a UserProgress row exists for each drill type."""
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

# ---- Pages

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
        s.add(UserSettings(user_id=u.id))  # retained for compatibility
        s.commit()
        new_id = u.id
    # create progress rows
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

# Choose/start

@app.post("/start", response_class=HTMLResponse)
def start_drill(request: Request, drill_type: DrillTypeEnum = Form(...)):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    lvl, lbl, preset = level_info(uid, drill_type)
    p, ans, tts = generate_from_preset(drill_type, preset)
    settings_human = f"{lbl}"
    return templates.TemplateResponse("drill.html", {
        "request": request, "drill_type": drill_type.value,
        "target_count": 20,
        "first_prompt": p, "first_answer": ans, "first_tts": tts,
        "settings_human": settings_human
    })

@app.post("/next")
def next_problem(request: Request, drill_type: DrillTypeEnum = Form(...)):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    _, _, preset = level_info(uid, drill_type)
    p, ans, tts = generate_from_preset(drill_type, preset)
    return JSONResponse({"prompt": p, "answer": ans, "tts": tts})

# Finish & awards

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

    # Persist result + questions
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

        # Update progress & compute awards
        prog = s.exec(select(UserProgress).where(UserProgress.user_id == uid, UserProgress.drill_type == drill_type)).first()
        if not prog:
            prog = UserProgress(user_id=uid, drill_type=drill_type, level=1)
            s.add(prog); s.commit(); s.refresh(prog)

        metrics = compute_first_try_metrics(logs)
        star, exp = star_decision(prog.level, metrics, elapsed_ms, prog.ewma_tpq_ms)

        # EWMA updates (only if we have usable values)
        if metrics["tpq_ms"] is not None:
            prog.ewma_tpq_ms = ewma_update(prog.ewma_tpq_ms, float(metrics["tpq_ms"]))
        prog.ewma_acc = ewma_update(prog.ewma_acc, float(metrics["acc"]))

        # Update bests (within current level)
        awards: list[tuple[str,str]] = []
        if star:
            awards.append(("star", "⭐ Star earned"))
        if prog.best_time_ms is None or elapsed_ms < prog.best_time_ms:
            prog.best_time_ms = elapsed_ms
            awards.append(("pb_time", "🏁 New best time"))
        if prog.best_acc is None or metrics["acc"] > prog.best_acc:
            prog.best_acc = metrics["acc"]
            awards.append(("pb_acc", "🎯 New best accuracy"))

        sr = (prog.stars_recent + ("1" if star else "0"))[-6:]
        prog.stars_recent = sr

        did_level_up = levelup_decision(prog.stars_recent[:-1], star)
        if did_level_up:
            prog.level = clamp_level(drill_type, prog.level + 1)
            prog.last_levelup_at = datetime.utcnow()
            # reset level-based PBs when level changes
            prog.best_time_ms = None
            prog.best_acc = None
            awards.append(("level_up", f"⬆️ Level up to {level_label(drill_type, prog.level)}"))

        s.add(prog); s.commit()

        # Store awards
        for (t, text) in awards:
            s.add(DrillAward(drill_result_id=rec.id, award_type=t, payload=text))
        s.commit()

    # Surface celebrations to the client
    return JSONResponse({
        "ok": True,
        "star": star,
        "level_up": did_level_up,
        "new_level": prog.level,
        "awards": [a for _, a in awards],
        "explain": {"need": "Earn 3 of your last 5 stars to level up.", "last5": prog.stars_recent[-5:]},
    })

# ---- Feed / stats / progress

@app.get("/feed")
def feed(request: Request, limit: int = 20):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    with get_session() as s:
        drills = s.exec(
            select(DrillResult)
            .where(DrillResult.user_id == uid)
            .order_by(DrillResult.created_at.desc())
            .limit(limit)
        ).all()
    items = [
        {"ts": d.created_at.isoformat() + "Z", "settings": d.settings_snapshot, "elapsed_ms": d.elapsed_ms,
         "type": d.drill_type.value if d.drill_type else str(d.drill_type)}
        for d in drills
    ]
    return JSONResponse({"items": items})

@app.get("/stats")
def stats(request: Request, tz_offset: int = 0):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    offset = timedelta(minutes=tz_offset)
    now_utc = datetime.utcnow()
    local_now = now_utc - offset
    start_local = datetime(local_now.year, local_now.month, local_now.day)
    start_utc = start_local + offset
    end_utc = start_utc + timedelta(days=1)
    with get_session() as s:
        drills = s.exec(
            select(DrillResult)
            .where(DrillResult.user_id == uid, DrillResult.created_at >= start_utc, DrillResult.created_at < end_utc)
        ).all()
    counts = {"total": len(drills), "addition": 0, "subtraction": 0, "multiplication": 0, "division": 0}
    for d in drills:
        t = d.drill_type.value if hasattr(d.drill_type, "value") else str(d.drill_type)
        if t in counts: counts[t] += 1
    return JSONResponse(counts)

@app.get("/progress")
def progress(request: Request):
    """Per-type: level, label, last5 stars, ready flag."""
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    ensure_progress_rows(uid)
    out = {}
    with get_session() as s:
        for dt in DrillTypeEnum:
            p = s.exec(select(UserProgress).where(UserProgress.user_id == uid, UserProgress.drill_type == dt)).first()
            if not p:
                p = UserProgress(user_id=uid, drill_type=dt, level=1)
                s.add(p); s.commit(); s.refresh(p)
            lbl = level_label(dt, p.level)
            last5 = p.stars_recent[-5:]
            # Would levelling occur if the next drill is a star? (for UI hint)
            ready = (last5.count("1") >= 2 and last5[-2:].count("1") >= 1)
            out[dt.value] = {"level": p.level, "label": lbl, "last5": last5, "ready_if_star": ready}
    return JSONResponse(out)
