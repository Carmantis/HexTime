"""Teams, invitations, roles and what each role may do (server mode).

Decided 2026-10-08: whoever creates a team is its lead; a lead invites people
already in the organisation, and they join only by saying yes. The
organisation administrator stands in only for a team left without a lead.

The cast: Anna is the organisation administrator, Liisa leads the team,
Mikko is a member, and Olli is in the organisation but not in the team.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.csrf import CSRF_HEADER
from app.core.errors import EmailFailedError
from app.models import AuditLog, Project, TeamInvitation, TeamMember, TeamRole, User
from app.services import entries
from app.services.users import make_admin
from tests.conftest import Outbox

PASSWORD = "correct horse battery"
CSRF = {CSRF_HEADER: "1"}
TEAMS = "/api/v1/teams"
MINE = "/api/v1/invitations"

SignIn = Callable[[str], TestClient]


def person(db: Session, email: str, name: str, *, admin: bool = False) -> User:
    user = make_admin(db, email=email, display_name=name, password=PASSWORD)
    user.is_admin = admin
    db.commit()
    return user


@pytest.fixture
def anna(db: Session) -> User:
    return person(db, "anna@example.org", "Anna", admin=True)


@pytest.fixture
def liisa(db: Session) -> User:
    return person(db, "liisa@example.org", "Liisa")


@pytest.fixture
def mikko(db: Session) -> User:
    return person(db, "mikko@example.org", "Mikko")


@pytest.fixture
def olli(db: Session) -> User:
    return person(db, "olli@example.org", "Olli")


@pytest.fixture
def as_(server: TestClient) -> SignIn:
    """Sign in as someone else on the same client."""

    def sign_in(email: str) -> TestClient:
        server.cookies.clear()
        response = server.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}, headers=CSRF
        )
        assert response.status_code == 200, response.text
        return server

    return sign_in


def invite(client: TestClient, team: UUID, user: User):
    return client.post(f"{TEAMS}/{team}/invitations", json={"user_id": str(user.id)}, headers=CSRF)


@pytest.fixture
def team(as_: SignIn, liisa: User, mikko: User) -> UUID:
    """Liisa's team: Liisa the lead, Mikko a member who said yes."""
    client = as_("liisa@example.org")
    team_id = UUID(client.post(TEAMS, json={"name": "Web"}, headers=CSRF).json()["id"])
    assert invite(client, team_id, mikko).status_code == 201
    assert (
        as_("mikko@example.org").post(f"{MINE}/{team_id}/accept", headers=CSRF).status_code == 204
    )
    return team_id


