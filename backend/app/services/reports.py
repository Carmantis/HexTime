"""Totals — the one source of numbers.

Every view, chart and PDF gets its sums from here and nowhere else, so the
number on screen, the bar in the chart and the figure in the exported PDF can
never disagree. The frontend never adds up durations or money itself.

Money is integer cents on the way in, Decimal in between, and is rounded
exactly once: on the final amount of each total. Rounding every entry first
and then adding them would drift by a cent every few entries.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, lazyload

from app.core.errors import NotFoundError, ValidationFailedError
from app.models import Project, TimeEntry, User
from app.services import ownership

SECONDS_PER_HOUR = Decimal(3600)

#: The group key for entries that have no project, no tag or no task.
NO_PROJECT = "none"
NO_TAG = "none"
NO_TASK = "none"

#: Every entry is EUR until multi-currency support is designed.
CURRENCY = "EUR"

#: A day-by-day summary is a list of days; cap it so a mistyped year in the
#: query string cannot make the server build a thousand-year list.
MAX_DAYS = 400
MAX_MONTHS = 120


class GroupBy(StrEnum):
    DAY = "day"
    MONTH = "month"
    PROJECT = "project"
    TAG = "tag"
    TASK = "task"
    #: Per person. Meant for a team report: one's own report has one person.
    USER = "user"


#: Groupings that return one row per period, including the empty ones — a week
#: view always wants seven days and a year view twelve months.
PERIOD_GROUPS = (GroupBy.DAY, GroupBy.MONTH)


def exact_amount_cents(duration_seconds: int, rate_cents: int) -> Decimal:
    """What an entry is worth, in cents, before any rounding."""
    return Decimal(duration_seconds) * Decimal(rate_cents) / SECONDS_PER_HOUR


def round_cents(amount: Decimal) -> int:
    """Round a final amount to whole cents, half up. The only rounding step.

    Half up rather than Python's default half-to-even ("banker's rounding"),
    because an invoice rounds 0.5 cents up.
    """
    return int(amount.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def entry_amount(duration_seconds: int, rate_cents: int) -> Decimal:
    """One entry's billable amount in euros, rounded half up to the cent."""
    euros = exact_amount_cents(duration_seconds, rate_cents) / 100
    return euros.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class _Accumulator:
    """Running totals for one group. Money stays unrounded in here."""

    total_seconds: int = 0
    billable_seconds: int = 0
    exact_cents: Decimal = field(default_factory=Decimal)
    entry_count: int = 0

    def add(self, entry: TimeEntry) -> None:
        seconds = entry.duration_seconds or 0
        self.total_seconds += seconds
        self.entry_count += 1
        if entry.billable:
            self.billable_seconds += seconds
            # Billable but without a rate still counts as billable hours; it
            # simply has no price yet.
            if entry.rate_snapshot_cents is not None:
                self.exact_cents += exact_amount_cents(seconds, entry.rate_snapshot_cents)


@dataclass(frozen=True)
class Group:
    #: An ISO date ("2026-03-29") for days, "2026-03" for months, otherwise a
    #: project, tag or task id, or "none" for entries without one.
    key: str
    total_seconds: int
    billable_seconds: int
    billable_amount_cents: int
    entry_count: int


@dataclass(frozen=True)
class Summary:
    group_by: GroupBy
    time_zone: str
    #: The range the totals cover; wider than the one asked for in a team
    #: report, which always covers whole days.
    starts_from: datetime
    starts_before: datetime
    currency: str
    groups: list[Group]
    total_seconds: int
    billable_seconds: int
    #: Rounded from the unrounded grand total, so it can differ by a cent from
    #: the sum of the rounded group amounts. That is deliberate: rounding the
    #: groups first would be rounding an intermediate step.
    billable_amount_cents: int
    entry_count: int
    #: Display names of the people in a by-user summary, by key, so the
    #: report can name people who have left the team since.
    labels: dict[str, str] = field(default_factory=dict)


