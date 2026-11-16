"""Signing in and out in server mode, and what a missing sign-in blocks."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import EMAIL_FORM_LIMIT
from app.core.csrf import CSRF_HEADER
from app.core.deps import SESSION_COOKIE
from app.models import AuthSession, LoginAttempt, User, utc_now
from app.services.auth import MAX_FAILURES, MAX_FAILURES_PER_IP
from app.services.users import make_admin

PASSWORD = "correct horse battery"
CSRF = {CSRF_HEADER: "1"}


@pytest.fixture
def anna(db: Session) -> User:
    return make_admin(db, email="anna@example.org", display_name="Anna", password=PASSWORD)


def login(client: TestClient, email: str = "anna@example.org", password: str = PASSWORD):
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}, headers=CSRF
    )


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def test_login_sets_a_safe_session_cookie(server: TestClient, anna: User) -> None:
    response = login(server)

    assert response.status_code == 200
    assert response.json()["email"] == "anna@example.org"
    assert response.json()["is_admin"] is True
    cookie = response.headers["set-cookie"].lower()
    assert f"{SESSION_COOKIE}=" in cookie
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie


def test_the_cookie_signs_the_next_requests_in(server: TestClient, anna: User) -> None:
    login(server)

    assert server.get("/api/v1/auth/me").json()["display_name"] == "Anna"
    assert server.get("/api/v1/entries").status_code == 200


def test_only_the_token_hash_is_stored(server: TestClient, anna: User, db: Session) -> None:
    token = login(server).cookies[SESSION_COOKIE]

    stored = db.scalars(select(AuthSession.token_hash)).one()
    assert token not in stored
    assert len(stored) == 64


def test_the_email_is_not_case_sensitive(server: TestClient, anna: User) -> None:
    assert login(server, email="  Anna@EXAMPLE.org ").status_code == 200


def test_a_wrong_password_and_an_unknown_address_look_the_same(
    server: TestClient, anna: User
) -> None:
    wrong_password = login(server, password="not the password")
    unknown = login(server, email="nobody@example.org")

    assert wrong_password.status_code == unknown.status_code == 401
    assert wrong_password.json() == unknown.json()
    assert wrong_password.json()["error"]["code"] == "not_authenticated"


def test_a_disabled_account_cannot_sign_in(server: TestClient, anna: User, db: Session) -> None:
    anna.is_active = False
    db.commit()

    assert login(server).status_code == 401


def test_repeated_failures_are_refused_for_a_while(server: TestClient, anna: User) -> None:
    for _ in range(MAX_FAILURES):
        assert login(server, password="guess guess guess").status_code == 401

    # Even the right password waits now: the guesser must not learn it worked.
    response = login(server)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "too_many_attempts"


def test_old_failures_stop_counting(server: TestClient, anna: User, db: Session) -> None:
    for _ in range(MAX_FAILURES):
        login(server, password="guess guess guess")
    for attempt in db.scalars(select(LoginAttempt)):
        attempt.attempted_at = utc_now() - timedelta(minutes=16)
    db.commit()

    assert login(server).status_code == 200


def test_a_successful_login_clears_the_failures(
    server: TestClient, anna: User, db: Session
) -> None:
    for _ in range(MAX_FAILURES - 1):
        login(server, password="guess guess guess")

    login(server)

    assert db.scalars(select(LoginAttempt)).all() == []


def test_one_network_cannot_try_a_password_on_every_account(
    server: TestClient, anna: User, db: Session
) -> None:
    # TestClient's requests come from the address "testclient"
    for n in range(MAX_FAILURES_PER_IP):
        db.add(LoginAttempt(email=f"person{n}@example.org", ip="testclient"))
    db.commit()

    response = login(server)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "too_many_attempts"


def test_failures_from_another_network_do_not_count(
    server: TestClient, anna: User, db: Session
) -> None:
    for n in range(MAX_FAILURES_PER_IP):
        db.add(LoginAttempt(email=f"person{n}@example.org", ip="203.0.113.9"))
    db.commit()

    assert login(server).status_code == 200


def test_the_forgotten_password_form_cannot_be_used_to_flood(server: TestClient) -> None:
    def ask() -> int:
        return server.post(
            "/api/v1/auth/password/forgot",
            json={"email": "someone@example.org"},
            headers={CSRF_HEADER: "1"},
        ).status_code

    assert [ask() for _ in range(EMAIL_FORM_LIMIT)] == [204] * EMAIL_FORM_LIMIT
    assert ask() == 429


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def test_without_a_session_the_api_answers_401(server: TestClient) -> None:
    response = server.get("/api/v1/entries")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_logout_ends_the_session_for_good(server: TestClient, anna: User) -> None:
    token = login(server).cookies[SESSION_COOKIE]

    assert server.post("/api/v1/auth/logout", headers=CSRF).status_code == 204
    # The server forgot the token: replaying the old cookie does not help.
    server.cookies.set(SESSION_COOKIE, token)
    assert server.get("/api/v1/auth/me").status_code == 401


def test_an_expired_session_is_refused_and_removed(
    server: TestClient, anna: User, db: Session
) -> None:
    login(server)
    session = db.scalars(select(AuthSession)).one()
    session.expires_at = utc_now() - timedelta(seconds=1)
    db.commit()

    assert server.get("/api/v1/auth/me").status_code == 401
    assert db.scalars(select(AuthSession)).all() == []


def test_using_the_app_keeps_the_session_alive(server: TestClient, anna: User, db: Session) -> None:
    login(server)
    session = db.scalars(select(AuthSession)).one()
    session.expires_at = utc_now() + timedelta(days=1)
    db.commit()

    server.get("/api/v1/auth/me")

    db.refresh(session)
    assert session.expires_at > utc_now() + timedelta(days=13)


def test_disabling_an_account_ends_its_sessions_at_once(
    server: TestClient, anna: User, db: Session
) -> None:
    login(server)
    anna.is_active = False
    db.commit()

    assert server.get("/api/v1/auth/me").status_code == 401


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------


def test_a_change_without_the_csrf_header_is_refused(server: TestClient, anna: User) -> None:
    login(server)

    response = server.post("/api/v1/timer/start", json={})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_missing"


def test_reading_needs_no_csrf_header(server: TestClient, anna: User) -> None:
    login(server)

    assert server.get("/api/v1/timer").status_code == 200


def test_with_the_header_a_change_goes_through(server: TestClient, anna: User) -> None:
    login(server)

    assert server.post("/api/v1/timer/start", json={}, headers=CSRF).status_code == 201


# ---------------------------------------------------------------------------
# Local mode is unchanged
# ---------------------------------------------------------------------------


def test_local_mode_has_no_login(api_client: TestClient) -> None:
    response = api_client.post("/api/v1/auth/login", json={"email": "a@b.fi", "password": PASSWORD})

    assert response.status_code == 404


def test_local_mode_still_knows_who_it_is(api_client: TestClient) -> None:
    assert api_client.get("/api/v1/auth/me").json()["is_admin"] is False
