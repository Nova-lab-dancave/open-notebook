"""Record transcript chunks, review meeting drafts, then publish approved notes."""

from uuid import uuid4

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel, Field

from api.command_service import CommandService
from api.meeting_service import (
    MAX_AUDIO_BYTES,
    approve_meeting,
    assemble_transcript,
    meeting_content,
    transcribe_audio,
)
from open_notebook.ai.models import model_manager
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.meeting import (
    MAX_CHUNKS,
    MAX_TRANSCRIPT,
    Meeting,
    MeetingAction,
)
from open_notebook.domain.notebook import Notebook
from open_notebook.exceptions import (
    ConfigurationError,
    InvalidInputError,
    NotFoundError,
)

router = APIRouter()


class StartMeeting(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    capture_mode: str = "microphone"


class FinishMeeting(BaseModel):
    total_chunks: int = Field(ge=0, le=MAX_CHUNKS)
    interrupted: bool = False


class EditMeeting(BaseModel):
    revision: int = Field(default=0, ge=0)
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(max_length=30_000)
    actions: list[MeetingAction] = Field(max_length=100)
    transcript: str = Field(min_length=1, max_length=MAX_TRANSCRIPT)


async def get_meeting(notebook_id: str, meeting_id: str) -> Meeting:
    if not meeting_id.startswith("meeting:"):
        raise NotFoundError("Meeting not found")
    meeting = await Meeting.get(meeting_id)
    if meeting.notebook_id != notebook_id:
        raise NotFoundError("Meeting not found in this notebook")
    return meeting


async def view(meeting: Meeting) -> dict:
    result = meeting.model_dump(mode="json")
    result["summary_status"] = "idle"
    if meeting.summary_job and meeting.summary_token and meeting.status == "review":
        job = await CommandService.get_command_status(meeting.summary_job)
        status = job["status"]
        if status == "completed":
            # The worker may have completed between the list query and this
            # status check. Return its fresh result before polling stops.
            meeting = await Meeting.get(str(meeting.id))
            result = meeting.model_dump(mode="json")
        result["summary_status"] = status
        if status in ("failed", "canceled", "unknown") or (
            status == "completed" and not (job.get("result") or {}).get("success")
        ):
            result["summary_error"] = (
                meeting.summary_error
                or "Summary worker failed. Retry summary generation."
            )
    if meeting.status == "recording":
        rows = await repo_query(
            "SELECT sequence, text FROM meeting_chunk WHERE meeting_id = $id ORDER BY sequence",
            {"id": str(meeting.id)},
        )
        result["transcript"] = "\n\n".join(
            f"[{r['sequence'] * 20 // 60:02d}:{r['sequence'] * 20 % 60:02d}] {r['text']}"
            for r in rows
        )
        result["total_chunks"] = max(
            meeting.total_chunks, max((r["sequence"] + 1 for r in rows), default=0)
        )
    return result


@router.get("/notebooks/{notebook_id}/meetings")
async def list_meetings(notebook_id: str):
    await Notebook.get(notebook_id)
    rows = await repo_query(
        "SELECT * FROM meeting WHERE notebook_id = $notebook_id ORDER BY created DESC",
        {"notebook_id": notebook_id},
    )
    return [await view(Meeting(**row)) for row in rows]


@router.post("/notebooks/{notebook_id}/meetings")
async def start_meeting(notebook_id: str, data: StartMeeting):
    await Notebook.get(notebook_id)
    if data.capture_mode not in ("microphone", "shared"):
        raise InvalidInputError("Unsupported audio source")
    if await model_manager.get_speech_to_text() is None:
        raise ConfigurationError("Configure a default speech-to-text model in Settings")
    meeting = Meeting(
        notebook_id=notebook_id, title=data.title, capture_mode=data.capture_mode
    )
    await meeting.save()
    return await view(meeting)


@router.post("/notebooks/{notebook_id}/meetings/{meeting_id}/chunks/{sequence}")
async def upload_chunk(
    notebook_id: str, meeting_id: str, sequence: int, audio: UploadFile = File(...)
):
    try:
        meeting = await get_meeting(notebook_id, meeting_id)
        if meeting.status != "recording" or not 0 <= sequence < MAX_CHUNKS:
            raise InvalidInputError("Meeting is finished or exceeds four hours")
        existing = await repo_query(
            "SELECT text FROM meeting_chunk WHERE meeting_id = $id AND sequence = $sequence",
            {"id": meeting_id, "sequence": sequence},
        )
        if existing:
            return {"text": existing[0]["text"]}
        await repo_query(
            "UPDATE $id SET total_chunks = math::max([total_chunks, $total]) WHERE status = 'recording'",
            {"id": ensure_record_id(meeting_id), "total": sequence + 1},
        )
        raw = await audio.read(MAX_AUDIO_BYTES + 1)
        text = await transcribe_audio(raw)
        # Guard the write against a concurrent finish/discard. The unique index
        # makes repeat deliveries safe without storing audio or duplicate text.
        await repo_query(
            "BEGIN TRANSACTION; LET $meeting = SELECT * FROM ONLY $id; "
            "IF $meeting.status = 'recording' { "
            "UPSERT meeting_chunk SET meeting_id = $meeting_id, sequence = $sequence, text = $text "
            "WHERE meeting_id = $meeting_id AND sequence = $sequence; "
            "}; COMMIT TRANSACTION;",
            {
                "id": ensure_record_id(meeting_id),
                "meeting_id": meeting_id,
                "sequence": sequence,
                "text": text,
            },
        )
        return {"text": text}
    finally:
        await audio.close()


@router.post("/notebooks/{notebook_id}/meetings/{meeting_id}/finish")
async def finish_meeting(notebook_id: str, meeting_id: str, data: FinishMeeting):
    meeting = await get_meeting(notebook_id, meeting_id)
    if meeting.status == "recording":
        total = max(data.total_chunks, meeting.total_chunks)
        text, missing = await assemble_transcript(meeting_id, total)
        await repo_query(
            "UPDATE $id SET transcript = $text, missing_chunks = $missing, total_chunks = $total, interrupted = $interrupted, status = 'review' "
            "WHERE status = 'recording'",
            {
                "id": ensure_record_id(meeting_id),
                "text": text,
                "missing": missing,
                "total": total,
                "interrupted": data.interrupted,
            },
        )
        meeting = await get_meeting(notebook_id, meeting_id)
        if text.strip() and len(missing) < total:
            await queue_summary(meeting)
    return await view(await get_meeting(notebook_id, meeting_id))


async def queue_summary(meeting: Meeting):
    import commands.meeting_commands  # noqa: F401

    if meeting.status != "review" or not meeting.transcript:
        raise InvalidInputError("Finish recording before generating a summary")
    if meeting.summary_job:
        job = await CommandService.get_command_status(meeting.summary_job)
        if job["status"] in ("new", "queued", "running"):
            raise InvalidInputError(
                "A summary is already queued or running; check the worker"
            )
    token = uuid4().hex
    await repo_query(
        "UPDATE $id SET summary_token = $summary_token, summary_error = '' WHERE status = 'review'",
        {"id": ensure_record_id(str(meeting.id)), "summary_token": token},
    )
    try:
        job_id = await CommandService.submit_command_job(
            "open_notebook",
            "summarize_meeting",
            {"meeting_id": str(meeting.id), "token": token},
        )
    except Exception:
        await repo_query(
            "UPDATE $id SET summary_error = $error WHERE summary_token = $summary_token",
            {
                "id": ensure_record_id(str(meeting.id)),
                "summary_token": token,
                "error": "Could not queue summary. Transcript saved; check the worker and retry.",
            },
        )
        return
    await repo_query(
        "UPDATE $id SET summary_job = $job WHERE summary_token = $summary_token",
        {
            "id": ensure_record_id(str(meeting.id)),
            "summary_token": token,
            "job": job_id,
        },
    )


@router.post("/notebooks/{notebook_id}/meetings/{meeting_id}/summarize")
async def retry_summary(notebook_id: str, meeting_id: str):
    await queue_summary(await get_meeting(notebook_id, meeting_id))
    return await view(await get_meeting(notebook_id, meeting_id))


@router.patch("/notebooks/{notebook_id}/meetings/{meeting_id}")
async def edit_meeting(notebook_id: str, meeting_id: str, data: EditMeeting):
    meeting = await get_meeting(notebook_id, meeting_id)
    if meeting.status == "recording":
        raise InvalidInputError("Finish recording before editing")
    if data.revision != meeting.revision:
        raise InvalidInputError("Meeting changed; reload it before saving your edits")
    # Keep the validated MeetingAction objects: a model_dump() would turn them
    # into plain dicts that model_copy does not convert back.
    edited = meeting.model_copy(update=dict(data))
    # A transaction keeps approved action checkboxes and the searchable note
    # consistent. Editing invalidates any in-flight generated summary.
    await repo_query(
        "BEGIN TRANSACTION; LET $draft = SELECT * FROM ONLY $id; "
        "IF $draft.revision != $revision { THROW 'Meeting changed; reload before editing'; }; "
        "UPDATE $id SET title = $title, transcript = $transcript, summary = $summary, actions = $actions, "
        "summary_token = '', revision += 1; "
        "IF $draft.status = 'approved' { UPDATE $note SET title = $title, content = $content; }; "
        "COMMIT TRANSACTION;",
        {
            "id": ensure_record_id(meeting_id),
            **data.model_dump(),
            "revision": data.revision,
            "note": ensure_record_id(meeting.note_id) if meeting.note_id else None,
            "content": meeting_content(edited),
        },
    )
    if meeting.status == "approved":
        from loguru import logger
        from surreal_commands import submit_command

        try:
            submit_command("open_notebook", "embed_note", {"note_id": meeting.note_id})
        except Exception:
            logger.warning("Meeting edited; embedding submission failed")
    return await view(await get_meeting(notebook_id, meeting_id))


@router.post("/notebooks/{notebook_id}/meetings/{meeting_id}/approve")
async def approve(notebook_id: str, meeting_id: str):
    return {
        "note_id": await approve_meeting(await get_meeting(notebook_id, meeting_id))
    }


@router.delete("/notebooks/{notebook_id}/meetings/{meeting_id}")
async def discard(notebook_id: str, meeting_id: str):
    meeting = await get_meeting(notebook_id, meeting_id)
    if meeting.status == "approved":
        raise InvalidInputError("Delete the approved note through Notes instead")
    await repo_query(
        "BEGIN TRANSACTION; LET $draft = SELECT * FROM ONLY $id; "
        "IF $draft.status != 'approved' { "
        "DELETE meeting_chunk WHERE meeting_id = $meeting_id; DELETE $id; "
        "}; COMMIT TRANSACTION;",
        {"id": ensure_record_id(meeting_id), "meeting_id": meeting_id},
    )
    return {"deleted": True}
