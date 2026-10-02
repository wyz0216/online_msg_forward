import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from .auth import require_user
from .db import connect
from .messages import _message_for_user, cleanup_expired


router = APIRouter()
SHARE_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
PREVIEW_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/avif", "image/bmp"}


@router.post("/messages/{message_id}/share")
def create_share(request: Request, message_id: int):
    user = require_user(request)
    settings = request.app.state.settings
    if _message_for_user(settings, message_id, user["id"]) is None:
        raise HTTPException(status_code=404, detail="Message not found")
    with connect(settings.database_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO message_shares (message_id, token) VALUES (?, ?)",
            (message_id, secrets.token_urlsafe(32)),
        )
        share = conn.execute("SELECT token FROM message_shares WHERE message_id = ?", (message_id,)).fetchone()
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"share_path": f"/s/{share['token']}"}, headers=SHARE_HEADERS)
    return RedirectResponse("/", status_code=303)


@router.post("/messages/{message_id}/share/revoke")
def revoke_share(request: Request, message_id: int):
    user = require_user(request)
    settings = request.app.state.settings
    if _message_for_user(settings, message_id, user["id"]) is None:
        raise HTTPException(status_code=404, detail="Message not found")
    with connect(settings.database_path) as conn:
        conn.execute("DELETE FROM message_shares WHERE message_id = ?", (message_id,))
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"shared": False}, headers=SHARE_HEADERS)
    return RedirectResponse("/", status_code=303)


def shared_message(request: Request, token: str):
    settings = request.app.state.settings
    cleanup_expired(settings)
    with connect(settings.database_path) as conn:
        message = conn.execute(
            "SELECT messages.* FROM messages JOIN message_shares ON message_shares.message_id = messages.id "
            "WHERE message_shares.token = ?",
            (token,),
        ).fetchone()
    if message is None:
        raise HTTPException(status_code=404, detail="Share not found or expired", headers=SHARE_HEADERS)
    return message


@router.get("/s/{token}", name="share_page")
def share_page(request: Request, token: str):
    message = shared_message(request, token)
    return request.app.state.templates.TemplateResponse(
        request,
        "share.html",
        {"message": message, "token": token, "can_preview": message["mime_type"] in PREVIEW_TYPES},
        headers=SHARE_HEADERS,
    )


@router.get("/s/{token}/download")
def download_share(request: Request, token: str, preview: bool = False):
    message = shared_message(request, token)
    if not message["stored_filename"]:
        raise HTTPException(status_code=404, detail="File not found", headers=SHARE_HEADERS)
    path = request.app.state.settings.upload_dir / message["stored_filename"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found", headers=SHARE_HEADERS)
    return FileResponse(
        path,
        media_type=message["mime_type"] or "application/octet-stream",
        filename=message["original_filename"],
        content_disposition_type="inline" if preview and message["mime_type"] in PREVIEW_TYPES else "attachment",
        headers={**SHARE_HEADERS, "X-Content-Type-Options": "nosniff"},
    )
