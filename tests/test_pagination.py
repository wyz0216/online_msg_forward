from datetime import datetime, timedelta, timezone

import pytest

from app.db import connect
from tests.conftest import login, register


@pytest.fixture
def populated(client, settings):
    register(client)
    login(client)
    register(client, username="bob")
    with connect(settings.database_path) as conn:
        conn.executemany(
            "INSERT INTO messages (user_id, kind, content) VALUES (1, 'text', ?)",
            [(f"message-{i:03}",) for i in range(65)],
        )
        conn.execute("INSERT INTO messages (user_id, kind, content) VALUES (2, 'text', 'message-private')")
    return client


def test_pages_are_bounded_ordered_and_do_not_overlap(populated):
    pages = [populated.get("/", params={"page": page}).context for page in (1, 2, 3)]

    assert [len(page["messages"]) for page in pages] == [30, 30, 5]
    assert all(page["total"] == 65 and page["page_count"] == 3 for page in pages)
    assert [row["content"] for page in pages for row in page["messages"]] == [
        f"message-{i:03}" for i in reversed(range(65))
    ]
    assert pages[0]["previous_url"] is None
    assert pages[-1]["next_url"] is None


def test_page_past_end_clamps_to_last_page(populated):
    page = populated.get("/?page=999999999999999999999999").context

    assert page["page"] == 3
    assert len(page["messages"]) == 5


def test_search_finds_older_messages_and_does_not_leak_other_users(populated):
    page = populated.get("/", params={"q": "MESSAGE-000"}).context

    assert page["total"] == 1
    assert page["messages"][0]["content"] == "message-000"
    assert populated.get("/?q=private").context["total"] == 0


def test_search_and_kind_filter_apply_before_pagination(populated, settings):
    with connect(settings.database_path) as conn:
        conn.executemany(
            "INSERT INTO messages (user_id, kind, original_filename) VALUES (1, 'file', ?)",
            [(f"Notes-{i:03}.txt",) for i in range(31)],
        )
        conn.execute("INSERT INTO messages (user_id, kind, content) VALUES (1, 'text', 'Notes')")
    page = populated.get("/", params={"q": "notes", "kind": "file", "page": 2}).context

    assert page["total"] == 31
    assert len(page["messages"]) == 1
    assert page["messages"][0]["original_filename"] == "Notes-000.txt"
    assert page["previous_url"] == "/?page=1&q=notes&kind=file"
    assert page["query"] == "notes"
    assert page["kind"] == "file"


def test_search_treats_special_characters_literally(populated, settings):
    with connect(settings.database_path) as conn:
        conn.execute("INSERT INTO messages (user_id, kind, content) VALUES (1, 'text', ?)", ("100%_done & 中文",))
    page = populated.get("/", params={"q": "%_done & 中文"}).context

    assert page["total"] == 1
    assert page["messages"][0]["content"] == "100%_done & 中文"


def test_expired_messages_do_not_count_towards_pages(populated, settings):
    expired = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with connect(settings.database_path) as conn:
        conn.execute("UPDATE messages SET expires_at = ? WHERE user_id = 1 AND id > 30", (expired,))
    page = populated.get("/?page=3").context

    assert page["total"] == 30
    assert page["page_count"] == page["page"] == 1


@pytest.mark.parametrize("params", [{"page": "0"}, {"page": "-1"}, {"page": "abc"}, {"kind": "invalid"}, {"q": "x" * 201}])
def test_invalid_pagination_parameters_are_rejected(client, params):
    register(client)
    login(client)
    assert client.get("/", params=params).status_code == 422


def test_empty_search_keeps_filters_available(client):
    register(client)
    login(client)
    response = client.get("/?q=missing&kind=image")

    assert response.context["total"] == 0
    assert response.context["page"] == 1
    assert 'id="message-filters"' in response.text
    assert 'data-no-results' in response.text
