import secrets
from typing import ClassVar, Optional

from pydantic import Field

from open_notebook.domain.base import RecordModel


class PodcastFeedSettings(RecordModel):
    """Instance-wide settings of the Podcast Feed (see CONTEXT.md)."""

    record_id: ClassVar[str] = "open_notebook:podcast_feed_settings"
    feed_token: Optional[str] = Field(
        None, description="Feed Token embedded in the Podcast Feed URL"
    )

    # Show Metadata (see CONTEXT.md). None means "use the default".
    show_title: Optional[str] = Field(None, description="Show title")
    show_author: Optional[str] = Field(None, description="Show author")
    show_description: Optional[str] = Field(None, description="Show description")
    show_language: Optional[str] = Field(None, description="Show language code")
    artwork_ext: Optional[str] = Field(
        None, description="Extension of the stored artwork (.png or .jpg)"
    )
    artwork_version: Optional[str] = Field(
        None, description="Content hash of the artwork; changes with the image"
    )

    @classmethod
    async def ensure_feed_token(cls) -> str:
        """Return the Feed Token, minting and saving one on first use.

        Idempotent: once saved, every later call (and every restart) returns
        the same value. Only a rotation replaces it.
        """
        settings = await cls.get_instance()
        if not settings.feed_token:  # type: ignore[attr-defined]
            settings.feed_token = secrets.token_urlsafe(32)  # type: ignore[attr-defined]
            await settings.update()
        return settings.feed_token  # type: ignore[attr-defined,no-any-return]

    @classmethod
    async def rotate_feed_token(cls) -> str:
        """Replace the Feed Token. Every URL carrying the old one stops working."""
        settings = await cls.get_instance()
        settings.feed_token = secrets.token_urlsafe(32)  # type: ignore[attr-defined]
        await settings.update()
        return settings.feed_token  # type: ignore[attr-defined,no-any-return]
