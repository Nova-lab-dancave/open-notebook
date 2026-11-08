"""
Tests for publishing episodes into the Podcast Feed (#31, spec #37, ticket #39).

Seam: the HTTP API through the FastAPI test client. The episode service and
the episode's `save()` are mocked at the database boundary; what `save()` would
write is captured and asserted, so the tests see persisted state, not objects.
Audio is real: files under a temporary podcasts folder.
"""

import shutil
import subprocess
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from open_notebook.podcasts.models import PodcastEpisode

MP3_FRAME = bytes([0xFF, 0xFB, 0x90, 0x00]) + b"\x00" * 413  # 128 kbps, 44.1 kHz
# 1000 frames x 1152 samples / 44100 Hz = 26.12 s; mutagen and ffprobe both
# measure the CBR file as 26.0625 s, which rounds to 26.
MP3_SECONDS = 26
OUTLINE = {
    "segments": [
        {
            "name": "Intro",
            "description": "Why   offline\nfirst matters.",
            "size": "short",
        },
        {
            "name": "Deep dive",
            "description": "How sync conflicts resolve.",
            "size": "long",
        },
    ]
}
DEFAULT_SUMMARY = "Why offline first matters. How sync conflicts resolve."
PUBLISH = "/api/podcasts/episodes/episode:ep1/publish"
UNPUBLISH = "/api/podcasts/episodes/episode:ep1/unpublish"


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


@pytest.fixture
def podcasts_root(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "open_notebook.podcasts.audio_paths.PODCASTS_FOLDER", str(tmp_path)
    )
    return tmp_path


def write_audio(root, rel="episodes/ep1/audio/ep1.mp3", data=MP3_FRAME * 1000):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return rel


def make_episode(audio_file="episodes/ep1/audio/ep1.mp3", **overrides):
    defaults = dict(
        id="episode:ep1",
        name="Offline first",
        episode_profile={"name": "default"},
        speaker_profile={"name": "default"},
        briefing="INTERNAL generation prompt, never shown in the feed",
        content="source text",
        audio_file=audio_file,
        outline=OUTLINE,
        command=None,
    )
    defaults.update(overrides)
    return PodcastEpisode(**defaults)


