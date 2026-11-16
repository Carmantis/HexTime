"""Project and task routes."""

from fastapi.testclient import TestClient

PROJECTS = "/api/v1/projects"
TASKS = "/api/v1/tasks"
UNKNOWN = "00000000-0000-4000-8000-000000000000"


def create(api_client: TestClient, **fields: object) -> dict:
    payload = {"name": "Website"} | fields
    response = api_client.post(PROJECTS, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Creating and reading
# ---------------------------------------------------------------------------


def test_create_returns_the_project(api_client: TestClient) -> None:
    body = create(api_client, hourly_rate_cents=8500, billable_default=True)

    assert body["name"] == "Website"
    assert body["hourly_rate_cents"] == 8500
    assert body["billable_default"] is True
    assert body["archived_at"] is None


def test_a_new_project_gets_the_default_colour(api_client: TestClient) -> None:
    assert create(api_client)["color"] == "#4A90D9"


def test_a_project_can_be_read_back(api_client: TestClient) -> None:
    created = create(api_client)

    assert api_client.get(f"{PROJECTS}/{created['id']}").json()["id"] == created["id"]


def test_an_unknown_project_is_not_found(api_client: TestClient) -> None:
    response = api_client.get(f"{PROJECTS}/{UNKNOWN}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_projects_are_listed_by_name(api_client: TestClient) -> None:
    create(api_client, name="Beta")
    create(api_client, name="Alpha")

    names = [p["name"] for p in api_client.get(PROJECTS).json()]

    assert names == ["Alpha", "Beta"]


# ---------------------------------------------------------------------------
# Validation at the edge
# ---------------------------------------------------------------------------


def test_a_negative_rate_is_rejected(api_client: TestClient) -> None:
    response = api_client.post(PROJECTS, json={"name": "X", "hourly_rate_cents": -1})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_a_malformed_colour_is_rejected(api_client: TestClient) -> None:
    response = api_client.post(PROJECTS, json={"name": "X", "color": "blue"})

    assert response.status_code == 422


def test_an_empty_name_is_rejected(api_client: TestClient) -> None:
    response = api_client.post(PROJECTS, json={"name": ""})

    assert response.status_code == 422


def test_clearing_the_name_is_rejected(api_client: TestClient) -> None:
    """name is not nullable, so an explicit null is a mistake, not a clear."""
    created = create(api_client)

    response = api_client.patch(f"{PROJECTS}/{created['id']}", json={"name": None})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Updating
# ---------------------------------------------------------------------------


def test_patch_changes_only_what_it_mentions(api_client: TestClient) -> None:
    created = create(api_client, client_name="Acme", hourly_rate_cents=8500)

    body = api_client.patch(f"{PROJECTS}/{created['id']}", json={"name": "Renamed"}).json()

    assert body["name"] == "Renamed"
    assert body["client_name"] == "Acme"
    assert body["hourly_rate_cents"] == 8500


def test_a_nullable_field_can_be_cleared(api_client: TestClient) -> None:
    created = create(api_client, client_name="Acme")

    body = api_client.patch(f"{PROJECTS}/{created['id']}", json={"client_name": None}).json()

    assert body["client_name"] is None


# ---------------------------------------------------------------------------
# Archiving
# ---------------------------------------------------------------------------


def test_archiving_hides_a_project_from_the_list(api_client: TestClient) -> None:
    created = create(api_client)

    archived = api_client.post(f"{PROJECTS}/{created['id']}/archive").json()

    assert archived["archived_at"] is not None
    assert api_client.get(PROJECTS).json() == []


def test_an_archived_project_is_still_there(api_client: TestClient) -> None:
    """Archive, never delete: old time entries must keep their context."""
    created = create(api_client)
    api_client.post(f"{PROJECTS}/{created['id']}/archive")

    assert api_client.get(f"{PROJECTS}/{created['id']}").status_code == 200
    listed = api_client.get(PROJECTS, params={"include_archived": True}).json()
    assert len(listed) == 1


def test_a_project_can_be_restored(api_client: TestClient) -> None:
    created = create(api_client)
    api_client.post(f"{PROJECTS}/{created['id']}/archive")

    restored = api_client.post(f"{PROJECTS}/{created['id']}/restore").json()

    assert restored["archived_at"] is None
    assert len(api_client.get(PROJECTS).json()) == 1


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


def test_a_task_belongs_to_its_project(api_client: TestClient) -> None:
    project = create(api_client)

    response = api_client.post(f"{PROJECTS}/{project['id']}/tasks", json={"name": "Design"})

    assert response.status_code == 201
    assert response.json()["project_id"] == project["id"]


def test_tasks_are_listed_for_their_project(api_client: TestClient) -> None:
    project = create(api_client)
    api_client.post(f"{PROJECTS}/{project['id']}/tasks", json={"name": "Development"})
    api_client.post(f"{PROJECTS}/{project['id']}/tasks", json={"name": "Design"})

    names = [t["name"] for t in api_client.get(f"{PROJECTS}/{project['id']}/tasks").json()]

    assert names == ["Design", "Development"]


def test_a_task_can_be_renamed(api_client: TestClient) -> None:
    project = create(api_client)
    task = api_client.post(f"{PROJECTS}/{project['id']}/tasks", json={"name": "Design"}).json()

    body = api_client.patch(f"{TASKS}/{task['id']}", json={"name": "UX"}).json()

    assert body["name"] == "UX"


def test_archiving_a_task_hides_it(api_client: TestClient) -> None:
    project = create(api_client)
    task = api_client.post(f"{PROJECTS}/{project['id']}/tasks", json={"name": "Design"}).json()

    api_client.post(f"{TASKS}/{task['id']}/archive")

    assert api_client.get(f"{PROJECTS}/{project['id']}/tasks").json() == []


def test_a_task_of_an_unknown_project_is_not_found(api_client: TestClient) -> None:
    response = api_client.post(f"{PROJECTS}/{UNKNOWN}/tasks", json={"name": "Design"})

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Together with time entries
# ---------------------------------------------------------------------------


def test_an_entry_can_be_booked_on_a_project_made_through_the_api(
    api_client: TestClient,
) -> None:
    """The whole point of this piece: a project can now be created and used
    without touching the database by hand."""
    project = create(api_client, hourly_rate_cents=9000, billable_default=True)

    entry = api_client.post(
        "/api/v1/entries",
        json={
            "started_at": "2026-05-04T10:00:00+00:00",
            "ended_at": "2026-05-04T11:00:00+00:00",
            "project_id": project["id"],
        },
    ).json()

    assert entry["rate_snapshot_cents"] == 9000
    assert entry["billable"] is True
