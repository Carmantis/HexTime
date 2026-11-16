"""Accounts through one-time email links: invitations, resets, signing up."""

import re
from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.csrf import CSRF_HEADER
from app.core.db import get_db
from app.core.email import get_mailer
from app.core.errors import EmailDomainNotAllowedError, UserExistsError
from app.main import create_app
from app.models import AccountToken, AuthSession, TokenPurpose, User, utc_now
from app.services.accounts import check_email_domain, invite_user, issue_token
from app.services.auth import create_session
from app.services.users import make_admin
from tests.conftest import SERVER_SETTINGS, Outbox, build_settings

PASSWORD = "correct horse battery"
CSRF = {CSRF_HEADER: "1"}


def token_in(outbox: Outbox, index: int = -1) -> str:
    match = re.search(r"token=([\w-]+)", outbox[index].body)
    assert match, outbox[index].body
    return match.group(1)


def post(client: TestClient, path: str, body: dict):
    return client.post(f"/api/v1/auth/{path}", json=body, headers=CSRF)


@pytest.fixture
def invited(db: Session, server_settings: Settings, outbox: Outbox) -> User:
    return invite_user(
        db, email="Ville@example.org", display_name="Ville", settings=server_settings, mailer=outbox
    )


# ---------------------------------------------------------------------------
# Inviting
# ---------------------------------------------------------------------------


def test_an_invited_person_gets_a_link_not_a_password(
    invited: User, outbox: Outbox, db: Session
) -> None:
    assert invited.email == "ville@example.org"
    assert invited.password_hash is None
    assert len(outbox) == 1

    email = outbox[0]
    assert email.to == "ville@example.org"
    assert email.subject == "Tervetuloa HexTimeen"
    assert email.body.startswith("Hei Ville,")
    assert "https://hextime.example.fi/#/set-password?token=" in email.body
    # The database holds only the hash of what the email carries.
    stored = db.scalars(select(AccountToken.token_hash)).one()
    assert token_in(outbox) not in stored


def test_the_email_is_in_english_for_an_english_server(db: Session, outbox: Outbox) -> None:
    settings = build_settings(**SERVER_SETTINGS | {"default_locale": "en"})
    invite_user(
        db, email="ville@example.org", display_name="Ville", settings=settings, mailer=outbox
    )

    assert outbox[0].subject == "Welcome to HexTime"


@pytest.mark.parametrize(
    "address",
    [
        "ville@gmail.com",
        "ville@example.org.example.com",
        "ville@sub.example.org",
        "example.org",
        # Ends in the right domain, but an email header reads more than one address
        "attacker@evil.example,ville@example.org",
        "attacker@evil.example;ville@example.org",
        '"ville@example.org" <attacker@evil.example>,@example.org',
        "Attacker <attacker@evil.example> ville@example.org",
        "a@b@example.org",
        "ville @example.org",
        "@example.org",
    ],
)
def test_only_the_organisations_addresses_can_be_invited(
    db: Session, server_settings: Settings, outbox: Outbox, address: str
) -> None:
    with pytest.raises(EmailDomainNotAllowedError):
        invite_user(db, email=address, display_name="", settings=server_settings, mailer=outbox)
    assert outbox == []


def test_inviting_again_replaces_the_link(
    invited: User, db: Session, server_settings: Settings, outbox: Outbox, server: TestClient
) -> None:
    first = token_in(outbox)
    invite_user(
        db, email="ville@example.org", display_name="", settings=server_settings, mailer=outbox
    )

    assert post(server, "token", {"token": first}).status_code == 400
    assert post(server, "token", {"token": token_in(outbox)}).status_code == 200


def test_someone_with_an_account_cannot_be_invited_again(
    db: Session, server_settings: Settings, outbox: Outbox
) -> None:
    make_admin(db, email="anna@example.org", display_name="Anna", password=PASSWORD)

    with pytest.raises(UserExistsError):
        invite_user(
            db, email="anna@example.org", display_name="", settings=server_settings, mailer=outbox
        )


# ---------------------------------------------------------------------------
# Setting the password through the link
# ---------------------------------------------------------------------------


def test_the_link_tells_the_page_whose_it_is(
    invited: User, outbox: Outbox, server: TestClient
) -> None:
    response = post(server, "token", {"token": token_in(outbox)})

    assert response.json() == {
        "purpose": "setup",
        "email": "ville@example.org",
        "display_name": "Ville",
    }


