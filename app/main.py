from __future__ import annotations

import os, secrets, random, json
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import select

from .storage import init_db, get_session
from .models import (
    User, UserSettings, DrillResult, DrillQuestion,
    DrillTypeEnum, AdminConfig, MinExpectations
)
from .logic import generate_problem, human_settings

APP_NAME = "Quickfire Math"
app = FastAPI(title=APP_NAME)
BASE_DIR = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# --- Admin password generation (plaintext by spec)
_WORDS = [
    "tui","kiwi","pohutukawa","harbour","beach","waka","kauri","ponga","kepler","southern",
    "albatross","river","island","koru","pounamu","sunrise","sunset","storm","mist","summit",
    "spark","ember","glow","spring","summer","autumn","winter","forest","valley","ocean",
    "kaitiaki","maunga","moana","wai","rimu","totara","manuka","harakeke","kumara","pipi",
    "tuatara","alpine","peak","shell","stone","fern","drift","breeze","chord","rhythm",
    "swift","clever","brave","steady","calm","bright","kind","solid","focused","nimble",
]
def _generate_admin_password() -> str:
    return f"{random.choice(_WORDS)}-{random.choice(_WORDS)}-{secrets.randbelow(100)}"

@app.on_event("startup")
def startup():
    init_db()
    with get_session() as s:
        cfg = s.exec(select(AdminConfig)).first()
        if not cfg or not cfg.admin_password_plain:
            pwd = _generate_admin_password()
            if not cfg:
                cfg = AdminConfig(admin_password_plain=pwd)
                s.add(cfg)
            else:
                cfg.admin_password_plain = pwd
            s.commit()
            print(f"[Quickfire Math] Admin password (generated): {pwd}")
        else:
            print(f"[Quickfire Math] Admin password: {cfg.admin_password_plain}")

def get_user_id(request: Request) -> int | None:
    v = request.cookies.get("uid")
    return int(v) if v and v.isdigit() else None

def is_admin(request: Request) -> bool:
    return request.cookies.get("admin") == "1"

def _iso_z(dt: datetime) -> str:
    return dt.isoformat() + "Z"

# --- Pages

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

@app.post("/user/add")
def user_add(display_name: str = Form(...)):
    name = display_name.strip()
    if not name:
        return RedirectResponse("/", status_code=303)
    with get_session() as s:
        u = User(display_name=name)
        s.add(u); s.commit(); s.refresh(u)
        s.add(UserSettings(user_id=u.id))
        s.commit()
    # auto-login the new user
    resp = RedirectResponse(url="/home", status_code=303)
    resp.set_cookie("uid", str(u.id), max_age=60 * 60 * 24 * 365)
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
            s.add(st); s.commit(); s.refresh(st)
        drills = s.exec(
            select(DrillResult)
            .where(DrillResult.user_id == uid)
            .order_by(DrillResult.created_at.desc())
            .limit(20)
        ).all()
        mins = s.exec(select(MinExpectations).where(MinExpectations.user_id == uid)).first()
    return templates.TemplateResponse("home.html", {
        "request": request, "user": user, "st": st, "drills": drills, "mins": mins
    })

@app.post("/settings/update")
def update_settings(
    request: Request,
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
    div_q_min: int = Form(...),
    div_q_max: int = Form(...),
    div_divisor_min: int = Form(...),
    div_divisor_max: int = Form(...),
):
    # Validate against Minimum Expectations
    with get_session() as s:
        mins = s.exec(select(MinExpectations).where(MinExpectations.user_id == user_id)).first()
        if mins:
            if add_enabled and not (add_min <= mins.add_req_min and add_max >= mins.add_req_max):
                return PlainTextResponse(
                    "Kia kaha! Please include at least the required addition range "
                    f"{mins.add_req_min}–{mins.add_req_max}. You’ve got this!",
                    status_code=400
                )
            if sub_enabled and not (sub_min <= mins.sub_req_min and sub_max >= mins.sub_req_max):
                return PlainTextResponse(
                    "Ka pai—nearly there. Make sure subtraction includes at least "
                    f"{mins.sub_req_min}–{mins.sub_req_max}.",
                    status_code=400
                )
            if mul_enabled:
                if not (mul_a_min <= mins.mul_a_req_min and mul_a_max >= mins.mul_a_req_max):
                    return PlainTextResponse(
                        "You’re capable of more! First factor must include at least "
                        f"{mins.mul_a_req_min}–{mins.mul_a_req_max}.",
                        status_code=400
                    )
                if not (mul_b_min <= mins.mul_b_req_min and mul_b_max >= mins.mul_b_req_max):
                    return PlainTextResponse(
                        "Awesome effort—now include at least "
                        f"{mins.mul_b_req_min}–{mins.mul_b_req_max} for the second factor.",
                        status_code=400
                    )

        st = s.exec(select(UserSettings).where(UserSettings.user_id == user_id)).first()
        if not st:
            st = UserSettings(user_id=user_id)
            s.add(st)

        st.add_enabled = add_enabled; st.add_min = add_min; st.add_max = add_max
        st.sub_enabled = sub_enabled; st.sub_min = sub_min; st.sub_max = sub_max
        st.mul_enabled = mul_enabled
        st.mul_a_min = mul_a_min; st.mul_a_max = mul_a_max
        st.mul_b_min = mul_b_min; st.mul_b_max = mul_b_max
        st.div_enabled = div_enabled
        st.div_q_min = div_q_min; st.div_q_max = div_q_max
        st.div_divisor_min = div_divisor_min; st.div_divisor_max = div_divisor_max

        s.add(st); s.commit()

    return PlainTextResponse("ok")

