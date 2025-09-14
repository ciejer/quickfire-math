from __future__ import annotations

import os, secrets, random, json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import select, delete

from .storage import init_db, get_session
from .models import (
    User, UserSettings, DrillResult, DrillQuestion,
    DrillTypeEnum, AdminConfig, UserProgress, DrillAward
)
from .levels import get_preset, clamp_level, level_label
from .logic import (
    generate_from_preset, compute_first_try_metrics, ewma_update,
    star_decision, levelup_decision
)

APP_NAME = "Quickfire Math"
app = FastAPI(title=APP_NAME)
BASE_DIR = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# ---------- Admin password generation ----------
_WORDS = ["tui","kiwi","pohutukawa","harbour","beach","waka","kauri","ponga","kepler",
          "southern","albatross","river","island","koru","pounamu","sunrise","sunset",
          "storm","mist","summit","spark","ember","glow","forest","valley","ocean","rimu",
          "totara","manuka","harakeke","kumara","tuatara","alpine","peak","fern","swift",
          "clever","brave","steady","calm","bright","kind","solid","focused","nimble"]
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

# ---------- Helpers ----------
def get_user_id(request: Request) -> Optional[int]:
    v = request.cookies.get("uid")
    return int(v) if v and v.isdigit() else None

def ensure_progress_rows(uid: int):
    with get_session() as s:
        for dt in DrillTypeEnum:
            prog = s.exec(select(UserProgress).where(
                UserProgress.user_id == uid, UserProgress.drill_type == dt
            )).first()
            if not prog:
                s.add(UserProgress(user_id=uid, drill_type=dt, level=1))
        s.commit()

def level_info(uid: int, dt: DrillTypeEnum) -> tuple[int,str,dict]:
    ensure_progress_rows(uid)
    with get_session() as s:
        prog = s.exec(select(UserProgress).where(
            UserProgress.user_id == uid, UserProgress.drill_type == dt
        )).first()
    lvl = clamp_level(dt, prog.level if prog else 1)
    return lvl, level_label(dt, lvl), get_preset(dt, lvl)

# ---------- Pages ----------
@app.get("/", response_class=HTMLResponse)
def login(request: Request):
    with get_session() as s:
        users = list(s.exec(select(User)).all())
    return templates.TemplateResponse("login.html", {"request": request, "users": users, "app_name": APP_NAME})

@app.post("/login")
def do_login(user_id: int = Form(...)):
    resp = RedirectResponse(url="/home", status_code=303)
    resp.set_cookie("uid", str(user_id), max_age=60*60*24*365, samesite="lax")
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
    resp.set_cookie("uid", str(new_id), max_age=60*60*24*365, samesite="lax")
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
    return templates.TemplateResponse("home.html", {"request": request, "user": user, "drills": drills})

@app.post("/start", response_class=HTMLResponse)
def start_drill(request: Request, drill_type: DrillTypeEnum = Form(...)):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    lvl, lbl, preset = level_info(uid, drill_type)
    p, ans, tts = generate_from_preset(drill_type, preset)
    return templates.TemplateResponse("drill.html", {
        "request": request, "drill_type": drill_type.value,
        "target_count": 20, "first_prompt": p, "first_answer": ans, "first_tts": tts,
        "settings_human": lbl
    })

