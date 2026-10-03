import os
from io import BytesIO
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app
from tests.conftest import login, register


def test_load_settings_uses_small_defaults(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.delenv("UPLOAD_DIR", raising=False)
    monkeypatch.delenv("MAX_UPLOAD_MB", raising=False)
    monkeypatch.delenv("CLEANUP_TOKEN", raising=False)
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("ALLOW_REGISTRATION", raising=False)

    settings = load_settings()

    assert settings.secret_key == "dev-secret-change-me"
    assert settings.database_path == Path("data/app.db")
    assert settings.upload_dir == Path("uploads")
    assert settings.max_upload_mb == 200
    assert settings.max_upload_bytes == 200 * 1024 * 1024
    assert settings.cleanup_token == "dev-cleanup-token"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.allow_registration is True


def test_load_settings_reads_environment(monkeypatch, tmp_path):
    db_path = tmp_path / "messages.db"
    upload_dir = tmp_path / "files"
    monkeypatch.setenv("SECRET_KEY", "secret")
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))
    monkeypatch.setenv("MAX_UPLOAD_MB", "7")
    monkeypatch.setenv("CLEANUP_TOKEN", "cleanup")
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("ALLOW_REGISTRATION", "false")

    settings = load_settings()

    assert settings.secret_key == "secret"
    assert settings.database_path == db_path
    assert settings.upload_dir == upload_dir
    assert settings.max_upload_mb == 200
    assert settings.max_upload_bytes == 200 * 1024 * 1024
    assert settings.cleanup_token == "cleanup"
    assert settings.host == "0.0.0.0"
    assert settings.port == 9000
    assert settings.allow_registration is False


@pytest.mark.parametrize("configured_mb", ["20", "200", "500"])
def test_upload_limit_is_fixed_at_200_mb(monkeypatch, configured_mb):
    monkeypatch.setenv("MAX_UPLOAD_MB", configured_mb)

    settings = load_settings()

    assert settings.max_upload_mb == 200
    assert settings.max_upload_bytes == 200 * 1024 * 1024


def test_old_dotenv_limit_does_not_block_uploads_above_20_mb(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("MAX_UPLOAD_MB=20\n", encoding="utf-8")
    monkeypatch.delenv("MAX_UPLOAD_MB", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("ALLOW_REGISTRATION", "true")
    monkeypatch.setattr("app.config.load_dotenv", lambda: load_dotenv(tmp_path / ".env"))
    settings = load_settings()
    assert os.environ["MAX_UPLOAD_MB"] == "20"

    with TestClient(create_app(settings)) as client:
        register(client)
        login(client)
        page = client.get("/")
        assert "单个文件最大 200 MB" in page.text
        assert 'data-max-upload-bytes="209715200"' in page.text

        contents = b"x" * (21 * 1024 * 1024)
        response = client.post(
            "/messages",
            files={"upload": ("above-old-limit.bin", BytesIO(contents), "application/octet-stream")},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert next(settings.upload_dir.iterdir()).read_bytes() == contents


def test_deploy_env_template_includes_registration_switch():
    deploy_script = Path("deploy_ubuntu.sh").read_text(encoding="utf-8")

    assert "ALLOW_REGISTRATION=true" in deploy_script