@app.post("/start")
def start_drill(request: Request, drill_type: DrillTypeEnum = Form(...)):
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
            "target_count": 20,
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
    qlog: str = Form("[]"),
):
    uid = get_user_id(request)
    if not uid:
        raise HTTPException(403)

    with get_session() as s:
        rec = DrillResult(
            user_id=uid,
            drill_type=drill_type,
            settings_snapshot=f"{settings_human} • Score {score}/{question_count}",
            question_count=question_count,
            elapsed_ms=elapsed_ms,
        )
        s.add(rec); s.commit(); s.refresh(rec)

        try:
            logs = json.loads(qlog)
        except Exception:
            logs = []

        for entry in logs:
            dq = DrillQuestion(
                drill_result_id=rec.id,
                drill_type=drill_type,
                a=int(entry.get("a", 0)),
                b=int(entry.get("b", 0)),
                prompt=str(entry.get("prompt", "")),
                correct_answer=int(entry.get("correct_answer", 0)),
                given_answer=int(entry.get("given_answer", 0)),
                correct=bool(entry.get("correct", False)),
                started_at=datetime.fromisoformat(entry.get("started_at").replace("Z","")),
                elapsed_ms=int(entry.get("elapsed_ms", 0)),
            )
            s.add(dq)
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

# --- Reports

@app.get("/report/multiplication")
def report_multiplication(request: Request):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    with get_session() as s:
        rows = s.exec(
            select(DrillQuestion)
            .join(DrillResult, DrillQuestion.drill_result_id == DrillResult.id)
            .where(
                DrillResult.user_id == uid,
                DrillQuestion.drill_type == DrillTypeEnum.multiplication
            )
        ).all()

    grid = [[None for _ in range(13)] for _ in range(13)]
    stats = {}
    for r in rows:
        key = (r.a, r.b)
        acc = stats.setdefault(key, {"n":0, "wrong":0, "ms":0})
        acc["n"] += 1
        acc["wrong"] += 0 if r.correct else 1
        acc["ms"] += r.elapsed_ms

    for a in range(1,13):
        for b in range(1,13):
            n = stats.get((a,b), {}).get("n", 0)
            if n == 0:
                grid[a][b] = None
            else:
                wrong = stats[(a,b)]["wrong"]
                ms = stats[(a,b)]["ms"] / n
                score = wrong / n + min(ms/4000, 1.0) * 0.6
                grid[a][b] = score
    return JSONResponse({"grid": grid})

@app.get("/report/addition")
def report_addition(request: Request):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    maxn = 20
    with get_session() as s:
        rows = s.exec(
            select(DrillQuestion)
            .join(DrillResult, DrillQuestion.drill_result_id == DrillResult.id)
            .where(
                DrillResult.user_id == uid,
                DrillQuestion.drill_type == DrillTypeEnum.addition
            )
        ).all()

    grid = [[None for _ in range(maxn+1)] for _ in range(maxn+1)]
    stats = {}
    for r in rows:
        a = min(maxn, max(0, r.a)); b = min(maxn, max(0, r.b))
        key = (a,b)
        acc = stats.setdefault(key, {"n":0, "wrong":0, "ms":0})
        acc["n"] += 1
        acc["wrong"] += 0 if r.correct else 1
        acc["ms"] += r.elapsed_ms

    for a in range(0,maxn+1):
        for b in range(0,maxn+1):
            n = stats.get((a,b), {}).get("n", 0)
            if n == 0:
                grid[a][b] = None
            else:
                wrong = stats[(a,b)]["wrong"]
                ms = stats[(a,b)]["ms"] / n
                diff = (a + b) / (maxn*2)
                score = wrong / n + min(ms/3500, 1.0) * 0.6 + diff * 0.2
                grid[a][b] = score
    return JSONResponse({"grid": grid, "labels_from": 0, "labels_to": maxn})

