"""The data of a PDF report, before anything is drawn.

Kept apart from the PDF drawing so the numbers can be tested as plain values,
without reading text back out of a PDF. Every total comes from
app/services/reports.py — the same function the Reports view calls — so the
PDF and the screen cannot disagree.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationFailedError
from app.models import Project, Task, Team, TimeEntry, User
from app.services import entries as entries_service
from app.services import ownership, reports
from app.services import projects as projects_service
from app.services.reports import GroupBy, Summary

#: A PDF lists every entry, so its range is capped like the day-by-day summary.
MAX_DAYS = reports.MAX_DAYS

#: The summary's key for "no project" and "no task" alike.
NONE_KEY = reports.NO_PROJECT


@dataclass(frozen=True)
class GroupLine:
    """One row of a "hours by project" or "hours by task" table."""

    #: None for time booked without a project or task.
    name: str | None
    color: str | None
    total_seconds: int
    billable_seconds: int
    billable_amount_cents: int


@dataclass(frozen=True)
class EntryLine:
    #: Local start and end, in the report's time zone.
    started_at: datetime
    ended_at: datetime
    project: str | None
    task: str | None
    description: str | None
    duration_seconds: int
    #: The row's own amount, for reading only; totals never add these up.
    amount_cents: int | None


@dataclass(frozen=True)
class Totals:
    currency: str
    total_seconds: int
    billable_seconds: int
    billable_amount_cents: int


@dataclass(frozen=True)
class ReportHeader:
    """What every report says about itself, whatever it covers."""

    person: str
    #: Local dates, both inclusive: what the reader thinks of as "the period".
    first_day: date
    last_day: date
    time_zone: str
    generated_at: datetime


@dataclass(frozen=True)
class PeriodReport:
    header: ReportHeader
    totals: Totals
    projects: list[GroupLine]
    entries: list[EntryLine]
    #: Set when the report covers only the user's hours on one team's projects.
    team_name: str | None = None


@dataclass(frozen=True)
class ProjectInfo:
    name: str
    color: str
    client_name: str | None
    #: The project's current rate. Entries keep the rate they were booked at.
    hourly_rate_cents: int | None
    currency: str


@dataclass(frozen=True)
class ProjectReport:
    header: ReportHeader
    project: ProjectInfo
    totals: Totals
    tasks: list[GroupLine]
    entries: list[EntryLine]


@dataclass(frozen=True)
class ProjectMembers:
    """One team project and how much each member put into it."""

    project: GroupLine
    members: list[GroupLine]


@dataclass(frozen=True)
class TeamReport:
    """Totals only: who put how much into the team's projects. No entries,
    no descriptions, no times of day (decided 2026-10-08)."""

    header: ReportHeader
    team_name: str
    totals: Totals
    members: list[GroupLine]
    projects: list[GroupLine]
    breakdown: list[ProjectMembers]


# ---------------------------------------------------------------------------
# Shared pieces
# ---------------------------------------------------------------------------


def _check_range(starts_from: datetime, starts_before: datetime) -> None:
    if starts_before - starts_from > timedelta(days=MAX_DAYS):
        raise ValidationFailedError(f"a PDF covers at most {MAX_DAYS} days")


def _header(user: User, starts_from: datetime, starts_before: datetime, tz: str) -> ReportHeader:
    zone = reports.zone_info(tz)
    first_day, last_day = reports.local_day_span(starts_from, starts_before, zone)
    return ReportHeader(
        person=user.display_name,
        first_day=first_day,
        last_day=last_day,
        time_zone=tz,
        generated_at=datetime.now(zone),
    )


def _totals(summary: Summary) -> Totals:
    return Totals(
        currency=summary.currency,
        total_seconds=summary.total_seconds,
        billable_seconds=summary.billable_seconds,
        billable_amount_cents=summary.billable_amount_cents,
    )


def _finished_entries(
    db: Session,
    user: User,
    starts_from: datetime,
    starts_before: datetime,
    project_id: UUID | None = None,
) -> list[TimeEntry]:
    """Oldest first. Running timers have no duration yet; the summary leaves
    them out too."""
    rows = [
        entry
        for entry in entries_service.list_entries(
            db,
            user_id=user.id,
            starts_from=starts_from,
            starts_before=starts_before,
            project_id=project_id,
        )
        if entry.ended_at is not None
    ]
    rows.sort(key=lambda entry: entry.started_at)
    return rows


def _by_id(db: Session, model: type[Project] | type[Task], ids: set[UUID]) -> dict:
    """Rows by id in one query, rather than one query per entry."""
    return {row.id: row for row in db.scalars(select(model).where(model.id.in_(ids)))}


def _entry_lines(db: Session, rows: list[TimeEntry], zone: ZoneInfo) -> list[EntryLine]:
    projects = _by_id(db, Project, {entry.project_id for entry in rows if entry.project_id})
    tasks = _by_id(db, Task, {entry.task_id for entry in rows if entry.task_id})

    lines = []
    for entry in rows:
        assert entry.ended_at is not None  # _finished_entries() filtered running timers
        seconds = entry.duration_seconds or 0
        amount = None
        if entry.billable and entry.rate_snapshot_cents is not None:
            amount = reports.round_cents(
                reports.exact_amount_cents(seconds, entry.rate_snapshot_cents)
            )
        project = projects.get(entry.project_id)
        task = tasks.get(entry.task_id)
        lines.append(
            EntryLine(
                started_at=entry.started_at.astimezone(zone),
                ended_at=entry.ended_at.astimezone(zone),
                project=project.name if project else None,
                task=task.name if task else None,
                description=entry.description,
                duration_seconds=seconds,
                amount_cents=amount,
            )
        )
    return lines


def _group_lines(
    db: Session, summary: Summary, model: type[Project] | type[Task]
) -> list[GroupLine]:
    """The summary's groups with names (and colours, for projects) filled in."""
    named = _by_id(db, model, {UUID(g.key) for g in summary.groups if g.key != NONE_KEY})
    lines = []
    for group in summary.groups:
        row = named.get(UUID(group.key)) if group.key != NONE_KEY else None
        lines.append(
            GroupLine(
                name=row.name if row else None,
                color=getattr(row, "color", None),
                total_seconds=group.total_seconds,
                billable_seconds=group.billable_seconds,
                billable_amount_cents=group.billable_amount_cents,
            )
        )
    return lines


