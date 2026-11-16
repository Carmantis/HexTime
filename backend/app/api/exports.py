"""PDF export. The one route that answers with a file instead of JSON."""

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import AwareDatetime

from app.core.config import Settings, get_settings
from app.core.deps import CurrentUser, DbSession
from app.core.errors import ValidationFailedError
from app.core.i18n import resolve_locale
from app.reports.data import (
    ReportHeader,
    build_period_report,
    build_project_report,
    build_team_report,
)
from app.reports.formatting import slugify
from app.reports.pdf import render_period_pdf, render_project_pdf, render_team_pdf

router = APIRouter(prefix="/exports", tags=["exports"])


class ExportScope(StrEnum):
    """What a report covers. One route for all of them, so a new scope is a
    new branch here and a new builder, not a new endpoint."""

    PERIOD = "period"
    PROJECT = "project"
    TEAM = "team"


def _pdf(content: bytes, name: str, header: ReportHeader) -> Response:
    """Send the PDF as a download named after what it covers."""
    span = f"{header.first_day.isoformat()}-{header.last_day.isoformat()}"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}-{span}.pdf"'},
    )


@router.get(
    "/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
def export_pdf(
    user: CurrentUser,
    db: DbSession,
    settings: Annotated[Settings, Depends(get_settings)],
    starts_from: Annotated[AwareDatetime, Query(alias="from")],
    starts_before: Annotated[AwareDatetime, Query(alias="to")],
    scope: ExportScope = ExportScope.PERIOD,
    target_id: Annotated[UUID | None, Query(alias="id")] = None,
    tz: Annotated[str, Query(max_length=64)] = "UTC",
    locale: Annotated[str | None, Query(max_length=5)] = None,
    mine: bool = False,
) -> Response:
    """A PDF report for a half-open range, in the requested language.

    ``scope=period`` covers all of the user's time; ``scope=project&id=…`` one
    project, with hours by task; ``scope=team&id=…`` a team's totals on its
    projects, per member and per project, for anyone in the team. With
    ``mine=true`` the team scope is the user's own hours on the team's
    projects instead, entry list included.
    """
    language = resolve_locale(locale, user.locale or settings.default_locale)
    span = {"starts_from": starts_from, "starts_before": starts_before, "tz": tz}

    if scope is ExportScope.PERIOD:
        report = build_period_report(db, user=user, **span)
        return _pdf(render_period_pdf(report, language), "hextime", report.header)

    if scope is ExportScope.PROJECT:
        if target_id is None:
            raise ValidationFailedError("a project report needs the project's id")
        project_report = build_project_report(db, user=user, project_id=target_id, **span)
        return _pdf(
            render_project_pdf(project_report, language),
            f"hextime-{slugify(project_report.project.name)}",
            project_report.header,
        )

    if target_id is None:
        raise ValidationFailedError("a team report needs the team's id")
    if mine:
        own = build_period_report(db, user=user, team_id=target_id, **span)
        assert own.team_name is not None
        return _pdf(
            render_period_pdf(own, language),
            f"hextime-{slugify(own.team_name)}-{slugify(user.display_name)}",
            own.header,
        )
    team_report = build_team_report(
        db, user=user, team_id=target_id, team_time_zone=settings.time_zone, **span
    )
    return _pdf(
        render_team_pdf(team_report, language),
        f"hextime-{slugify(team_report.team_name)}",
        team_report.header,
    )