class Harness:
    """Serves one episode to the API and records what save() would persist."""

    def __init__(self, episode):
        self.episode = episode
        self.saved: list[dict] = []

    def __enter__(self):
        async def fake_save(episode):
            self.saved.append(episode._prepare_save_data())

        self._patches = [
            patch(
                "api.routers.podcasts.PodcastService.get_episode",
                new=AsyncMock(return_value=self.episode),
            ),
            patch.object(PodcastEpisode, "save", autospec=True, side_effect=fake_save),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()


class TestPublishCompletedEpisode:
    def test_publish_stores_publication_state(self, client, podcasts_root):
        write_audio(podcasts_root)
        before = datetime.now(timezone.utc)

        with Harness(make_episode()) as h:
            response = client.post(PUBLISH, json={})

        assert response.status_code == 200
        assert len(h.saved) == 1
        saved = h.saved[0]
        assert saved["duration_seconds"] == MP3_SECONDS
        assert saved["feed_summary"] == DEFAULT_SUMMARY
        published_at = saved["published_at"]
        assert (
            before
            <= published_at.astimezone(timezone.utc)
            <= datetime.now(timezone.utc)
        )


def _running_job():
    return patch.object(
        PodcastEpisode,
        "get_job_detail",
        new=AsyncMock(return_value={"status": "running", "error_message": None}),
    )


def _completed_job():
    return patch.object(
        PodcastEpisode,
        "get_job_detail",
        new=AsyncMock(return_value={"status": "completed", "error_message": None}),
    )


def refusal_cases(root):
    """(id, episode builder, keyword the message must contain)."""
    write_audio(root, "episodes/ep1/audio/ep1.wav", data=b"RIFF....WAVE")
    write_audio(root, "episodes/ep1/audio/broken.mp3", data=b"definitely not audio")
    return [
        ("not_completed", make_episode(command="command:abc"), "not completed"),
        ("no_audio", make_episode(audio_file=None), "no audio file"),
        ("escaping_path", make_episode(audio_file="../../etc/passwd"), "invalid"),
        (
            "missing_file",
            make_episode(audio_file="episodes/ep1/audio/gone.mp3"),
            "not found on disk",
        ),
        (
            "unsupported_format",
            make_episode(audio_file="episodes/ep1/audio/ep1.wav"),
            ".mp3",
        ),
        (
            "unreadable_audio",
            make_episode(audio_file="episodes/ep1/audio/broken.mp3"),
            "could not read",
        ),
    ]


CASE_IDS = [
    "not_completed",
    "no_audio",
    "escaping_path",
    "missing_file",
    "unsupported_format",
    "unreadable_audio",
]


class TestPublishRefusals:
    @pytest.mark.parametrize("case_id", CASE_IDS)
    def test_refused_with_a_clear_400_and_nothing_saved(
        self, client, podcasts_root, case_id
    ):
        _, episode, keyword = next(
            c for c in refusal_cases(podcasts_root) if c[0] == case_id
        )

        with _running_job(), Harness(episode) as h:
            response = client.post(PUBLISH, json={})

        assert response.status_code == 400
        assert keyword in response.json()["detail"].lower()
        assert h.saved == []

    def test_every_refusal_has_its_own_message(self, client, podcasts_root):
        details = []
        for _, episode, _ in refusal_cases(podcasts_root):
            with _running_job(), Harness(episode):
                details.append(client.post(PUBLISH, json={}).json()["detail"])

        assert len(set(details)) == len(CASE_IDS)

    def test_an_episode_whose_job_completed_can_be_published(
        self, client, podcasts_root
    ):
        write_audio(podcasts_root)

        with _completed_job(), Harness(make_episode(command="command:abc")) as h:
            response = client.post(PUBLISH, json={})

        assert response.status_code == 200
        assert len(h.saved) == 1

    def test_m4a_is_accepted(self, client, podcasts_root):
        if not shutil.which("ffmpeg"):
            pytest.skip("ffmpeg is needed to generate an m4a fixture")
        path = podcasts_root / "episodes/ep1/audio/ep1.m4a"
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
             "sine=frequency=440:duration=3", "-c:a", "aac", str(path)],
            check=True,
        )  # fmt: skip

        with Harness(make_episode(audio_file="episodes/ep1/audio/ep1.m4a")) as h:
            response = client.post(PUBLISH, json={})

        assert response.status_code == 200
        assert h.saved[0]["duration_seconds"] == 3  # generated as 3 s of sine


class TestFeedSummary:
    def _publish(self, client, root, body, **episode_overrides):
        write_audio(root)
        with Harness(make_episode(**episode_overrides)) as h:
            response = client.post(PUBLISH, json=body)
        return response, h

    def test_edited_summary_is_stored_trimmed(self, client, podcasts_root):
        response, h = self._publish(
            client, podcasts_root, {"summary": "  My own show notes \n"}
        )

        assert response.status_code == 200
        assert h.saved[0]["feed_summary"] == "My own show notes"

    def test_blank_summary_falls_back_to_the_outline_excerpt(
        self, client, podcasts_root
    ):
        _, h = self._publish(client, podcasts_root, {"summary": "   "})

        assert h.saved[0]["feed_summary"] == DEFAULT_SUMMARY

    def test_over_long_edited_summary_is_refused(self, client, podcasts_root):
        response, h = self._publish(client, podcasts_root, {"summary": "x" * 4001})

        assert response.status_code == 400
        assert "summary" in response.json()["detail"].lower()
        assert h.saved == []

    def test_long_outline_excerpt_is_cut_at_a_word_boundary(
        self, client, podcasts_root
    ):
        outline = {"segments": [{"name": "A", "description": "word " * 200}]}

        _, h = self._publish(client, podcasts_root, {}, outline=outline)

        summary = h.saved[0]["feed_summary"]
        assert len(summary) <= 300
        assert summary.endswith("word…")
        assert set(summary[:-1].split()) == {"word"}

    def test_episode_without_an_outline_uses_its_name(self, client, podcasts_root):
        # Read-script episodes have no outline.
        _, h = self._publish(client, podcasts_root, {}, outline=None)

        assert h.saved[0]["feed_summary"] == "Offline first"

    def test_no_request_body_at_all_is_fine(self, client, podcasts_root):
        write_audio(podcasts_root)
        with Harness(make_episode()) as h:
            response = client.post(PUBLISH)

        assert response.status_code == 200
        assert h.saved[0]["feed_summary"] == DEFAULT_SUMMARY


