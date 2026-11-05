"""Interactive HTML explainers generated from a notebook (background job)."""

from fastapi import APIRouter, HTTPException
from loguru import logger

from api.command_service import CommandService
from api.models import ExplainerCreateRequest, ExplainerJobResponse
from open_notebook.domain.notebook import Notebook
from open_notebook.exceptions import InvalidInputError

router = APIRouter()


@router.post("/notebooks/{notebook_id}/explainers", response_model=ExplainerJobResponse)
async def create_explainer(notebook_id: str, request: ExplainerCreateRequest):
    """Start generating an explainer; the result appears as a note in the notebook.

    Poll ``GET /api/commands/jobs/{job_id}``: on success ``result.note_id`` is the
    new note, otherwise ``result.error_message`` says why.
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
            },
        )
    except Exception as e:
        logger.error(f"Failed to submit generate_explainer job: {e}")
        raise HTTPException(status_code=500, detail="Failed to start the explainer")

    return ExplainerJobResponse(
        job_id=job_id, status="queued", notebook_id=str(notebook.id)
    )
