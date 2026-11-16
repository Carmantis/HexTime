"""Time entry routes.

The interesting parts here are the PATCH semantics (an absent key must not
clear a field) and that every error, including a malformed request, comes back
in the one envelope the frontend knows how to translate.
"""

from fastapi.testclient import TestClient

from app.models import Project

ENTRIES = "/api/v1/entries"


def iso(hour: int, minute: int = 0) -> str:
    """A UTC timestamp on one fixed day, with an explicit offset."""
    return f"2026-05-04T{hour:02d}:{minute:02d}:00+00:00"


def create(api_client: TestClient, **fields: object) -> dict:
    payload = {"started_at": iso(10), "ended_at": iso(11)} | fields
    response = api_client.post(ENTRIES, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Creating
# ---------------------------------------------------------------------------


def test_create_returns_the_stored_entry(api_client: TestClient) -> None:
    body = create(api_client, description="Meeting")

    assert body["description"] == "Meeting"
    assert body["duration_seconds"] == 3600
    assert body["billable"] is False


def test_create_copies_the_project_rate(api_client: TestClient, project: Project) -> None:
    body = create(api_client, project_id=str(project.id))

    assert body["rate_snapshot_cents"] == 8500
    assert body["billable"] is True


def test_overlapping_entry_is_a_conflict(api_client: TestClient) -> None:
    create(api_client)

    response = api_client.post(ENTRIES, json={"started_at": iso(10, 30), "ended_at": iso(11, 30)})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "entry_overlap"


def test_a_touching_entry_is_accepted(api_client: TestClient) -> None:
    """Half-open ranges: ending exactly when the next begins is not an overlap."""
    create(api_client)

    response = api_client.post(ENTRIES, json={"started_at": iso(11), "ended_at": iso(12)})

    assert response.status_code == 201


def test_a_naive_timestamp_is_rejected_in_the_same_envelope(api_client: TestClient) -> None:
    """FastAPI would answer with its own {"detail": ...} shape; the handler in
    core/errors.py makes request validation speak the same language as
    everything else."""
    response = api_client.post(ENTRIES, json={"started_at": "2026-05-04T10:00:00"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_failed"
    assert any("started_at" in field for field in error["fields"])


def test_an_entry_cannot_end_before_it_starts(api_client: TestClient) -> None:
    response = api_client.post(ENTRIES, json={"started_at": iso(11), "ended_at": iso(10)})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def test_an_entry_can_be_read_by_id(api_client: TestClient) -> None:
    created = create(api_client, description="Findable")

    body = api_client.get(f"{ENTRIES}/{created['id']}").json()

    assert body["description"] == "Findable"


def test_an_unknown_entry_is_not_found(api_client: TestClient) -> None:
    response = api_client.get(f"{ENTRIES}/00000000-0000-4000-8000-000000000000")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_listing_filters_by_time_range(api_client: TestClient) -> None:
    api_client.post(
        ENTRIES, json={"started_at": iso(8), "ended_at": iso(9), "description": "early"}
    )
    api_client.post(
        ENTRIES, json={"started_at": iso(10), "ended_at": iso(11), "description": "middle"}
    )
    api_client.post(
        ENTRIES, json={"started_at": iso(12), "ended_at": iso(13), "description": "late"}
    )

    found = api_client.get(ENTRIES, params={"from": iso(10), "to": iso(12)}).json()

    assert [entry["description"] for entry in found] == ["middle"]


def test_listing_returns_newest_first(api_client: TestClient) -> None:
    api_client.post(
        ENTRIES, json={"started_at": iso(8), "ended_at": iso(9), "description": "first"}
    )
    api_client.post(
        ENTRIES, json={"started_at": iso(12), "ended_at": iso(13), "description": "second"}
    )

    found = api_client.get(ENTRIES).json()

    assert [entry["description"] for entry in found] == ["second", "first"]


def test_listing_filters_by_project(api_client: TestClient, project: Project) -> None:
    create(api_client, project_id=str(project.id))
    api_client.post(ENTRIES, json={"started_at": iso(12), "ended_at": iso(13)})

    found = api_client.get(ENTRIES, params={"project_id": str(project.id)}).json()

    assert len(found) == 1
    assert found[0]["project_id"] == str(project.id)


# ---------------------------------------------------------------------------
# Updating
# ---------------------------------------------------------------------------


def test_patch_changes_only_what_it_mentions(api_client: TestClient) -> None:
    """An absent key must leave the field alone — the UNSET sentinel in the
    service exists exactly for this."""
    created = create(api_client, description="original")

    body = api_client.patch(f"{ENTRIES}/{created['id']}", json={"billable": True}).json()

    assert body["billable"] is True
    assert body["description"] == "original"


def test_patch_can_explicitly_clear_a_field(api_client: TestClient) -> None:
    created = create(api_client, description="original")

    body = api_client.patch(f"{ENTRIES}/{created['id']}", json={"description": None}).json()

    assert body["description"] is None


def test_patch_rejects_moving_an_entry_onto_another(api_client: TestClient) -> None:
    create(api_client)
    second = create(api_client, started_at=iso(12), ended_at=iso(13))

    response = api_client.patch(f"{ENTRIES}/{second['id']}", json={"started_at": iso(10, 30)})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "entry_overlap"


def test_patching_an_unknown_entry_is_not_found(api_client: TestClient) -> None:
    response = api_client.patch(
        f"{ENTRIES}/00000000-0000-4000-8000-000000000000", json={"description": "x"}
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Deleting
# ---------------------------------------------------------------------------


def test_delete_removes_the_entry(api_client: TestClient) -> None:
    created = create(api_client)

    response = api_client.delete(f"{ENTRIES}/{created['id']}")

    assert response.status_code == 204
    assert api_client.get(f"{ENTRIES}/{created['id']}").status_code == 404


def test_deleting_an_unknown_entry_is_not_found(api_client: TestClient) -> None:
    response = api_client.delete(f"{ENTRIES}/00000000-0000-4000-8000-000000000000")

    assert response.status_code == 404