class TestPublishIsIdempotent:
    FIRST = datetime(2026, 11, 1, 9, 30, tzinfo=timezone.utc)

    def _published(self):
        return make_episode(
            published_at=self.FIRST, duration_seconds=26, feed_summary="Old notes"
        )

    def test_republishing_keeps_the_original_publish_time_and_notes(
        self, client, podcasts_root
    ):
        write_audio(podcasts_root)

        with Harness(self._published()) as h:
            response = client.post(PUBLISH, json={})

        assert response.status_code == 200
        assert h.saved[-1]["published_at"] == self.FIRST
        assert h.saved[-1]["feed_summary"] == "Old notes"

    def test_republishing_with_a_summary_edits_only_the_summary(
        self, client, podcasts_root
    ):
        write_audio(podcasts_root)

        with Harness(self._published()) as h:
            client.post(PUBLISH, json={"summary": "New notes"})

        assert h.saved[-1]["published_at"] == self.FIRST
        assert h.saved[-1]["feed_summary"] == "New notes"
        assert h.saved[-1]["duration_seconds"] == MP3_SECONDS


class TestUnpublish:
    def test_unpublish_clears_the_publication_state(self, client, podcasts_root):
        episode = make_episode(
            published_at=TestPublishIsIdempotent.FIRST,
            duration_seconds=26,
            feed_summary="Notes",
        )

        with Harness(episode) as h:
            response = client.post(UNPUBLISH)

        assert response.status_code == 200
        saved = h.saved[-1]
        # Present and None: nullable fields are written as NONE, not skipped.
        for field in ("published_at", "duration_seconds", "feed_summary"):
            assert field in saved and saved[field] is None

    def test_unpublishing_an_unpublished_episode_is_a_no_op(
        self, client, podcasts_root
    ):
        with Harness(make_episode()) as h:
            response = client.post(UNPUBLISH)

        assert response.status_code == 200
        assert h.saved == []

    def test_republishing_after_an_unpublish_gets_a_new_publish_time(
        self, client, podcasts_root
    ):
        write_audio(podcasts_root)
        episode = make_episode(
            published_at=TestPublishIsIdempotent.FIRST, feed_summary="Notes"
        )

        with Harness(episode) as h:
            client.post(UNPUBLISH)
            client.post(PUBLISH, json={})

        assert h.saved[-1]["published_at"] > TestPublishIsIdempotent.FIRST


class TestEpisodeResponsesShowPublicationState:
    def _published(self):
        return make_episode(
            published_at=TestPublishIsIdempotent.FIRST,
            duration_seconds=26,
            feed_summary="Notes",
        )

    def test_get_episode_reports_publication_state(self, client, podcasts_root):
        with Harness(self._published()):
            body = client.get("/api/podcasts/episodes/episode:ep1").json()

        assert body["published_at"] == "2026-11-01T09:30:00+00:00"
        assert body["duration_seconds"] == 26
        assert body["feed_summary"] == "Notes"

    def test_unpublished_episode_reports_nothing(self, client, podcasts_root):
        with Harness(make_episode()):
            body = client.get("/api/podcasts/episodes/episode:ep1").json()

        assert body["published_at"] is None
        assert body["feed_summary"] is None

    def test_episode_list_reports_publication_state(self, client, podcasts_root):
        with (
            Harness(self._published()),
            patch(
                "api.routers.podcasts.PodcastService.list_episodes",
                new=AsyncMock(return_value=[self._published()]),
            ),
        ):
            (body,) = client.get("/api/podcasts/episodes").json()

        assert body["published_at"] == "2026-11-01T09:30:00+00:00"
