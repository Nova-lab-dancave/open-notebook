"""
Tests for the Podcast Feed (#31, spec #37, ticket #38).

Seam: the HTTP API through the FastAPI test client, with the feed settings
record mocked. The feed is token-gated: the Feed Token lives in the URL path
and replaces the password login for this one prefix.
"""

import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from open_notebook.domain.podcast_feed import PodcastFeedSettings

ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
ATOM = "{http://www.w3.org/2005/Atom}"
TOKEN = "tok-abc123"
FEED_PATH = f"/api/podcasts/feed/{TOKEN}/feed.xml"
PUBLIC_URL = "https://lab.example.ts.net:8502"


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


@pytest.fixture
def feed_settings():
    """Feed settings record holding TOKEN; env has a public HTTPS origin."""
    settings = SimpleNamespace(feed_token=TOKEN)
    with patch.object(
        PodcastFeedSettings, "get_instance", AsyncMock(return_value=settings)
    ):
        yield settings


@pytest.fixture
def password_client(monkeypatch):
    """Test client for the real app with OPEN_NOTEBOOK_PASSWORD set.

    The auth middleware reads the password when the middleware stack is built,
    so force a rebuild with the password set, and another one afterwards so
    other tests get the usual password-less app back.
    """
    from api.main import app

    monkeypatch.setenv("OPEN_NOTEBOOK_PASSWORD", "app-password")
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


class TestFeedWithValidToken:
    def test_returns_well_formed_rss_with_no_items(self, client, feed_settings):
        response = client.get(FEED_PATH)

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/rss+xml")
        root = ET.fromstring(response.content)
        assert root.tag == "rss"
        assert root.attrib["version"] == "2.0"
        channel = root.find("channel")
        assert channel is not None
        assert channel.findall("item") == []

    def test_channel_has_default_show_info(self, client, feed_settings):
        channel = ET.fromstring(client.get(FEED_PATH).content).find("channel")

        assert channel is not None
        for tag in ("title", "description", "language"):
            element = channel.find(tag)
            assert element is not None and (element.text or "").strip()
        author = channel.find(f"{ITUNES}author")
        assert author is not None and (author.text or "").strip()

    def test_channel_is_blocked_from_the_public_directory(self, client, feed_settings):
        channel = ET.fromstring(client.get(FEED_PATH).content).find("channel")

        assert channel is not None
        block = channel.find(f"{ITUNES}block")
        assert block is not None and block.text == "yes"


class TestFeedRejectsWrongToken:
    def test_wrong_token_is_404(self, client, feed_settings):
        response = client.get("/api/podcasts/feed/not-the-token/feed.xml")

        assert response.status_code == 404

    def test_non_ascii_token_is_404_not_an_error(self, client, feed_settings):
        response = client.get("/api/podcasts/feed/t%C3%B6k/feed.xml")

        assert response.status_code == 404

    def test_no_token_configured_looks_the_same_as_a_wrong_token(self, client):
        with patch.object(
            PodcastFeedSettings,
            "get_instance",
            AsyncMock(return_value=SimpleNamespace(feed_token=None)),
        ):
            unconfigured = client.get(FEED_PATH)
        with patch.object(
            PodcastFeedSettings,
            "get_instance",
            AsyncMock(return_value=SimpleNamespace(feed_token=TOKEN)),
        ):
            wrong = client.get("/api/podcasts/feed/not-the-token/feed.xml")

        assert unconfigured.status_code == wrong.status_code == 404
        assert unconfigured.content == wrong.content


class TestFeedBypassesPasswordLoginOnlyForItsOwnPrefix:
    def test_feed_works_without_bearer_header_when_password_is_set(
        self, password_client, feed_settings
    ):
        response = password_client.get(FEED_PATH)

        assert response.status_code == 200

    def test_wrong_token_is_still_404_not_401(self, password_client, feed_settings):
        response = password_client.get("/api/podcasts/feed/not-the-token/feed.xml")

        assert response.status_code == 404

    def test_other_podcast_routes_still_require_the_password(
        self, password_client, feed_settings
    ):
        assert password_client.get("/api/podcasts/episodes").status_code == 401

    def test_route_that_only_resembles_the_prefix_stays_protected(
        self, password_client, feed_settings
    ):
        # "/api/podcasts/feed-url" shares a stem with the feed prefix but is
        # not under "/api/podcasts/feed/", so the password must still apply.
        assert password_client.get("/api/podcasts/feed-url").status_code == 401


def _self_link(response) -> str:
    channel = ET.fromstring(response.content).find("channel")
    assert channel is not None
    link = channel.find(f"{ATOM}link")
    assert link is not None and link.attrib["rel"] == "self"
    return link.attrib["href"]


class TestFeedBaseUrl:
    def test_self_link_uses_the_public_url_setting(self, client, feed_settings):
        assert _self_link(client.get(FEED_PATH)) == f"{PUBLIC_URL}{FEED_PATH}"

    def test_trailing_slash_on_the_setting_is_ignored(
        self, client, feed_settings, monkeypatch
    ):
        monkeypatch.setenv("OPEN_NOTEBOOK_PUBLIC_URL", f"{PUBLIC_URL}/")

        assert _self_link(client.get(FEED_PATH)) == f"{PUBLIC_URL}{FEED_PATH}"

    def test_api_url_is_used_when_no_public_url_is_set(
        self, client, feed_settings, monkeypatch
    ):
        monkeypatch.delenv("OPEN_NOTEBOOK_PUBLIC_URL")
        monkeypatch.setenv("API_URL", "https://api.example.ts.net:8502")

        assert (
            _self_link(client.get(FEED_PATH))
            == f"https://api.example.ts.net:8502{FEED_PATH}"
        )

    def test_public_url_wins_over_api_url(self, client, feed_settings, monkeypatch):
        monkeypatch.setenv("API_URL", "https://api.example.ts.net:8502")

        assert _self_link(client.get(FEED_PATH)).startswith(PUBLIC_URL)

    def test_forwarded_headers_are_the_last_resort(
        self, client, feed_settings, monkeypatch
    ):
        monkeypatch.delenv("OPEN_NOTEBOOK_PUBLIC_URL")

        response = client.get(
            FEED_PATH,
            headers={
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "fwd.example.ts.net",
            },
        )

        assert _self_link(response) == f"https://fwd.example.ts.net{FEED_PATH}"

    def test_sources_that_are_not_https_are_skipped(
        self, client, feed_settings, monkeypatch
    ):
        monkeypatch.setenv("OPEN_NOTEBOOK_PUBLIC_URL", "http://lab.local:8502")
        monkeypatch.setenv("API_URL", "https://api.example.ts.net:8502")

        assert _self_link(client.get(FEED_PATH)).startswith(
            "https://api.example.ts.net:8502"
        )

    def test_no_https_origin_is_a_clear_error(self, client, feed_settings, monkeypatch):
        monkeypatch.delenv("OPEN_NOTEBOOK_PUBLIC_URL")

        response = client.get(
            FEED_PATH, headers={"X-Forwarded-Proto": "http", "X-Forwarded-Host": "x"}
        )

        assert response.status_code == 422
        assert "OPEN_NOTEBOOK_PUBLIC_URL" in response.json()["detail"]

    def test_wrong_token_is_404_even_without_a_base_url(
        self, client, feed_settings, monkeypatch
    ):
        monkeypatch.delenv("OPEN_NOTEBOOK_PUBLIC_URL")

        response = client.get("/api/podcasts/feed/not-the-token/feed.xml")

        assert response.status_code == 404
