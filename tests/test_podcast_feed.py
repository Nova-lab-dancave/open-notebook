"""
Tests for the Podcast Feed (#31, spec #37, ticket #38).

Seam: the HTTP API through the FastAPI test client, with the feed settings
record mocked. The feed is token-gated: the Feed Token lives in the URL path
and replaces the password login for this one prefix.
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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
    settings = SimpleNamespace(feed_token=TOKEN, artwork_ext=None, artwork_version=None)
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
def no_published_episodes():
    """By default no episode is published; `published(...)` overrides this."""
    with patch("open_notebook.podcasts.models.repo_query", AsyncMock(return_value=[])):
        yield


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
            AsyncMock(
                return_value=SimpleNamespace(
                    feed_token=None, artwork_ext=None, artwork_version=None
                )
            ),
        ):
            unconfigured = client.get(FEED_PATH)
        with patch.object(
            PodcastFeedSettings,
            "get_instance",
            AsyncMock(
                return_value=SimpleNamespace(
                    feed_token=TOKEN, artwork_ext=None, artwork_version=None
                )
            ),
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


class TestFeedTokenMinting:
    """The Feed Token is minted once and then stays the same across restarts.

    The settings record is the real `PodcastFeedSettings`; only the database
    boundary is faked, with a one-record in-memory store.
    """

    @pytest.fixture
    def db(self):
        store: dict = {}
        saves: list = []

        async def fake_query(query, params=None):
            return [dict(store)] if store else []

        async def fake_upsert(table, id, data, add_timestamp=False):
            saves.append(dict(data))
            store.update(data)
            return [dict(store)]

        PodcastFeedSettings.clear_instance()
        with (
            patch("open_notebook.domain.base.repo_query", fake_query),
            patch("open_notebook.domain.base.repo_upsert", fake_upsert),
        ):
            yield SimpleNamespace(store=store, saves=saves)
        PodcastFeedSettings.clear_instance()

    @pytest.mark.asyncio
    async def test_first_call_mints_and_saves_a_strong_token(self, db):
        token = await PodcastFeedSettings.ensure_feed_token()

        assert len(token) >= 43  # token_urlsafe(32) is 43 characters
        assert all(c.isalnum() or c in "-_" for c in token)
        assert db.store["feed_token"] == token
        assert len(db.saves) == 1

    @pytest.mark.asyncio
    async def test_token_survives_a_restart_unchanged(self, db):
        first = await PodcastFeedSettings.ensure_feed_token()
        PodcastFeedSettings.clear_instance()  # a new process, same database

        second = await PodcastFeedSettings.ensure_feed_token()

        assert second == first
        assert len(db.saves) == 1

    @pytest.mark.asyncio
    async def test_different_instances_get_different_tokens(self, db):
        first = await PodcastFeedSettings.ensure_feed_token()
        db.store.clear()
        PodcastFeedSettings.clear_instance()

        assert await PodcastFeedSettings.ensure_feed_token() != first


class TestFeedTokenIsMintedAtStartup:
    def test_api_startup_mints_the_token_after_migrations(self):
        from api.main import app

        calls: list[str] = []

        async def fake_migrations():
            calls.append("migrations")

        async def fake_mint():
            calls.append("mint")
            return TOKEN

        with (
            patch("api.main._run_database_migrations", fake_migrations),
            patch.object(PodcastFeedSettings, "ensure_feed_token", fake_mint),
            TestClient(app),  # entering the client runs the lifespan
        ):
            pass

        assert calls == ["migrations", "mint"]


def episode_row(key, name, published_at, ext="mp3", **overrides):
    row = dict(
        id=f"episode:{key}",
        name=name,
        episode_profile={"name": "default"},
        speaker_profile={"name": "default"},
        briefing="INTERNAL generation prompt, never shown in the feed",
        content="source text",
        audio_file=f"episodes/{key}/audio/{key}.{ext}",
        published_at=published_at,
        duration_seconds=26,
        feed_summary=f"About {name}",
    )
    row.update(overrides)
    return row


@pytest.fixture
def published(tmp_path, monkeypatch):
    """Serve `rows` as the published episodes, with real audio files for them."""
    monkeypatch.setattr(
        "open_notebook.podcasts.audio_paths.PODCASTS_FOLDER", str(tmp_path)
    )

    def serve(rows, audio=b"A" * 417000):
        for row in rows:
            if audio is not None:
                path = tmp_path / row["audio_file"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(audio)
        return patch(
            "open_notebook.podcasts.models.repo_query",
            AsyncMock(return_value=rows),
        )

    return serve


def _items(response):
    channel = ET.fromstring(response.content).find("channel")
    assert channel is not None
    return channel.findall("item")


class TestFeedItems:
    OLDER = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)
    NEWER = datetime(2026, 11, 5, 18, 45, tzinfo=timezone.utc)

    def test_published_episode_becomes_an_item(self, client, feed_settings, published):
        with published([episode_row("ep1", "Offline first", self.NEWER)]):
            response = client.get(FEED_PATH)

        (item,) = _items(response)
        assert item.findtext("title") == "Offline first"
        assert item.findtext("description") == "About Offline first"
        assert parsedate_to_datetime(item.findtext("pubDate")) == self.NEWER
        assert item.findtext(f"{ITUNES}duration") == "26"
        guid = item.find("guid")
        assert guid is not None
        assert guid.text == "open-notebook-episode-ep1"
        assert guid.attrib["isPermaLink"] == "false"
        enclosure = item.find("enclosure")
        assert enclosure is not None
        assert enclosure.attrib == {
            "url": f"{PUBLIC_URL}/api/podcasts/feed/{TOKEN}/episodes/ep1.mp3",
            "length": "417000",  # bytes written by the fixture
            "type": "audio/mpeg",
        }

    def test_items_are_newest_published_first(self, client, feed_settings, published):
        rows = [
            episode_row("old", "Older", self.OLDER),
            episode_row("new", "Newer", self.NEWER),
        ]
        with published(rows):
            titles = [i.findtext("title") for i in _items(client.get(FEED_PATH))]

        assert titles == ["Newer", "Older"]

    def test_m4a_episode_has_the_m4a_mime_type(self, client, feed_settings, published):
        with published([episode_row("ep1", "Talk", self.NEWER, ext="m4a")]):
            (item,) = _items(client.get(FEED_PATH))

        enclosure = item.find("enclosure")
        assert enclosure is not None
        assert enclosure.attrib["type"] == "audio/x-m4a"
        assert enclosure.attrib["url"].endswith("/episodes/ep1.m4a")

    def test_generation_briefing_never_reaches_the_feed(
        self, client, feed_settings, published
    ):
        with published([episode_row("ep1", "Offline first", self.NEWER)]):
            response = client.get(FEED_PATH)

        assert b"INTERNAL generation prompt" not in response.content

    def test_published_episode_whose_audio_vanished_is_left_out(
        self, client, feed_settings, published
    ):
        with published([episode_row("ep1", "Gone", self.NEWER)], audio=None):
            assert _items(client.get(FEED_PATH)) == []


class TestDeleteAndRetryOfPublishedEpisodes:
    PUBLISHED = datetime(2026, 11, 5, 18, 45, tzinfo=timezone.utc)

    def test_deleting_a_published_episode_removes_it_from_the_feed(
        self, client, feed_settings, published
    ):
        from open_notebook.podcasts.models import PodcastEpisode

        rows = [episode_row("ep1", "Offline first", self.PUBLISHED)]
        episode = PodcastEpisode(**rows[0])

        async def fake_delete(self):
            rows.clear()
            return True

        with (
            published(rows),
            patch(
                "api.routers.podcasts.PodcastService.get_episode",
                new=AsyncMock(return_value=episode),
            ),
            patch.object(PodcastEpisode, "delete", fake_delete),
        ):
            assert len(_items(client.get(FEED_PATH))) == 1

            deleted = client.delete("/api/podcasts/episodes/episode:ep1")

            assert deleted.status_code == 200
            assert _items(client.get(FEED_PATH)) == []

    def test_a_published_episode_cannot_be_retried(
        self, client, feed_settings, published
    ):
        from open_notebook.podcasts.models import PodcastEpisode

        episode = PodcastEpisode(**episode_row("ep1", "Offline first", self.PUBLISHED))

        with (
            patch(
                "api.routers.podcasts.PodcastService.get_episode",
                new=AsyncMock(return_value=episode),
            ),
            patch.object(
                PodcastEpisode,
                "get_job_detail",
                new=AsyncMock(
                    return_value={"status": "completed", "error_message": None}
                ),
            ),
            patch.object(PodcastEpisode, "delete", new=AsyncMock()) as delete,
        ):
            response = client.post("/api/podcasts/episodes/episode:ep1/retry")

        assert response.status_code == 400
        delete.assert_not_awaited()


class TestFeedAnswersHead:
    """Podcast apps and feed validators may HEAD the feed before fetching it."""

    def test_head_returns_the_feed_headers_and_no_body(self, client, feed_settings):
        get = client.get(FEED_PATH)

        head = client.head(FEED_PATH)

        assert head.status_code == 200
        assert head.headers["content-type"].startswith("application/rss+xml")
        assert head.headers["content-length"] == str(len(get.content))
        assert head.content == b""

    def test_head_with_a_wrong_token_is_the_same_404(self, client, feed_settings):
        head = client.head("/api/podcasts/feed/not-the-token/feed.xml")

        assert head.status_code == 404

    def test_head_works_without_a_bearer_header_when_a_password_is_set(
        self, password_client, feed_settings
    ):
        assert password_client.head(FEED_PATH).status_code == 200
