from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from ..utils.session import get_user_id
from ..utils.feed_builders import fetch_results_with_stars, build_feed_items, today_counts
from ..utils.progress import progress_payload

router = APIRouter()

@router.get("/feed")
def feed(request: Request):
    uid = get_user_id(request)
    if not uid:
        raise HTTPException(403)
    results, star_ids = fetch_results_with_stars(uid, limit=25)
    return JSONResponse({"items": build_feed_items(results, star_ids)})

@router.get("/stats")
def stats(request: Request, tz_offset: int = 0):
    uid = get_user_id(request)
    if not uid:
        raise HTTPException(403)
    return JSONResponse(today_counts(uid, tz_offset))

@router.get("/progress")
def progress(request: Request):
    uid = get_user_id(request)
    if not uid:
        raise HTTPException(403)
    return JSONResponse(progress_payload(uid))