@pytest.fixture
def team_project(as_: SignIn, team: UUID) -> UUID:
    client = as_("liisa@example.org")
    response = client.post(
        "/api/v1/projects", json={"name": "Asiakassivut", "team_id": str(team)}, headers=CSRF
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


def at(hour: int) -> datetime:
    return datetime(2026, 10, 5, hour, tzinfo=UTC)


def roles_in(db: Session, team: UUID) -> dict[str, TeamRole]:
    db.expire_all()
    return {
        user.display_name: member.role
        for user, member in db.execute(
            select(User, TeamMember)
            .join(TeamMember, TeamMember.user_id == User.id)
            .where(TeamMember.team_id == team)
        )
    }


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------


def test_the_creator_becomes_the_lead(as_: SignIn, liisa: User) -> None:
    created = as_("liisa@example.org").post(TEAMS, json={"name": "  Web  "}, headers=CSRF)

    assert created.status_code == 201
    body = created.json()
    assert (body["name"], body["role"], body["member_count"]) == ("Web", "lead", 1)
    assert body["can_manage"] is True


def test_people_see_only_their_own_teams(as_: SignIn, team: UUID, olli: User) -> None:
    assert [t["name"] for t in as_("mikko@example.org").get(TEAMS).json()] == ["Web"]
    assert as_("olli@example.org").get(TEAMS).json() == []
    assert as_("olli@example.org").get(f"{TEAMS}/{team}/members").status_code == 404


def test_members_see_each_other(as_: SignIn, team: UUID) -> None:
    members = as_("mikko@example.org").get(f"{TEAMS}/{team}/members").json()

    assert [(m["display_name"], m["role"]) for m in members] == [
        ("Liisa", "lead"),
        ("Mikko", "member"),
    ]


def test_only_a_lead_renames_the_team(as_: SignIn, team: UUID) -> None:
    denied = as_("mikko@example.org").patch(f"{TEAMS}/{team}", json={"name": "X"}, headers=CSRF)
    assert denied.status_code == 403

    renamed = as_("liisa@example.org").patch(
        f"{TEAMS}/{team}", json={"name": "Verkko"}, headers=CSRF
    )
    assert renamed.json()["name"] == "Verkko"


def test_a_team_with_booked_hours_cannot_be_deleted(
    as_: SignIn, team: UUID, team_project: UUID, mikko: User, db: Session
) -> None:
    entries.create_entry(db, user=mikko, started_at=at(9), ended_at=at(10), project_id=team_project)

    response = as_("liisa@example.org").delete(f"{TEAMS}/{team}", headers=CSRF)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "team_has_entries"


def test_deleting_an_unused_team_takes_its_projects(
    as_: SignIn, team: UUID, team_project: UUID, db: Session
) -> None:
    assert as_("mikko@example.org").delete(f"{TEAMS}/{team}", headers=CSRF).status_code == 403

    assert as_("liisa@example.org").delete(f"{TEAMS}/{team}", headers=CSRF).status_code == 204
    db.expire_all()
    assert db.get(Project, team_project) is None
    assert db.scalars(select(TeamMember)).all() == []


def test_local_mode_has_no_teams(api_client: TestClient) -> None:
    for path in (TEAMS, MINE, "/api/v1/people"):
        assert api_client.get(path).status_code == 404


# ---------------------------------------------------------------------------
# Inviting and answering
# ---------------------------------------------------------------------------


def test_nobody_joins_without_saying_yes(as_: SignIn, team: UUID, olli: User) -> None:
    assert invite(as_("liisa@example.org"), team, olli).status_code == 201

    client = as_("olli@example.org")
    # Invited, not a member: the team stays out of sight until he answers.
    assert client.get(TEAMS).json() == []
    pending = client.get(MINE).json()
    assert [(p["team_name"], p["invited_by"]) for p in pending] == [("Web", "Liisa")]

    assert client.post(f"{MINE}/{team}/accept", headers=CSRF).status_code == 204
    assert [(t["name"], t["role"]) for t in client.get(TEAMS).json()] == [("Web", "member")]
    assert client.get(MINE).json() == []


def test_saying_no_leaves_no_trace(as_: SignIn, team: UUID, olli: User, db: Session) -> None:
    invite(as_("liisa@example.org"), team, olli)

    client = as_("olli@example.org")
    assert client.post(f"{MINE}/{team}/decline", headers=CSRF).status_code == 204

    assert client.get(TEAMS).json() == []
    assert db.scalars(select(TeamInvitation)).all() == []
    # An answer needs an invitation: the same yes cannot be given twice.
    assert client.post(f"{MINE}/{team}/accept", headers=CSRF).status_code == 404


def test_the_lead_sees_and_cancels_whom_they_invited(as_: SignIn, team: UUID, olli: User) -> None:
    client = as_("liisa@example.org")
    invite(client, team, olli)

    assert [i["display_name"] for i in client.get(f"{TEAMS}/{team}/invitations").json()] == ["Olli"]
    cancel = client.delete(f"{TEAMS}/{team}/invitations/{olli.id}", headers=CSRF)

    assert cancel.status_code == 204
    assert as_("olli@example.org").get(MINE).json() == []


def test_nobody_is_invited_twice_or_while_in_the_team(
    as_: SignIn, team: UUID, mikko: User, olli: User
) -> None:
    client = as_("liisa@example.org")
    invite(client, team, olli)

    assert invite(client, team, olli).json()["error"]["code"] == "already_invited"
    assert invite(client, team, mikko).json()["error"]["code"] == "already_member"


def test_a_member_invites_nobody(as_: SignIn, team: UUID, olli: User) -> None:
    assert invite(as_("mikko@example.org"), team, olli).status_code == 403


def test_a_disabled_account_cannot_be_invited(
    as_: SignIn, team: UUID, olli: User, db: Session
) -> None:
    olli.is_active = False
    db.commit()

    assert invite(as_("liisa@example.org"), team, olli).status_code == 404


def test_the_search_finds_people_in_the_organisation(
    as_: SignIn, liisa: User, mikko: User, olli: User, db: Session
) -> None:
    olli.is_active = False
    db.commit()
    client = as_("liisa@example.org")

    found = client.get("/api/v1/people", params={"q": "MIK"}).json()
    everyone = client.get("/api/v1/people").json()

    assert [p["email"] for p in found] == ["mikko@example.org"]
    # Disabled accounts are not offered.
    assert [p["display_name"] for p in everyone] == ["Liisa", "Mikko"]


# ---------------------------------------------------------------------------
# Roles and leaving
# ---------------------------------------------------------------------------


def test_a_lead_makes_a_member_a_lead(as_: SignIn, team: UUID, mikko: User, db: Session) -> None:
    url = f"{TEAMS}/{team}/members/{mikko.id}"

    assert (
        as_("mikko@example.org").patch(url, json={"role": "lead"}, headers=CSRF).status_code == 403
    )
    assert (
        as_("liisa@example.org").patch(url, json={"role": "lead"}, headers=CSRF).status_code == 200
    )

    assert roles_in(db, team) == {"Liisa": TeamRole.LEAD, "Mikko": TeamRole.LEAD}


def test_there_is_no_admin_role_in_a_team(as_: SignIn, team: UUID, mikko: User) -> None:
    response = as_("liisa@example.org").patch(
        f"{TEAMS}/{team}/members/{mikko.id}", json={"role": "admin"}, headers=CSRF
    )

    assert response.status_code == 422


def test_the_last_lead_cannot_step_down_or_leave(as_: SignIn, team: UUID, liisa: User) -> None:
    client = as_("liisa@example.org")
    url = f"{TEAMS}/{team}/members/{liisa.id}"

    assert client.patch(url, json={"role": "member"}, headers=CSRF).json()["error"]["code"] == (
        "last_team_lead"
    )
    assert client.delete(url, headers=CSRF).json()["error"]["code"] == "last_team_lead"


def test_a_lead_may_leave_once_there_is_another(
    as_: SignIn, team: UUID, liisa: User, mikko: User, db: Session
) -> None:
    client = as_("liisa@example.org")
    client.patch(f"{TEAMS}/{team}/members/{mikko.id}", json={"role": "lead"}, headers=CSRF)

    assert client.delete(f"{TEAMS}/{team}/members/{liisa.id}", headers=CSRF).status_code == 204
    assert roles_in(db, team) == {"Mikko": TeamRole.LEAD}


def test_a_member_may_leave_but_not_remove_others(
    as_: SignIn, team: UUID, liisa: User, mikko: User
) -> None:
    client = as_("mikko@example.org")

    assert client.delete(f"{TEAMS}/{team}/members/{liisa.id}", headers=CSRF).status_code == 403
    assert client.delete(f"{TEAMS}/{team}/members/{mikko.id}", headers=CSRF).status_code == 204
    assert client.get(TEAMS).json() == []


# ---------------------------------------------------------------------------
# The administrator: sees teams, steps in only when no lead is left
# ---------------------------------------------------------------------------


def test_the_administrator_sees_every_team_but_does_not_run_it(
    as_: SignIn, team: UUID, anna: User, mikko: User, olli: User
) -> None:
    client = as_("anna@example.org")

    listed = client.get(TEAMS).json()
    assert [(t["name"], t["role"], t["can_manage"], t["has_lead"]) for t in listed] == [
        ("Web", None, False, True)
    ]
    assert client.get(f"{TEAMS}/{team}/members").status_code == 200
    promote = client.patch(
        f"{TEAMS}/{team}/members/{mikko.id}", json={"role": "lead"}, headers=CSRF
    )
    assert promote.status_code == 403
    assert invite(client, team, olli).status_code == 403


def test_the_administrator_steps_in_when_the_lead_is_gone(
    as_: SignIn, team: UUID, anna: User, liisa: User, mikko: User, db: Session
) -> None:
    """Liisa left the organisation and her account was disabled."""
    liisa.is_active = False
    db.commit()
    client = as_("anna@example.org")

    assert client.get(TEAMS).json()[0]["can_manage"] is True
    promote = client.patch(
        f"{TEAMS}/{team}/members/{mikko.id}", json={"role": "lead"}, headers=CSRF
    )
    assert promote.status_code == 200

    # A lead is back, and the administrator steps aside again.
    assert client.get(TEAMS).json()[0]["can_manage"] is False


# ---------------------------------------------------------------------------
# The team's projects
# ---------------------------------------------------------------------------


def test_members_see_and_book_on_the_teams_projects(
    as_: SignIn, team_project: UUID, mikko: User, db: Session
) -> None:
    listed = as_("mikko@example.org").get("/api/v1/projects").json()

    assert [(p["name"], p["owner_team_id"] is not None) for p in listed] == [("Asiakassivut", True)]
    entry = entries.create_entry(
        db, user=mikko, started_at=at(9), ended_at=at(10), project_id=team_project
    )
    assert entry.project_id == team_project


def test_only_a_lead_changes_a_teams_project(as_: SignIn, team_project: UUID) -> None:
    url = f"/api/v1/projects/{team_project}"

    denied = as_("mikko@example.org").patch(url, json={"hourly_rate_cents": 1}, headers=CSRF)
    no_task = as_("mikko@example.org").post(f"{url}/tasks", json={"name": "Design"}, headers=CSRF)
    allowed = as_("liisa@example.org").patch(url, json={"hourly_rate_cents": 9000}, headers=CSRF)

    assert denied.status_code == 403
    assert no_task.status_code == 403
    assert allowed.json()["hourly_rate_cents"] == 9000


def test_a_member_cannot_create_a_teams_project(as_: SignIn, team: UUID) -> None:
    response = as_("mikko@example.org").post(
        "/api/v1/projects", json={"name": "Oma", "team_id": str(team)}, headers=CSRF
    )

    assert response.status_code == 403


def test_outsiders_neither_see_nor_book_on_it(
    as_: SignIn, team_project: UUID, olli: User, db: Session
) -> None:
    client = as_("olli@example.org")

    assert client.get("/api/v1/projects").json() == []
    assert client.get(f"/api/v1/projects/{team_project}").status_code == 404
    booked = client.post(
        "/api/v1/entries",
        json={
            "started_at": at(9).isoformat(),
            "ended_at": at(10).isoformat(),
            "project_id": str(team_project),
        },
        headers=CSRF,
    )
    assert booked.status_code == 404


def test_a_team_tag_is_shared_too(as_: SignIn, team: UUID) -> None:
    created = as_("liisa@example.org").post(
        "/api/v1/tags", json={"name": "kiire", "team_id": str(team)}, headers=CSRF
    )
    assert created.status_code == 201

    client = as_("mikko@example.org")
    assert [t["name"] for t in client.get("/api/v1/tags").json()] == ["kiire"]
    tag_id = created.json()["id"]
    assert client.post(f"/api/v1/tags/{tag_id}/archive", headers=CSRF).status_code == 403


# ---------------------------------------------------------------------------
# Nobody else's hours (decided 2026-10-08)
#
# A team sees each member's total on the team's projects in the team report.
# Single entries stay their owner's alone, whatever anyone's role.
# ---------------------------------------------------------------------------


@pytest.fixture
def mikkos_entry(team_project: UUID, mikko: User, db: Session) -> UUID:
    """Mikko's hour on the team's own project, the most shared kind there is."""
    return entries.create_entry(
        db, user=mikko, started_at=at(9), ended_at=at(10), project_id=team_project
    ).id


@pytest.mark.parametrize("who", ["liisa@example.org", "anna@example.org"])
def test_neither_the_lead_nor_the_administrator_sees_an_entry(
    as_: SignIn, mikkos_entry: UUID, anna: User, who: str
) -> None:
    client = as_(who)

    assert client.get(f"/api/v1/entries/{mikkos_entry}").status_code == 404
    assert client.get("/api/v1/entries").json() == []


def test_a_lead_cannot_change_or_delete_a_members_entry(
    as_: SignIn, mikkos_entry: UUID, db: Session
) -> None:
    client = as_("liisa@example.org")
    url = f"/api/v1/entries/{mikkos_entry}"

    assert client.patch(url, json={"ended_at": at(16).isoformat()}, headers=CSRF).status_code == 404
    assert client.delete(url, headers=CSRF).status_code == 404
    db.expire_all()
    assert db.scalars(select(AuditLog).where(AuditLog.action != "create")).all() == []


def test_asking_for_someone_elses_entries_by_id_gives_ones_own(
    as_: SignIn, mikkos_entry: UUID, mikko: User
) -> None:
    """There is no user filter: an unknown query parameter is ignored."""
    listed = as_("liisa@example.org").get("/api/v1/entries", params={"user_id": str(mikko.id)})

    assert listed.json() == []


def test_a_member_stops_their_own_forgotten_timer(
    as_: SignIn, team: UUID, mikko: User, db: Session
) -> None:
    forgotten = entries.create_entry(db, user=mikko, started_at=at(8)).id

    stopped = as_("mikko@example.org").patch(
        f"/api/v1/entries/{forgotten}", json={"ended_at": at(16).isoformat()}, headers=CSRF
    )

    assert stopped.status_code == 200


def test_the_invited_person_gets_an_email(
    as_: SignIn, team: UUID, olli: User, outbox: Outbox
) -> None:
    invite(as_("liisa@example.org"), team, olli)

    assert outbox[-1].to == "olli@example.org"
    assert outbox[-1].subject == "HexTime: kutsu tiimiin Web"
    assert "Liisa kutsui sinut tiimiin Web" in outbox[-1].body
    assert "https://hextime.example.fi/#/teams" in outbox[-1].body


def test_an_invitation_stands_when_the_email_fails(
    as_: SignIn, team: UUID, olli: User, outbox: Outbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(_email: object) -> None:
        raise EmailFailedError("the email could not be sent")

    monkeypatch.setattr(outbox, "send", broken)

    assert invite(as_("liisa@example.org"), team, olli).status_code == 201
    assert as_("olli@example.org").get(MINE).json()[0]["team_name"] == "Web"
