from typing import Optional
from fastapi import Request

def get_user_id(request: Request) -> Optional[int]:
    v = request.cookies.get("uid")
    return int(v) if v and v.isdigit() else None

def is_admin(request: Request) -> bool:
    return request.cookies.get("is_admin") == "1"
