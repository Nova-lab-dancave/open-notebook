"""Job lists for notebook generators (explainers, infographics).

A generator runs as a surreal-commands job whose args carry ``notebook_id`` and
``requested_at`` and whose result carries ``success``, ``note_id``, ``title``
and ``error_message``. The notes pane lists those jobs so one that fails stays
visible with its reason instead of vanishing.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from api.models import ExplainerJobSummary
from open_notebook.database.repository import repo_query

# Finished jobs older than this drop out of the notes pane.
RECENT_JOBS_WINDOW = timedelta(hours=24)
# A generation takes minutes. A job still queued or running after this was
# orphaned (worker restarted or died mid-job) and is shown as failed, so the
# pane stops polling and the row can be dismissed.
STALE_JOB_AFTER = timedelta(minutes=30)
MAX_JOBS = 10


async def list_generation_jobs(
    command_name: str,
    notebook_id: str,
    *,
    worker_failed_message: str,
    stale_message: str,
) -> List[ExplainerJobSummary]:
    """Jobs of ``command_name`` for the notebook: every queued or running one,
    plus those requested in the last 24 hours, newest first. A job queued or
    running for more than 30 minutes is reported as failed."""
    rows = await repo_query(
        "SELECT id, status, args, result, error_message FROM command "
        "WHERE app = 'open_notebook' AND name = $name "
        "AND args.notebook_id = $notebook_id",
        {"name": command_name, "notebook_id": notebook_id},
    )
    now = datetime.now(timezone.utc)
    jobs = [
        job
        for job in (
            summarize_job(row, now, worker_failed_message, stale_message)
            for row in rows or []
        )
        if job
    ]
    jobs = [
        job
        for job in jobs
        if job.status in ("queued", "running")
        or _after(job.requested_at, now - RECENT_JOBS_WINDOW)
    ]
    jobs.sort(key=lambda job: job.requested_at or "", reverse=True)
    return jobs[:MAX_JOBS]


def summarize_job(
    row: Dict[str, Any],
    now: datetime,
    worker_failed_message: str,
    stale_message: str,
) -> Optional[ExplainerJobSummary]:
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
    if status in ("queued", "running") and not _after(
        requested_at, now - STALE_JOB_AFTER
    ):
        status, error = "failed", stale_message
    elif status == "failed":
        error = (
            result.get("error_message")
            or row.get("error_message")
            or worker_failed_message
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
