from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from .auth import current_user, router as auth_router
from .config import Settings, load_settings
from .db import init_db
from .messages import list_user_messages, router as messages_router


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app_settings.upload_dir.mkdir(parents=True, exist_ok=True)
        init_db(app_settings.database_path)
        yield

    app = FastAPI(lifespan=lifespan)
    app.state.settings = app_settings
    app.add_middleware(SessionMiddleware, secret_key=app_settings.secret_key)
    app.include_router(auth_router)
    app.include_router(messages_router)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        user = current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        messages = list_user_messages(app_settings, user["id"])
        items = []
        for message in messages:
            if message["kind"] == "text":
                items.append(f"<li>{message['content']}</li>")
            else:
                items.append(f"<li>{message['original_filename']}</li>")
        return f"<h1>Messages</h1><p>{user['username']}</p><ul>{''.join(items)}</ul>"

    return app


app = create_app()
