"""Interactive HTML explainers generated from a notebook (background job)."""

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, HTTPException
from loguru import logger

from api.command_service import CommandService
from api.generation_jobs import list_generation_jobs
from api.models import (
    ExplainerCreateRequest,
    ExplainerJobResponse,
    ExplainerJobSummary,
)
from open_notebook.domain.notebook import Notebook
from open_notebook.exceptions import InvalidInputError

router = APIRouter()

WORKER_FAILED_MESSAGE = "The background worker could not run the explainer job."
STALE_JOB_MESSAGE = (
    "The explainer job stopped unexpectedly or never started. Check that the "
    "worker is running, then start a new explainer."
)


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
    requested in the last 24 hours, newest first. A job queued or running for
    more than 30 minutes is reported as failed.

    This is what the notes pane shows, so a job that fails (no model, model
    error, worker problem) stays visible with its reason instead of vanishing.
    """
    notebook = await Notebook.get(notebook_id)  # NotFoundError -> 404
    return await list_generation_jobs(
        "generate_explainer",
        str(notebook.id),
        worker_failed_message=WORKER_FAILED_MESSAGE,
        stale_message=STALE_JOB_MESSAGE,
    )
