"""Token-gated Podcast Feed routes.

These routes are the one place the password middleware does not apply: the
Feed Token in the path is the credential (see the podcast feed ADR). Anything
added under this router is public to token holders and must check the token.
"""

import secrets

from fastapi import APIRouter, Request
from fastapi.responses import Response

from open_notebook.domain.podcast_feed import PodcastFeedSettings
from open_notebook.exceptions import NotFoundError
from open_notebook.podcasts.feed import build_feed_xml, resolve_public_base_url

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


@router.get("/podcasts/feed/{token}/feed.xml")
async def get_podcast_feed(token: str, request: Request):
    await _require_feed_token(token)
    # Resolved after the token check so a wrong token is always the uniform 404.
    base_url = resolve_public_base_url(
        request.headers.get("x-forwarded-proto"),
        request.headers.get("x-forwarded-host"),
    )
    feed_url = f"{base_url}/api/podcasts/feed/{token}/feed.xml"
    return Response(
        content=build_feed_xml(feed_url, base_url), media_type="application/rss+xml"
    )
