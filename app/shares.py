import secrets

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .auth import require_user
from .db import connect
from .messages import _message_for_user, cleanup_expired


router = APIRouter()
SHARE_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
PREVIEW_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/avif", "image/bmp"}
DOWNLOAD_ACCESS_SECONDS = 3600


def access_signer(request: Request):
    return URLSafeTimedSerializer(request.app.state.settings.secret_key, salt="share-download-access")


@router.post("/messages/{message_id}/share")
async def create_share(request: Request, message_id: int, max_views: str = Form("")):
    user = require_user(request)
    settings = request.app.state.settings
    if _message_for_user(settings, message_id, user["id"]) is None:
        raise HTTPException(status_code=404, detail="Message not found")
    limit = None
    if max_views.strip():
        try:
            limit = int(max_views)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid view limit") from exc
        if not 1 <= limit <= 2_147_483_647:
            raise HTTPException(status_code=400, detail="Invalid view limit")
    update_limit = "max_views" in await request.form()
    with connect(settings.database_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO message_shares (message_id, token, max_views) VALUES (?, ?, ?)",
            (message_id, secrets.token_urlsafe(32), limit),
        )
        if update_limit:
            conn.execute("UPDATE message_shares SET max_views = ? WHERE message_id = ?", (limit, message_id))
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
            "SELECT messages.*, message_shares.max_views FROM messages "
            "JOIN message_shares ON message_shares.message_id = messages.id "
            "WHERE message_shares.token = ?",
            (token,),
        ).fetchone()
    if message is None:
        raise HTTPException(status_code=404, detail="Share not found or expired", headers=SHARE_HEADERS)
    return message


@router.get("/s/{token}", name="share_page")
def share_page(request: Request, token: str):
    message = shared_message(request, token)
    # SQLite serializes writes; only one request can take the final available view.
    with connect(request.app.state.settings.database_path) as conn:
        opened = conn.execute(
            "UPDATE message_shares SET view_count = view_count + 1 "
            "WHERE token = ? AND (max_views IS NULL OR view_count < max_views)",
            (token,),
        ).rowcount
    if not opened:
        return request.app.state.templates.TemplateResponse(
            request, "share_unavailable.html", status_code=410, headers=SHARE_HEADERS,
        )
    access = access_signer(request).dumps(token) if message["max_views"] is not None else None
    download_url = f"/s/{token}/download" + (f"?access={access}" if access else "")
    return request.app.state.templates.TemplateResponse(
        request,
        "share.html",
        {
            "message": message, "token": token,
            "can_preview": message["mime_type"] in PREVIEW_TYPES,
            "download_url": download_url,
            "preview_url": download_url + ("&" if access else "?") + "preview=true",
        },
        headers=SHARE_HEADERS,
    )


@router.get("/s/{token}/download")
def download_share(request: Request, token: str, preview: bool = False, access: str = ""):
    message = shared_message(request, token)
    if message["max_views"] is not None:
        try:
            valid_access = access_signer(request).loads(access, max_age=DOWNLOAD_ACCESS_SECONDS)
        except BadSignature as exc:
            raise HTTPException(status_code=403, detail="Open the share page first", headers=SHARE_HEADERS) from exc
        if valid_access != token:
            raise HTTPException(status_code=403, detail="Invalid download access", headers=SHARE_HEADERS)
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
