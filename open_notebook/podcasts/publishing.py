"""Publishing episodes into the Podcast Feed (see CONTEXT.md, ADR podcast feed)."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import mutagen
from mutagen import MutagenError

from open_notebook.exceptions import InvalidInputError
from open_notebook.podcasts.audio_paths import resolve_contained_audio_path
from open_notebook.podcasts.models import PodcastEpisode

# Formats Apple Podcasts plays, mapped to the MIME type used for the enclosure.
PUBLISHABLE_AUDIO_TYPES = {".mp3": "audio/mpeg", ".m4a": "audio/x-m4a"}


SUMMARY_EXCERPT_CHARS = 300  # default description length (outline excerpt)
SUMMARY_MAX_CHARS = 4000  # longest description an edited summary may have


def default_feed_summary(outline: Optional[dict], fallback: str = "") -> str:
    """Plain-text episode description built from the outline's segments.

    Cut at a word boundary with an ellipsis; falls back to `fallback` (the
    episode name) when there is no outline, as for read-script episodes.
    """
    segments = (outline or {}).get("segments") or []
    parts = [" ".join(str(s.get("description", "")).split()) for s in segments]
    text = " ".join(p for p in parts if p) or fallback
    if len(text) <= SUMMARY_EXCERPT_CHARS:
        return text
    cut = text[: SUMMARY_EXCERPT_CHARS - 1]
    if not text[SUMMARY_EXCERPT_CHARS - 1].isspace():
        cut = cut.rsplit(" ", 1)[0] if " " in cut else cut
    return cut.rstrip() + "…"


def _duration_seconds(path: Path) -> int:
    try:
        audio = mutagen.File(path)
    except (MutagenError, OSError):
        audio = None
    if audio is None or audio.info is None:
        raise InvalidInputError(
            "Could not read the audio file; it may be corrupt or not real "
            "mp3/m4a audio."
        )
    return int(round(audio.info.length))


async def _require_publishable(episode: PodcastEpisode) -> Path:
    """Return the episode's audio path, or raise a specific InvalidInputError."""
    if episode.command:
        status = (await episode.get_job_detail())["status"]
        if status != "completed":
            raise InvalidInputError(
                f"Episode is not completed (job status: {status}); only "
                "completed episodes can be published."
            )
    if not episode.audio_file:
        raise InvalidInputError("Episode has no audio file.")
    audio_path = resolve_contained_audio_path(episode.audio_file)
    if audio_path is None:
        raise InvalidInputError(
            "Episode audio file path is invalid (outside the podcasts folder)."
        )
    if not audio_path.is_file():
        raise InvalidInputError("Audio file not found on disk.")
    if audio_path.suffix.lower() not in PUBLISHABLE_AUDIO_TYPES:
        raise InvalidInputError(
            f"Unsupported audio format '{audio_path.suffix}': only .mp3 and "
            ".m4a episodes can be published."
        )
    return audio_path


async def publish_episode(
    episode: PodcastEpisode, summary: Optional[str] = None
) -> None:
    """Put a completed episode in the Podcast Feed and save it."""
    audio_path = await _require_publishable(episode)
    edited = (summary or "").strip()
    if len(edited) > SUMMARY_MAX_CHARS:
        raise InvalidInputError(
            f"Summary is too long ({len(edited)} characters; the limit is "
            f"{SUMMARY_MAX_CHARS})."
        )
    episode.duration_seconds = _duration_seconds(audio_path)
    if edited:
        episode.feed_summary = edited
    elif not episode.published_at:
        # First publish: describe the episode from its outline. A republish
        # without a summary keeps whatever notes the episode already has.
        episode.feed_summary = default_feed_summary(
            episode.outline, fallback=episode.name
        )
    if not episode.published_at:
        episode.published_at = datetime.now(timezone.utc)
    await episode.save()


async def unpublish_episode(episode: PodcastEpisode) -> None:
    """Take an episode out of the Podcast Feed. A no-op if it is not in it."""
    if not episode.published_at:
        return
    episode.published_at = None
    episode.duration_seconds = None
    episode.feed_summary = None
    await episode.save()
