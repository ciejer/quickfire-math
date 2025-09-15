from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlmodel import select
from ..deps import templates
from ..storage import get_session
from ..models import User, UserSettings, DrillTypeEnum, UserProgress
from ..levels import thresholds_for_level

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
def login(request: Request):
    with get_session() as s:
        users = list(s.exec(select(User)).all())
    return templates.TemplateResponse("login.html", {"request": request, "users": users, "app_name": "Quickfire Math"})

@router.post("/login")
def do_login(user_id: int = Form(...)):
    resp = RedirectResponse(url="/dashboard", status_code=303)
    resp.set_cookie("uid", str(user_id), max_age=60*60*24*365, samesite="lax")
    return resp

@router.post("/user/add")
def user_add(display_name: str = Form(...)):
    name = (display_name or "").strip()
    if not name:
        return RedirectResponse("/", status_code=303)
    with get_session() as s:
        u = User(display_name=name)
        s.add(u); s.commit(); s.refresh(u)
        s.add(UserSettings(user_id=u.id))
        for dt in DrillTypeEnum:
            _, _, _, _, TMAX = thresholds_for_level(1)
            s.add(UserProgress(user_id=u.id, drill_type=dt, level=1, target_time_sec=TMAX))
        s.commit()
        new_id = u.id
    resp = RedirectResponse(url="/dashboard", status_code=303)
    resp.set_cookie("uid", str(new_id), max_age=60*60*24*365, samesite="lax")
    return resp
