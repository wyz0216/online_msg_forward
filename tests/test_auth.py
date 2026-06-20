from tests.conftest import login, register


def test_user_can_register(client):
    response = register(client)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


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

    assert response.status_code == 400
    assert "Invalid username or password" in response.text


def test_home_requires_login(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
