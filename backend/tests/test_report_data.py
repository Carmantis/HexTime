"""The data behind the PDF reports.

The PDF must show the same numbers as the Reports view, so these tests check
the report against summarize() itself rather than against hand-made sums.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationFailedError
from app.models import Project, User
from app.reports.data import build_period_report, build_project_report
from app.services import entries, reports, timer
from app.services import projects as projects_service
from app.services.reports import GroupBy

HELSINKI = "Europe/Helsinki"
OCT_1 = datetime(2026, 9, 30, 21, tzinfo=UTC)  # 1.10. 00:00 in Helsinki
NOV_1 = datetime(2026, 10, 31, 22, tzinfo=UTC)  # 1.11. 00:00 in Helsinki (winter time)


def book(db: Session, user: User, start: datetime, minutes: int, **fields: object):
    return entries.create_entry(
        db, user=user, started_at=start, ended_at=start + timedelta(minutes=minutes), **fields
    )


def report(db: Session, user: User):
    return build_period_report(db, user=user, starts_from=OCT_1, starts_before=NOV_1, tz=HELSINKI)


def test_totals_are_the_reports_service_totals(db: Session, user: User, project: Project) -> None:
    book(db, user, datetime(2026, 10, 5, 6, tzinfo=UTC), 90, project_id=project.id, billable=True)
    book(db, user, datetime(2026, 10, 6, 6, tzinfo=UTC), 20, project_id=project.id, billable=True)
    book(db, user, datetime(2026, 10, 7, 6, tzinfo=UTC), 45)

    built = report(db, user)
    summary = reports.summarize(
        db, user=user, starts_from=OCT_1, starts_before=NOV_1, group_by=GroupBy.PROJECT, tz=HELSINKI
    )

    assert built.totals.total_seconds == summary.total_seconds == (90 + 20 + 45) * 60
    assert built.totals.billable_seconds == summary.billable_seconds
    assert built.totals.billable_amount_cents == summary.billable_amount_cents
    assert [line.total_seconds for line in built.projects] == [
        group.total_seconds for group in summary.groups
    ]


def test_project_lines_carry_names_and_a_line_for_no_project(
    db: Session, user: User, project: Project
) -> None:
    book(db, user, datetime(2026, 10, 5, 6, tzinfo=UTC), 120, project_id=project.id)
    book(db, user, datetime(2026, 10, 6, 6, tzinfo=UTC), 30)

    built = report(db, user)

    assert [(line.name, line.total_seconds) for line in built.projects] == [
        ("Website", 7200),
        (None, 1800),
    ]
    assert built.projects[0].color == project.color


def test_entries_are_in_local_time_oldest_first(db: Session, user: User, project: Project) -> None:
    task = projects_service.create_task(db, project=project, name="Design")
    book(db, user, datetime(2026, 10, 6, 6, tzinfo=UTC), 60, description="later")
    book(
        db,
        user,
        datetime(2026, 10, 5, 21, 30, tzinfo=UTC),
        60,
        project_id=project.id,
        task_id=task.id,
        description="earlier",
    )

    built = report(db, user)

    first = built.entries[0]
    assert first.description == "earlier"
    # 21:30 UTC on the 5th is 00:30 on the 6th in Helsinki (UTC+3 in October).
    assert (first.started_at.day, first.started_at.hour, first.started_at.minute) == (6, 0, 30)
    assert (first.project, first.task) == ("Website", "Design")
    assert built.entries[1].description == "later"


def test_a_running_timer_is_left_out(db: Session, user: User) -> None:
    book(db, user, datetime(2026, 10, 5, 6, tzinfo=UTC), 60)
    timer.start(db, user=user, at=datetime(2026, 10, 6, 6, tzinfo=UTC))

    built = report(db, user)

    assert len(built.entries) == 1
    assert built.totals.total_seconds == 3600


def test_entry_amounts_use_the_rate_snapshot(db: Session, user: User, project: Project) -> None:
    # 20 min at 85,00 €/h = 28,333… € → 28,33 € on the row.
    book(db, user, datetime(2026, 10, 5, 6, tzinfo=UTC), 20, project_id=project.id, billable=True)
    book(db, user, datetime(2026, 10, 6, 6, tzinfo=UTC), 20, project_id=project.id, billable=False)

    built = report(db, user)

    assert [line.amount_cents for line in built.entries] == [2833, None]


def test_the_period_is_written_as_local_inclusive_days(db: Session, user: User) -> None:
    built = report(db, user)

    assert (built.header.first_day.isoformat(), built.header.last_day.isoformat()) == (
        "2026-10-01",
        "2026-10-31",
    )
    assert built.entries == []


def test_other_users_entries_are_not_in_the_report(
    db: Session, user: User, other_user: User
) -> None:
    book(db, other_user, datetime(2026, 10, 5, 6, tzinfo=UTC), 60)

    assert report(db, user).entries == []


def test_a_range_longer_than_the_cap_is_refused(db: Session, user: User) -> None:
    with pytest.raises(ValidationFailedError):
        build_period_report(
            db,
            user=user,
            starts_from=OCT_1,
            starts_before=OCT_1 + timedelta(days=500),
            tz=HELSINKI,
        )


# ---------------------------------------------------------------------------
# Project report
# ---------------------------------------------------------------------------


def project_report(db: Session, user: User, project: Project):
    return build_project_report(
        db, user=user, project_id=project.id, starts_from=OCT_1, starts_before=NOV_1, tz=HELSINKI
    )


def test_the_project_report_covers_only_that_project(
    db: Session, user: User, project: Project
) -> None:
    other = Project(name="Other", owner_user_id=user.id)
    db.add(other)
    db.commit()
    book(db, user, datetime(2026, 10, 5, 6, tzinfo=UTC), 60, project_id=project.id, billable=True)
    book(db, user, datetime(2026, 10, 6, 6, tzinfo=UTC), 45, project_id=other.id, billable=True)
    book(db, user, datetime(2026, 10, 7, 6, tzinfo=UTC), 30)

    built = project_report(db, user, project)

    assert built.totals.total_seconds == 3600
    assert built.totals.billable_amount_cents == 8500
    assert [entry.project for entry in built.entries] == ["Website"]
    assert (built.project.name, built.project.hourly_rate_cents) == ("Website", 8500)


def test_the_project_report_matches_the_task_summary(
    db: Session, user: User, project: Project
) -> None:
    design = projects_service.create_task(db, project=project, name="Design")
    build = projects_service.create_task(db, project=project, name="Build")
    book(
        db, user, datetime(2026, 10, 5, 6, tzinfo=UTC), 60, project_id=project.id, task_id=design.id
    )
    book(
        db, user, datetime(2026, 10, 6, 6, tzinfo=UTC), 120, project_id=project.id, task_id=build.id
    )
    book(db, user, datetime(2026, 10, 7, 6, tzinfo=UTC), 30, project_id=project.id)

    built = project_report(db, user, project)
    summary = reports.summarize(
        db,
        user=user,
        starts_from=OCT_1,
        starts_before=NOV_1,
        group_by=GroupBy.TASK,
        tz=HELSINKI,
        project_id=project.id,
    )

    assert [(line.name, line.total_seconds) for line in built.tasks] == [
        ("Build", 7200),
        ("Design", 3600),
        (None, 1800),
    ]
    assert [line.total_seconds for line in built.tasks] == [g.total_seconds for g in summary.groups]
    # Tasks have no colour of their own.
    assert all(line.color is None for line in built.tasks)


def test_another_users_project_is_not_found(
    db: Session, user: User, other_user: User, project: Project
) -> None:
    with pytest.raises(NotFoundError):
        project_report(db, other_user, project)
