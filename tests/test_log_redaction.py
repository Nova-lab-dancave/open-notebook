"""
Tests for the Feed Token log filter (#31, spec #37, ticket #44).

The Feed Token is a URL path segment, so server access logs would record it.
uvicorn logs requests as a record with a message template and an args tuple:
('%s - "%s %s HTTP/%s" %d', (client, method, path, http_version, status)).
"""

import logging

import pytest

from api.logging_filters import RedactFeedToken

SECRET = "s3cr3t-Feed_Token-abc123"
ACCESS_TEMPLATE = '%s - "%s %s HTTP/%s" %d'


def access_record(path, status=200):
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=ACCESS_TEMPLATE,
        args=("100.64.0.7:51234", "GET", path, "1.1", status),
        exc_info=None,
    )


def filtered(record):
    assert RedactFeedToken().filter(record) is True  # never drops a record
    return record


class TestRedactsTheTokenSegment:
    @pytest.mark.parametrize(
        "path,expected",
        [
            (
                f"/api/podcasts/feed/{SECRET}/feed.xml",
                "/api/podcasts/feed/<redacted>/feed.xml",
            ),
            (
                f"/api/podcasts/feed/{SECRET}/episodes/ep1.mp3",
                "/api/podcasts/feed/<redacted>/episodes/ep1.mp3",
            ),
            (
                f"/api/podcasts/feed/{SECRET}/episodes/ep1.mp3?start=10",
                "/api/podcasts/feed/<redacted>/episodes/ep1.mp3?start=10",
            ),
            (
                "/api/podcasts/feed/t%C3%B6k-%2D/feed.xml",
                "/api/podcasts/feed/<redacted>/feed.xml",
            ),
            # A mistyped URL still 404s, and must not log the token either.
            (f"/api/podcasts/feed/{SECRET}", "/api/podcasts/feed/<redacted>"),
            (
                f"/api/podcasts/feed/{SECRET}?x=1",
                "/api/podcasts/feed/<redacted>?x=1",
            ),
        ],
    )
    def test_uvicorn_access_record(self, path, expected):
        message = filtered(access_record(path)).getMessage()

        assert expected in message
        assert SECRET not in message
        assert message.startswith('100.64.0.7:51234 - "GET ')
        assert message.endswith(' HTTP/1.1" 200')

    def test_token_written_straight_into_the_message_text(self):
        record = logging.LogRecord(
            "any", logging.INFO, __file__, 1,
            f"fetching http://host/api/podcasts/feed/{SECRET}/feed.xml now",
            None, None,
        )  # fmt: skip

        message = filtered(record).getMessage()

        assert SECRET not in message
        assert "/api/podcasts/feed/<redacted>/feed.xml" in message

    def test_token_in_a_mapping_style_args(self):
        record = logging.LogRecord(
            "any", logging.INFO, __file__, 1, "GET %(path)s", ({"path": f"/api/podcasts/feed/{SECRET}/feed.xml"},), None,
        )  # fmt: skip

        assert SECRET not in filtered(record).getMessage()

    def test_a_one_character_token_is_still_hidden(self):
        message = filtered(
            access_record("/api/podcasts/feed/a/episodes/b/c.mp3")
        ).getMessage()

        assert "/api/podcasts/feed/<redacted>/episodes/b/c.mp3" in message


class TestLeavesEverythingElseAlone:
    @pytest.mark.parametrize(
        "path",
        [
            "/api/podcasts/episodes",
            "/api/podcasts/episodes/episode:ep1/audio",
            "/api/podcasts/feed-url",
            "/api/podcasts/feed",
            "/api/podcasts/feed/",
            "/health",
        ],
    )
    def test_other_paths_are_unchanged(self, path):
        record = access_record(path)
        before = record.getMessage()

        assert filtered(record).getMessage() == before

    def test_args_keep_their_types(self):
        record = filtered(access_record("/health", status=404))

        assert record.args == ("100.64.0.7:51234", "GET", "/health", "1.1", 404)

    def test_records_without_args_or_with_odd_args_do_not_break(self):
        plain = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", None, None)
        odd = logging.LogRecord("x", logging.INFO, __file__, 1, "n=%s", (None,), None)

        assert filtered(plain).getMessage() == "hello"
        assert filtered(odd).getMessage() == "n=None"


class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class TestInstalledAtStartup:
    """The API installs the filter on uvicorn's access logger when it starts."""

    def _start_app(self):
        from unittest.mock import AsyncMock, patch

        from fastapi.testclient import TestClient

        from api.main import app

        async def no_migrations():
            return None

        with (
            patch("api.main._run_database_migrations", no_migrations),
            patch(
                "api.main.PodcastFeedSettings.ensure_feed_token",
                AsyncMock(return_value="x"),
            ),
            TestClient(app),  # entering the client runs the lifespan
        ):
            pass

    def test_access_log_lines_no_longer_carry_the_token(self):
        access = logging.getLogger("uvicorn.access")
        saved = (list(access.filters), list(access.handlers), access.level)
        handler = _CaptureHandler()
        try:
            self._start_app()
            access.addHandler(handler)
            access.setLevel(logging.INFO)

            access.info(
                ACCESS_TEMPLATE,
                "100.64.0.7:51234",
                "GET",
                f"/api/podcasts/feed/{SECRET}/feed.xml",
                "1.1",
                200,
            )

            assert len(handler.records) == 1
            message = handler.records[0].getMessage()
            assert SECRET not in message
            assert "/api/podcasts/feed/<redacted>/feed.xml" in message
        finally:
            access.filters[:] = saved[0]
            access.handlers[:] = saved[1]
            access.setLevel(saved[2])

    def test_starting_twice_installs_it_once(self):
        access = logging.getLogger("uvicorn.access")
        saved = list(access.filters)
        try:
            self._start_app()
            self._start_app()

            installed = [f for f in access.filters if isinstance(f, RedactFeedToken)]
            assert len(installed) == 1
        finally:
            access.filters[:] = saved
