"""Authenticated Show Metadata and artwork settings for the Podcast Feed.

These routes need the app password (they sit outside the token-exempt feed
prefix). The public, token-gated artwork route is in podcast_feed.py.
"""

import re
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import BaseModel

from open_notebook.domain.podcast_feed import PodcastFeedSettings
from open_notebook.exceptions import InvalidInputError, NotFoundError, OpenNotebookError
from open_notebook.podcasts.artwork import (
    MAX_BYTES,
    current_artwork,
    save_artwork,
    validate_artwork,
)
from open_notebook.podcasts.feed import ShowMetadata

router = APIRouter()

TITLE_MAX = 255
AUTHOR_MAX = 255
DESCRIPTION_MAX = 4000
# BCP 47-style: "en", "pt-BR", "zh-Hans-CN"
LANGUAGE_PATTERN = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")


class FeedSettingsResponse(BaseModel):
    title: str
    author: str
    description: str
    language: str
    has_artwork: bool
    artwork_version: Optional[str] = None


class FeedSettingsUpdate(BaseModel):
    """A field left out is kept; a blank one goes back to its default."""

    title: Optional[str] = None
    author: Optional[str] = None
    description: Optional[str] = None
    language: Optional[str] = None


def _view(settings: PodcastFeedSettings) -> FeedSettingsResponse:
    show = ShowMetadata.from_settings(settings)
    has_artwork = current_artwork(settings.artwork_ext) is not None
    return FeedSettingsResponse(
        title=show.title,
        author=show.author,
        description=show.description,
        language=show.language,
        has_artwork=has_artwork,
        artwork_version=settings.artwork_version if has_artwork else None,
    )


def _checked(label: str, value: Optional[str], limit: int) -> Optional[str]:
    text = (value or "").strip()
    if len(text) > limit:
        raise InvalidInputError(
            f"The show {label} is too long ({len(text)} characters; the limit is {limit})."
        )
    return text or None


def _checked_language(value: Optional[str]) -> Optional[str]:
    text = (value or "").strip()
    if text and not LANGUAGE_PATTERN.match(text):
        raise InvalidInputError(
            "The show language must be a language code such as 'en' or 'pt-BR'."
        )
    return text or None


@router.get("/podcasts/feed-settings", response_model=FeedSettingsResponse)
async def get_feed_settings():
    try:
        settings = await PodcastFeedSettings.get_instance()
        return _view(settings)  # type: ignore[arg-type]
    except (HTTPException, OpenNotebookError):
        raise
    except Exception as e:
        logger.error(f"Error reading the podcast feed settings: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to read the feed settings")


@router.put("/podcasts/feed-settings", response_model=FeedSettingsResponse)
async def update_feed_settings(update: FeedSettingsUpdate):
    try:
        # Check every provided field first so a refused edit changes nothing.
        changes: dict[str, Optional[str]] = {}
        provided = update.model_fields_set
        if "title" in provided:
            changes["show_title"] = _checked("title", update.title, TITLE_MAX)
        if "author" in provided:
            changes["show_author"] = _checked("author", update.author, AUTHOR_MAX)
        if "description" in provided:
            changes["show_description"] = _checked(
                "description", update.description, DESCRIPTION_MAX
            )
        if "language" in provided:
            changes["show_language"] = _checked_language(update.language)

        settings = await PodcastFeedSettings.get_instance()
        if changes:
            for field, value in changes.items():
                setattr(settings, field, value)
            await settings.update()
        return _view(settings)  # type: ignore[arg-type]
    except (HTTPException, OpenNotebookError):
        raise
    except Exception as e:
        logger.error(f"Error updating the podcast feed settings: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to update the feed settings"
        )


@router.post("/podcasts/feed-settings/artwork", response_model=FeedSettingsResponse)
async def upload_feed_artwork(file: UploadFile = File(...)):
    """Replace the show artwork (square PNG or JPEG, 1400-3000 px)."""
    try:
        # One byte over the limit is enough to know the file is too large.
        data = await file.read(MAX_BYTES + 1)
        artwork = validate_artwork(data)
        save_artwork(data, artwork)
        settings = await PodcastFeedSettings.get_instance()
        settings.artwork_ext = artwork.extension  # type: ignore[attr-defined]
        settings.artwork_version = artwork.version  # type: ignore[attr-defined]
        await settings.update()
        return _view(settings)  # type: ignore[arg-type]
    except (HTTPException, OpenNotebookError):
        raise
    except Exception as e:
        logger.error(f"Error saving the podcast feed artwork: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to save the artwork")
    finally:
        await file.close()


@router.get("/podcasts/feed-settings/artwork")
async def get_feed_artwork():
    """The current artwork, for the settings page preview."""
    settings = await PodcastFeedSettings.get_instance()
    found = current_artwork(settings.artwork_ext)  # type: ignore[attr-defined]
    if found is None:
        raise NotFoundError("No artwork has been uploaded")
    path, media_type = found
    return FileResponse(path, media_type=media_type)
