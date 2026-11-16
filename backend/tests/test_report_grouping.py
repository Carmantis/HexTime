"""Grouping by tag and by month.

Tags are the only grouping where one entry lands in several groups, so the
group totals can legitimately add up to more than the overall total. That is
worth pinning down, because it looks like a bug the first time you see it.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailedError
from app.models import Project, User
from app.services import entries, reports
from app.services import projects as projects_service
from app.services import tags as tags_service
from app.services.reports import GroupBy

HELSINKI = "Europe/Helsinki"


def book(db: Session, user: User, start: datetime, minutes: int, **fields: object):
    return entries.create_entry(
        db, user=user, started_at=start, ended_at=start + timedelta(minutes=minutes), **fields
    )


def group(db: Session, user: User, start: datetime, end: datetime, by: GroupBy, **kw: object):
    return reports.summarize(db, user=user, starts_from=start, starts_before=end, group_by=by, **kw)


MAY_4 = datetime(2026, 5, 4, tzinfo=UTC)
MAY_5 = datetime(2026, 5, 5, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_hours_are_counted_under_each_tag(db: Session, user: User) -> None:
    """One entry with two tags counts in both groups. The group totals then
    exceed the overall total, and that is the right answer to "how many hours
    were tagged urgent"."""
    urgent = tags_service.create_tag(db, user=user, name="urgent")
    review = tags_service.create_tag(db, user=user, name="review")
    book(db, user, MAY_4.replace(hour=9), 60, tag_ids=[urgent.id, review.id])

    summary = group(db, user, MAY_4, MAY_5, GroupBy.TAG)

    assert {g.key: g.total_seconds for g in summary.groups} == {
        str(urgent.id): 3600,
        str(review.id): 3600,
    }
    assert summary.total_seconds == 3600
    assert summary.entry_count == 1


def test_untagged_time_gets_its_own_group(db: Session, user: User) -> None:
    urgent = tags_service.create_tag(db, user=user, name="urgent")
    book(db, user, MAY_4.replace(hour=9), 60, tag_ids=[urgent.id])
    book(db, user, MAY_4.replace(hour=11), 30)

    summary = group(db, user, MAY_4, MAY_5, GroupBy.TAG)

    assert {g.key: g.total_seconds for g in summary.groups} == {
        str(urgent.id): 3600,
        reports.NO_TAG: 1800,
    }


def test_the_busiest_tag_comes_first(db: Session, user: User) -> None:
    small = tags_service.create_tag(db, user=user, name="small")
    big = tags_service.create_tag(db, user=user, name="big")
    book(db, user, MAY_4.replace(hour=9), 15, tag_ids=[small.id])
    book(db, user, MAY_4.replace(hour=11), 120, tag_ids=[big.id])

    summary = group(db, user, MAY_4, MAY_5, GroupBy.TAG)

    assert [g.key for g in summary.groups] == [str(big.id), str(small.id)]


def test_tag_groups_carry_the_money_too(db: Session, user: User, project: Project) -> None:
    urgent = tags_service.create_tag(db, user=user, name="urgent")
    book(db, user, MAY_4.replace(hour=9), 60, project_id=project.id, tag_ids=[urgent.id])

    summary = group(db, user, MAY_4, MAY_5, GroupBy.TAG)

    assert summary.groups[0].billable_amount_cents == 8500


# ---------------------------------------------------------------------------
# Months
# ---------------------------------------------------------------------------


def test_a_year_has_twelve_months_even_when_empty(db: Session, user: User) -> None:
    summary = group(
        db,
        user,
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2027, 1, 1, tzinfo=UTC),
        GroupBy.MONTH,
    )

    assert [g.key for g in summary.groups] == [f"2026-{m:02d}" for m in range(1, 13)]
    assert all(g.total_seconds == 0 for g in summary.groups)


def test_months_stay_in_chronological_order(db: Session, user: User) -> None:
    """Periods are not sorted by size: a chart of the year has to read
    January to December."""
    book(db, user, datetime(2026, 3, 2, 9, tzinfo=UTC), 30)
    book(db, user, datetime(2026, 1, 2, 9, tzinfo=UTC), 240)

    summary = group(
        db, user, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 4, 1, tzinfo=UTC), GroupBy.MONTH
    )

    assert [g.key for g in summary.groups] == ["2026-01", "2026-02", "2026-03"]
    assert [g.total_seconds for g in summary.groups] == [14400, 0, 1800]


def test_months_are_local_months(db: Session, user: User) -> None:
    """22:30 UTC on 31 March is 01:30 on 1 April in Helsinki."""
    book(db, user, datetime(2026, 3, 31, 22, 30, tzinfo=UTC), 30)
    start = datetime(2026, 3, 1, tzinfo=UTC)
    end = datetime(2026, 5, 1, tzinfo=UTC)

    in_utc = group(db, user, start, end, GroupBy.MONTH, tz="UTC")
    in_helsinki = group(db, user, start, end, GroupBy.MONTH, tz=HELSINKI)

    assert _busy(in_utc) == ["2026-03"]
    assert _busy(in_helsinki) == ["2026-04"]


def test_an_absurdly_long_month_range_is_refused(db: Session, user: User) -> None:
    with pytest.raises(ValidationFailedError):
        group(
            db,
            user,
            datetime(2000, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
            GroupBy.MONTH,
        )


def _busy(summary: reports.Summary) -> list[str]:
    return [g.key for g in summary.groups if g.total_seconds > 0]


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


def test_hours_are_grouped_by_task(db: Session, user: User, project: Project) -> None:
    design = projects_service.create_task(db, project=project, name="Design")
    build = projects_service.create_task(db, project=project, name="Build")
    book(db, user, MAY_4.replace(hour=8), 60, project_id=project.id, task_id=design.id)
    book(db, user, MAY_4.replace(hour=10), 120, project_id=project.id, task_id=build.id)
    book(db, user, MAY_4.replace(hour=13), 30, project_id=project.id)

    summary = group(db, user, MAY_4, MAY_5, GroupBy.TASK, project_id=project.id)

    # Biggest first, and time without a task gets its own group.
    assert [(g.key, g.total_seconds) for g in summary.groups] == [
        (str(build.id), 7200),
        (str(design.id), 3600),
        (reports.NO_TASK, 1800),
    ]
    assert summary.total_seconds == 3.5 * 3600


def test_the_project_filter_leaves_other_projects_out(
    db: Session, user: User, project: Project
) -> None:
    other = Project(name="Other", owner_user_id=user.id)
    db.add(other)
    db.commit()
    book(db, user, MAY_4.replace(hour=8), 60, project_id=project.id)
    book(db, user, MAY_4.replace(hour=10), 45, project_id=other.id)
    book(db, user, MAY_4.replace(hour=12), 15)

    summary = group(db, user, MAY_4, MAY_5, GroupBy.TASK, project_id=project.id)

    assert summary.total_seconds == 3600
    assert summary.entry_count == 1
    # The money follows the filter too: 1 h at 85,00 €/h.
    assert summary.billable_amount_cents == 8500


def test_another_users_project_shows_nothing(
    db: Session, user: User, other_user: User, project: Project
) -> None:
    book(db, user, MAY_4.replace(hour=8), 60, project_id=project.id)

    summary = group(db, other_user, MAY_4, MAY_5, GroupBy.TASK, project_id=project.id)

    assert summary.groups == []
    assert summary.total_seconds == 0
