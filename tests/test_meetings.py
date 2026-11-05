"""Meeting privacy, loss reporting, provider cleanup and publication contracts."""

import io
import json
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient

from api import meeting_service
from api.routers import meetings
from commands.meeting_commands import (
    SummarizeMeetingInput,
    parse_summary,
    summarize_meeting_command,
)
from open_notebook.domain.meeting import Meeting
from open_notebook.exceptions import (
    ConfigurationError,
    InvalidInputError,
    NotFoundError,
)


def draft(**kwargs):
    return Meeting(
        id="meeting:test", notebook_id="notebook:test", title="Planning", **kwargs
    )


def wav_bytes(frames=1600):
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * frames)
    return output.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_transcription_always_removes_private_audio(fails):
    paths = []

    async def transcribe(*, audio_file):
        paths.append(Path(audio_file))
        assert paths[-1].is_file()
        assert paths[-1].parent.stat().st_mode & 0o777 == 0o700
        if fails:
            raise RuntimeError("provider failed")
        return SimpleNamespace(text=" Hello ")

    with patch.object(
        meeting_service.model_manager,
        "get_speech_to_text",
        AsyncMock(return_value=SimpleNamespace(atranscribe=transcribe)),
    ):
        if fails:
            with pytest.raises(Exception):
                await meeting_service.transcribe_audio(wav_bytes())
        else:
            assert await meeting_service.transcribe_audio(wav_bytes()) == "Hello"
    assert len(paths) == 1
    assert not paths[0].exists()
    assert not paths[0].parent.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "audio",
    [b"", b"not WAV", wav_bytes(16000 * 26), wav_bytes()[:-2], b"x" * 4_000_001],
)
async def test_invalid_audio_never_reaches_provider(audio):
    with patch.object(
        meeting_service.model_manager, "get_speech_to_text", AsyncMock()
    ) as provider:
        with pytest.raises(InvalidInputError):
            await meeting_service.transcribe_audio(audio)
        provider.assert_not_called()


@pytest.mark.asyncio
async def test_transcription_requires_configured_model():
    with patch.object(
        meeting_service.model_manager,
        "get_speech_to_text",
        AsyncMock(return_value=None),
    ):
        with pytest.raises(ConfigurationError):
            await meeting_service.transcribe_audio(wav_bytes())


@pytest.mark.asyncio
async def test_transcript_preserves_order_and_explicit_gaps():
    with patch.object(
        meeting_service,
        "repo_query",
        AsyncMock(
            return_value=[
                {"sequence": 2, "text": "Last"},
                {"sequence": 0, "text": "First"},
            ]
        ),
    ):
        transcript, missing = await meeting_service.assemble_transcript(
            "meeting:test", 4
        )
    assert missing == [1, 3]
    assert transcript.index("First") < transcript.index("Last")
    assert "[00:20] [Missing audio section]" in transcript
    assert "[01:00] [Missing audio section]" in transcript


@pytest.mark.asyncio
async def test_chunk_delivery_is_idempotent_and_upload_closed():
    audio = UploadFile(io.BytesIO(b"unused"))
    with (
        patch.object(meetings, "get_meeting", AsyncMock(return_value=draft())),
        patch.object(
            meetings,
            "repo_query",
            AsyncMock(return_value=[{"text": "Already transcribed"}]),
        ),
        patch.object(meetings, "transcribe_audio", AsyncMock()) as transcribe,
    ):
        assert await meetings.upload_chunk(
            "notebook:test", "meeting:test", 0, audio
        ) == {"text": "Already transcribed"}
        transcribe.assert_not_called()
        assert audio.file.closed


@pytest.mark.asyncio
async def test_wrong_notebook_cannot_access_meeting():
    with patch.object(meetings.Meeting, "get", AsyncMock(return_value=draft())):
        with pytest.raises(NotFoundError):
            await meetings.get_meeting("notebook:other", "meeting:test")


@pytest.mark.asyncio
async def test_drafts_cannot_be_published_during_recording():
    with patch.object(meeting_service.Notebook, "get", AsyncMock()):
        with pytest.raises(InvalidInputError):
            await meeting_service.approve_meeting(draft(transcript="Some words"))


@pytest.mark.asyncio
async def test_repeated_approval_returns_same_note_without_reembedding():
    with (
        patch.object(meeting_service.Notebook, "get", AsyncMock()),
        patch.object(meeting_service, "repo_query", AsyncMock()) as query,
        patch.object(meeting_service, "submit_command") as submit,
    ):
        assert (
            await meeting_service.approve_meeting(
                draft(status="approved", note_id="note:published")
            )
            == "note:published"
        )
        query.assert_not_called()
        submit.assert_not_called()


