from __future__ import annotations

import os, secrets, random, json, re
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Set

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
from .levels import get_preset, clamp_level, level_label, thresholds_for_level
from .logic import (
    generate_from_preset, compute_first_try_metrics,
    star_decision, levelup_decision, is_commutative_op_key
)

APP_NAME = "Quickfire Math"
app = FastAPI(title=APP_NAME)
BASE_DIR = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# ---------- Admin password ----------
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
                # per-level personalised speed target = TMAX(level)
                _, _, _, _, TMAX = thresholds_for_level(1)
                s.add(UserProgress(user_id=uid, drill_type=dt, level=1, target_time_sec=TMAX))
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
        # initialise progress rows
        for dt in DrillTypeEnum:
            _, _, _, _, TMAX = thresholds_for_level(1)
            s.add(UserProgress(user_id=u.id, drill_type=dt, level=1, target_time_sec=TMAX))
        s.commit()
        new_id = u.id
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
    avoid_pair: Optional[str] = Form(default=None),   # e.g. "×:4,6" sorted
):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    _, _, preset = level_info(uid, drill_type)

    def ok_pair(new_prompt: str) -> bool:
        if not avoid_pair: return True
        return is_commutative_op_key(new_prompt) != avoid_pair

    for _ in range(16):
        p, ans, tts = generate_from_preset(drill_type, preset)
        if (not avoid_prompt or p != avoid_prompt) and ok_pair(p):
            return JSONResponse({"prompt": p, "answer": ans, "tts": tts})
    return JSONResponse({"prompt": p, "answer": ans, "tts": tts})

def _friendly_fail(metrics: dict, target_time_sec: float, why: str) -> str:
    items = metrics.get("items", 20) or 20
    A, _, _, _, _ = thresholds_for_level(1)  # A only (varies slightly by level—fine for messaging)
    need = int((A * items + 0.9999))  # ceil
    ftc = metrics.get("first_try_correct", round(metrics.get("acc", 0.0) * items))

    if why == "accuracy_below_gate":
        more = max(0, need - ftc)
        if more <= 1:
            return "Just one more correct and you’ll get a star!"
        return f"Great effort — {need}/{items} correct is the goal."
    if why == "too_slow":
        m = int(target_time_sec // 60); s = int(target_time_sec % 60)
        return f"Just a bit faster — finish under {m}:{str(s).zfill(2)} to earn a star."
    return "So close — one more push and you’ll have it!"

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
        prog = s.exec(select(UserProgress).where(
            UserProgress.user_id == uid, UserProgress.drill_type == drill_type
        )).first()
        if not prog:
            _, _, _, _, TMAX = thresholds_for_level(1)
            prog = UserProgress(user_id=uid, drill_type=drill_type, level=1, target_time_sec=TMAX)
            s.add(prog); s.commit(); s.refresh(prog)

        # record result (prefix label with [L#] so feed can show it)
        level_at = int(prog.level)
        snapshot = f"[L{level_at}] {settings_human} • Score {score}/{question_count}"
        rec = DrillResult(
            user_id=uid, drill_type=drill_type,
            settings_snapshot=snapshot, question_count=question_count, elapsed_ms=elapsed_ms,
        )
        s.add(rec); s.commit(); s.refresh(rec)

        # store questions
        try:
            logs = json.loads(qlog)
        except Exception:
            logs = []
        for e in logs:
            try:
                started = datetime.fromisoformat(str(e.get("started_at")).replace("Z",""))
            except Exception:
                started = datetime.utcnow()
            dq = DrillQuestion(
                drill_result_id=rec.id, drill_type=drill_type,
                a=int(e.get("a", 0)), b=int(e.get("b", 0)), prompt=str(e.get("prompt","")),
                correct_answer=int(e.get("correct_answer",0)), given_answer=int(e.get("given_answer",0)),
                correct=bool(e.get("correct", False)), started_at=started, elapsed_ms=int(e.get("elapsed_ms",0)),
            )
            s.add(dq)
        s.commit()

        # metrics + star
        metrics = compute_first_try_metrics(logs)
        target_time_sec = float(prog.target_time_sec or thresholds_for_level(prog.level)[4])
        star, exp = star_decision(metrics, elapsed_ms, target_time_sec)

        awards: list[tuple[str,str]] = []
        if star: awards.append(("star", "⭐ Star earned"))

        # personal bests (per level)
        if prog.best_time_ms is None or elapsed_ms < prog.best_time_ms:
            prog.best_time_ms = elapsed_ms; awards.append(("pb_time", "🏁 New best time"))
        if prog.best_acc is None or metrics["acc"] > (prog.best_acc or 0):
            prog.best_acc = metrics["acc"]; awards.append(("pb_acc", "🎯 New best accuracy"))

        # stars history + level up calc (before appending this one)
        sr_before = prog.stars_recent or ""
        did_level_up = levelup_decision(sr_before, star)

        # append this drill
        prog.stars_recent = (sr_before + ("1" if star else "0"))[-6:]

        # level up → compute next level's personalised target, then reset per-level stats
        new_level_label = ""
        if did_level_up:
            prev_best_sec = (prog.best_time_ms or elapsed_ms) / 1000.0
            next_level = clamp_level(drill_type, prog.level + 1)
            _, _, _, _, TMAX = thresholds_for_level(next_level)
            next_target = min(TMAX, prev_best_sec * 1.5)
            prog.level = next_level
            prog.last_levelup_at = datetime.utcnow()
            prog.target_time_sec = int(round(next_target))
            new_level_label = level_label(drill_type, next_level)
            # reset per-level stats for the new level
            prog.best_time_ms = None
            prog.best_acc = None
            prog.stars_recent = ""
            awards.append(("level_up", f"⬆️ Level up to {new_level_label}"))

        # resolve values before commit/session closes
        new_level_val = int(prog.level)
        star_bool = bool(star)
        levelup_bool = bool(did_level_up)
        fail_msg = "" if star_bool else _friendly_fail(metrics, target_time_sec, exp.get("why",""))

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
        "need_hint": need_hint_text(sr_before, star),  # before-append view for “what do I need now?”
    })

