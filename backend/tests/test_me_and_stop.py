"""Editing your own profile, and stopping the timer at a remembered moment."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import TimeEntry, utc_now


def test_a_user_can_rename_themselves(api_client: TestClient) -> None:
    response = api_client.patch("/api/v1/me", json={"display_name": "  Heikki  "})

    assert response.status_code == 200
    assert response.json()["display_name"] == "Heikki"
    assert api_client.get("/api/v1/auth/me").json()["display_name"] == "Heikki"


def test_language_and_theme_are_stored(api_client: TestClient) -> None:
    body = api_client.patch("/api/v1/me", json={"locale": "en", "theme": "light"}).json()

    assert (body["locale"], body["theme"]) == ("en", "light")


def test_unknown_language_and_empty_name_are_refused(api_client: TestClient) -> None:
    assert api_client.patch("/api/v1/me", json={"locale": "sv"}).status_code == 422
    assert api_client.patch("/api/v1/me", json={"display_name": "   "}).status_code == 422


def _start(api_client: TestClient, minutes_ago: int, db: Session) -> TimeEntry:
    api_client.post("/api/v1/timer/start", json={})
    entry = db.query(TimeEntry).one()
    entry.started_at = utc_now() - timedelta(minutes=minutes_ago)
    db.commit()
    return entry


def test_a_retried_stop_keeps_the_time_of_the_click(api_client: TestClient, db: Session) -> None:
    _start(api_client, 30, db)
    clicked = utc_now() - timedelta(minutes=2)

    response = api_client.post("/api/v1/timer/stop", json={"at": clicked.isoformat()})

    assert response.status_code == 200
    ended = datetime.fromisoformat(response.json()["ended_at"])
    assert abs(ended - clicked) < timedelta(seconds=1)


def test_a_stop_without_a_body_still_means_now(api_client: TestClient, db: Session) -> None:
    _start(api_client, 30, db)

    ended = datetime.fromisoformat(api_client.post("/api/v1/timer/stop").json()["ended_at"])

    assert abs(ended - datetime.now(UTC)) < timedelta(seconds=5)


def test_a_stop_cannot_be_dated_far_back(api_client: TestClient, db: Session) -> None:
    _start(api_client, 120, db)
    long_ago = utc_now() - timedelta(minutes=30)

    response = api_client.post("/api/v1/timer/stop", json={"at": long_ago.isoformat()})

    assert response.status_code == 422
    assert api_client.get("/api/v1/timer").json() is not None