# ---------------------------------------------------------------------------
# Builders, one per export scope
# ---------------------------------------------------------------------------


def build_period_report(
    db: Session,
    *,
    user: User,
    starts_from: datetime,
    starts_before: datetime,
    tz: str,
    team_id: UUID | None = None,
) -> PeriodReport:
    """Totals, per-project lines and the entry list for one half-open range.

    With ``team_id``: only the user's own hours on that team's projects, for
    reporting one's work in the team. Still nobody else's entries.
    """
    _check_range(starts_from, starts_before)
    team = None
    if team_id is not None:
        team = db.get(Team, team_id)
        if team is None or ownership.role_in_team(db, user, team.id) is None:
            raise NotFoundError("team not found")
    summary = reports.summarize(
        db,
        user=user,
        starts_from=starts_from,
        starts_before=starts_before,
        group_by=GroupBy.PROJECT,
        tz=tz,
        team_id=team_id,
        mine_only=True,
    )
    rows = _finished_entries(db, user, starts_from, starts_before)
    if team is not None:
        team_projects = set(db.scalars(select(Project.id).where(Project.owner_team_id == team.id)))
        rows = [entry for entry in rows if entry.project_id in team_projects]

    return PeriodReport(
        header=_header(user, starts_from, starts_before, tz),
        totals=_totals(summary),
        projects=_group_lines(db, summary, Project),
        entries=_entry_lines(db, rows, reports.zone_info(tz)),
        team_name=team.name if team else None,
    )


def build_project_report(
    db: Session,
    *,
    user: User,
    project_id: UUID,
    starts_from: datetime,
    starts_before: datetime,
    tz: str,
) -> ProjectReport:
    """One project's totals, per-task lines and entries for a half-open range.

    Only the user's own entries for now. When teams arrive (phase 7), a team
    lead's project report is where the members' entries join in.
    """
    _check_range(starts_from, starts_before)
    # Not found, rather than an empty report, for a project the user cannot see.
    project = projects_service.get_project(db, project_id, user)
    summary = reports.summarize(
        db,
        user=user,
        starts_from=starts_from,
        starts_before=starts_before,
        group_by=GroupBy.TASK,
        tz=tz,
        project_id=project.id,
    )
    rows = _finished_entries(db, user, starts_from, starts_before, project_id=project.id)

    return ProjectReport(
        header=_header(user, starts_from, starts_before, tz),
        project=ProjectInfo(
            name=project.name,
            color=project.color,
            client_name=project.client_name,
            hourly_rate_cents=project.hourly_rate_cents,
            currency=project.currency,
        ),
        totals=_totals(summary),
        tasks=_group_lines(db, summary, Task),
        entries=_entry_lines(db, rows, reports.zone_info(tz)),
    )


def _member_lines(summary: Summary) -> list[GroupLine]:
    """A by-user summary's groups, named from the summary's own labels."""
    return [
        GroupLine(
            name=summary.labels.get(group.key),
            color=None,
            total_seconds=group.total_seconds,
            billable_seconds=group.billable_seconds,
            billable_amount_cents=group.billable_amount_cents,
        )
        for group in summary.groups
    ]


def build_team_report(
    db: Session,
    *,
    user: User,
    team_id: UUID,
    starts_from: datetime,
    starts_before: datetime,
    tz: str,
    team_time_zone: str = "UTC",
) -> TeamReport:
    """A team's totals for a half-open range: per member, per project, and
    per member within each project. For anyone in the team.

    Whole days of ``team_time_zone``, as on screen; see reports.summarize().
    """
    team = db.get(Team, team_id)
    # The same answer for a team that does not exist and one the user is not
    # in; reports.summarize_team() checks again.
    if team is None or ownership.role_in_team(db, user, team.id) is None:
        raise NotFoundError("team not found")

    # The range the totals will cover, so the limit applies to it.
    _check_range(
        *reports.whole_days(
            starts_from, starts_before, reports.zone_info(tz), reports.zone_info(team_time_zone)
        )
    )
    summaries = reports.summarize_team(
        db,
        user=user,
        team_id=team.id,
        starts_from=starts_from,
        starts_before=starts_before,
        tz=tz,
        team_time_zone=team_time_zone,
    )
    by_project = summaries.by_project

    projects = _group_lines(db, by_project, Project)
    breakdown = [
        ProjectMembers(
            project=line,
            members=_member_lines(summaries.members_by_project[group.key]),
        )
        # Every entry in a team report has a project: the team's.
        for group, line in zip(by_project.groups, projects, strict=True)
    ]

    return TeamReport(
        # The days the totals really cover, in the zone they were counted in.
        header=_header(
            user, by_project.starts_from, by_project.starts_before, by_project.time_zone
        ),
        team_name=team.name,
        totals=_totals(by_project),
        members=_member_lines(summaries.by_member),
        projects=projects,
        breakdown=breakdown,
    )
