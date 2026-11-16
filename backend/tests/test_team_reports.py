"""The team report: each member's totals on the team's projects, nothing more.

Decided 2026-10-08: everyone in the team sees the same totals; nobody sees
anyone's single entries, and hours on anything but the team's projects never
show up here. The organisation administrator sees none of it without being
in the team.

The cast: Liisa leads the team, Mikko is a member, Olli is outside it, Anna
is the organisation administrator.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.csrf import CSRF_HEADER
from app.core.errors import NotFoundError, ValidationFailedError
from app.models import Project, Team, TeamMember, TeamRole, User
from app.reports.data import build_period_report, build_team_report
from app.services import entries, reports, teams
from app.services.reports import GroupBy
from app.services.users import make_admin

PASSWORD = "correct horse battery"
CSRF = {CSRF_HEADER: "1"}
OCTOBER = {"from": "2026-10-01T00:00:00Z", "to": "2026-11-01T00:00:00Z", "tz": "UTC"}
START, END = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)


def person(db: Session, email: str, name: str, *, admin: bool = False) -> User:
    user = make_admin(db, email=email, display_name=name, password=PASSWORD)
    user.is_admin = admin
    db.commit()
    return user


def book(db: Session, user: User, project: Project | None, day: int, hours: int) -> None:
    start = datetime(2026, 10, day, 8, tzinfo=UTC)
    entries.create_entry(
        db,
        user=user,
        started_at=start,
        ended_at=start.replace(hour=8 + hours),
        project_id=project.id if project else None,
        description="secret details",
    )


class Cast:
    def __init__(self, db: Session) -> None:
        self.liisa = person(db, "liisa@example.org", "Liisa")
        self.mikko = person(db, "mikko@example.org", "Mikko")
        self.olli = person(db, "olli@example.org", "Olli")
        self.anna = person(db, "anna@example.org", "Anna", admin=True)
        self.team: Team = teams.create_team(db, user=self.liisa, name="Web")
        db.add(TeamMember(team_id=self.team.id, user_id=self.mikko.id, role=TeamRole.MEMBER))
        db.commit()

        def project(name: str, **owner: object) -> Project:
            row = Project(name=name, billable_default=True, hourly_rate_cents=6000, **owner)
            db.add(row)
            db.commit()
            return row

        self.site = project("Site", owner_team_id=self.team.id)
        self.shop = project("Shop", owner_team_id=self.team.id)
        self.mikkos_own = project("Course", owner_user_id=self.mikko.id)

        book(db, self.liisa, self.site, 5, 3)
        book(db, self.mikko, self.site, 6, 4)
        book(db, self.mikko, self.shop, 7, 2)
        # Not the team's: never in its report.
        book(db, self.mikko, self.mikkos_own, 8, 5)
        book(db, self.mikko, None, 9, 1)


@pytest.fixture
def cast(db: Session) -> Cast:
    return Cast(db)


def team_summary(db: Session, cast: Cast, group_by: GroupBy, user: User | None = None, **kw):
    return reports.summarize(
        db,
        user=user or cast.mikko,
        starts_from=START,
        starts_before=END,
        group_by=group_by,
        team_id=cast.team.id,
        **kw,
    )


# ---------------------------------------------------------------------------
# The numbers
# ---------------------------------------------------------------------------


def test_each_member_has_a_total_on_the_teams_projects(db: Session, cast: Cast) -> None:
    summary = team_summary(db, cast, GroupBy.USER)

    assert [(summary.labels[g.key], g.total_seconds // 3600) for g in summary.groups] == [
        ("Mikko", 6),
        ("Liisa", 3),
    ]
    # Mikko's own project and his time without a project are not the team's.
    assert summary.total_seconds == 9 * 3600


def test_each_team_project_has_a_total(db: Session, cast: Cast) -> None:
    summary = team_summary(db, cast, GroupBy.PROJECT)

    assert [(g.key, g.total_seconds // 3600) for g in summary.groups] == [
        (str(cast.site.id), 7),
        (str(cast.shop.id), 2),
    ]
    assert summary.billable_amount_cents == 9 * 6000


def test_one_project_split_by_member(db: Session, cast: Cast) -> None:
    summary = team_summary(db, cast, GroupBy.USER, project_id=cast.site.id)

    assert {summary.labels[g.key]: g.total_seconds // 3600 for g in summary.groups} == {
        "Mikko": 4,
        "Liisa": 3,
    }


def test_every_member_sees_the_same_report(db: Session, cast: Cast) -> None:
    as_member = team_summary(db, cast, GroupBy.USER, user=cast.mikko)
    as_lead = team_summary(db, cast, GroupBy.USER, user=cast.liisa)

    assert as_member == as_lead


def test_someone_who_left_still_counts_by_name(db: Session, cast: Cast) -> None:
    teams.remove_member(db, actor=cast.mikko, team=cast.team, user_id=cast.mikko.id)

    summary = team_summary(db, cast, GroupBy.USER, user=cast.liisa)

    assert summary.labels[str(cast.mikko.id)] == "Mikko"
    assert summary.total_seconds == 9 * 3600


def test_ones_own_report_is_unchanged(db: Session, cast: Cast) -> None:
    """Mikko's personal report still has all of his time, team projects too."""
    own = reports.summarize(
        db, user=cast.mikko, starts_from=START, starts_before=END, group_by=GroupBy.PROJECT
    )

    assert own.total_seconds == 12 * 3600


