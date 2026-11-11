"""
Tests for the authenticated feed-URL and token-rotation endpoints (#31, spec #37,
ticket #41).

Seam: the HTTP API through the FastAPI test client against the real app, with
the app password set. The settings record is the real `PodcastFeedSettings`;
only the database boundary is faked (a one-record in-memory store).
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from open_notebook.domain.podcast_feed import PodcastFeedSettings

PASSWORD = "app-password"
AUTH = {"Authorization": f"Bearer {PASSWORD}"}
TOKEN = "tok-abc123"
PUBLIC_URL = "https://lab.example.ts.net:8502"
FEED_URL = "/api/podcasts/feed-url"
ROTATE = "/api/podcasts/feed-token/rotate"


def feed_path(token):
    return f"/api/podcasts/feed/{token}/feed.xml"


@pytest.fixture
def client(monkeypatch):
    """The real app with OPEN_NOTEBOOK_PASSWORD set (rebuilds the middleware)."""
    from api.main import app

    monkeypatch.setenv("OPEN_NOTEBOOK_PASSWORD", PASSWORD)
    app.middleware_stack = None
    try:
        yield TestClient(app)
    finally:
        monkeypatch.setenv("OPEN_NOTEBOOK_PASSWORD", "")
        app.middleware_stack = None


@pytest.fixture(autouse=True)
def public_url(monkeypatch):
    monkeypatch.setenv("OPEN_NOTEBOOK_PUBLIC_URL", PUBLIC_URL)
    monkeypatch.delenv("API_URL", raising=False)


@pytest.fixture(autouse=True)
def no_published_episodes():
    with patch("open_notebook.podcasts.models.repo_query", AsyncMock(return_value=[])):
        yield


@pytest.fixture
def db():
    """Fake database for the settings record, starting with TOKEN saved."""
    store: dict = {"feed_token": TOKEN}

    async def fake_query(query, params=None):
        return [dict(store)] if store else []

    async def fake_upsert(table, id, data, add_timestamp=False):
        store.update(data)
        return [dict(store)]

    PodcastFeedSettings.clear_instance()
    with (
        patch("open_notebook.domain.base.repo_query", fake_query),
        patch("open_notebook.domain.base.repo_upsert", fake_upsert),
    ):
        yield store
    PodcastFeedSettings.clear_instance()


class TestFeedUrl:
    def test_requires_the_app_password(self, client, db):
        assert client.get(FEED_URL).status_code == 401

    def test_returns_the_full_feed_url(self, client, db):
        response = client.get(FEED_URL, headers=AUTH)

        assert response.status_code == 200
        assert response.json() == {"feed_url": f"{PUBLIC_URL}{feed_path(TOKEN)}"}

    def test_the_url_it_returns_is_the_working_feed(self, client, db):
        url = client.get(FEED_URL, headers=AUTH).json()["feed_url"]

        feed = client.get(url.removeprefix(PUBLIC_URL))  # no password: token only

        assert feed.status_code == 200

    def test_mints_the_token_if_none_exists_yet(self, client, db):
        db.clear()

        response = client.get(FEED_URL, headers=AUTH)

        assert response.status_code == 200
        assert len(db["feed_token"]) >= 43
        assert (
            response.json()["feed_url"] == f"{PUBLIC_URL}{feed_path(db['feed_token'])}"
        )

    def test_without_an_https_origin_it_explains_why_and_gives_no_url(
        self, client, db, monkeypatch
    ):
        monkeypatch.delenv("OPEN_NOTEBOOK_PUBLIC_URL")

        response = client.get(FEED_URL, headers=AUTH)

        assert response.status_code == 422
        assert "OPEN_NOTEBOOK_PUBLIC_URL" in response.json()["detail"]
        assert TOKEN not in response.text


class TestRotateToken:
    def test_requires_the_app_password(self, client, db):
        assert client.post(ROTATE).status_code == 401
        assert db["feed_token"] == TOKEN

    def test_replaces_the_token_and_returns_the_new_url(self, client, db):
        response = client.post(ROTATE, headers=AUTH)

        assert response.status_code == 200
        new_token = db["feed_token"]
        assert new_token != TOKEN and len(new_token) >= 43
        assert response.json() == {"feed_url": f"{PUBLIC_URL}{feed_path(new_token)}"}

    def test_the_old_url_stops_working_and_the_new_one_works(self, client, db):
        client.post(ROTATE, headers=AUTH)

        assert client.get(feed_path(TOKEN)).status_code == 404
        assert client.get(feed_path(db["feed_token"])).status_code == 200

    def test_each_rotation_makes_a_different_token(self, client, db):
        client.post(ROTATE, headers=AUTH)
        first = db["feed_token"]
        client.post(ROTATE, headers=AUTH)

        assert db["feed_token"] not in (TOKEN, first)

    def test_it_refuses_to_rotate_blind_when_there_is_no_https_origin(
        self, client, db, monkeypatch
    ):
        monkeypatch.delenv("OPEN_NOTEBOOK_PUBLIC_URL")

        response = client.post(ROTATE, headers=AUTH)

        assert response.status_code == 422
        assert db["feed_token"] == TOKEN  # nothing was changed
