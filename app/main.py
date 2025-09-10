from __future__ import annotations

import os
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import select

from .storage import init_db, get_session
from .models import User, UserSettings, DrillResult, DrillTypeEnum
from .logic import generate_problem, human_settings

APP_NAME = "Koiahi Maths"
app = FastAPI(title=APP_NAME)
BASE_DIR = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.on_event("startup")
def startup():
    init_db()


def get_user_id(request: Request) -> int | None:
    v = request.cookies.get("uid")
    return int(v) if v and v.isdigit() else None


def _iso_z(dt: datetime) -> str:
    # created_at stored as UTC-naive; treat as UTC and add Z
    return dt.isoformat() + "Z"


@app.get("/", response_class=HTMLResponse)
def login(request: Request):
    with get_session() as s:
        users = list(s.exec(select(User)).all())
    return templates.TemplateResponse("login.html", {"request": request, "users": users, "app_name": APP_NAME})


@app.post("/login")
def do_login(user_id: int = Form(...)):
    resp = RedirectResponse(url="/home", status_code=303)
    resp.set_cookie("uid", str(user_id), max_age=60 * 60 * 24 * 365)
    return resp


@app.get("/home", response_class=HTMLResponse)
def home(request: Request):
    uid = get_user_id(request)
    if not uid:
        return RedirectResponse("/")
    with get_session() as s:
        user = s.get(User, uid)
        if not user:
            return RedirectResponse("/")
        st = s.exec(select(UserSettings).where(UserSettings.user_id == uid)).first()
        if not st:
            st = UserSettings(user_id=uid)
            s.add(st)
            s.commit()
            s.refresh(st)
        drills = s.exec(
            select(DrillResult)
            .where(DrillResult.user_id == uid)
            .order_by(DrillResult.created_at.desc())
            .limit(20)
        ).all()
    return templates.TemplateResponse("home.html", {"request": request, "user": user, "st": st, "drills": drills})


@app.get("/settings", response_class=HTMLResponse)
def settings(request: Request):
    with get_session() as s:
        users = list(s.exec(select(User)).all())
        settings_list = list(s.exec(select(UserSettings)).all())
    settings_map = {st.user_id: st for st in settings_list}
    rows = [{"user": u, "settings": settings_map.get(u.id)} for u in users]
    return templates.TemplateResponse("settings.html", {"request": request, "rows": rows})


@app.post("/settings/add_user")
def add_user(display_name: str = Form(...)):
    with get_session() as s:
        u = User(display_name=display_name.strip())
        s.add(u)
        s.commit()
        s.refresh(u)
        s.add(UserSettings(user_id=u.id))
        s.commit()
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/settings/delete_user")
def delete_user(user_id: int = Form(...)):
    with get_session() as s:
        u = s.get(User, user_id)
        if u:
            s.delete(u)
            s.commit()
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/settings/update")
def update_settings(
    user_id: int = Form(...),
    add_enabled: bool = Form(False),
    add_min: int = Form(...),
    add_max: int = Form(...),
    sub_enabled: bool = Form(False),
    sub_min: int = Form(...),
    sub_max: int = Form(...),
    mul_enabled: bool = Form(False),
    mul_a_min: int = Form(...),
    mul_a_max: int = Form(...),
    mul_b_min: int = Form(...),
    mul_b_max: int = Form(...),
    div_enabled: bool = Form(False),
    div_dividend_max: int = Form(...),
    div_divisor_min: int = Form(...),
    div_divisor_max: int = Form(...),
):
    with get_session() as s:
        st = s.exec(select(UserSettings).where(UserSettings.user_id == user_id)).first()
        if not st:
            st = UserSettings(user_id=user_id)
            s.add(st)
        st.add_enabled = add_enabled
        st.add_min, st.add_max = add_min, add_max
        st.sub_enabled = sub_enabled
        st.sub_min, st.sub_max = sub_min, sub_max
        st.mul_enabled = mul_enabled
        st.mul_a_min, st.mul_a_max = mul_a_min, mul_a_max
        st.mul_b_min, st.mul_b_max = mul_b_min, mul_b_max
        st.div_enabled = div_enabled
        st.div_dividend_max = div_dividend_max
        st.div_divisor_min, st.div_divisor_max = div_divisor_min, div_divisor_max
        s.add(st)
        s.commit()
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/start")
def start_drill(request: Request, drill_type: DrillTypeEnum = Form(...), count: int = Form(20)):
    uid = get_user_id(request)
    if not uid:
        raise HTTPException(403)
    with get_session() as s:
        st = s.exec(select(UserSettings).where(UserSettings.user_id == uid)).first()
        user = s.get(User, uid)
    if not st or not user:
        raise HTTPException(404, "User not found")
    enable_map = {
        "addition": st.add_enabled,
        "subtraction": st.sub_enabled,
        "multiplication": st.mul_enabled,
        "division": st.div_enabled,
    }
    if not enable_map[drill_type.value]:
        raise HTTPException(400, "Drill type disabled for this user")

    prompt, ans, tts = generate_problem(drill_type.value, st)
    settings_human = human_settings(drill_type.value, st)
    return templates.TemplateResponse(
        "drill.html",
        {
            "request": request,
            "drill_type": drill_type.value,
            "target_count": count,
            "first_prompt": prompt,
            "first_answer": ans,
            "first_tts": tts,
            "settings_human": settings_human,
        },
    )


