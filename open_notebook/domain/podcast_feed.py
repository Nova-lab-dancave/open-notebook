from typing import ClassVar, Optional

from pydantic import Field

from open_notebook.domain.base import RecordModel


class PodcastFeedSettings(RecordModel):
    """Instance-wide settings of the Podcast Feed (see CONTEXT.md)."""

    record_id: ClassVar[str] = "open_notebook:podcast_feed_settings"
    feed_token: Optional[str] = Field(
        None, description="Feed Token embedded in the Podcast Feed URL"
    )
