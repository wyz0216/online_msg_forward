import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(
        secret_key="test-secret",
        database_path=tmp_path / "test.db",
        upload_dir=tmp_path / "uploads",
        max_upload_mb=20,
        cleanup_token="test-cleanup-token",
        host="127.0.0.1",
        port=8000,
    )


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def register(client, username="alice", password="password123"):
    return client.post(
        "/register",
        data={"username": username, "password": password},
        follow_redirects=False,
    )


def login(client, username="alice", password="password123"):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