def test_setting_the_password_signs_in(
    invited: User, outbox: Outbox, server: TestClient, db: Session
) -> None:
    response = post(server, "password/set", {"token": token_in(outbox), "password": PASSWORD})

    assert response.status_code == 200
    assert server.get("/api/v1/auth/me").json()["email"] == "ville@example.org"
    db.refresh(invited)
    assert invited.email_verified_at is not None


def test_a_link_works_only_once(invited: User, outbox: Outbox, server: TestClient) -> None:
    token = token_in(outbox)
    post(server, "password/set", {"token": token, "password": PASSWORD})

    again = post(server, "password/set", {"token": token, "password": "another password!"})

    assert again.status_code == 400
    assert again.json()["error"]["code"] == "invalid_token"


def test_a_too_short_password_leaves_the_link_usable(
    invited: User, outbox: Outbox, server: TestClient
) -> None:
    token = token_in(outbox)

    short = post(server, "password/set", {"token": token, "password": "short"})
    assert short.json()["error"]["code"] == "password_too_short"

    assert post(server, "password/set", {"token": token, "password": PASSWORD}).status_code == 200


def test_an_expired_link_is_refused(
    invited: User, outbox: Outbox, server: TestClient, db: Session
) -> None:
    stored = db.scalars(select(AccountToken)).one()
    stored.expires_at = utc_now() - timedelta(seconds=1)
    db.commit()

    response = post(server, "password/set", {"token": token_in(outbox), "password": PASSWORD})

    assert response.json()["error"]["code"] == "invalid_token"


def test_an_unknown_token_is_refused(server: TestClient) -> None:
    response = post(server, "token", {"token": "x" * 43})

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Forgotten password
# ---------------------------------------------------------------------------


@pytest.fixture
def anna(db: Session) -> User:
    return make_admin(db, email="anna@example.org", display_name="Anna", password=PASSWORD)


def test_a_forgotten_password_gets_a_reset_link(
    anna: User, outbox: Outbox, server: TestClient
) -> None:
    response = post(server, "password/forgot", {"email": "ANNA@example.org"})

    assert response.status_code == 204
    assert outbox[0].subject == "HexTime: uusi salasana"
    assert "#/set-password?token=" in outbox[0].body


def test_an_unknown_address_gets_the_same_answer_and_no_email(
    outbox: Outbox, server: TestClient
) -> None:
    response = post(server, "password/forgot", {"email": "nobody@example.org"})

    assert response.status_code == 204
    assert outbox == []


def test_asking_twice_in_a_row_sends_one_email(
    anna: User, outbox: Outbox, server: TestClient
) -> None:
    post(server, "password/forgot", {"email": "anna@example.org"})
    post(server, "password/forgot", {"email": "anna@example.org"})

    assert len(outbox) == 1


def test_someone_who_never_set_a_password_gets_the_setup_link_again(
    invited: User, outbox: Outbox, server: TestClient, db: Session
) -> None:
    # Pretend the invitation went out long ago and was lost.
    for token in db.scalars(select(AccountToken)):
        token.created_at = utc_now() - timedelta(days=3)
    db.commit()

    post(server, "password/forgot", {"email": "ville@example.org"})

    assert len(outbox) == 2
    assert outbox[1].subject == "Tervetuloa HexTimeen"


def test_a_reset_signs_out_every_other_session(
    anna: User, outbox: Outbox, server: TestClient, db: Session
) -> None:
    post(server, "login", {"email": "anna@example.org", "password": PASSWORD})
    old_cookie = dict(server.cookies)

    post(server, "password/forgot", {"email": "anna@example.org"})
    post(server, "password/set", {"token": token_in(outbox), "password": "a brand new one!"})

    server.cookies.clear()
    server.cookies.update(old_cookie)
    assert server.get("/api/v1/auth/me").status_code == 401


# ---------------------------------------------------------------------------
# Signing up yourself
# ---------------------------------------------------------------------------


