import hashlib
import secrets
import sqlite3

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from .db import connect


router = APIRouter()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt, digest = password_hash.split("$", 1)
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return secrets.compare_digest(check.hex(), digest)


def get_user_by_id(request: Request, user_id: int) -> sqlite3.Row | None:
    with connect(request.app.state.settings.database_path) as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def current_user(request: Request) -> sqlite3.Row | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return get_user_by_id(request, int(user_id))


def require_user(request: Request) -> sqlite3.Row:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


@router.get("/register")
def register_page(request: Request):
    return request.app.state.templates.TemplateResponse(request, "register.html")


@router.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
) -> RedirectResponse:
    username = username.strip()
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")
    try:
        with connect(request.app.state.settings.database_path) as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, hash_password(password)),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=400, detail="Username already exists") from exc
    return RedirectResponse("/login", status_code=303)


@router.get("/login")
def login_page(request: Request):
    return request.app.state.templates.TemplateResponse(request, "login.html")


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
) -> RedirectResponse:
    with connect(request.app.state.settings.database_path) as conn:
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
    if user is None or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Invalid username or password")
    request.session["user_id"] = user["id"]
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
