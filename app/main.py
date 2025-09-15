from __future__ import annotations
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .deps import templates  # noqa: F401  (ensures template dir exists)
from .storage import init_db
from .utils.admin_pwd import ensure_admin_password

from .routers.auth import router as auth_router
from .routers.dashboard import router as dashboard_router
from .routers.drills import router as drills_router
from .routers.feeds import router as feeds_router
from .routers.reports import router as reports_router
from .routers.admin import router as admin_router

APP_NAME = "Quickfire Math"

def create_app() -> FastAPI:
    app = FastAPI(title=APP_NAME)

    # Static files
    base_dir = os.path.dirname(__file__)
    app.mount("/static", StaticFiles(directory=os.path.join(base_dir, "static")), name="static")

    # Routers
    app.include_router(auth_router)
    app.include_router(dashboard_router)
    app.include_router(drills_router)
    app.include_router(feeds_router)
    app.include_router(reports_router)
    app.include_router(admin_router)

    @app.on_event("startup")
    def on_startup():
        init_db()
        ensure_admin_password()  # prints/admin password handling

    return app

app = create_app()