# ---------- Stars-needed messaging ----------
def need_hint_text(stars_recent: str, this_star: bool) -> str:
    """
    Return a short hint like:
    - "Need a star next round to level up" OR
    - "Need 2 of the next 4 rounds to level up"
    Looks ahead up to 4 rounds, considering the rolling 5-window + last-3 rule.
    """
    s = (stars_recent or "")[-5:]
    # If a star now would level up immediately:
    if levelup_decision(s, True):
        return "Need a star next round to level up"
    # brute-force minimal stars over horizon 2..4
    for horizon in range(2, 5):
        best_needed = 10
        # enumerate all patterns of S/N over horizon with k stars
        from itertools import product
        for seq in product([0,1], repeat=horizon):
            # count stars
            k = sum(seq)
            # simulate rolling window
            win = s
            ok = False
            for b in seq:
                win = (win + ("1" if b else "0"))[-5:]
                if win.count("1") >= 3 and win[-3:].count("1") >= 2:
                    ok = True; break
            if ok:
                best_needed = min(best_needed, k)
        if best_needed < 10:
            if horizon == 1:
                return "Need a star next round to level up"
            if best_needed == 1 and horizon == 2:
                return "Need 1 of the next 2 rounds to level up"
            return f"Need {best_needed} of the next {horizon} rounds to level up"
    return "Get 3 of your last 5 stars to level up"

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
                out[dt.value] = {"level": 1, "label": level_label(dt, 1), "last5": "", "ready_if_star": False, "need_msg": "Get 3 of your last 5 stars to level up"}
            else:
                sr = (prog.stars_recent or "")[-5:]
                out[dt.value] = {
                    "level": prog.level,
                    "label": level_label(dt, prog.level),
                    "last5": sr,
                    "ready_if_star": levelup_decision(sr, True),
                    "need_msg": need_hint_text(sr, False),
                }
    return JSONResponse(out)

@app.get("/feed")
def feed(request: Request):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)

    with get_session() as s:
        results: List[DrillResult] = s.exec(
            select(DrillResult)
            .where(DrillResult.user_id == uid)
            .order_by(DrillResult.created_at.desc())
            .limit(25)
        ).all()

        # map: result_id -> has_star
        res_ids = [r.id for r in results]
        star_ids: Set[int] = set()
        if res_ids:
            aw = s.exec(
                select(DrillAward.drill_result_id)
                .where(DrillAward.drill_result_id.in_(res_ids))
                .where(DrillAward.award_type == "star")
            ).all()
            star_ids = set(x for (x,) in aw)

    items = []
    for r in results:
        # parse [L#] out of snapshot if present
        m = re.match(r"^\[L(\d+)\]\s+(.*)$", r.settings_snapshot or "")
        level_num = int(m.group(1)) if m else None
        label_part = m.group(2) if m else (r.settings_snapshot or "")
        # extract score from "• Score a/b" if present
        score_num = None
        ms = re.search(r"Score\s+(\d+)\s*/\s*(\d+)", r.settings_snapshot or "")
        if ms:
            score_num = f"{ms.group(1)}/{ms.group(2)}"
        items.append({
            "ts": r.created_at.isoformat(),
            "drill_type": r.drill_type.value,
            "level": level_num,
            "label": label_part,
            "score": score_num,
            "time_ms": r.elapsed_ms,
            "star": (r.id in star_ids),
        })
    return JSONResponse({"items": items})

