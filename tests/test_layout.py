from tests.conftest import login, register


def test_base_template_loads_local_pico_css(client):
    register(client)
    login(client)

    response = client.get("/")

    assert response.status_code == 200
    assert '<link rel="stylesheet" href="/static/vendor/pico.min.css">' in response.text