def zone_info(name: str) -> ZoneInfo:
    """An IANA time zone, or a validation error naming the bad value."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationFailedError(f"unknown time zone {name!r}") from exc


def local_day_span(
    starts_from: datetime, starts_before: datetime, zone: ZoneInfo
) -> tuple[date, date]:
    """The first and the last local day a half-open range touches."""
    first = starts_from.astimezone(zone).date()
    last = (starts_before - timedelta(microseconds=1)).astimezone(zone).date()
    return first, last


def whole_days(
    starts_from: datetime, starts_before: datetime, picked: ZoneInfo, zone: ZoneInfo
) -> tuple[datetime, datetime]:
    """The days a range covers in ``picked``, as midnight to midnight in ``zone``.

    A team report always covers whole days of the organisation's zone.
    Otherwise a member could ask for 09:00-09:15, then 09:00-09:05, and read
    from the totals when a colleague started work. The browser's zone only
    says which days were picked; it cannot move where a day begins.
    """
    first, last = local_day_span(starts_from, starts_before, picked)

    def midnight(day: date) -> datetime:
        return datetime.combine(day, time(), tzinfo=zone).astimezone(UTC)

    return midnight(first), midnight(last + timedelta(days=1))


def _local_days(starts_from: datetime, starts_before: datetime, zone: ZoneInfo) -> Iterator[date]:
    """Every local calendar day the half-open range touches."""
    first, last = local_day_span(starts_from, starts_before, zone)
    if (last - first).days >= MAX_DAYS:
        raise ValidationFailedError(f"a day-by-day summary covers at most {MAX_DAYS} days")

    day = first
    while day <= last:
        yield day
        day += timedelta(days=1)


def _local_months(starts_from: datetime, starts_before: datetime, zone: ZoneInfo) -> Iterator[str]:
    """Every local month the half-open range touches, as "2026-05"."""
    first, last = local_day_span(starts_from, starts_before, zone)
    span = (last.year - first.year) * 12 + last.month - first.month
    if span >= MAX_MONTHS:
        raise ValidationFailedError(f"a month-by-month summary covers at most {MAX_MONTHS} months")

    year, month = first.year, first.month
    for _ in range(span + 1):
        yield f"{year:04d}-{month:02d}"
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def _keys(entry: TimeEntry, group_by: GroupBy, zone: ZoneInfo) -> list[str]:
    """Which group or groups an entry belongs to.

    Tags are the one grouping that can return several keys, because an entry
    can carry several tags. Such an entry is counted once in each of its tag
    groups, so the tag groups can add up to more than the total — which is the
    honest answer to "how many hours were tagged urgent".
    """
    if group_by is GroupBy.DAY:
        # The local day the entry started on. An entry that runs past midnight
        # is counted wholly on its first day.
        return [entry.started_at.astimezone(zone).date().isoformat()]
    if group_by is GroupBy.MONTH:
        local = entry.started_at.astimezone(zone).date()
        return [f"{local.year:04d}-{local.month:02d}"]
    if group_by is GroupBy.TAG:
        return [str(tag.id) for tag in entry.tags] or [NO_TAG]
    if group_by is GroupBy.TASK:
        return [str(entry.task_id) if entry.task_id else NO_TASK]
    if group_by is GroupBy.USER:
        return [str(entry.user_id)]
    return [str(entry.project_id) if entry.project_id else NO_PROJECT]


def _freeze(key: str, acc: _Accumulator) -> Group:
    return Group(
        key=key,
        total_seconds=acc.total_seconds,
        billable_seconds=acc.billable_seconds,
        billable_amount_cents=round_cents(acc.exact_cents),
        entry_count=acc.entry_count,
    )


def summarize(
    db: Session,
    *,
    user: User,
    starts_from: datetime,
    starts_before: datetime,
    group_by: GroupBy,
    tz: str = "UTC",
    project_id: UUID | None = None,
    team_id: UUID | None = None,
    mine_only: bool = False,
    team_time_zone: str = "UTC",
) -> Summary:
    """Totals of finished entries that start inside the range.

    Without ``team_id``: the user's own entries, all of them.

    With ``team_id``: every member's entries on the team's projects, for the
    team report. Only for someone in the team, and only as totals — the
    entries themselves stay their owner's (decided 2026-10-08). Time on
    anything that is not the team's project is never counted here. Entries of
    people who have left the team still count: the hours went into its
    projects.

    ``team_id`` with ``mine_only``: the user's own entries on the team's
    projects, for "my hours in this team".

    A team report (``team_id`` without ``mine_only``) covers the days picked
    in ``tz``, but as whole days of ``team_time_zone``, the organisation's
    zone (``Settings.time_zone``): no times of day, and no boundaries the
    browser can move. Its days and months are that zone's too.

    Days are the user's *local* days, which is why a time zone name is needed
    rather than an offset: a week that crosses a daylight saving change has two
    different offsets in it. Running timers are left out — they have no
    duration yet.

    ``project_id`` narrows the totals to one project, which is what "hours per
    task" needs: task names only mean something inside their own project.
    """
    if starts_before <= starts_from:
        raise ValidationFailedError("'to' must be after 'from'")
    team_wide = team_id is not None and not mine_only
    if team_id is not None:
        # First: an outsider learns nothing, not even that tags are refused.
        _check_team(db, user, team_id)
        if group_by is GroupBy.TAG:
            # Tags are mostly personal: grouping a team's hours by them would
            # show what people tag their work with.
            raise ValidationFailedError("a team report is not grouped by tag")
    if team_wide:
        starts_from, starts_before = _team_span(starts_from, starts_before, tz, team_time_zone)
        tz = team_time_zone
    zone = zone_info(tz)
    query = _entries_query(
        user=user,
        starts_from=starts_from,
        starts_before=starts_before,
        project_id=project_id,
        team_id=team_id,
        mine_only=mine_only,
        with_tags=not team_wide,
    )

    buckets: dict[str, _Accumulator] = {}
    # Empty periods are part of the answer: a week view always has seven days.
    if group_by is GroupBy.DAY:
        for day in _local_days(starts_from, starts_before, zone):
            buckets[day.isoformat()] = _Accumulator()
    elif group_by is GroupBy.MONTH:
        for month in _local_months(starts_from, starts_before, zone):
            buckets[month] = _Accumulator()

    overall = _Accumulator()
    for entry in db.scalars(query):
        for key in _keys(entry, group_by, zone):
            buckets.setdefault(key, _Accumulator()).add(entry)
        # Once per entry, however many groups it landed in.
        overall.add(entry)

    return _summary(db, group_by, tz, starts_from, starts_before, buckets, overall)


@dataclass(frozen=True)
class TeamSummaries:
    """Everything the team PDF shows, from one reading of the entries."""

    by_project: Summary
    by_member: Summary
    #: Per project id: that project's hours by member.
    members_by_project: dict[str, Summary]


def summarize_team(
    db: Session,
    *,
    user: User,
    team_id: UUID,
    starts_from: datetime,
    starts_before: datetime,
    tz: str = "UTC",
    team_time_zone: str = "UTC",
) -> TeamSummaries:
    """A team report by project, by member, and by member within each project.

    The same numbers as three or more summarize() calls (the same scope,
    the same whole days), but the entries are read once.
    """
    if starts_before <= starts_from:
        raise ValidationFailedError("'to' must be after 'from'")
    _check_team(db, user, team_id)
    starts_from, starts_before = _team_span(starts_from, starts_before, tz, team_time_zone)
    zone = zone_info(team_time_zone)
    query = _entries_query(
        user=user,
        starts_from=starts_from,
        starts_before=starts_before,
        team_id=team_id,
        with_tags=False,
    )

    by_project: dict[str, _Accumulator] = {}
    by_member: dict[str, _Accumulator] = {}
    per_project: dict[str, dict[str, _Accumulator]] = {}
    overall = _Accumulator()
    for entry in db.scalars(query):
        project_key = _keys(entry, GroupBy.PROJECT, zone)[0]
        member_key = _keys(entry, GroupBy.USER, zone)[0]
        by_project.setdefault(project_key, _Accumulator()).add(entry)
        by_member.setdefault(member_key, _Accumulator()).add(entry)
        per_project.setdefault(project_key, {}).setdefault(member_key, _Accumulator()).add(entry)
        overall.add(entry)

    # Everyone's name once, for all the by-member tables.
    names = _names(db, list(by_member))
    span = (team_time_zone, starts_from, starts_before)
    return TeamSummaries(
        by_project=_summary(db, GroupBy.PROJECT, *span, by_project, overall),
        by_member=_summary(db, GroupBy.USER, *span, by_member, overall, names),
        members_by_project={
            key: _summary(
                db,
                GroupBy.USER,
                *span,
                members,
                by_project[key],
                {member: names[member] for member in members if member in names},
            )
            for key, members in per_project.items()
        },
    )


def _check_team(db: Session, user: User, team_id: UUID) -> None:
    """Only someone in the team; the same answer whether it exists or not."""
    if ownership.role_in_team(db, user, team_id) is None:
        raise NotFoundError("team not found")


def _team_span(
    starts_from: datetime, starts_before: datetime, tz: str, team_time_zone: str
) -> tuple[datetime, datetime]:
    """A team report's range: the days picked in ``tz``, as whole days of
    the organisation's zone. The one place that rule lives."""
    return whole_days(starts_from, starts_before, zone_info(tz), zone_info(team_time_zone))