@app.get("/report/subtraction")
def report_subtraction(request: Request):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    maxn = 20
    with get_session() as s:
        rows = s.exec(
            select(DrillQuestion)
            .join(DrillResult, DrillQuestion.drill_result_id == DrillResult.id)
            .where(
                DrillResult.user_id == uid,
                DrillQuestion.drill_type == DrillTypeEnum.subtraction
            )
        ).all()

    grid = [[None for _ in range(maxn+1)] for _ in range(maxn+1)]
    stats = {}
    for r in rows:
        a = max(r.a, r.b); b = min(r.a, r.b)
        a = min(maxn, max(0, a)); b = min(maxn, max(0, b))
        key = (a,b)
        acc = stats.setdefault(key, {"n":0, "wrong":0, "ms":0})
        acc["n"] += 1
        acc["wrong"] += 0 if r.correct else 1
        acc["ms"] += r.elapsed_ms

    for a in range(0,maxn+1):
        for b in range(0,maxn+1):
            n = stats.get((a,b), {}).get("n", 0)
            if n == 0:
                grid[a][b] = None
            else:
                wrong = stats[(a,b)]["wrong"]
                ms = stats[(a,b)]["ms"] / n
                gap = (a - b) / maxn if a >= b else 0
                score = wrong / n + min(ms/3500, 1.0) * 0.6 + gap * 0.2
                grid[a][b] = score
    return JSONResponse({"grid": grid, "labels_from": 0, "labels_to": maxn})

# --- Admin console

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    with get_session() as s:
        users = list(s.exec(select(User)).all())
    return templates.TemplateResponse("admin.html", {
        "request": request, "users": users, "admin": is_admin(request)
    })

@app.post("/admin/login")
def admin_login(request: Request, password: str = Form(...)):
    with get_session() as s:
        cfg = s.exec(select(AdminConfig)).first()
    if not cfg or password != cfg.admin_password_plain:
        return RedirectResponse("/admin", status_code=303)
    resp = RedirectResponse("/admin", status_code=303)
    resp.set_cookie("admin", "1", max_age=60*60*8, httponly=True)
    return resp

@app.get("/admin/logout")
def admin_logout():
    resp = RedirectResponse("/admin", status_code=303)
    resp.delete_cookie("admin")
    return resp

@app.post("/admin/password")
def admin_change_password(request: Request, new_password: str = Form(...)):
    if not is_admin(request): raise HTTPException(403)
    with get_session() as s:
        cfg = s.exec(select(AdminConfig)).first()
        if not cfg:
            cfg = AdminConfig(admin_password_plain=new_password)
            s.add(cfg)
        else:
            cfg.admin_password_plain = new_password
        s.commit()
    print(f"[Quickfire Math] Admin password (changed): {new_password}")
    return RedirectResponse("/admin", status_code=303)

@app.post("/admin/delete_user")
def admin_delete_user(request: Request, user_id: int = Form(...)):
    if not is_admin(request): raise HTTPException(403)
    with get_session() as s:
        u = s.get(User, user_id)
        if u: s.delete(u); s.commit()
    return RedirectResponse("/admin", status_code=303)

@app.post("/admin/expectations")
def admin_expectations(request: Request,
    user_id: int = Form(...),
    add_req_min: int = Form(...), add_req_max: int = Form(...),
    sub_req_min: int = Form(...), sub_req_max: int = Form(...),
    mul_a_req_min: int = Form(...), mul_a_req_max: int = Form(...),
    mul_b_req_min: int = Form(...), mul_b_req_max: int = Form(...),
):
    if not is_admin(request): raise HTTPException(403)
    with get_session() as s:
        mins = s.exec(select(MinExpectations).where(MinExpectations.user_id == user_id)).first()
        if not mins:
            mins = MinExpectations(user_id=user_id)
            s.add(mins)
        mins.add_req_min = add_req_min; mins.add_req_max = add_req_max
        mins.sub_req_min = sub_req_min; mins.sub_req_max = sub_req_max
        mins.mul_a_req_min = mul_a_req_min; mins.mul_a_req_max = mul_a_req_max
        mins.mul_b_req_min = mul_b_req_min; mins.mul_b_req_max = mul_b_req_max
        s.add(mins); s.commit()
    return RedirectResponse("/admin", status_code=303)
@app.get("/admin/expectations/get")
def admin_expectations_get(user_id: int):
    """Return current MinExpectations for a user (or sensible defaults) for admin form prefill."""
    with get_session() as s:
        mins = s.exec(select(MinExpectations).where(MinExpectations.user_id == user_id)).first()
    if not mins:
        # defaults aligned with model defaults
        return JSONResponse({
            "add_req_min": 0, "add_req_max": 10,
            "sub_req_min": 0, "sub_req_max": 10,
            "mul_a_req_min": 1, "mul_a_req_max": 7,
            "mul_b_req_min": 1, "mul_b_req_max": 7,
        })
    return JSONResponse({
        "add_req_min": mins.add_req_min, "add_req_max": mins.add_req_max,
        "sub_req_min": mins.sub_req_min, "sub_req_max": mins.sub_req_max,
        "mul_a_req_min": mins.mul_a_req_min, "mul_a_req_max": mins.mul_a_req_max,
        "mul_b_req_min": mins.mul_b_req_min, "mul_b_req_max": mins.mul_b_req_max,
    })
