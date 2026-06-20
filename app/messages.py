from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from .auth import require_user
from .config import Settings
from .db import connect


ALLOWED_EXPIRATION_MINUTES = {1, 5, 10, 30, 60}
router = APIRouter()


def parse_expiration(value: str | None) -> str | None:
    if not value:
        return None
    try:
        minutes = int(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid expiration") from exc
    if minutes not in ALLOWED_EXPIRATION_MINUTES:
        raise HTTPException(status_code=400, detail="Invalid expiration")
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def cleanup_expired(settings: Settings) -> int:
    now = datetime.now(timezone.utc).isoformat()
    deleted = 0
    with connect(settings.database_path) as conn:
        rows = conn.execute(
            "SELECT id, stored_filename FROM messages WHERE expires_at IS NOT NULL AND expires_at <= ?",
            (now,),
        ).fetchall()
        for row in rows:
            if row["stored_filename"]:
                path = settings.upload_dir / row["stored_filename"]
                if path.exists():
                    path.unlink()
            conn.execute("DELETE FROM messages WHERE id = ?", (row["id"],))
            deleted += 1
    return deleted


def list_user_messages(settings: Settings, user_id: int):
    cleanup_expired(settings)
    with connect(settings.database_path) as conn:
        return conn.execute(
            """
            SELECT *
            FROM messages
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()


def _safe_stored_name(filename: str) -> str:
    original = Path(filename).name
    suffix = Path(original).suffix
    return f"{secrets.token_hex(16)}{suffix}"


def _message_for_user(settings: Settings, message_id: int, user_id: int):
    cleanup_expired(settings)
    with connect(settings.database_path) as conn:
        return conn.execute(
            "SELECT * FROM messages WHERE id = ? AND user_id = ?",
            (message_id, user_id),
        ).fetchone()


@router.post("/messages")
async def create_message(
    request: Request,
    content: str = Form(""),
    expires_minutes: str = Form(""),
    upload: UploadFile | None = File(None),
) -> RedirectResponse:
    user = require_user(request)
    settings = request.app.state.settings
    cleanup_expired(settings)
    expires_at = parse_expiration(expires_minutes)
    text = content.strip()
    created = 0

    with connect(settings.database_path) as conn:
        if text:
            conn.execute(
                """
                INSERT INTO messages (user_id, kind, content, expires_at)
                VALUES (?, 'text', ?, ?)
                """,
                (user["id"], text, expires_at),
            )
            created += 1

        if upload is not None and upload.filename:
            data = await upload.read()
            if len(data) > settings.max_upload_bytes:
                raise HTTPException(status_code=400, detail="File is too large")
            settings.upload_dir.mkdir(parents=True, exist_ok=True)
            stored_filename = _safe_stored_name(upload.filename)
            (settings.upload_dir / stored_filename).write_bytes(data)
            kind = "image" if (upload.content_type or "").startswith("image/") else "file"
            conn.execute(
                """
                INSERT INTO messages (
                    user_id, kind, original_filename, stored_filename, mime_type, size_bytes, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"],
                    kind,
                    Path(upload.filename).name,
                    stored_filename,
                    upload.content_type,
                    len(data),
                    expires_at,
                ),
            )
            created += 1

    if created == 0:
        raise HTTPException(status_code=400, detail="Message content or file is required")
    return RedirectResponse("/", status_code=303)


@router.get("/messages/{message_id}/download")
def download_message(request: Request, message_id: int) -> FileResponse:
    user = require_user(request)
    settings = request.app.state.settings
    message = _message_for_user(settings, message_id, user["id"])
    if message is None or not message["stored_filename"]:
        raise HTTPException(status_code=404, detail="Message not found")
    path = settings.upload_dir / message["stored_filename"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path,
        media_type=message["mime_type"] or "application/octet-stream",
        filename=message["original_filename"],
    )


@router.post("/messages/{message_id}/delete")
def delete_message(request: Request, message_id: int) -> RedirectResponse:
    user = require_user(request)
    settings = request.app.state.settings
    message = _message_for_user(settings, message_id, user["id"])
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    if message["stored_filename"]:
        path = settings.upload_dir / message["stored_filename"]
        if path.exists():
            path.unlink()
    with connect(settings.database_path) as conn:
        conn.execute("DELETE FROM messages WHERE id = ? AND user_id = ?", (message_id, user["id"]))
    return RedirectResponse("/", status_code=303)


@router.post("/cleanup")
def cleanup(request: Request) -> JSONResponse:
    token = request.headers.get("X-Cleanup-Token")
    settings = request.app.state.settings
    if token != settings.cleanup_token:
        raise HTTPException(status_code=403, detail="Invalid cleanup token")
    deleted = cleanup_expired(settings)
    return JSONResponse({"deleted": deleted})