def _names(db: Session, keys: list[str]) -> dict[str, str]:
    """Display names by user id, for by-user groups."""
    if not keys:
        return {}
    people = select(User).where(User.id.in_([UUID(key) for key in keys]))
    return {str(person.id): person.display_name for person in db.scalars(people)}


def _entries_query(
    *,
    user: User,
    starts_from: datetime,
    starts_before: datetime,
    project_id: UUID | None = None,
    team_id: UUID | None = None,
    mine_only: bool = False,
    with_tags: bool = True,
) -> Select[tuple[TimeEntry]]:
    """The finished entries a summary counts. Team membership is checked
    before this (_check_team).

    ``with_tags=False`` skips loading the tags, which only a by-tag summary
    needs. Only for a team-wide query: those entries are someone else's and
    nothing reads them later in the same session, where the skipped tags
    would then be fetched one entry at a time.
    """
    query = select(TimeEntry).where(
        TimeEntry.started_at >= starts_from,
        TimeEntry.started_at < starts_before,
        TimeEntry.ended_at.is_not(None),
    )
    if team_id is None or mine_only:
        # Filtering on the user's own entries is the access check: a project
        # id that is not theirs simply matches nothing.
        query = query.where(TimeEntry.user_id == user.id)
    if team_id is not None:
        query = query.join(Project, Project.id == TimeEntry.project_id).where(
            Project.owner_team_id == team_id
        )
    if project_id is not None:
        query = query.where(TimeEntry.project_id == project_id)
    if not with_tags:
        query = query.options(lazyload(TimeEntry.tags))
    return query.order_by(TimeEntry.started_at)


def _summary(
    db: Session,
    group_by: GroupBy,
    tz: str,
    starts_from: datetime,
    starts_before: datetime,
    buckets: dict[str, _Accumulator],
    overall: _Accumulator,
    labels: dict[str, str] | None = None,
) -> Summary:
    groups = [_freeze(key, acc) for key, acc in buckets.items()]
    if group_by not in PERIOD_GROUPS:
        # Periods stay in chronological order; everything else reads better
        # with the biggest first.
        groups.sort(key=lambda group: group.total_seconds, reverse=True)

    if labels is None:
        labels = _names(db, [group.key for group in groups]) if group_by is GroupBy.USER else {}

    return Summary(
        group_by=group_by,
        time_zone=tz,
        starts_from=starts_from,
        starts_before=starts_before,
        currency=CURRENCY,
        groups=groups,
        total_seconds=overall.total_seconds,
        billable_seconds=overall.billable_seconds,
        billable_amount_cents=round_cents(overall.exact_cents),
        entry_count=overall.entry_count,
        labels=labels,
    )
