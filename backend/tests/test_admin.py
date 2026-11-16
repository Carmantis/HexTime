"""The organisation administrator's user list (server mode)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.csrf import CSRF_HEADER
from app.core.errors import EmailFailedError
from app.models import User
from app.services.accounts import invite_user
from app.services.users import make_admin
from tests.conftest import Outbox

PASSWORD = "correct horse battery"
CSRF = {CSRF_HEADER: "1"}
USERS = "/api/v1/admin/users"


def sign_in(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}, headers=CSRF
    )
    assert response.status_code == 200, response.text


@pytest.fixture
def anna(db: Session) -> User:
    return make_admin(db, email="anna@example.org", display_name="Anna", password=PASSWORD)


@pytest.fixture
def as_admin(server: TestClient, anna: User) -> TestClient:
    sign_in(server, "anna@example.org")
    return server


@pytest.fixture
def ville(db: Session, anna: User) -> User:
    """An ordinary member with a password."""
    user = make_admin(db, email="ville@example.org", display_name="Ville", password=PASSWORD)
    user.is_admin = False
    db.commit()
    return user


def add(client: TestClient, *people: tuple[str, str]):
    body = {"people": [{"email": email, "display_name": name} for email, name in people]}
    return client.post(USERS, json=body, headers=CSRF)


# ---------------------------------------------------------------------------
# Who may use it
# ---------------------------------------------------------------------------


def test_only_administrators_get_in(server: TestClient, ville: User) -> None:
    sign_in(server, "ville@example.org")

    response = server.get(USERS)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_signed_out_is_401(server: TestClient) -> None:
    assert server.get(USERS).status_code == 401


def test_local_mode_has_no_admin_view(api_client: TestClient) -> None:
    assert api_client.get(USERS).status_code == 404


# ---------------------------------------------------------------------------
# The list
# ---------------------------------------------------------------------------


def test_the_list_shows_each_persons_status(
    as_admin: TestClient, db: Session, ville: User, server_settings, outbox: Outbox
) -> None:
    invite_user(
        db, email="uusi@example.org", display_name="Uusi", settings=server_settings, mailer=outbox
    )
    ville.is_active = False
    db.commit()

    rows = {row["email"]: row for row in as_admin.get(USERS).json()}

    assert rows["anna@example.org"]["status"] == "active"
    assert rows["anna@example.org"]["is_admin"] is True
    assert rows["uusi@example.org"]["status"] == "invited"
    assert rows["ville@example.org"]["status"] == "disabled"


# ---------------------------------------------------------------------------
# Adding many at once
# ---------------------------------------------------------------------------


def test_adding_a_list_invites_everyone(as_admin: TestClient, outbox: Outbox) -> None:
    response = add(as_admin, ("matti@example.org", "Matti"), ("Liisa@EXAMPLE.org", "Liisa"))

    assert response.status_code == 200
    assert [r["outcome"] for r in response.json()["results"]] == ["invited", "invited"]
    assert sorted(email.to for email in outbox) == ["liisa@example.org", "matti@example.org"]


def test_one_bad_row_does_not_stop_the_rest(
    as_admin: TestClient, ville: User, outbox: Outbox
) -> None:
    response = add(
        as_admin,
        ("matti@example.org", "Matti"),
        ("someone@gmail.com", "Outsider"),
        ("ville@example.org", "Ville"),
        ("MATTI@example.org", "Matti again"),
        ("liisa@example.org", ""),
    )

    outcomes = [r["outcome"] for r in response.json()["results"]]
    assert outcomes == ["invited", "invalid_domain", "exists", "duplicate", "invited"]
    assert len(outbox) == 2
    # Without a name, the part before @ stands in until they change it.
    assert response.json()["results"][4]["display_name"] == "liisa"


def test_adding_someone_who_never_set_a_password_resends(
    as_admin: TestClient, outbox: Outbox
) -> None:
    add(as_admin, ("matti@example.org", "Matti"))

    response = add(as_admin, ("matti@example.org", "Matti"))

    assert response.json()["results"][0]["outcome"] == "resent"
    assert len(outbox) == 2


def test_a_failed_email_still_adds_the_person(
    as_admin: TestClient, outbox: Outbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(email) -> None:
        raise EmailFailedError("down")

    monkeypatch.setattr(outbox, "send", refuse)

    result = add(as_admin, ("matti@example.org", "Matti")).json()["results"][0]

    assert result["outcome"] == "email_failed"
    assert result["user_id"] is not None
    assert any(row["email"] == "matti@example.org" for row in as_admin.get(USERS).json())


def test_an_empty_list_is_refused(as_admin: TestClient) -> None:
    assert as_admin.post(USERS, json={"people": []}, headers=CSRF).status_code == 422


# ---------------------------------------------------------------------------
# Links, disabling, administrator rights
# ---------------------------------------------------------------------------


def test_sending_a_link_to_someone_with_a_password_sends_a_reset(
    as_admin: TestClient, ville: User, outbox: Outbox
) -> None:
    response = as_admin.post(f"{USERS}/{ville.id}/send-link", headers=CSRF)

    assert response.status_code == 204
    assert outbox[-1].subject == "HexTime: uusi salasana"


def test_sending_a_link_to_an_invited_person_resends_the_invitation(
    as_admin: TestClient, outbox: Outbox
) -> None:
    user_id = add(as_admin, ("matti@example.org", "Matti")).json()["results"][0]["user_id"]

    as_admin.post(f"{USERS}/{user_id}/send-link", headers=CSRF)

    assert [email.subject for email in outbox] == ["Tervetuloa HexTimeen"] * 2


def test_disabling_signs_the_person_out_at_once(
    as_admin: TestClient, ville: User, db: Session, server: TestClient
) -> None:
    response = as_admin.patch(f"{USERS}/{ville.id}", json={"is_active": False}, headers=CSRF)

    assert response.json()["status"] == "disabled"
    db.refresh(ville)
    assert not ville.is_active
    # Disabled people get no link either, until enabled again.
    assert as_admin.post(f"{USERS}/{ville.id}/send-link", headers=CSRF).status_code == 422


def test_administrator_rights_can_be_granted(as_admin: TestClient, ville: User) -> None:
    response = as_admin.patch(f"{USERS}/{ville.id}", json={"is_admin": True}, headers=CSRF)

    assert response.json()["is_admin"] is True


@pytest.mark.parametrize("change", [{"is_active": False}, {"is_admin": False}])
def test_an_administrator_cannot_lock_themselves_out(
    as_admin: TestClient, anna: User, change: dict
) -> None:
    response = as_admin.patch(f"{USERS}/{anna.id}", json=change, headers=CSRF)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "cannot_change_self"


def test_an_unknown_user_is_404(as_admin: TestClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert as_admin.patch(f"{USERS}/{missing}", json={}, headers=CSRF).status_code == 404