# ---------------------------------------------------------------------------
# Who may see it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("who", ["olli", "anna"])
def test_nobody_outside_the_team_sees_it(db: Session, cast: Cast, who: str) -> None:
    with pytest.raises(NotFoundError):
        team_summary(db, cast, GroupBy.USER, user=getattr(cast, who))


def test_tags_are_not_a_team_grouping(db: Session, cast: Cast) -> None:
    with pytest.raises(ValidationFailedError):
        team_summary(db, cast, GroupBy.TAG)


# ---------------------------------------------------------------------------
# No times of day: a team report always covers whole days
# ---------------------------------------------------------------------------


def test_a_part_of_a_day_counts_the_whole_day(db: Session, cast: Cast) -> None:
    """Narrowing the range must not tell when Liisa started on the 5th."""

    def total(start_hour: int, end_hour: int) -> int:
        return reports.summarize(
            db,
            user=cast.mikko,
            starts_from=datetime(2026, 10, 5, start_hour, tzinfo=UTC),
            starts_before=datetime(2026, 10, 5, end_hour, tzinfo=UTC),
            group_by=GroupBy.USER,
            team_id=cast.team.id,
        ).total_seconds

    # Her entry starts at 08:00; every slice of the day gives the same answer.
    assert total(8, 9) == total(0, 1) == total(20, 21) == 3 * 3600


def test_whole_days_follow_the_zone() -> None:
    from zoneinfo import ZoneInfo

    helsinki = ZoneInfo("Europe/Helsinki")
    start, end = reports.whole_days(
        datetime(2026, 10, 5, 7, 15, tzinfo=UTC),
        datetime(2026, 10, 5, 7, 30, tzinfo=UTC),
        helsinki,
        helsinki,
    )

    # Helsinki is UTC+3 until the end of October.
    assert (start, end) == (
        datetime(2026, 10, 4, 21, tzinfo=UTC),
        datetime(2026, 10, 5, 21, tzinfo=UTC),
    )


