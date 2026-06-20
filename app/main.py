from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .auth import current_user, router as auth_router
from .config import Settings, load_settings
from .db import init_db
from .messages import list_user_messages, router as messages_router
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

    @app.get("/")
    def index(request: Request):
        user = current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        messages = list_user_messages(app_settings, user["id"])
        return request.app.state.templates.TemplateResponse(
            request,
            "index.html",
            {
                "user": user,
                "messages": messages,
                "expiration_options": [1, 5, 10, 30, 60],
            },
        )

    return app


app = create_app()
