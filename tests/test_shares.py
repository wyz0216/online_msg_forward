from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from html import unescape
import re
from threading import Barrier
import time

import pytest
from itsdangerous import TimestampSigner, URLSafeTimedSerializer

from app.db import connect, init_db
from tests.conftest import login, register


def create_message(client, settings, kind="text", content="shared text", mime_type=None):
    register(client)
    login(client)
    if kind == "text":
        client.post("/messages", data={"content": content})
    else:
        client.post("/messages", files={"upload": ("example.bin", b"shared file", mime_type)})
    with connect(settings.database_path) as conn:
        return conn.execute("SELECT id FROM messages ORDER BY id DESC LIMIT 1").fetchone()["id"]


def share(client, message_id):
    return client.post(f"/messages/{message_id}/share", headers={"Accept": "application/json"})


@pytest.mark.parametrize("kind,mime_type", [("text", None), ("file", "application/octet-stream"), ("image", "image/png")])
def test_shared_message_is_accessible_without_login(client, settings, kind, mime_type):
    message_id = create_message(client, settings, kind, mime_type=mime_type)
    response = share(client, message_id)
    assert response.status_code == 200
    path = response.json()["share_path"]
    assert share(client, message_id).json()["share_path"] == path
    client.post("/messages", data={"content": "another private message"})
    page = client.get("/")
    assert f'http://testserver{path}' in page.text
    assert "取消分享" in page.text
    client.post("/logout")

    page = client.get(path)
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store"
    assert "another private message" not in page.text
    assert "alice" not in page.text
    if kind == "text":
        assert "shared text" in page.text
        assert client.get(path + "/download").status_code == 404
    else:
        download = client.get(path + "/download")
        assert download.content == b"shared file"
        assert download.headers["content-disposition"].startswith("attachment;")
        if kind == "image":
            assert f'src="{path}/download?preview=true"' in page.text
            preview = client.get(path + "/download?preview=true")
            assert preview.headers["content-disposition"].startswith("inline;")
        assert client.get(f"/messages/{message_id}/download", follow_redirects=False).status_code == 303