def test_signing_up_is_closed_by_default(server: TestClient) -> None:
    response = post(
        server,
        "register",
        {"email": "uusi@example.org", "display_name": "Uusi"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "registration_closed"


@pytest.fixture
def open_settings() -> Settings:
    return build_settings(**SERVER_SETTINGS | {"allow_self_registration": True})


@pytest.fixture
def open_server(db: Session, outbox: Outbox, open_settings: Settings) -> Iterator[TestClient]:
    """Like the `server` fixture, on a server that lets people sign up."""
    app = create_app(settings=open_settings, serve_static=False)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_mailer] = lambda: outbox
    with TestClient(app, base_url="https://testserver") as client:
        yield client


def test_signing_up_sends_a_link_for_choosing_the_password(
    open_server: TestClient, outbox: Outbox
) -> None:
    body = {"email": "uusi@example.org", "display_name": "Uusi"}
    assert post(open_server, "register", body).status_code == 202

    assert outbox[0].to == "uusi@example.org"
    assert outbox[0].subject == "HexTime: viimeistele tunnuksesi"
    assert "#/set-password?token=" in outbox[0].body
    info = post(open_server, "token", {"token": token_in(outbox)}).json()
    assert info["purpose"] == "setup"
    assert info["display_name"] == "Uusi"

    # Choosing the password proves the address and signs in
    response = post(open_server, "password/set", {"token": token_in(outbox), "password": PASSWORD})
    assert response.status_code == 200
    open_server.cookies.clear()
    login = post(open_server, "login", {"email": "uusi@example.org", "password": PASSWORD})
    assert login.status_code == 200


def test_signing_up_for_someone_else_gives_no_way_in(
    open_server: TestClient, outbox: Outbox, db: Session
) -> None:
    # An attacker signs up the victim's address. A password sent along, as
    # the old form did, is ignored: none is stored before the link is used.
    body = {"email": "anna@example.org", "display_name": "Anna", "password": "attacker's own!"}
    assert post(open_server, "register", body).status_code == 202

    account = db.scalars(select(User).where(User.email == "anna@example.org")).one()
    assert account.password_hash is None
    login = post(open_server, "login", {"email": "anna@example.org", "password": "attacker's own!"})
    assert login.status_code == 401
    # Only the inbox's owner gets the link that sets a password
    assert [email.to for email in outbox] == ["anna@example.org"]


def test_signing_up_with_a_taken_address_reveals_nothing(
    anna: User, open_server: TestClient, outbox: Outbox
) -> None:
    body = {"email": "anna@example.org", "display_name": "Fake"}

    response = post(open_server, "register", body)

    # The same answer as for a new address; the owner gets a reset link.
    assert response.status_code == 202
    assert outbox[0].to == "anna@example.org"
    assert outbox[0].subject == "HexTime: uusi salasana"


def test_signing_up_needs_an_organisation_address(open_server: TestClient) -> None:
    body = {"email": "someone@gmail.com", "display_name": ""}

    assert post(open_server, "register", body).json()["error"]["code"] == "email_domain_not_allowed"


def test_signing_up_cannot_send_the_link_to_another_address(
    open_server: TestClient, outbox: Outbox
) -> None:
    body = {"email": "me@evil.example,anna@example.org", "display_name": ""}

    assert post(open_server, "register", body).json()["error"]["code"] == "email_domain_not_allowed"
    assert outbox == []


def test_plain_organisation_addresses_still_pass(server_settings: Settings) -> None:
    for address in [
        "anna@example.org",
        " Anna.Virtanen+hextime@Example.ORG ",
        "o'neil@example.org",
    ]:
        assert check_email_domain(address, server_settings) == address.strip().lower()


# ---------------------------------------------------------------------------
# Local mode
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["token", "password/set", "password/forgot", "register"])
def test_local_mode_has_none_of_this(api_client: TestClient, path: str) -> None:
    response = api_client.post(
        f"/api/v1/auth/{path}", json={"token": "x" * 43, "email": "a@b.fi", "password": PASSWORD}
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Tidying up
# ---------------------------------------------------------------------------


def test_issuing_a_link_clears_out_dead_ones(
    invited: User, db: Session, server_settings: Settings, outbox: Outbox
) -> None:
    old = db.scalars(select(AccountToken)).one()
    old.expires_at = utc_now() - timedelta(seconds=1)
    db.commit()
    other = make_admin(db, email="anna@example.org", display_name="Anna", password=PASSWORD)
    issue_token(db, other, TokenPurpose.RESET)
    db.commit()

    # Only the new one is left: the expired invitation link is gone.
    assert [t.user_id for t in db.scalars(select(AccountToken))] == [other.id]


def test_signing_in_clears_out_expired_sessions(server: TestClient, db: Session) -> None:
    anna = make_admin(db, email="anna@example.org", display_name="Anna", password=PASSWORD)
    create_session(db, user=anna, days=14)
    for session in db.scalars(select(AuthSession)):
        session.expires_at = utc_now() - timedelta(seconds=1)
    db.commit()

    post(server, "login", {"email": "anna@example.org", "password": PASSWORD})

    assert len(db.scalars(select(AuthSession)).all()) == 1
