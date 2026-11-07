"""Meeting drafts are isolated from notes, search and embeddings until approval."""

from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from open_notebook.domain.base import ObjectModel

MAX_CHUNKS = 720  # Four hours at twenty seconds per chunk.
MAX_TRANSCRIPT = 400_000


class MeetingAction(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    owner: str = Field(default="", max_length=200)
    due: str = Field(default="", max_length=200)
    evidence: str = Field(min_length=1, max_length=3000)
    done: bool = False


class MeetingSummary(BaseModel):
    summary: str = Field(min_length=1, max_length=30_000)
    actions: list[MeetingAction] = Field(default_factory=list, max_length=100)


class Meeting(ObjectModel):
    table_name: ClassVar[str] = "meeting"
    notebook_id: str
    title: str = Field(min_length=1, max_length=200)
    capture_mode: Literal["microphone", "shared"] = "microphone"
    status: Literal["recording", "review", "approved"] = "recording"
    transcript: str = Field(default="", max_length=MAX_TRANSCRIPT)
    summary: str = Field(default="", max_length=30_000)
    actions: list[MeetingAction] = Field(default_factory=list, max_length=100)
    total_chunks: int = 0
    missing_chunks: list[int] = Field(default_factory=list)
    revision: int = 0
    interrupted: bool = False
    summary_token: str = ""
    summary_job: str = ""
    summary_error: str = ""
    note_id: str = ""