def test_share_creation_and_revocation_require_owner(client, settings):
    message_id = create_message(client, settings)
    path = share(client, message_id).json()["share_path"]
    client.post("/logout")
    for suffix in ("share", "share/revoke"):
        response = client.post(f"/messages/{message_id}/{suffix}", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"
    register(client, username="bob")
    login(client, username="bob")
    for suffix in ("share", "share/revoke"):
        assert client.post(f"/messages/{message_id}/{suffix}").status_code == 404
    assert client.get(path).status_code == 200


def test_revocation_invalidates_link_and_resharing_generates_new_link(client, settings):
    message_id = create_message(client, settings)
    old_path = share(client, message_id).json()["share_path"]
    response = client.post(f"/messages/{message_id}/share/revoke", headers={"Accept": "application/json"})
    assert response.json() == {"shared": False}
    assert client.get(old_path).status_code == 404
    assert client.get(old_path + "/download").status_code == 404
    new_path = share(client, message_id).json()["share_path"]
    assert old_path != new_path
    assert client.get(new_path).status_code == 200


@pytest.mark.parametrize("invalidate", ["delete", "expire"])
def test_deleted_or_expired_message_invalidates_share(client, settings, invalidate):
    message_id = create_message(client, settings, "file", mime_type="text/plain")
    path = share(client, message_id).json()["share_path"]
    if invalidate == "delete":
        client.post(f"/messages/{message_id}/delete")
    else:
        with connect(settings.database_path) as conn:
            conn.execute("UPDATE messages SET expires_at = ? WHERE id = ?", (
                (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), message_id,
            ))
    client.post("/logout")
    assert client.get(path).status_code == 404
    assert client.get(path + "/download").status_code == 404
    with connect(settings.database_path) as conn:
        assert conn.execute("SELECT count(*) FROM message_shares").fetchone()[0] == 0
    assert list(settings.upload_dir.iterdir()) == []


def test_unknown_share_is_not_accessible(client):
    assert client.get("/s/unknown").status_code == 404
    assert client.get("/s/unknown/download").status_code == 404


def test_shared_text_is_escaped(client, settings):
    message_id = create_message(client, settings, content="<script>alert(1)</script>")
    path = share(client, message_id).json()["share_path"]
    client.post("/logout")
    page = client.get(path)
    assert "<script>alert(1)</script>" not in page.text
    assert "&lt;script&gt;" in page.text


def test_svg_share_download_cannot_render_inline(client, settings):
    message_id = create_message(client, settings, "image", mime_type="image/svg+xml")
    path = share(client, message_id).json()["share_path"]
    client.post("/logout")
    assert '<img ' not in client.get(path).text
    response = client.get(path + "/download?preview=true")
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_sharing_works_without_javascript(client, settings):
    message_id = create_message(client, settings)
    response = client.post(f"/messages/{message_id}/share")
    assert response.status_code == 200
    assert "复制链接" in response.text
    response = client.post(f"/messages/{message_id}/share/revoke")
    assert "复制链接" not in response.text


def test_database_upgrade_preserves_existing_messages(settings):
    with connect(settings.database_path) as conn:
        conn.executescript("""
            CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT);
            CREATE TABLE messages (id INTEGER PRIMARY KEY, user_id INTEGER, kind TEXT, content TEXT, created_at TEXT);
            INSERT INTO users VALUES (1, 'alice', 'hash');
            INSERT INTO messages VALUES (1, 1, 'text', 'keep me', CURRENT_TIMESTAMP);
        """)
    init_db(settings.database_path)
    init_db(settings.database_path)
    with connect(settings.database_path) as conn:
        assert conn.execute("SELECT content FROM messages").fetchone()[0] == "keep me"
        conn.execute("INSERT INTO message_shares (message_id, token) VALUES (1, 'token')")


def limited_share(client, message_id, limit):
    return client.post(
        f"/messages/{message_id}/share", data={"max_views": limit}, headers={"Accept": "application/json"},
    )


def download_link(page):
    return unescape(re.search(r'<a href="([^"]+)" role="button"', page.text)[1])


def view_count(settings, message_id):
    with connect(settings.database_path) as conn:
        return conn.execute("SELECT view_count FROM message_shares WHERE message_id = ?", (message_id,)).fetchone()[0]


def test_share_blocks_further_opens_at_limit(client, settings):
    message_id = create_message(client, settings)
    path = limited_share(client, message_id, "2").json()["share_path"]
    assert share(client, message_id).json()["share_path"] == path
    client.post("/logout")
    assert client.get(path).status_code == 200
    assert client.get(path).status_code == 200
    blocked = client.get(path)
    assert blocked.status_code == 410
    assert "分享次数已用完" in blocked.text
    assert "shared text" not in blocked.text
    assert blocked.headers["cache-control"] == "no-store"
    assert view_count(settings, message_id) == 2
    login(client)
    page = client.get("/")
    assert "已打开 2 次" in page.text
    assert "剩余 0 次" in page.text


@pytest.mark.parametrize("mime_type", ["text/plain", "image/png"])
def test_final_allowed_view_can_download_without_consuming_more_views(client, settings, mime_type):
    message_id = create_message(client, settings, "file", mime_type=mime_type)
    path = limited_share(client, message_id, "1").json()["share_path"]
    client.post("/logout")
    assert client.get(path + "/download").status_code == 403
    assert view_count(settings, message_id) == 0
    page = client.get(path)
    assert page.status_code == 200
    download = download_link(page)
    assert "access=" in download
    assert client.get(path).status_code == 410
    for _ in range(2):
        response = client.get(download)
        assert response.status_code == 200
        assert response.content == b"shared file"
    if mime_type == "image/png":
        preview_url = unescape(re.search(r'<img src="([^"]+)"', page.text)[1])
        assert client.get(preview_url).status_code == 200
    assert view_count(settings, message_id) == 1
    login(client)
    client.post(f"/messages/{message_id}/share/revoke")
    assert client.get(download).status_code == 404


def test_limit_edits_keep_link_and_used_count(client, settings):
    message_id = create_message(client, settings)
    path = limited_share(client, message_id, "1").json()["share_path"]
    assert client.get(path).status_code == 200
    assert client.get(path).status_code == 410
    assert limited_share(client, message_id, "3").json()["share_path"] == path
    assert client.get(path).status_code == 200
    assert client.get(path).status_code == 200
    assert client.get(path).status_code == 410
    assert view_count(settings, message_id) == 3
    # Lowering the limit cannot reset the used count or reveal a negative remainder.
    limited_share(client, message_id, "1")
    assert "剩余 0 次" in client.get("/").text
    assert client.get(path).status_code == 410
    assert limited_share(client, message_id, "").json()["share_path"] == path
    assert client.get(path).status_code == 200
    assert view_count(settings, message_id) == 4


def test_resharing_starts_new_view_budget(client, settings):
    message_id = create_message(client, settings)
    old_path = limited_share(client, message_id, "1").json()["share_path"]
    assert client.get(old_path).status_code == 200
    client.post(f"/messages/{message_id}/share/revoke")
    new_path = limited_share(client, message_id, "1").json()["share_path"]
    assert new_path != old_path
    assert view_count(settings, message_id) == 0
    assert client.get(new_path).status_code == 200
    assert client.get(new_path).status_code == 410
    assert client.get(old_path).status_code == 404


@pytest.mark.parametrize("limit", ["0", "-1", "1.5", "abc", "2147483648"])
def test_invalid_limits_do_not_create_or_change_share(client, settings, limit):
    message_id = create_message(client, settings)
    assert limited_share(client, message_id, limit).status_code == 400
    with connect(settings.database_path) as conn:
        assert conn.execute("SELECT count(*) FROM message_shares").fetchone()[0] == 0
    limited_share(client, message_id, "2")
    assert limited_share(client, message_id, limit).status_code == 400
    with connect(settings.database_path) as conn:
        assert conn.execute("SELECT max_views FROM message_shares").fetchone()[0] == 2


def test_another_user_cannot_edit_limit(client, settings):
    message_id = create_message(client, settings)
    limited_share(client, message_id, "1")
    client.post("/logout")
    register(client, username="bob")
    login(client, username="bob")
    assert limited_share(client, message_id, "").status_code == 404
    with connect(settings.database_path) as conn:
        assert conn.execute("SELECT max_views FROM message_shares").fetchone()[0] == 1


def test_concurrent_opens_cannot_exceed_limit(client, settings):
    message_id = create_message(client, settings)
    path = limited_share(client, message_id, "3").json()["share_path"]
    client.post("/logout")
    barrier = Barrier(8)

    def open_share(_):
        barrier.wait(timeout=10)
        return client.get(path).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(open_share, range(8)))
    assert statuses.count(200) == 3
    assert statuses.count(410) == 5
    assert view_count(settings, message_id) == 3


