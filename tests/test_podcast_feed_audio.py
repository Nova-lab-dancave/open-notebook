"""
Tests for the token-gated Podcast Feed audio route (#31, spec #37, ticket #40).

Seam: the HTTP API through the FastAPI test client. Only the database boundary
is faked (a one-table in-memory library of episodes); audio files are real
files under a temporary podcasts folder, so size and byte ranges are checked
against known bytes, not against the code's own arithmetic.
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from open_notebook.domain.podcast_feed import PodcastFeedSettings

TOKEN = "tok-abc123"
PUBLIC_URL = "https://lab.example.ts.net:8502"
# 10240 bytes in a repeating 0..255 pattern: every byte offset is recognisable.
AUDIO = bytes(range(256)) * 40
PUBLISHED = datetime(2026, 11, 5, 18, 45, tzinfo=timezone.utc)
NOT_FOUND = {"detail": "Not found"}


def audio_path(key="ep1", ext="mp3", token=TOKEN):
    return f"/api/podcasts/feed/{token}/episodes/{key}.{ext}"


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def feed_settings(monkeypatch):
    monkeypatch.setenv("OPEN_NOTEBOOK_PUBLIC_URL", PUBLIC_URL)
    monkeypatch.delenv("API_URL", raising=False)
    settings = SimpleNamespace(feed_token=TOKEN, artwork_ext=None, artwork_version=None)
    with patch.object(
        PodcastFeedSettings, "get_instance", AsyncMock(return_value=settings)
    ):
        yield settings


class Library:
    """Episodes in a fake database plus their audio files on disk."""

    def __init__(self, root):
        self.root = root
        self.rows: list[dict] = []

    def add(self, key="ep1", ext="mp3", published=True, data=AUDIO, write=True):
        rel = f"episodes/{key}/audio/{key}.{ext}"
        if write:
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.rows.append(
            dict(
                id=f"episode:{key}",
                name=f"Episode {key}",
                episode_profile={"name": "default"},
                speaker_profile={"name": "default"},
                briefing="INTERNAL",
                content="source",
                audio_file=rel,
                published_at=PUBLISHED if published else None,
                duration_seconds=26,
                feed_summary="Notes",
            )
        )


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "open_notebook.podcasts.audio_paths.PODCASTS_FOLDER", str(tmp_path)
    )
    lib = Library(tmp_path)

    async def published_query(query, params=None):
        return [r for r in lib.rows if r["published_at"] is not None]

    async def get_by_id(query, params=None):
        return [r for r in lib.rows if r["id"] == str(params["id"])]

    with (
        patch("open_notebook.podcasts.models.repo_query", published_query),
        patch("open_notebook.domain.base.repo_query", get_by_id),
    ):
        yield lib


class TestServesPublishedAudio:
    def test_mp3_is_served_whole_with_length_and_range_support(self, client, library):
        library.add("ep1", "mp3")

        response = client.get(audio_path("ep1", "mp3"))

        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/mpeg"
        assert response.headers["content-length"] == str(len(AUDIO))
        assert response.headers["accept-ranges"] == "bytes"
        assert response.content == AUDIO

    def test_m4a_has_the_m4a_content_type(self, client, library):
        library.add("ep1", "m4a")

        response = client.get(audio_path("ep1", "m4a"))

        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/x-m4a"
        assert response.content == AUDIO


class TestByteRanges:
    """Apple Podcasts seeks and resumes with Range requests."""

    def test_a_byte_range_returns_206_with_exactly_those_bytes(self, client, library):
        library.add()

        response = client.get(audio_path(), headers={"Range": "bytes=100-199"})

        assert response.status_code == 206
        assert response.headers["content-range"] == f"bytes 100-199/{len(AUDIO)}"
        assert response.headers["content-length"] == "100"
        assert response.content == AUDIO[100:200]

    def test_probe_range_of_the_first_two_bytes(self, client, library):
        library.add()

        response = client.get(audio_path(), headers={"Range": "bytes=0-1"})

        assert response.status_code == 206
        assert response.content == AUDIO[0:2]

    def test_open_ended_range_runs_to_the_end(self, client, library):
        library.add()

        response = client.get(audio_path(), headers={"Range": "bytes=10000-"})

        assert response.status_code == 206
        assert response.headers["content-range"] == (
            f"bytes 10000-{len(AUDIO) - 1}/{len(AUDIO)}"
        )
        assert response.content == AUDIO[10000:]

    def test_suffix_range_returns_the_last_bytes(self, client, library):
        library.add()

        response = client.get(audio_path(), headers={"Range": "bytes=-50"})

        assert response.status_code == 206
        assert response.content == AUDIO[-50:]

    def test_unsatisfiable_range_returns_416(self, client, library):
        library.add()

        response = client.get(audio_path(), headers={"Range": "bytes=20000-30000"})

        assert response.status_code == 416
        assert response.headers["content-range"] == f"bytes */{len(AUDIO)}"


class TestHeadRequests:
    """Podcast apps often HEAD an enclosure to read its size before fetching."""

    def test_head_returns_the_headers_and_no_body(self, client, library):
        library.add()

        response = client.head(audio_path())

        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/mpeg"
        assert response.headers["content-length"] == str(len(AUDIO))
        assert response.headers["accept-ranges"] == "bytes"
        assert response.content == b""


def _setup_wrong_token(lib, settings):
    lib.add()
    return audio_path(token="not-the-token")


def _setup_unknown_episode(lib, settings):
    return audio_path("ep9")


def _setup_unpublished(lib, settings):
    lib.add(published=False)
    return audio_path()


def _setup_extension_mismatch(lib, settings):
    lib.add("ep1", "mp3")
    return audio_path("ep1", "m4a")


def _setup_no_extension(lib, settings):
    lib.add()
    return f"/api/podcasts/feed/{TOKEN}/episodes/ep1"


def _setup_file_missing_on_disk(lib, settings):
    lib.add(write=False)
    return audio_path()


def _setup_path_outside_the_podcasts_folder(lib, settings):
    lib.add()
    lib.rows[0]["audio_file"] = "../../etc/passwd.mp3"
    return audio_path()


def _setup_no_token_configured(lib, settings):
    lib.add()
    settings.feed_token = None
    return audio_path()


NOT_FOUND_CASES = {
    "wrong_token": _setup_wrong_token,
    "unknown_episode": _setup_unknown_episode,
    "unpublished_episode": _setup_unpublished,
    "extension_mismatch": _setup_extension_mismatch,
    "no_extension": _setup_no_extension,
    "file_missing_on_disk": _setup_file_missing_on_disk,
    "path_outside_podcasts_folder": _setup_path_outside_the_podcasts_folder,
    "no_token_configured": _setup_no_token_configured,
}


class TestEveryFailureLooksTheSame:
    """Nothing about the response may reveal which check failed."""

    @pytest.mark.parametrize("case", NOT_FOUND_CASES)
    def test_is_the_one_uniform_404(self, client, library, feed_settings, case):
        url = NOT_FOUND_CASES[case](library, feed_settings)

        response = client.get(url)

        assert response.status_code == 404
        assert response.json() == NOT_FOUND

    @pytest.mark.parametrize("case", NOT_FOUND_CASES)
    def test_head_requests_get_the_same_404(self, client, library, feed_settings, case):
        url = NOT_FOUND_CASES[case](library, feed_settings)

        assert client.head(url).status_code == 404


@pytest.fixture
def password_client(monkeypatch):
    """Test client for the real app with OPEN_NOTEBOOK_PASSWORD set."""
    from api.main import app

    monkeypatch.setenv("OPEN_NOTEBOOK_PASSWORD", "app-password")
    app.middleware_stack = None
    try:
        yield TestClient(app)
    finally:
        monkeypatch.setenv("OPEN_NOTEBOOK_PASSWORD", "")
        app.middleware_stack = None


class TestPasswordLoginDoesNotApplyToTheFeedPrefix:
    def test_audio_works_without_a_bearer_header(self, password_client, library):
        library.add()

        response = password_client.get(audio_path())

        assert response.status_code == 200
        assert response.content == AUDIO

    def test_a_wrong_token_is_404_not_401(self, password_client, library):
        library.add()

        assert password_client.get(audio_path(token="nope")).status_code == 404

    def test_the_authenticated_audio_route_still_needs_the_password(
        self, password_client, library
    ):
        library.add()

        response = password_client.get("/api/podcasts/episodes/episode:ep1/audio")

        assert response.status_code == 401


class TestFeedEnclosuresResolveToThisRoute:
    def test_following_each_enclosure_url_returns_the_advertised_file(
        self, client, library
    ):
        library.add("ep1", "mp3")
        library.add("ep2", "m4a", data=AUDIO[:5000])

        feed = client.get(f"/api/podcasts/feed/{TOKEN}/feed.xml")
        channel = ET.fromstring(feed.content).find("channel")
        assert channel is not None
        enclosures = [i.find("enclosure") for i in channel.findall("item")]
        assert len(enclosures) == 2

        for enclosure in enclosures:
            assert enclosure is not None
            url = enclosure.attrib["url"]
            assert url.startswith(PUBLIC_URL)
            response = client.get(url.removeprefix(PUBLIC_URL))
            assert response.status_code == 200
            assert response.headers["content-type"] == enclosure.attrib["type"]
            assert len(response.content) == int(enclosure.attrib["length"])
