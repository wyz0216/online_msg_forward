import hashlib
import secrets

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .auth import hash_password, require_user, verify_password
from .db import connect
from .messages import _message_for_user, cleanup_expired


router = APIRouter()
SHARE_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
PREVIEW_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/avif", "image/bmp"}
DOWNLOAD_ACCESS_SECONDS = 3600
SHARE_PASSWORD_MAX_LENGTH = 128


def access_signer(request: Request):
    return URLSafeTimedSerializer(request.app.state.settings.secret_key, salt="share-download-access")


def password_signer(request: Request):
    return URLSafeTimedSerializer(request.app.state.settings.secret_key, salt="share-password-access")


def password_access_data(token: str, password_hash: str):
    return [token, hashlib.sha256(password_hash.encode()).hexdigest()]


def has_password_access(request: Request, token: str, message) -> bool:
    if not message["password_hash"]:
        return True
    try:
        data = password_signer(request).loads(
            request.cookies.get("share_access", ""), max_age=DOWNLOAD_ACCESS_SECONDS,
        )
    except BadSignature:
        return False
    return data == password_access_data(token, message["password_hash"])


def share_password_page(request: Request, token: str, error: str = "", status_code: int = 200):
    return request.app.state.templates.TemplateResponse(
        request, "share_password.html", {"token": token, "password_error": error},
        status_code=status_code, headers=SHARE_HEADERS,
    )


def share_unavailable(
    request: Request,
    status_code: int = 404,
    title: str = "分享已失效",
    description: str = "链接不存在，或资源已删除、过期、取消分享。请联系分享者确认并重新分享。",
):
    return request.app.state.templates.TemplateResponse(
        request, "share_unavailable.html",
        {"title": title, "description": description},
        status_code=status_code, headers=SHARE_HEADERS,
    )


@router.post("/messages/{message_id}/share")
async def create_share(
    request: Request, message_id: int, max_views: str = Form(""),
    password: str = Form(""), clear_password: bool = Form(False),
):
    user = require_user(request)
    settings = request.app.state.settings
    if _message_for_user(settings, message_id, user["id"]) is None:
        raise HTTPException(status_code=404, detail="Message not found")
    if len(password) > SHARE_PASSWORD_MAX_LENGTH or (password and clear_password):
        raise HTTPException(status_code=400, detail="Invalid share password settings")
    password_hash = hash_password(password) if password else None
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
            "INSERT OR IGNORE INTO message_shares (message_id, token, max_views, password_hash) VALUES (?, ?, ?, ?)",
            (message_id, secrets.token_urlsafe(32), limit, password_hash),
        )
        if update_limit:
            conn.execute("UPDATE message_shares SET max_views = ? WHERE message_id = ?", (limit, message_id))
        if password or clear_password:
            conn.execute("UPDATE message_shares SET password_hash = ? WHERE message_id = ?", (password_hash, message_id))
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
            "SELECT messages.*, message_shares.max_views, message_shares.password_hash FROM messages "
            "JOIN message_shares ON message_shares.message_id = messages.id "
            "WHERE message_shares.token = ?",
            (token,),
        ).fetchone()
    if message is not None and message["kind"] != "text":
        if not message["stored_filename"] or not (settings.upload_dir / message["stored_filename"]).is_file():
            return None
    return message


@router.get("/s/{token}", name="share_page")
def share_page(request: Request, token: str):
    message = shared_message(request, token)
    if message is None:
        return share_unavailable(request)
    if not has_password_access(request, token, message):
        return share_password_page(request, token)
    # SQLite serializes writes; only one request can take the final available view.
    with connect(request.app.state.settings.database_path) as conn:
        opened = conn.execute(
            "UPDATE message_shares SET view_count = view_count + 1 "
            "WHERE token = ? AND (max_views IS NULL OR view_count < max_views)",
            (token,),
        ).rowcount
    if not opened:
        return share_unavailable(
            request, status_code=410, title="分享次数已用完",
            description="该链接已达到最大打开次数，请联系分享者调整限制。",
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


@router.post("/s/{token}/unlock")
def unlock_share(request: Request, token: str, password: str = Form("")):
    message = shared_message(request, token)
    if message is None:
        return share_unavailable(request)
    response = RedirectResponse(f"/s/{token}", status_code=303, headers=SHARE_HEADERS)
    if not message["password_hash"]:
        return response
    if len(password) > SHARE_PASSWORD_MAX_LENGTH or not verify_password(password, message["password_hash"]):
        return share_password_page(request, token, error="密码错误，请重新输入。", status_code=403)
    response.set_cookie(
        "share_access", password_signer(request).dumps(password_access_data(token, message["password_hash"])),
        max_age=DOWNLOAD_ACCESS_SECONDS, httponly=True, secure=request.url.scheme == "https",
        samesite="lax", path=f"/s/{token}",
    )
    return response


@router.get("/s/{token}/download")
def download_share(request: Request, token: str, preview: bool = False, access: str = ""):
    message = shared_message(request, token)
    if message is None:
        return share_unavailable(request)
    if not has_password_access(request, token, message):
        return share_password_page(request, token, status_code=403)
    if message["max_views"] is not None:
        try:
            valid_access = access_signer(request).loads(access, max_age=DOWNLOAD_ACCESS_SECONDS)
        except BadSignature as exc:
            raise HTTPException(status_code=403, detail="Open the share page first", headers=SHARE_HEADERS) from exc
        if valid_access != token:
            raise HTTPException(status_code=403, detail="Invalid download access", headers=SHARE_HEADERS)
    if not message["stored_filename"]:
        return share_unavailable(request, title="文件不可用", description="该分享没有可下载的文件，请联系分享者确认。")
    path = request.app.state.settings.upload_dir / message["stored_filename"]
    if not path.is_file():
        return share_unavailable(request)
    return FileResponse(
        path,
        media_type=message["mime_type"] or "application/octet-stream",
        filename=message["original_filename"],
        content_disposition_type="inline" if preview and message["mime_type"] in PREVIEW_TYPES else "attachment",
        headers={**SHARE_HEADERS, "X-Content-Type-Options": "nosniff"},
    )