@app.get("/stats")
def stats(request: Request, tz_offset: int = 0):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    local_now = datetime.utcnow() - timedelta(minutes=tz_offset)
    local_start = datetime(local_now.year, local_now.month, local_now.day)
    local_end = local_start + timedelta(days=1)
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

# ---- Heatmaps (last-5 attempts, brighter=needs work) ----
def _last5_error_rate(rows: List[Tuple[int,int,bool,datetime]], a_range, b_range):
    bucket: Dict[int, Dict[int, List[Tuple[datetime,bool]]]] = {a:{b:[] for b in b_range} for a in a_range}
    for a,b,ok,ts in rows:
        if a in bucket and b in bucket[a]:
            bucket[a][b].append((ts, ok))
    grid = {a:{b:None for b in b_range} for a in a_range}
    for a in a_range:
        for b in b_range:
            if not bucket[a][b]:
                grid[a][b] = None
            else:
                bucket[a][b].sort(key=lambda t: t[0])
                last = [ok for _,ok in bucket[a][b][-5:]]
                wrong = last.count(False)
                grid[a][b] = wrong / len(last)
    return grid

@app.get("/report/multiplication")
def report_mul(request: Request):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    rows: List[Tuple[int,int,bool,datetime]] = []
    with get_session() as s:
        q = s.exec(
            select(DrillQuestion.a, DrillQuestion.b, DrillQuestion.correct, DrillQuestion.started_at, DrillResult.user_id)
            .join(DrillResult, DrillResult.id == DrillQuestion.drill_result_id)
            .where(DrillResult.user_id == uid)
        ).all()
    for a, b, ok, ts, _uid in q:
        rows.append((int(a), int(b), bool(ok), ts))
    grid = _last5_error_rate(rows, range(1,13), range(1,13))
    return JSONResponse({"labels_from": 1, "labels_to": 12, "grid": grid})

@app.get("/report/addition")
def report_add(request: Request):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    rng = 20
    rows: List[Tuple[int,int,bool,datetime]] = []
    with get_session() as s:
        q = s.exec(
            select(DrillQuestion.a, DrillQuestion.b, DrillQuestion.correct, DrillQuestion.started_at, DrillResult.user_id)
            .join(DrillResult, DrillResult.id == DrillQuestion.drill_result_id)
            .where(DrillResult.user_id == uid)
        ).all()
    for a, b, ok, ts, _uid in q:
        rows.append((int(a), int(b), bool(ok), ts))
    grid = _last5_error_rate(rows, range(0,rng+1), range(0,rng+1))
    return JSONResponse({"labels_from": 0, "labels_to": rng, "grid": grid})

@app.get("/report/subtraction")
def report_sub(request: Request):
    uid = get_user_id(request)
    if not uid: raise HTTPException(403)
    rng = 20
    rows: List[Tuple[int,int,bool,datetime]] = []
    with get_session() as s:
        q = s.exec(
            select(DrillQuestion.a, DrillQuestion.b, DrillQuestion.correct, DrillQuestion.started_at, DrillResult.user_id)
            .join(DrillResult, DrillResult.id == DrillQuestion.drill_result_id)
            .where(DrillResult.user_id == uid)
        ).all()
    for a, b, ok, ts, _uid in q:
        rows.append((int(a), int(b), bool(ok), ts))
    grid = _last5_error_rate(rows, range(0,rng+1), range(0,rng+1))
    return JSONResponse({"labels_from": 0, "labels_to": rng, "grid": grid})

# ---------- Admin ----------
def _is_admin(request: Request) -> bool:
    return request.cookies.get("is_admin") == "1"

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    with get_session() as s:
        users = list(s.exec(select(User).order_by(User.display_name)).all())
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
    resp.set_cookie("is_admin", "1", max_age=60*60*6, samesite="lax")
    return resp

@app.post("/admin/delete_user")
def admin_delete_user(request: Request, user_id: int = Form(...)):
    if not _is_admin(request):
        raise HTTPException(403)
    with get_session() as s:
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
