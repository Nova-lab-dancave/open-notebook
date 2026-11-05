"""Opt-in real SurrealDB tests. Uses a unique, disposable namespace.

MEETINGS_TEST_DATABASE_URL=ws://localhost:18000/rpc SURREAL_USER=root \\
  uv run pytest tests/test_meetings_integration.py
"""

import io
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import UploadFile

from api import meeting_service
from api.routers import meetings
from open_notebook.database.async_migrate import AsyncMigrationManager
from open_notebook.database.repository import db_connection, repo_query
from open_notebook.domain.meeting import Meeting
from open_notebook.domain.notebook import Note, Notebook

pytestmark = pytest.mark.skipif(
    not os.getenv("MEETINGS_TEST_DATABASE_URL"),
    reason="Requires opt-in isolated SurrealDB",
)


@pytest.mark.asyncio
async def test_database_meeting_lifecycle_and_rollback(monkeypatch):
    namespace = "meeting_test_" + uuid4().hex
    monkeypatch.setenv("SURREAL_URL", os.environ["MEETINGS_TEST_DATABASE_URL"])
    monkeypatch.setenv("SURREAL_NAMESPACE", namespace)
    monkeypatch.setenv("SURREAL_DATABASE", "test")
    try:
        await AsyncMigrationManager().run_migration_up()
        notebook = Notebook(name="Meeting test", description="")
        await notebook.save()
        meeting = Meeting(notebook_id=str(notebook.id), title="Planning")
        await meeting.save()
        with patch.object(
            meetings,
            "transcribe_audio",
            AsyncMock(return_value="Sam will ship Friday."),
        ):
            for sequence in (0, 0, 2):
                await meetings.upload_chunk(
                    str(notebook.id),
                    str(meeting.id),
                    sequence,
                    UploadFile(io.BytesIO(b"audio")),
                )
        assert len(await repo_query("SELECT * FROM meeting_chunk")) == 2
        with patch.object(meetings, "queue_summary", AsyncMock()):
            result = await meetings.finish_meeting(
                str(notebook.id),
                str(meeting.id),
                meetings.FinishMeeting(total_chunks=3),
            )
        assert result["missing_chunks"] == [1]
        assert "[00:20] [Missing audio section]" in result["transcript"]
        assert not await notebook.get_notes()
        assert not await repo_query("SELECT * FROM note")
        edit = meetings.EditMeeting(
            title="Reviewed",
            summary="Plan agreed",
            actions=[],
            transcript=result["transcript"],
        )
        await meetings.edit_meeting(str(notebook.id), str(meeting.id), edit)
        with patch.object(
            meeting_service, "submit_command", return_value="command:test"
        ):
            note_id = await meeting_service.approve_meeting(
                await Meeting.get(str(meeting.id))
            )
            assert note_id == await meeting_service.approve_meeting(
                await Meeting.get(str(meeting.id))
            )
        assert len(await notebook.get_notes()) == 1
        edit.revision = (await Meeting.get(str(meeting.id))).revision
        edit.summary = "Updated after approval"
        with patch("surreal_commands.submit_command", return_value="command:test"):
            await meetings.edit_meeting(str(notebook.id), str(meeting.id), edit)
        assert "Updated after approval" in ((await Note.get(note_id)).content or "")
        assert (await Meeting.get(str(meeting.id))).summary == edit.summary
        await (await Note.get(note_id)).delete()
        assert not await repo_query("SELECT * FROM meeting")
        assert not await repo_query("SELECT * FROM meeting_chunk")
        published = Meeting(
            notebook_id=str(notebook.id),
            title="Keep after rollback",
            status="review",
            transcript="Published words",
        )
        await published.save()
        with patch.object(
            meeting_service, "submit_command", return_value="command:test"
        ):
            note_id = await meeting_service.approve_meeting(published)
        # Rollback removes drafts but never deletes the published note.
        await repo_query(
            Path("open_notebook/database/migrations/105_down.surrealql").read_text()
        )
        assert await Note.get(note_id)
        await repo_query(
            Path("open_notebook/database/migrations/105.surrealql").read_text()
        )
        draft = Meeting(notebook_id=str(notebook.id), title="Unfinished")
        await draft.save()
        await notebook.delete()
        assert not await repo_query("SELECT * FROM meeting")
        assert not await repo_query("SELECT * FROM meeting_chunk")
    finally:
        # Namespace is generated locally, never user input.
        async with db_connection() as connection:
            await connection.query(f"REMOVE NAMESPACE {namespace}")
