from datetime import datetime, timedelta, timezone
from io import BytesIO

from app.db import connect
from tests.conftest import login, register


def sign_in(client, username="alice"):
    register(client, username=username)
    login(client, username=username)


def message_ids(settings):
    with connect(settings.database_path) as conn:
        return [row["id"] for row in conn.execute("SELECT id FROM messages ORDER BY id").fetchall()]


def test_text_message_is_created_and_listed(client):
    sign_in(client)

    response = client.post(
        "/messages",
        data={"content": "hello from web", "expires_minutes": ""},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    page = client.get("/")
    assert "hello from web" in page.text


def test_message_page_has_refresh_button(client):
    sign_in(client)

    response = client.get("/")

    assert response.status_code == 200
    assert 'class="page-shell"' in response.text
    assert 'class="panel composer-panel"' in response.text
    assert 'class="section-heading"' in response.text
    assert 'data-refresh-button' in response.text
    assert "刷新" in response.text


def test_text_message_has_copy_button(client):
    sign_in(client)
    client.post("/messages", data={"content": "copy me", "expires_minutes": ""})

    response = client.get("/")

    assert response.status_code == 200
    assert 'data-copy-text="copy me"' in response.text
    assert "复制" in response.text


def test_file_message_has_no_copy_button(client):
    sign_in(client)
    client.post(
        "/messages",
        data={"content": "", "expires_minutes": ""},
        files={"upload": ("a.txt", BytesIO(b"private"), "text/plain")},
    )

    response = client.get("/")

    assert response.status_code == 200
    assert 'data-copy-text=' not in response.text


def test_users_only_see_their_own_messages(client):
    sign_in(client, "alice")
    client.post("/messages", data={"content": "alice secret", "expires_minutes": ""})
    client.post("/logout")
    sign_in(client, "bob")

    response = client.get("/")

    assert "alice secret" not in response.text


def test_user_cannot_download_another_users_file(client, settings):
    sign_in(client, "alice")
    client.post(
        "/messages",
        data={"content": "", "expires_minutes": ""},
        files={"upload": ("a.txt", BytesIO(b"private"), "text/plain")},
    )
    file_id = message_ids(settings)[0]
    client.post("/logout")
    sign_in(client, "bob")

    response = client.get(f"/messages/{file_id}/download")

    assert response.status_code == 404


def test_user_cannot_delete_another_users_message(client, settings):
    sign_in(client, "alice")
    client.post("/messages", data={"content": "keep", "expires_minutes": ""})
    message_id = message_ids(settings)[0]
    client.post("/logout")
    sign_in(client, "bob")

    response = client.post(f"/messages/{message_id}/delete")

    assert response.status_code == 404
    assert message_ids(settings) == [message_id]


def test_oversized_file_is_rejected(client):
    sign_in(client)
    too_large = BytesIO(b"x" * (20 * 1024 * 1024 + 1))

    response = client.post(
        "/messages",
        data={"content": "", "expires_minutes": ""},
        files={"upload": ("big.bin", too_large, "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "File is too large" in response.text


def test_image_message_is_previewed_inline(client, settings):
    sign_in(client)

    client.post(
        "/messages",
        data={"content": "", "expires_minutes": ""},
        files={"upload": ("photo.png", BytesIO(b"fake-png"), "image/png")},
    )
    image_id = message_ids(settings)[0]

    response = client.get("/")

    assert response.status_code == 200
    assert f'<img src="/messages/{image_id}/download"' in response.text
    assert 'alt="photo.png"' in response.text


def test_image_preview_opens_dialog_instead_of_download_link(client, settings):
    sign_in(client)

    client.post(
        "/messages",
        data={"content": "", "expires_minutes": ""},
        files={"upload": ("photo.png", BytesIO(b"fake-png"), "image/png")},
    )
    image_id = message_ids(settings)[0]

    response = client.get("/")

    assert response.status_code == 200
    assert f'data-preview-target="image-preview-{image_id}"' in response.text
    assert f'<dialog id="image-preview-{image_id}"' in response.text
    assert f'<a href="/messages/{image_id}/download" class="image-link">' not in response.text


def test_download_link_uses_button_role(client, settings):
    sign_in(client)

    client.post(
        "/messages",
        data={"content": "", "expires_minutes": ""},
        files={"upload": ("a.txt", BytesIO(b"private"), "text/plain")},
    )
    file_id = message_ids(settings)[0]

    response = client.get("/")

    assert response.status_code == 200
    assert f'href="/messages/{file_id}/download" role="button"' in response.text


def test_expiration_minutes_must_be_allowed(client):
    sign_in(client)

    response = client.post(
        "/messages",
        data={"content": "bad expiry", "expires_minutes": "2"},
    )

    assert response.status_code == 400
    assert "Invalid expiration" in response.text


def test_cleanup_deletes_expired_records_and_files(client, settings):
    sign_in(client)
    stored = settings.upload_dir / "old.txt"
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(b"old")
    expired_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with connect(settings.database_path) as conn:
        conn.execute(
            """
            INSERT INTO messages
                (user_id, kind, original_filename, stored_filename, size_bytes, expires_at)
            VALUES (1, 'file', 'old.txt', 'old.txt', 3, ?)
            """,
            (expired_at,),
        )

    response = client.post(
        "/cleanup",
        headers={"X-Cleanup-Token": settings.cleanup_token},
    )

    assert response.status_code == 200
    assert message_ids(settings) == []
    assert not stored.exists()
