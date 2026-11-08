"""Token-gated Podcast Feed routes.

These routes are the one place the password middleware does not apply: the
Feed Token in the path is the credential (see the podcast feed ADR). Anything
added under this router is public to token holders and must check the token.
"""

import secrets
from datetime import timezone

from fastapi import APIRouter, Request
from fastapi.responses import Response
from loguru import logger

from open_notebook.domain.podcast_feed import PodcastFeedSettings
from open_notebook.exceptions import NotFoundError
from open_notebook.podcasts.audio_paths import resolve_contained_audio_path
from open_notebook.podcasts.feed import (
    FeedItem,
    build_feed_xml,
    resolve_public_base_url,
)
from open_notebook.podcasts.models import PodcastEpisode
from open_notebook.podcasts.publishing import PUBLISHABLE_AUDIO_TYPES

router = APIRouter()


async def _require_feed_token(token: str) -> None:
    """Raise the one uniform 404 unless `token` is the instance's Feed Token.

    A wrong token, a missing token and (later) unknown or unpublished episodes
    must be indistinguishable, so nothing can probe for valid values.
    """
    settings = await PodcastFeedSettings.get_instance()
    expected = getattr(settings, "feed_token", None)
    if not expected or not secrets.compare_digest(
        token.encode("utf-8"), expected.encode("utf-8")
    ):
        raise NotFoundError("Not found")


def _feed_items(episodes: list[PodcastEpisode], base_url: str, token: str):
    """Feed items for Published Episodes whose audio is still publishable.

    The feed must never point at nothing: an episode whose file vanished (or
    whose path is no longer valid) is left out and logged, not served.
    """
    items = []
    for episode in episodes:
        audio_path = resolve_contained_audio_path(episode.audio_file)
        mime = (
            PUBLISHABLE_AUDIO_TYPES.get(audio_path.suffix.lower())
            if audio_path is not None
            else None
        )
        if audio_path is None or not audio_path.is_file() or mime is None:
            logger.warning(f"Leaving published episode {episode.id} out of the feed")
            continue
        published_at = episode.published_at
        assert published_at is not None  # get_published() only returns these
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        key = str(episode.id).split(":", 1)[-1]
        items.append(
            FeedItem(
                title=episode.name,
                description=episode.feed_summary or episode.name,
                published_at=published_at,
                guid=f"open-notebook-episode-{key}",
                enclosure_url=(
                    f"{base_url}/api/podcasts/feed/{token}/episodes/"
                    f"{key}{audio_path.suffix.lower()}"
                ),
                enclosure_bytes=audio_path.stat().st_size,
                enclosure_type=mime,
                duration_seconds=episode.duration_seconds or 0,
            )
        )
    return items


@router.get("/podcasts/feed/{token}/feed.xml")
async def get_podcast_feed(token: str, request: Request):
    await _require_feed_token(token)
    # Resolved after the token check so a wrong token is always the uniform 404.
    base_url = resolve_public_base_url(
        request.headers.get("x-forwarded-proto"),
        request.headers.get("x-forwarded-host"),
    )
    feed_url = f"{base_url}/api/podcasts/feed/{token}/feed.xml"
    items = _feed_items(await PodcastEpisode.get_published(), base_url, token)
    return Response(
        content=build_feed_xml(feed_url, base_url, items),
        media_type="application/rss+xml",
    )
