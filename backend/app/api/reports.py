"""Report routes. Thin: every number comes from app/services/reports.py."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from app.core.config import Settings, get_settings
from app.core.deps import CurrentUser, DbSession
from app.schemas.report import ReportSummary
from app.services import reports
from app.services.reports import GroupBy

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/summary", response_model=ReportSummary)
def read_summary(
    user: CurrentUser,
    db: DbSession,
    settings: Annotated[Settings, Depends(get_settings)],
    starts_from: Annotated[AwareDatetime, Query(alias="from")],
    starts_before: Annotated[AwareDatetime, Query(alias="to")],
    group_by: GroupBy = GroupBy.DAY,
    tz: Annotated[str, Query(max_length=64)] = "UTC",
    project_id: UUID | None = None,
    team_id: UUID | None = None,
) -> object:
    """Totals for a half-open range, grouped by period, project, tag or task.

    ``project_id`` limits the totals to one project (used with ``group_by=task``).

    ``team_id`` makes it the team report: every member's totals on the team's
    projects, for anyone in the team. Usually with ``group_by=user`` or
    ``project``; never ``tag``.

    ``tz`` is an IANA name such as ``Europe/Helsinki``; the browser knows it as
    ``Intl.DateTimeFormat().resolvedOptions().timeZone``. In a team report it
    only says which days were picked: the report counts whole days in the
    organisation's zone.
    """
    return reports.summarize(
        db,
        user=user,
        starts_from=starts_from,
        starts_before=starts_before,
        group_by=group_by,
        tz=tz,
        project_id=project_id,
        team_id=team_id,
        team_time_zone=settings.time_zone,
    )
