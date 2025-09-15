from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select, delete
from ..deps import templates
from ..utils.session import is_admin
from ..storage import get_session
from ..models import User, UserSettings, UserProgress, DrillResult, DrillQuestion, DrillAward, AdminConfig

router = APIRouter()

@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    with get_session() as s:
        users = list(s.exec(select(User).order_by(User.display_name)).all())
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "users": users,
        "hint": "Password is printed to the container logs on boot.",
        "authed": is_admin(request),
        "app_name": "Quickfire Math",
    })

@router.post("/admin/login")
def admin_login(password: str = Form(...)):
    with get_session() as s:
        cfg = s.exec(select(AdminConfig)).first()
    if not cfg or password != cfg.admin_password_plain:
        return RedirectResponse("/admin", status_code=303)
    resp = RedirectResponse("/admin", status_code=303)
    resp.set_cookie("is_admin", "1", max_age=60*60*6, samesite="lax", httponly=True)
    return resp

@router.post("/admin/logout")
def admin_logout():
    resp = RedirectResponse("/admin", status_code=303)
    resp.delete_cookie("is_admin")
    return resp

@router.post("/admin/delete_user")
def admin_delete_user(request: Request, user_id: int = Form(...)):
    if not is_admin(request):
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
