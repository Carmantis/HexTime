"""The running timer.

Thin routing only: parse the request, call the service, return the result.
Every rule lives in app/services/timer.py.
"""

from fastapi import APIRouter, status

from app.core.deps import CurrentUser, DbSession
from app.schemas.time_entry import TimeEntryRead, TimerStart, TimerStop
from app.services import timer

router = APIRouter(prefix="/timer", tags=["timer"])


@router.get("", response_model=TimeEntryRead | None)
def read_running_timer(user: CurrentUser, db: DbSession) -> object:
    """The entry currently being timed, or null when nothing is running."""
    return timer.get_running(db, user.id)


@router.post("/start", response_model=TimeEntryRead, status_code=status.HTTP_201_CREATED)
def start_timer(payload: TimerStart, user: CurrentUser, db: DbSession) -> object:
    """Start a timer, stopping whatever was already running."""
    return timer.start(
        db,
        user=user,
        project_id=payload.project_id,
        task_id=payload.task_id,
        description=payload.description,
        billable=payload.billable,
        tag_ids=payload.tag_ids,
    )


@router.post("/stop", response_model=TimeEntryRead)
def stop_timer(user: CurrentUser, db: DbSession, payload: TimerStop | None = None) -> object:
    """Stop the running timer and return the finished entry.

    Without a body the timer stops now. With ``{"at": ...}`` it stops at the
    moment the user pressed Stop, for a request retried after an outage.
    """
    if payload is not None and payload.at is not None:
        return timer.stop_at_client_time(db, user=user, at=payload.at)
    return timer.stop(db, user=user)
