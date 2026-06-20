from pathlib import Path

from app.config import load_settings


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
    assert settings.max_upload_mb == 20
    assert settings.max_upload_bytes == 20 * 1024 * 1024
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
    assert settings.max_upload_mb == 7
    assert settings.max_upload_bytes == 7 * 1024 * 1024
    assert settings.cleanup_token == "cleanup"
    assert settings.host == "0.0.0.0"
    assert settings.port == 9000
    assert settings.allow_registration is False


def test_deploy_env_template_includes_registration_switch():
    deploy_script = Path("deploy_ubuntu.sh").read_text(encoding="utf-8")

    assert "ALLOW_REGISTRATION=true" in deploy_script
