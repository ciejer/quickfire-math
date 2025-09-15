from typing import List, Tuple
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from sqlmodel import select
from ..utils.session import get_user_id
from ..storage import get_session
from ..models import DrillQuestion, DrillResult, DrillTypeEnum

router = APIRouter()

def _last5_error_rate(rows: List[Tuple[int,int,bool,datetime]], a_range, b_range):
    bucket = {a:{b:[] for b in b_range} for a in a_range}
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

@router.get("/report/multiplication")
def report_mul(request: Request):
    uid = get_user_id(request)
    if not uid:
        raise HTTPException(403)
    rows: List[Tuple[int,int,bool,datetime]] = []
    with get_session() as s:
        q = s.exec(
            select(DrillQuestion.a, DrillQuestion.b, DrillQuestion.correct, DrillQuestion.started_at, DrillResult.user_id)
            .join(DrillResult, DrillResult.id == DrillQuestion.drill_result_id)
            .where(DrillResult.user_id == uid)
            .where(DrillQuestion.drill_type == DrillTypeEnum.multiplication)
        ).all()
    for a, b, ok, ts, _uid in q:
        rows.append((int(a), int(b), bool(ok), ts))
    grid = _last5_error_rate(rows, range(1,13), range(1,13))
    return JSONResponse({"labels_from": 1, "labels_to": 12, "grid": grid})

@router.get("/report/addition")
def report_add(request: Request):
    uid = get_user_id(request)
    if not uid:
        raise HTTPException(403)
    rng = 20
    rows: List[Tuple[int,int,bool,datetime]] = []
    with get_session() as s:
        q = s.exec(
            select(DrillQuestion.a, DrillQuestion.b, DrillQuestion.correct, DrillQuestion.started_at, DrillResult.user_id)
            .join(DrillResult, DrillResult.id == DrillQuestion.drill_result_id)
            .where(DrillResult.user_id == uid)
            .where(DrillQuestion.drill_type == DrillTypeEnum.addition)
        ).all()
    for a, b, ok, ts, _uid in q:
        rows.append((int(a), int(b), bool(ok), ts))
    grid = _last5_error_rate(rows, range(0,rng+1), range(0,rng+1))
    return JSONResponse({"labels_from": 0, "labels_to": rng, "grid": grid})

@router.get("/report/subtraction")
def report_sub(request: Request):
    uid = get_user_id(request)
    if not uid:
        raise HTTPException(403)
    rng = 20
    rows: List[Tuple[int,int,bool,datetime]] = []
    with get_session() as s:
        q = s.exec(
            select(DrillQuestion.a, DrillQuestion.b, DrillQuestion.correct, DrillQuestion.started_at, DrillResult.user_id)
            .join(DrillResult, DrillResult.id == DrillQuestion.drill_result_id)
            .where(DrillResult.user_id == uid)
            .where(DrillQuestion.drill_type == DrillTypeEnum.subtraction)
        ).all()
    for a, b, ok, ts, _uid in q:
        rows.append((int(a), int(b), bool(ok), ts))
    grid = _last5_error_rate(rows, range(0,rng+1), range(0,rng+1))
    return JSONResponse({"labels_from": 0, "labels_to": rng, "grid": grid})
