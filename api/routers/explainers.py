"""Interactive HTML explainers generated from a notebook (background job)."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from loguru import logger

from api.command_service import CommandService
from api.models import (
    ExplainerCreateRequest,
    ExplainerJobResponse,
    ExplainerJobSummary,
)
from open_notebook.database.repository import repo_query
from open_notebook.domain.notebook import Notebook
from open_notebook.exceptions import InvalidInputError

router = APIRouter()

# Finished jobs older than this drop out of the notes pane; active ones never do.
RECENT_JOBS_WINDOW = timedelta(hours=24)
MAX_JOBS = 10
WORKER_FAILED_MESSAGE = "The background worker could not run the explainer job."


@router.post("/notebooks/{notebook_id}/explainers", response_model=ExplainerJobResponse)
async def create_explainer(notebook_id: str, request: ExplainerCreateRequest):
    """Start generating an explainer; the result appears as a note in the notebook.

    Follow it with ``GET /api/notebooks/{id}/explainers/jobs`` (or
    ``GET /api/commands/jobs/{job_id}``): on success the job has ``note_id``,
    otherwise ``error_message`` says why.
    """
    # Imported here so the command is registered before submit_command runs.
    import commands.explainer_commands  # noqa: F401

    notebook = await Notebook.get(notebook_id)  # NotFoundError -> 404
    if not await notebook.get_sources():
        raise InvalidInputError(
            "Add at least one source to this notebook before generating an explainer."
        )

    try:
        job_id = await CommandService.submit_command_job(
            "open_notebook",
            "generate_explainer",
            {
                "notebook_id": str(notebook.id),
                "mode": request.mode,
                "instructions": (request.instructions or "").strip() or None,
                "requested_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as e:
        logger.error(f"Failed to submit generate_explainer job: {e}")
        raise HTTPException(status_code=500, detail="Failed to start the explainer")

    return ExplainerJobResponse(
        job_id=job_id, status="queued", notebook_id=str(notebook.id)
    )


@router.get(
    "/notebooks/{notebook_id}/explainers/jobs",
    response_model=List[ExplainerJobSummary],
)
async def list_explainer_jobs(notebook_id: str):
    """Explainer jobs for this notebook: every queued or running one, plus those
    that finished in the last 24 hours, newest first.

    This is what the notes pane shows, so a job that fails (no model, model
    error, worker problem) stays visible with its reason instead of vanishing.
    """
    notebook = await Notebook.get(notebook_id)  # NotFoundError -> 404
    rows = await repo_query(
        "SELECT id, status, args, result, error_message FROM command "
        "WHERE app = 'open_notebook' AND name = 'generate_explainer' "
        "AND args.notebook_id = $notebook_id",
        {"notebook_id": str(notebook.id)},
    )
    cutoff = datetime.now(timezone.utc) - RECENT_JOBS_WINDOW
    jobs = [job for job in (_summarize(row) for row in rows or []) if job]
    jobs = [
        job
        for job in jobs
        if job.status in ("queued", "running") or _after(job.requested_at, cutoff)
    ]
    jobs.sort(key=lambda job: job.requested_at or "", reverse=True)
    return jobs[:MAX_JOBS]


def _summarize(row: Dict[str, Any]) -> Optional[ExplainerJobSummary]:
    args = row.get("args") or {}
    requested_at = args.get("requested_at")
    if not requested_at:
        return None  # submitted before job tracking existed
    result = row.get("result") or {}
    raw = str(row.get("status") or "")
    if raw == "new":
        status = "queued"
    elif raw == "running":
        status = "running"
    elif raw == "completed" and result.get("success"):
        status = "completed"
    else:  # failed, canceled, or completed with success=False
        status = "failed"
    error = None
    if status == "failed":
        error = (
            result.get("error_message")
            or row.get("error_message")
            or WORKER_FAILED_MESSAGE
        )
    return ExplainerJobSummary(
        job_id=str(row.get("id")),
        status=status,  # type: ignore[arg-type]
        requested_at=requested_at,
        note_id=result.get("note_id") if status == "completed" else None,
        title=result.get("title") if status == "completed" else None,
        error_message=error,
    )


def _after(stamp: Optional[str], cutoff: datetime) -> bool:
    try:
        when = datetime.fromisoformat(stamp or "")
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when >= cutoff
