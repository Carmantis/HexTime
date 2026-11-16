"""Timer routes.

These run against the in-memory database through a real HTTP client, so they
also check the wiring: dependencies, status codes and the error envelope.
"""

from fastapi.testclient import TestClient

from app.models import Project

TIMER = "/api/v1/timer"
ENTRIES = "/api/v1/entries"


def test_nothing_is_running_at_first(api_client: TestClient) -> None:
    response = api_client.get(TIMER)

    assert response.status_code == 200
    assert response.json() is None


def test_start_returns_a_running_entry(api_client: TestClient) -> None:
    response = api_client.post(f"{TIMER}/start", json={"description": "Writing docs"})

    assert response.status_code == 201
    body = response.json()
    assert body["description"] == "Writing docs"
    assert body["ended_at"] is None
    assert body["duration_seconds"] is None


def test_the_running_timer_can_be_read_back(api_client: TestClient) -> None:
    started = api_client.post(f"{TIMER}/start", json={}).json()

    assert api_client.get(TIMER).json()["id"] == started["id"]


def test_stop_finishes_the_entry(api_client: TestClient) -> None:
    api_client.post(f"{TIMER}/start", json={})

    response = api_client.post(f"{TIMER}/stop")

    assert response.status_code == 200
    body = response.json()
    assert body["ended_at"] is not None
    assert body["duration_seconds"] is not None
    assert api_client.get(TIMER).json() is None


def test_stopping_nothing_uses_the_shared_error_envelope(api_client: TestClient) -> None:
    response = api_client.post(f"{TIMER}/stop")

    assert response.status_code == 409
    assert response.json() == {
        "error": {"code": "timer_not_running", "message": "no timer is running"}
    }


def test_starting_again_stops_the_previous_timer(api_client: TestClient) -> None:
    first = api_client.post(f"{TIMER}/start", json={}).json()

    second = api_client.post(f"{TIMER}/start", json={}).json()

    assert first["id"] != second["id"]
    assert api_client.get(TIMER).json()["id"] == second["id"]
    assert api_client.get(f"{ENTRIES}/{first['id']}").json()["ended_at"] is not None


def test_started_timer_inherits_the_projects_defaults(
    api_client: TestClient, project: Project
) -> None:
    body = api_client.post(f"{TIMER}/start", json={"project_id": str(project.id)}).json()

    assert body["billable"] is True
    assert body["rate_snapshot_cents"] == 8500
    assert body["currency"] == "EUR"


def test_unknown_project_is_reported_as_not_found(api_client: TestClient) -> None:
    response = api_client.post(
        f"{TIMER}/start", json={"project_id": "00000000-0000-4000-8000-000000000000"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_the_timer_starts_with_tags(api_client: TestClient) -> None:
    tag = api_client.post("/api/v1/tags", json={"name": "kiire"}).json()

    started = api_client.post("/api/v1/timer/start", json={"tag_ids": [tag["id"]]})

    assert started.status_code == 201
    assert [t["name"] for t in started.json()["tags"]] == ["kiire"]
