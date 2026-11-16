"""The report service: the one source of numbers.

Covers three of the tests the numbers must always pass: report totals equal the
sum of entries, Decimal rounding, and UTC-to-local conversion around a
daylight saving change.
"""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailedError
from app.models import Project, TimeEntry, User
from app.services import entries, reports
from app.services.reports import GroupBy

HELSINKI = "Europe/Helsinki"
EET = timezone(timedelta(hours=2))  # Finnish winter time
EEST = timezone(timedelta(hours=3))  # Finnish summer time


def book(db: Session, user: User, start: datetime, minutes: int, **fields: object) -> TimeEntry:
    return entries.create_entry(
        db, user=user, started_at=start, ended_at=start + timedelta(minutes=minutes), **fields
    )


def summarize(db: Session, user: User, start: datetime, end: datetime, **kw: object):
    return reports.summarize(
        db, user=user, starts_from=start, starts_before=end, group_by=GroupBy.DAY, **kw
    )


MAY_4 = datetime(2026, 5, 4, tzinfo=UTC)
MAY_5 = datetime(2026, 5, 5, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Totals equal the sum of the entries
# ---------------------------------------------------------------------------


def test_totals_equal_the_sum_of_the_entries(db: Session, user: User) -> None:
    booked = [
        book(db, user, MAY_4.replace(hour=8), 45),
        book(db, user, MAY_4.replace(hour=10), 90),
        book(db, user, MAY_4.replace(hour=14), 7),
    ]

    summary = summarize(db, user, MAY_4, MAY_5)

    assert summary.total_seconds == sum(e.duration_seconds for e in booked)
    assert summary.entry_count == 3
    assert sum(group.total_seconds for group in summary.groups) == summary.total_seconds


def test_running_timers_are_left_out(db: Session, user: User) -> None:
    book(db, user, MAY_4.replace(hour=8), 60)
    entries.create_entry(db, user=user, started_at=MAY_4.replace(hour=10))

    summary = summarize(db, user, MAY_4, MAY_5)

    assert summary.entry_count == 1
    assert summary.total_seconds == 3600


def test_another_users_entries_never_count(db: Session, user: User, other_user: User) -> None:
    book(db, other_user, MAY_4.replace(hour=8), 60)

    assert summarize(db, user, MAY_4, MAY_5).total_seconds == 0


def test_entries_outside_the_range_do_not_count(db: Session, user: User) -> None:
    book(db, user, MAY_4.replace(hour=8), 60)
    book(db, user, MAY_5.replace(hour=8), 60)

    assert summarize(db, user, MAY_4, MAY_5).entry_count == 1


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------


def test_rounding_happens_once_on_the_total(db: Session, user: User, project: Project) -> None:
    """Three 20-minute entries at 85,00 €/h are exactly 85,00 €. Rounding each
    entry first (3 x 28,33) would give 84,99 €."""
    for hour in (8, 9, 10):
        book(db, user, MAY_4.replace(hour=hour), 20, project_id=project.id)

    summary = summarize(db, user, MAY_4, MAY_5)

    assert summary.billable_amount_cents == 8500


def test_rounding_is_half_up_not_bankers() -> None:
    """Python's round() sends 2.5 to 2. An invoice sends it to 3."""
    assert round_trip("0.5") == 1
    assert round_trip("2.5") == 3
    assert round_trip("2.4999") == 2


def round_trip(value: str) -> int:
    return reports.round_cents(Decimal(value))


def test_entry_amount_matches_the_plan() -> None:
    assert reports.entry_amount(3600, 8500) == Decimal("85.00")
    assert reports.entry_amount(1200, 8500) == Decimal("28.33")
    assert reports.entry_amount(30, 100) == Decimal("0.01")


def test_non_billable_time_counts_but_costs_nothing(
    db: Session, user: User, project: Project
) -> None:
    book(db, user, MAY_4.replace(hour=8), 60, project_id=project.id, billable=False)

    summary = summarize(db, user, MAY_4, MAY_5)

    assert summary.total_seconds == 3600
    assert summary.billable_seconds == 0
    assert summary.billable_amount_cents == 0


def test_billable_time_without_a_rate_has_no_price(db: Session, user: User) -> None:
    book(db, user, MAY_4.replace(hour=8), 60, billable=True)

    summary = summarize(db, user, MAY_4, MAY_5)

    assert summary.billable_seconds == 3600
    assert summary.billable_amount_cents == 0


# ---------------------------------------------------------------------------
# Local days, around a daylight saving change
# ---------------------------------------------------------------------------


def test_days_are_local_not_utc(db: Session, user: User) -> None:
    """22:30 UTC on 28 March is 00:30 on 29 March in Helsinki."""
    book(db, user, datetime(2026, 3, 28, 22, 30, tzinfo=UTC), 30)
    start = datetime(2026, 3, 28, tzinfo=UTC)
    end = datetime(2026, 3, 30, tzinfo=UTC)

    in_utc = summarize(db, user, start, end, tz="UTC")
    in_helsinki = summarize(db, user, start, end, tz=HELSINKI)

    assert _busy_days(in_utc) == ["2026-03-28"]
    assert _busy_days(in_helsinki) == ["2026-03-29"]


def test_a_week_across_the_dst_change_still_has_seven_days(db: Session, user: User) -> None:
    """Summer time starts on Sunday 29 March 2026. Monday begins at +02:00 and
    the next Monday at +03:00, so the week is 167 hours long — but it is still
    seven days."""
    start = datetime(2026, 3, 23, tzinfo=EET)
    end = datetime(2026, 3, 30, tzinfo=EEST)

    summary = summarize(db, user, start, end, tz=HELSINKI)

    assert [group.key for group in summary.groups] == [
        "2026-03-23",
        "2026-03-24",
        "2026-03-25",
        "2026-03-26",
        "2026-03-27",
        "2026-03-28",
        "2026-03-29",
    ]


def test_an_entry_on_the_short_night_lands_on_the_right_day(db: Session, user: User) -> None:
    """02:30 local on 29 March 2026 — just before the clocks jump — is 00:30 UTC."""
    book(db, user, datetime(2026, 3, 29, 0, 30, tzinfo=UTC), 60)

    summary = summarize(
        db, user, datetime(2026, 3, 23, tzinfo=EET), datetime(2026, 3, 30, tzinfo=EEST), tz=HELSINKI
    )

    assert _busy_days(summary) == ["2026-03-29"]


def test_empty_days_are_included(db: Session, user: User) -> None:
    summary = summarize(db, user, MAY_4, MAY_4 + timedelta(days=3))

    assert [g.key for g in summary.groups] == ["2026-05-04", "2026-05-05", "2026-05-06"]
    assert all(g.total_seconds == 0 for g in summary.groups)


def _busy_days(summary: reports.Summary) -> list[str]:
    return [group.key for group in summary.groups if group.total_seconds > 0]


# ---------------------------------------------------------------------------
# Grouping by project
# ---------------------------------------------------------------------------


def test_grouping_by_project_puts_the_busiest_first(
    db: Session, user: User, project: Project
) -> None:
    book(db, user, MAY_4.replace(hour=8), 30)
    book(db, user, MAY_4.replace(hour=9), 120, project_id=project.id)

    summary = reports.summarize(
        db, user=user, starts_from=MAY_4, starts_before=MAY_5, group_by=GroupBy.PROJECT
    )

    assert [g.key for g in summary.groups] == [str(project.id), reports.NO_PROJECT]
    assert summary.groups[0].total_seconds == 7200


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_an_unknown_time_zone_is_rejected(db: Session, user: User) -> None:
    with pytest.raises(ValidationFailedError, match="time zone"):
        summarize(db, user, MAY_4, MAY_5, tz="Mars/Olympus_Mons")


def test_a_path_like_time_zone_is_rejected(db: Session, user: User) -> None:
    with pytest.raises(ValidationFailedError):
        summarize(db, user, MAY_4, MAY_5, tz="../../etc/passwd")


def test_to_must_be_after_from(db: Session, user: User) -> None:
    with pytest.raises(ValidationFailedError):
        summarize(db, user, MAY_5, MAY_4)


def test_an_absurdly_long_day_range_is_refused(db: Session, user: User) -> None:
    with pytest.raises(ValidationFailedError):
        summarize(db, user, MAY_4, MAY_4 + timedelta(days=365 * 20))


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

SUMMARY = "/api/v1/reports/summary"


def test_the_summary_endpoint(api_client: TestClient) -> None:
    api_client.post(
        "/api/v1/entries",
        json={"started_at": "2026-05-04T08:00:00+00:00", "ended_at": "2026-05-04T09:30:00+00:00"},
    )

    body = api_client.get(
        SUMMARY,
        params={
            "from": "2026-05-04T00:00:00+00:00",
            "to": "2026-05-05T00:00:00+00:00",
            "group_by": "day",
            "tz": "UTC",
        },
    ).json()

    assert body["total_seconds"] == 5400
    assert body["currency"] == "EUR"
    assert body["groups"] == [
        {
            "key": "2026-05-04",
            "total_seconds": 5400,
            "billable_seconds": 0,
            "billable_amount_cents": 0,
            "entry_count": 1,
        }
    ]


def test_the_summary_endpoint_groups_one_project_by_task(api_client: TestClient) -> None:
    project = api_client.post("/api/v1/projects", json={"name": "Website"}).json()
    task = api_client.post(
        f"/api/v1/projects/{project['id']}/tasks", json={"name": "Design"}
    ).json()
    api_client.post(
        "/api/v1/entries",
        json={
            "started_at": "2026-05-04T08:00:00+00:00",
            "ended_at": "2026-05-04T09:00:00+00:00",
            "project_id": project["id"],
            "task_id": task["id"],
        },
    )
    # A second entry outside the project must not count.
    api_client.post(
        "/api/v1/entries",
        json={"started_at": "2026-05-04T10:00:00+00:00", "ended_at": "2026-05-04T11:00:00+00:00"},
    )

    body = api_client.get(
        SUMMARY,
        params={
            "from": "2026-05-04T00:00:00+00:00",
            "to": "2026-05-05T00:00:00+00:00",
            "group_by": "task",
            "project_id": project["id"],
        },
    ).json()

    assert body["group_by"] == "task"
    assert body["total_seconds"] == 3600
    assert [(g["key"], g["total_seconds"]) for g in body["groups"]] == [(task["id"], 3600)]


def test_the_range_is_required(api_client: TestClient) -> None:
    response = api_client.get(SUMMARY)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_an_unknown_time_zone_is_a_422(api_client: TestClient) -> None:
    response = api_client.get(
        SUMMARY,
        params={
            "from": "2026-05-04T00:00:00+00:00",
            "to": "2026-05-05T00:00:00+00:00",
            "tz": "Nowhere/Special",
        },
    )

    assert response.status_code == 422