def test_summary_requires_grounded_actions():
    result: dict = {
        "summary": "Delivery agreed",
        "actions": [
            {
                "text": "Ship report",
                "owner": "Sam",
                "due": "Friday",
                "evidence": "Sam will ship Friday.",
                "done": True,
            }
        ],
    }
    parsed = parse_summary(
        "```json\n" + json.dumps(result) + "\n```", "Sam will ship Friday."
    )
    assert parsed.actions[0].done is False
    result["actions"][0]["evidence"] = "An invented quote"
    with pytest.raises(InvalidInputError):
        parse_summary(json.dumps(result), "Sam will ship Friday.")


@pytest.mark.asyncio
async def test_stale_summary_cannot_overwrite_user_edits():
    with (
        patch(
            "commands.meeting_commands.Meeting.get",
            AsyncMock(return_value=draft(status="review", summary_token="new")),
        ),
        patch(
            "commands.meeting_commands.provision_langchain_model", AsyncMock()
        ) as provision,
    ):
        result = await summarize_meeting_command(
            SummarizeMeetingInput(meeting_id="meeting:test", token="old")
        )
        assert not result.success
        provision.assert_not_called()


@pytest.mark.asyncio
async def test_summary_provider_failure_retains_transcript():
    meeting = draft(
        status="review", summary_token="current", transcript="Original words"
    )
    with (
        patch("commands.meeting_commands.Meeting.get", AsyncMock(return_value=meeting)),
        patch(
            "commands.meeting_commands.provision_langchain_model",
            AsyncMock(side_effect=ConfigurationError("No chat model")),
        ),
        patch("commands.meeting_commands.repo_query", AsyncMock()) as query,
    ):
        result = await summarize_meeting_command(
            SummarizeMeetingInput(meeting_id="meeting:test", token="current")
        )
    assert not result.success
    assert meeting.transcript == "Original words"
    assert "summary_error" in query.call_args.args[0]
    assert "transcript =" not in query.call_args.args[0]


@pytest.mark.asyncio
async def test_completed_poll_returns_fresh_summary():
    stale = draft(status="review", summary_job="command:test", summary_token="current")
    fresh = stale.model_copy(update={"summary": "New summary"})
    with (
        patch.object(
            meetings.CommandService,
            "get_command_status",
            AsyncMock(
                return_value={"status": "completed", "result": {"success": True}}
            ),
        ),
        patch.object(meetings.Meeting, "get", AsyncMock(return_value=fresh)),
    ):
        result = await meetings.view(stale)
    assert result["summary"] == "New summary"
    assert result["summary_status"] == "completed"


def test_api_model_configuration_error_reaches_global_handler():
    from api.main import app

    with (
        patch.object(meetings.Notebook, "get", AsyncMock()),
        patch.object(
            meetings.model_manager, "get_speech_to_text", AsyncMock(return_value=None)
        ),
    ):
        response = TestClient(app).post(
            "/api/notebooks/notebook:test/meetings", json={"title": "Meeting"}
        )
    assert response.status_code == 422


def test_meeting_summary_registered_for_worker():
    from commands import summarize_meeting_command as registered

    assert registered is summarize_meeting_command


@pytest.mark.asyncio
async def test_stale_editor_does_not_overwrite_newer_meeting():
    current = draft(status="review", revision=2, transcript="Words")
    with (
        patch.object(meetings, "get_meeting", AsyncMock(return_value=current)),
        patch.object(meetings, "repo_query", AsyncMock()) as query,
    ):
        with pytest.raises(InvalidInputError, match="Meeting changed"):
            await meetings.edit_meeting(
                "notebook:test",
                "meeting:test",
                meetings.EditMeeting(
                    revision=1, title="Old", summary="Old", actions=[], transcript="Old"
                ),
            )
        query.assert_not_called()


@pytest.mark.asyncio
async def test_edit_with_actions_renders_the_note_content():
    """Saving a reviewed meeting that has actions must not crash.

    Regression: model_copy(update=model_dump()) left the actions as plain
    dicts, so building the note content raised AttributeError (HTTP 500) for
    every meeting the summary had produced actions for.
    """
    current = draft(status="approved", revision=2, transcript="Words", note_id="note:a")
    action = {
        "text": "Send budget",
        "owner": "Priya",
        "due": "Friday",
        "evidence": "Priya will send it",
        "done": True,
    }
    with (
        patch.object(meetings, "get_meeting", AsyncMock(return_value=current)),
        patch.object(meetings, "repo_query", AsyncMock()) as query,
        patch("surreal_commands.submit_command", return_value="command:test"),
    ):
        await meetings.edit_meeting(
            "notebook:test",
            "meeting:test",
            meetings.EditMeeting(
                revision=2,
                title="Reviewed",
                summary="Plan agreed",
                actions=[action],
                transcript="Words",
            ),
        )
    content = query.await_args_list[0].args[1]["content"]
    assert "- [x] Send budget — Priya — Friday" in content
    assert "Evidence: Priya will send it" in content