# ---------- API: next / finish ----------
@app.post("/next")
def next_problem(
    request: Request,
    drill_type: DrillTypeEnum = Form(...),
    avoid_prompt: Optional[str] = Form(default=None),
):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    _, _, preset = level_info(uid, drill_type)

    # try to avoid immediate duplicates (up to 10 attempts)
    for _ in range(10):
        p, ans, tts = generate_from_preset(drill_type, preset)
        if not avoid_prompt or p != avoid_prompt:
            return JSONResponse({"prompt": p, "answer": ans, "tts": tts})
    # give up gracefully
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
            user_id=uid, drill_type=drill_type,
            settings_snapshot=f"{settings_human} • Score {score}/{question_count}",
            question_count=question_count, elapsed_ms=elapsed_ms,
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
                correct=bool(e.get("correct", False)),
                started_at=started, elapsed_ms=int(e.get("elapsed_ms",0)),
            ))
        s.commit()

        prog = s.exec(select(UserProgress).where(
            UserProgress.user_id == uid, UserProgress.drill_type == drill_type
        )).first()
        if not prog:
            prog = UserProgress(user_id=uid, drill_type=drill_type, level=1)
            s.add(prog); s.commit(); s.refresh(prog)

        metrics = compute_first_try_metrics(logs)
        star, exp = star_decision(prog.level, metrics, elapsed_ms, prog.ewma_tpq_ms)

        # update EWMAs (if we got any timing/accuracy at all)
        if metrics.get("tpq_ms") is not None:
            prog.ewma_tpq_ms = ewma_update(prog.ewma_tpq_ms, float(metrics["tpq_ms"]))
        if metrics.get("acc") is not None:
            prog.ewma_acc = ewma_update(prog.ewma_acc, float(metrics["acc"]))

        awards: list[tuple[str,str]] = []
        if star: awards.append(("star", "⭐ Star earned"))
        if prog.best_time_ms is None or elapsed_ms < prog.best_time_ms:
            prog.best_time_ms = elapsed_ms; awards.append(("pb_time", "🏁 New best time"))
        if prog.best_acc is None or metrics["acc"] > prog.best_acc:
            prog.best_acc = metrics["acc"]; awards.append(("pb_acc", "🎯 New best accuracy"))

        # history BEFORE appending this drill
        sr_before = prog.stars_recent or ""
        did_level_up = levelup_decision(sr_before, star)

        # append this drill to history (keep last 6 just for cushion)
        prog.stars_recent = (sr_before + ("1" if star else "0"))[-6:]

        if did_level_up:
            prog.level = clamp_level(drill_type, prog.level + 1)
            prog.last_levelup_at = datetime.utcnow()
            # reset per-level progress
            prog.best_time_ms = None
            prog.best_acc = None
            prog.stars_recent = ""     # reset for the new level
            prog.ewma_tpq_ms = None
            prog.ewma_acc = None
            awards.append(("level_up", f"⬆️ Level up to {level_label(drill_type, prog.level)}"))

        s.add(prog); s.commit()

        for (t, text) in awards:
            s.add(DrillAward(drill_result_id=rec.id, award_type=t, payload=text))
        s.commit()

    return JSONResponse({
        "ok": True,
        "star": bool(star),
        "level_up": bool(did_level_up),
        "new_level": prog.level,
        "awards": [a for _, a in awards],
        "explain": {"need": "Earn 3 of your last 5 stars to level up."},
    })

# ---------- API: tiles/feed/stats/reports ----------
@app.get("/progress")
def progress(request: Request):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    ensure_progress_rows(uid)
    out = {}
    with get_session() as s:
        for dt in DrillTypeEnum:
            prog = s.exec(select(UserProgress).where(
                UserProgress.user_id == uid, UserProgress.drill_type == dt
            )).first()
            if not prog:
                out[dt.value] = {"level": 1, "label": level_label(dt, 1), "last5": "", "ready_if_star": False}
            else:
                out[dt.value] = {
                    "level": prog.level,
                    "label": level_label(dt, prog.level),
                    "last5": (prog.stars_recent or "")[-5:],
                    "ready_if_star": levelup_decision(prog.stars_recent or "", True),
                }
    return JSONResponse(out)

@app.get("/feed")
def feed(request: Request):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    with get_session() as s:
        rows = s.exec(
            select(DrillResult)
            .where(DrillResult.user_id == uid)
            .order_by(DrillResult.created_at.desc())
            .limit(25)
        ).all()
    items = [{"ts": r.created_at.isoformat(), "settings": r.settings_snapshot, "elapsed_ms": r.elapsed_ms} for r in rows]
    return JSONResponse({"items": items})

@app.get("/stats")
def stats(request: Request, tz_offset: int = 0):
    """tz_offset is minutes from UTC (window.getTimezoneOffset())"""
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    # convert "now UTC" to local using tz_offset (note: NZ is -720)
    local_now = datetime.utcnow() - timedelta(minutes=tz_offset)
    local_start = datetime(local_now.year, local_now.month, local_now.day)
    local_end = local_start + timedelta(days=1)
    # back to UTC for querying
    start_utc = local_start + timedelta(minutes=tz_offset)
    end_utc = local_end + timedelta(minutes=tz_offset)

    with get_session() as s:
        q = s.exec(
            select(DrillResult)
            .where(DrillResult.user_id == uid)
            .where(DrillResult.created_at >= start_utc)
            .where(DrillResult.created_at < end_utc)
        )
        rows = q.all()
    counts = {"total": len(rows), "addition": 0, "subtraction": 0, "multiplication": 0, "division": 0}
    for r in rows:
        counts[r.drill_type.value] += 1
    return JSONResponse(counts)

@app.get("/report/multiplication")
def report_mul(request: Request):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    grid = {a: {b: None for b in range(1,13)} for a in range(1,13)}
    counts = {a: {b: {"ok":0, "wrong":0} for b in range(1,13)} for a in range(1,13)}
    with get_session() as s:
        qs = s.exec(select(DrillQuestion).where(
            DrillQuestion.user_id == uid if hasattr(DrillQuestion, "user_id") else True  # fallback if model lacks column
        )).all()
    # fall back: derive user_id via result join if DrillQuestion has no user_id column
    if qs and not hasattr(qs[0], "user_id"):
        with get_session() as s:
            for q in s.exec(select(DrillQuestion, DrillResult.user_id).join(DrillResult, DrillQuestion.drill_result_id == DrillResult.id)).all():
                dq, uid_fk = q  # tuple
                if dq.drill_type != DrillTypeEnum.multiplication: continue
                a, b = int(dq.a), int(dq.b)
                if 1 <= a <= 12 and 1 <= b <= 12:
                    (counts[a][b]["ok"] if dq.correct else counts[a][b]["wrong"]) += 1
    else:
        for dq in qs:
            if dq.drill_type != DrillTypeEnum.multiplication: continue
            a, b = int(dq.a), int(dq.b)
            if 1 <= a <= 12 and 1 <= b <= 12:
                (counts[a][b]["ok"] if dq.correct else counts[a][b]["wrong"]) += 1

    for a in range(1,13):
        for b in range(1,13):
            c = counts[a][b]
            tot = c["ok"] + c["wrong"]
            grid[a][b] = None if tot == 0 else (c["wrong"] / tot)  # 0 good .. 1 bad
    return JSONResponse({"labels_from": 1, "labels_to": 12, "grid": grid})