def test_the_browsers_zone_picks_the_days_the_organisations_cuts_them(
    db: Session, cast: Cast
) -> None:
    """A Helsinki browser picks 5-11 October; an organisation on UTC still
    gets exactly those seven days, not an eighth from the zone difference."""
    summary = reports.summarize(
        db,
        user=cast.mikko,
        starts_from=datetime(2026, 10, 4, 21, tzinfo=UTC),  # Mon 5th 00:00 in Helsinki
        starts_before=datetime(2026, 10, 11, 21, tzinfo=UTC),
        group_by=GroupBy.DAY,
        tz="Europe/Helsinki",
        team_id=cast.team.id,
        team_time_zone="UTC",
    )

    assert summary.groups[0].key == "2026-10-05"
    assert len(summary.groups) == 7
    assert summary.time_zone == "UTC"
    assert (summary.starts_from, summary.starts_before) == (
        datetime(2026, 10, 5, tzinfo=UTC),
        datetime(2026, 10, 12, tzinfo=UTC),
    )


def test_my_own_hours_in_the_team_keep_the_exact_range(db: Session, cast: Cast) -> None:
    """One's own entries are one's own: no reason to widen them."""
    summary = reports.summarize(
        db,
        user=cast.mikko,
        starts_from=datetime(2026, 10, 6, 0, tzinfo=UTC),
        starts_before=datetime(2026, 10, 6, 8, tzinfo=UTC),
        group_by=GroupBy.USER,
        team_id=cast.team.id,
        mine_only=True,
    )

    assert summary.total_seconds == 0


def test_the_team_pdf_covers_whole_days(db: Session, cast: Cast) -> None:
    report = build_team_report(
        db,
        user=cast.mikko,
        team_id=cast.team.id,
        starts_from=datetime(2026, 10, 5, 8, tzinfo=UTC),
        starts_before=datetime(2026, 10, 5, 8, 15, tzinfo=UTC),
        tz="UTC",
    )

    assert report.header.first_day == report.header.last_day
    assert report.header.first_day.isoformat() == "2026-10-05"
    assert report.totals.total_seconds == 3 * 3600


def sign_in(client: TestClient, email: str) -> TestClient:
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}, headers=CSRF
    )
    assert response.status_code == 200, response.text
    return client


def test_the_api_gives_totals_and_names(server: TestClient, cast: Cast) -> None:
    client = sign_in(server, "mikko@example.org")

    body = client.get(
        "/api/v1/reports/summary",
        params={**OCTOBER, "group_by": "user", "team_id": str(cast.team.id)},
    ).json()

    assert sorted(body["labels"].values()) == ["Liisa", "Mikko"]
    assert body["total_seconds"] == 9 * 3600
    assert "secret details" not in str(body)


def test_the_api_uses_the_organisations_zone_for_a_team(server: TestClient, cast: Cast) -> None:
    """A browser's half-hour zone cannot shift the day boundaries."""
    client = sign_in(server, "mikko@example.org")

    body = client.get(
        "/api/v1/reports/summary",
        params={**OCTOBER, "tz": "Asia/Kolkata", "group_by": "user", "team_id": str(cast.team.id)},
    ).json()

    assert body["time_zone"] == "UTC"


