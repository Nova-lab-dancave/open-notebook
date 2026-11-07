"""Shared meeting transcription, transcript assembly and approval operations."""

import asyncio
import io
import tempfile
import wave
from pathlib import Path

from loguru import logger
from surreal_commands import submit_command

from open_notebook.ai.models import model_manager
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.meeting import MAX_CHUNKS, MAX_TRANSCRIPT, Meeting
from open_notebook.domain.notebook import Notebook
from open_notebook.exceptions import ConfigurationError, InvalidInputError
from open_notebook.utils.error_classifier import classify_error

MAX_AUDIO_BYTES = 4_000_000


async def transcribe_audio(raw: bytes) -> str:
    """Only accept bounded mono PCM WAV; the private temporary file is always removed."""
    if not raw or len(raw) > MAX_AUDIO_BYTES:
        raise InvalidInputError("Audio chunk is empty or exceeds 4 MB")
    try:
        with wave.open(io.BytesIO(raw), "rb") as wav:
            if (
                wav.getnchannels() != 1
                or wav.getsampwidth() != 2
                or not 8_000 <= wav.getframerate() <= 48_000
                or wav.getnframes() > wav.getframerate() * 25
                or wav.getnframes() == 0
                or len(wav.readframes(wav.getnframes())) != wav.getnframes() * 2
            ):
                raise ValueError("Invalid PCM format")
    except (wave.Error, EOFError, ValueError) as e:
        raise InvalidInputError(
            "Expected at most 25 seconds of mono 16-bit PCM WAV"
        ) from e
    model = await model_manager.get_speech_to_text()
    if model is None:
        raise ConfigurationError("Configure a default speech-to-text model in Settings")
    # Esperanto providers accept a file path, not an in-memory stream. Never put
    # audio in uploads, command arguments or a persistent meeting record.
    with tempfile.TemporaryDirectory(prefix="meeting-") as directory:
        path = Path(directory) / "chunk.wav"
        await asyncio.to_thread(path.write_bytes, raw)
        try:
            result = await asyncio.wait_for(
                model.atranscribe(audio_file=str(path)), timeout=90
            )
            return str(result.text).strip()
        except Exception as e:
            exc_class, message = classify_error(e)
            raise exc_class(message) from e


async def assemble_transcript(meeting_id: str, total: int) -> tuple[str, list[int]]:
    if not 0 <= total <= MAX_CHUNKS:
        raise InvalidInputError("Meeting exceeds the four-hour limit")
    rows = await repo_query(
        "SELECT sequence, text FROM meeting_chunk WHERE meeting_id = $meeting_id ORDER BY sequence",
        {"meeting_id": meeting_id},
    )
    chunks = {row["sequence"]: row["text"] for row in rows}
    parts, missing = [], []
    for sequence in range(total):
        if sequence in chunks:
            parts.append(
                f"[{sequence * 20 // 60:02d}:{sequence * 20 % 60:02d}] {chunks[sequence]}"
            )
        else:
            missing.append(sequence)
            parts.append(
                f"[{sequence * 20 // 60:02d}:{sequence * 20 % 60:02d}] [Missing audio section]"
            )
    text = "\n\n".join(parts)
    if len(text) > MAX_TRANSCRIPT:
        raise InvalidInputError(
            "Transcript exceeds the supported size; completed chunks are retained"
        )
    return text, missing


def meeting_content(meeting: Meeting) -> str:
    actions = "\n".join(
        f"- [{'x' if a.done else ' '}] {a.text}"
        + (f" — {a.owner}" if a.owner else "")
        + (f" — {a.due}" if a.due else "")
        + f"\n  Evidence: {a.evidence}"
        for a in meeting.actions
    )
    return (
        f"## Summary\n{meeting.summary}\n\n## Actions\n{actions}\n\n"
        f"## Transcript\n{meeting.transcript}"
    )


async def approve_meeting(meeting: Meeting) -> str:
    """Atomically publish once; concurrent approvals cannot create duplicate notes."""
    await Notebook.get(meeting.notebook_id)
    if meeting.status == "approved":
        return meeting.note_id
    if meeting.status != "review" or not meeting.transcript.strip():
        raise InvalidInputError("Finish the meeting and review its transcript first")
    content = meeting_content(meeting)
    note_id = ensure_record_id("note:meeting_" + str(meeting.id).split(":", 1)[1])
    await repo_query(
        "BEGIN TRANSACTION; "
        "LET $draft = SELECT * FROM ONLY $meeting_id; "
        "IF $draft.status = 'review' AND $draft.revision = $revision { "
        "CREATE $note_id CONTENT {title: $title, content: $content, note_type: 'human', embedding: [], meeting_id: $meeting_string}; "
        "RELATE $note_id->artifact->$notebook_id; "
        "UPDATE $meeting_id SET status = 'approved', note_id = $note_string; "
        "}; COMMIT TRANSACTION;",
        {
            "meeting_id": ensure_record_id(str(meeting.id)),
            "note_id": note_id,
            "note_string": str(note_id),
            "notebook_id": ensure_record_id(meeting.notebook_id),
            "title": meeting.title,
            "content": content,
            "revision": meeting.revision,
            "meeting_string": str(meeting.id),
        },
    )
    published = await Meeting.get(str(meeting.id))
    if published.status != "approved":
        raise InvalidInputError(
            "Meeting changed during approval; reload it and try again"
        )
    try:
        submit_command("open_notebook", "embed_note", {"note_id": published.note_id})
    except Exception:
        logger.warning("Meeting approved; embedding submission failed")
    return published.note_id