@app.post("/next")
def next_problem(request: Request, drill_type: DrillTypeEnum = Form(...)):
    uid = get_user_id(request)
    if not uid:
        raise HTTPException(403)
    with get_session() as s:
        st = s.exec(select(UserSettings).where(UserSettings.user_id == uid)).first()
    if not st:
        raise HTTPException(404)
    p, a, tts = generate_problem(drill_type.value, st)
    return JSONResponse({"prompt": p, "answer": a, "tts": tts})


@app.post("/finish")
def finish_drill(
    request: Request,
    drill_type: DrillTypeEnum = Form(...),
    elapsed_ms: int = Form(...),
    settings_human: str = Form(...),
    question_count: int = Form(20),
    score: int = Form(0),
):
    uid = get_user_id(request)
    if not uid:
        raise HTTPException(403)
    snapshot = settings_human
    if score and question_count:
        snapshot = f"{settings_human} • Score {score}/{question_count}"
    with get_session() as s:
        rec = DrillResult(
            user_id=uid,
            drill_type=drill_type,
            settings_snapshot=snapshot,
            question_count=question_count,
            elapsed_ms=elapsed_ms,
        )
        s.add(rec)
        s.commit()
    return JSONResponse({"ok": True})


@app.get("/feed")
def feed(request: Request, limit: int = 20):
    uid = get_user_id(request)
    if not uid:
        raise HTTPException(403)
    with get_session() as s:
        drills = s.exec(
            select(DrillResult)
            .where(DrillResult.user_id == uid)
            .order_by(DrillResult.created_at.desc())
            .limit(limit)
        ).all()
    items = [
        {
            "ts": _iso_z(d.created_at),
            "settings": d.settings_snapshot,
            "elapsed_ms": d.elapsed_ms,
            "type": d.drill_type.value if d.drill_type else str(d.drill_type),
        }
        for d in drills
    ]
    return JSONResponse({"items": items})


@app.get("/stats")
def stats(request: Request, tz_offset: int = 0):
    """Counts for 'today' in the client's local timezone (offset minutes)."""
    uid = get_user_id(request)
    if not uid:
        raise HTTPException(403)
    offset = timedelta(minutes=tz_offset)
    now_utc = datetime.utcnow()
    local_now = now_utc - offset
    start_local = datetime(local_now.year, local_now.month, local_now.day)
    start_utc = start_local + offset
    end_utc = start_utc + timedelta(days=1)
    with get_session() as s:
        drills = s.exec(
            select(DrillResult)
            .where(
                DrillResult.user_id == uid,
                DrillResult.created_at >= start_utc,
                DrillResult.created_at < end_utc,
            )
        ).all()
    counts = {"total": len(drills), "addition": 0, "subtraction": 0, "multiplication": 0, "division": 0}
    for d in drills:
        t = d.drill_type.value if hasattr(d.drill_type, "value") else str(d.drill_type)
        if t in counts:
            counts[t] += 1
    return JSONResponse(counts)
