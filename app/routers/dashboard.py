from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select
from ..deps import templates
from ..utils.session import get_user_id
from ..utils.progress import ensure_progress_rows
from ..storage import get_session
from ..models import DrillResult, User

router = APIRouter()

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    uid = get_user_id(request)
    if not uid:
        return RedirectResponse("/")
    ensure_progress_rows(uid)
    with get_session() as s:
        user = s.get(User, uid)
        drills = s.exec(
            select(DrillResult)
            .where(DrillResult.user_id == uid)
            .order_by(DrillResult.created_at.desc())
            .limit(20)
        ).all()
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user, "drills": drills})