def test_limited_download_rejects_forged_or_expired_access(client, settings, monkeypatch):
    message_id = create_message(client, settings, "file", mime_type="text/plain")
    path = limited_share(client, message_id, "1").json()["share_path"]
    token = path.rsplit("/", 1)[1]
    signer = URLSafeTimedSerializer(settings.secret_key, salt="share-download-access")
    wrong_share_access = signer.dumps("another-share")
    assert client.get(path + "/download?access=" + wrong_share_access).status_code == 403
    assert client.get(path + "/download?access=forged").status_code == 403
    with monkeypatch.context() as patch:
        patch.setattr(TimestampSigner, "get_timestamp", lambda self: int(time.time()) - 3601)
        expired_access = signer.dumps(token)
    assert client.get(path + "/download?access=" + expired_access).status_code == 403
    assert view_count(settings, message_id) == 0


def test_count_limit_form_works_without_javascript(client, settings):
    message_id = create_message(client, settings)
    response = client.post(f"/messages/{message_id}/share", data={"max_views": "3"})
    assert response.status_code == 200
    assert "上限 3 次" in response.text
    assert "剩余 3 次" in response.text
    assert "保存限制" in response.text
    assert 'name="max_views"' in response.text


def test_existing_shares_upgrade_without_losing_links(client, settings):
    message_id = create_message(client, settings)
    with connect(settings.database_path) as conn:
        conn.executescript("""
            DROP TABLE message_shares;
            CREATE TABLE message_shares (
                message_id INTEGER PRIMARY KEY, token TEXT NOT NULL UNIQUE,
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
            );
        """)
        conn.execute("INSERT INTO message_shares VALUES (?, 'existing-token')", (message_id,))
    init_db(settings.database_path)
    init_db(settings.database_path)
    with connect(settings.database_path) as conn:
        row = conn.execute("SELECT * FROM message_shares").fetchone()
        assert row["token"] == "existing-token"
        assert row["max_views"] is None
        assert row["view_count"] == 0
    assert client.get("/s/existing-token").status_code == 200
    assert client.get("/s/existing-token").status_code == 200
