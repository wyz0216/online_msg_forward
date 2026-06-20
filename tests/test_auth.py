from dataclasses import replace

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import login, register


def client_with_registration(settings, enabled):
    app = create_app(replace(settings, allow_registration=enabled))
    return TestClient(app)


def test_user_can_register(client):
    response = register(client)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_page_shows_register_link_when_registration_is_open(client):
    response = client.get("/login")

    assert response.status_code == 200
    assert '<a href="/register">注册账号</a>' in response.text


def test_login_page_hides_register_link_when_registration_is_closed(settings):
    with client_with_registration(settings, False) as client:
        response = client.get("/login")

    assert response.status_code == 200
    assert '<a href="/register">注册账号</a>' not in response.text


def test_register_page_is_not_available_when_registration_is_closed(settings):
    with client_with_registration(settings, False) as client:
        response = client.get("/register")

    assert response.status_code == 404


def test_register_post_is_not_available_when_registration_is_closed(settings):
    with client_with_registration(settings, False) as client:
        response = register(client)

    assert response.status_code == 404


def test_duplicate_username_is_rejected(client):
    register(client)

    response = register(client)

    assert response.status_code == 400
    assert "Username already exists" in response.text


def test_user_can_login(client):
    register(client)

    response = login(client)

    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_bad_password_is_rejected(client):
    register(client)

    response = login(client, password="wrong")

    assert response.status_code == 200
    assert 'alert("\\u7528\\u6237\\u540d\\u6216\\u5bc6\\u7801\\u9519\\u8bef")' in response.text
    assert "<h1>登录</h1>" in response.text


def test_home_requires_login(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
