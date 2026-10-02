from datetime import datetime, timedelta, timezone

import pytest

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
        conn.execute("INSERT INTO message_shares VALUES (1, 'token')")