def test_the_api_hides_the_team_from_outsiders(server: TestClient, cast: Cast) -> None:
    client = sign_in(server, "olli@example.org")

    response = client.get(
        "/api/v1/reports/summary", params={**OCTOBER, "team_id": str(cast.team.id)}
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# The PDF
# ---------------------------------------------------------------------------


def test_the_team_pdf_data_has_totals_and_no_entries(db: Session, cast: Cast) -> None:
    report = build_team_report(
        db, user=cast.mikko, team_id=cast.team.id, starts_from=START, starts_before=END, tz="UTC"
    )

    assert report.team_name == "Web"
    assert [(m.name, m.total_seconds // 3600) for m in report.members] == [
        ("Mikko", 6),
        ("Liisa", 3),
    ]
    assert [p.name for p in report.projects] == ["Site", "Shop"]
    assert [
        (part.project.name, [(m.name, m.total_seconds // 3600) for m in part.members])
        for part in report.breakdown
    ] == [("Site", [("Mikko", 4), ("Liisa", 3)]), ("Shop", [("Mikko", 2)])]
    assert not hasattr(report, "entries")


def test_the_team_summaries_match_separate_summaries(db: Session, cast: Cast) -> None:
    """One reading of the entries, the same numbers as one query per table."""
    together = reports.summarize_team(
        db, user=cast.mikko, team_id=cast.team.id, starts_from=START, starts_before=END
    )

    assert together.by_project == team_summary(db, cast, GroupBy.PROJECT)
    assert together.by_member == team_summary(db, cast, GroupBy.USER)
    for project in (cast.site, cast.shop):
        assert together.members_by_project[str(project.id)] == team_summary(
            db, cast, GroupBy.USER, project_id=project.id
        )


def test_the_team_pdf_reads_the_entries_once(db: Session, cast: Cast) -> None:
    statements: list[str] = []

    def record(conn, cursor, statement, *args) -> None:  # type: ignore[no-untyped-def]
        statements.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        build_team_report(
            db,
            user=cast.mikko,
            team_id=cast.team.id,
            starts_from=START,
            starts_before=END,
            tz="UTC",
        )
    finally:
        event.remove(engine, "before_cursor_execute", record)

    def count(table: str) -> int:
        return sum(f"FROM {table}" in statement for statement in statements)

    # One reading of the entries, no tags (a team report never shows them),
    # and everyone's name once.
    assert count("time_entries") == 1
    assert count("tags") == 0
    assert sum("WHERE users.id IN" in statement for statement in statements) == 1


def test_an_outsider_asking_for_tags_still_gets_not_found(db: Session, cast: Cast) -> None:
    with pytest.raises(NotFoundError):
        team_summary(db, cast, GroupBy.TAG, user=cast.olli)


def test_the_team_pdf_downloads(server: TestClient, cast: Cast) -> None:
    client = sign_in(server, "liisa@example.org")

    response = client.get(
        "/api/v1/exports/pdf", params={**OCTOBER, "scope": "team", "id": str(cast.team.id)}
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert (
        'filename="hextime-web-2026-10-01-2026-10-31.pdf"'
        in response.headers["content-disposition"]
    )


def test_an_outsider_gets_no_team_pdf(server: TestClient, cast: Cast) -> None:
    client = sign_in(server, "anna@example.org")

    response = client.get(
        "/api/v1/exports/pdf", params={**OCTOBER, "scope": "team", "id": str(cast.team.id)}
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# My hours in the team: one's own entries on the team's projects
# ---------------------------------------------------------------------------


def test_my_hours_in_the_team_are_mine_on_its_projects_only(db: Session, cast: Cast) -> None:
    report = build_period_report(
        db, user=cast.mikko, team_id=cast.team.id, starts_from=START, starts_before=END, tz="UTC"
    )

    assert report.team_name == "Web"
    # Site 4 h and Shop 2 h; not Liisa's hours, not his own Course or loose hour.
    assert report.totals.total_seconds == 6 * 3600
    assert sorted(line.project or "" for line in report.entries) == ["Shop", "Site"]
    # His own entries keep their descriptions: they are his.
    assert {line.description for line in report.entries} == {"secret details"}


def test_my_hours_in_a_team_im_not_in_is_not_found(db: Session, cast: Cast) -> None:
    with pytest.raises(NotFoundError):
        build_period_report(
            db, user=cast.olli, team_id=cast.team.id, starts_from=START, starts_before=END, tz="UTC"
        )


def test_my_hours_in_the_team_download(server: TestClient, cast: Cast) -> None:
    client = sign_in(server, "mikko@example.org")

    response = client.get(
        "/api/v1/exports/pdf",
        params={**OCTOBER, "scope": "team", "id": str(cast.team.id), "mine": "true"},
    )

    assert response.status_code == 200
    assert (
        'filename="hextime-web-mikko-2026-10-01-2026-10-31.pdf"'
        in response.headers["content-disposition"]
    )
