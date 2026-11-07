"""Static SVG infographics generated from a notebook (background job)."""

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, HTTPException
from loguru import logger

from api.command_service import CommandService
from api.generation_jobs import list_generation_jobs
from api.models import (
    ExplainerJobResponse,
    ExplainerJobSummary,
    InfographicCreateRequest,
)
from open_notebook.domain.notebook import Notebook
from open_notebook.exceptions import InvalidInputError
from open_notebook.utils.infographic import LAYOUTS, STYLES

router = APIRouter()

NO_SOURCES_MESSAGE = (
    "Add at least one source to this notebook before generating an infographic"
)
WORKER_FAILED_MESSAGE = "The background worker could not run the infographic job."
STALE_JOB_MESSAGE = (
    "The infographic job stopped unexpectedly or never started. Check that the "
    "worker is running, then start a new infographic."
)


@router.post(
    "/notebooks/{notebook_id}/infographics", response_model=ExplainerJobResponse
)
async def create_infographic(notebook_id: str, request: InfographicCreateRequest):
    """Start generating an infographic; the result appears as a note.

    Follow it with ``GET /api/notebooks/{id}/infographics/jobs``: on success the
    job has ``note_id``, otherwise ``error_message`` says why.
    """
    # Imported here so the command is registered before submit_command runs.
    import commands.infographic_commands  # noqa: F401

    if request.style not in STYLES:
        raise InvalidInputError(f"Unknown infographic style: {request.style}")
    if request.layout not in LAYOUTS:
        raise InvalidInputError(f"Unknown infographic layout: {request.layout}")

    notebook = await Notebook.get(notebook_id)  # NotFoundError -> 404
    if not await notebook.get_sources():
        raise InvalidInputError(NO_SOURCES_MESSAGE + ".")

    try:
        job_id = await CommandService.submit_command_job(
            "open_notebook",
            "generate_infographic",
            {
                "notebook_id": str(notebook.id),
                "style": request.style,
                "layout": request.layout,
                "aspect": request.aspect,
                "instructions": (request.instructions or "").strip() or None,
                "requested_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as e:
        logger.error(f"Failed to submit generate_infographic job: {e}")
        raise HTTPException(status_code=500, detail="Failed to start the infographic")

    return ExplainerJobResponse(
        job_id=job_id, status="queued", notebook_id=str(notebook.id)
    )


@router.get(
    "/notebooks/{notebook_id}/infographics/jobs",
    response_model=List[ExplainerJobSummary],
)
async def list_infographic_jobs(notebook_id: str):
    """Infographic jobs for this notebook: every queued or running one, plus
    those requested in the last 24 hours, newest first. A job queued or running
    for more than 30 minutes is reported as failed."""
    notebook = await Notebook.get(notebook_id)  # NotFoundError -> 404
    return await list_generation_jobs(
        "generate_infographic",
        str(notebook.id),
        worker_failed_message=WORKER_FAILED_MESSAGE,
        stale_message=STALE_JOB_MESSAGE,
    )