@app.get("/report/addition")
def report_add(request: Request):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    rng = 20
    grid = {a: {b: None for b in range(0,rng+1)} for a in range(0,rng+1)}
    counts = {a: {b: {"ok":0, "wrong":0} for b in range(0,rng+1)} for a in range(0,rng+1)}
    with get_session() as s:
        rows = s.exec(select(DrillQuestion, DrillResult.user_id).join(DrillResult, DrillQuestion.drill_result_id == DrillResult.id)).all()
    for dq, uid_fk in rows:
        if uid_fk != uid: continue
        if dq.drill_type != DrillTypeEnum.addition: continue
        a, b = int(dq.a), int(dq.b)
        if 0 <= a <= rng and 0 <= b <= rng:
            (counts[a][b]["ok"] if dq.correct else counts[a][b]["wrong"]) += 1
    for a in range(0,rng+1):
        for b in range(0,rng+1):
            c = counts[a][b]; tot = c["ok"] + c["wrong"]
            grid[a][b] = None if tot == 0 else (c["wrong"] / tot)
    return JSONResponse({"labels_from": 0, "labels_to": rng, "grid": grid})

@app.get("/report/subtraction")
def report_sub(request: Request):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    rng = 20
    grid = {a: {b: None for b in range(0,rng+1)} for a in range(0,rng+1)}
    counts = {a: {b: {"ok":0, "wrong":0} for b in range(0,rng+1)} for a in range(0,rng+1)}
    with get_session() as s:
        rows = s.exec(select(DrillQuestion, DrillResult.user_id).join(DrillResult, DrillQuestion.drill_result_id == DrillResult.id)).all()
    for dq, uid_fk in rows:
        if uid_fk != uid: continue
        if dq.drill_type != DrillTypeEnum.subtraction: continue
        a, b = int(dq.a), int(dq.b)
        if 0 <= a <= rng and 0 <= b <= rng:
            (counts[a][b]["ok"] if dq.correct else counts[a][b]["wrong"]) += 1
    for a in range(0,rng+1):
        for b in range(0,rng+1):
            c = counts[a][b]; tot = c["ok"] + c["wrong"]
            grid[a][b] = None if tot == 0 else (c["wrong"] / tot)
    return JSONResponse({"labels_from": 0, "labels_to": rng, "grid": grid})

# ---------- Admin (minimal: delete users) ----------
def _is_admin(request: Request) -> bool:
    return request.cookies.get("is_admin") == "1"

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    with get_session() as s:
        users = list(s.exec(select(User).order_by(User.display_name)).all())
        cfg = s.exec(select(AdminConfig)).first()
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "users": users,
        "hint": "Password is printed to the container logs on boot.",
        "authed": _is_admin(request),
        "app_name": APP_NAME,
    })

@app.post("/admin/login")
def admin_login(request: Request, password: str = Form(...)):
    with get_session() as s:
        cfg = s.exec(select(AdminConfig)).first()
    if not cfg or password != cfg.admin_password_plain:
        return RedirectResponse("/admin", status_code=303)
    resp = RedirectResponse("/admin", status_code=303)
    resp.set_cookie("is_admin", "1", max_age=60*60*6, samesite="lax")  # 6 hours
    return resp

@app.post("/admin/delete_user")
def admin_delete_user(request: Request, user_id: int = Form(...)):
    if not _is_admin(request):
        raise HTTPException(403)
    with get_session() as s:
        # delete drill questions -> results -> settings -> progress -> user
        s.exec(delete(DrillQuestion).where(DrillQuestion.drill_result_id.in_(
            select(DrillResult.id).where(DrillResult.user_id == user_id)
        )))
        s.exec(delete(DrillAward).where(DrillAward.drill_result_id.in_(
            select(DrillResult.id).where(DrillResult.user_id == user_id)
        )))
        s.exec(delete(DrillResult).where(DrillResult.user_id == user_id))
        s.exec(delete(UserSettings).where(UserSettings.user_id == user_id))
        s.exec(delete(UserProgress).where(UserProgress.user_id == user_id))
        s.exec(delete(User).where(User.id == user_id))
        s.commit()
    return RedirectResponse("/admin", status_code=303)
