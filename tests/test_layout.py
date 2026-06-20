from pathlib import Path

from tests.conftest import login, register


def test_base_template_loads_local_pico_css(client):
    register(client)
    login(client)

    response = client.get("/")

    assert response.status_code == 200
    assert '<link rel="stylesheet" href="/static/vendor/pico.min.css">' in response.text


def test_message_actions_are_separated_below_content():
    css = Path("app/static/style.css").read_text(encoding="utf-8")

    assert ".message-actions" in css
    assert "grid-template-columns: 1fr;" in css
    assert "border-top: 1px solid #e0e8f0;" in css
