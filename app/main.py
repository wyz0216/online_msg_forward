from contextlib import asynccontextmanager
from typing import Literal
from urllib.parse import urlencode

from fastapi import FastAPI, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .auth import current_user, router as auth_router
from .config import Settings, load_settings
from .db import init_db
from .messages import list_user_messages, router as messages_router
from .shares import router as shares_router
from .time_utils import format_shanghai_time


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app_settings.upload_dir.mkdir(parents=True, exist_ok=True)
        init_db(app_settings.database_path)
        yield

    app = FastAPI(lifespan=lifespan)
    app.state.settings = app_settings
    app.state.templates = Jinja2Templates(directory="app/templates")
    app.state.templates.env.filters["shanghai_time"] = format_shanghai_time
    app.add_middleware(SessionMiddleware, secret_key=app_settings.secret_key)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(auth_router)
    app.include_router(messages_router)
    app.include_router(shares_router)

    @app.get("/")
    def index(
        request: Request,
        page: int = Query(1, ge=1),
        q: str = Query("", max_length=200),
        kind: Literal["all", "text", "image", "file"] = "all",
    ):
        user = current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        query = q.strip()
        result = list_user_messages(app_settings, user["id"], page, query, kind)
        page = result["page"]
        return request.app.state.templates.TemplateResponse(
            request,
            "index.html",
            {
                "user": user,
                **result,
                "query": query,
                "kind": kind,
                "previous_url": "/?" + urlencode({"page": page - 1, "q": query, "kind": kind}) if page > 1 else None,
                "next_url": "/?" + urlencode({"page": page + 1, "q": query, "kind": kind}) if page < result["page_count"] else None,
                "expiration_options": [1, 5, 10, 30, 60],
                "max_upload_mb": app_settings.max_upload_mb,
                "max_upload_bytes": app_settings.max_upload_bytes,
            },
        )

    return app


app = create_app()
