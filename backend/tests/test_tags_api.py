"""Tag routes."""

from fastapi.testclient import TestClient

TAGS = "/api/v1/tags"
UNKNOWN = "00000000-0000-4000-8000-000000000000"


def create(api_client: TestClient, **fields: object) -> dict:
    payload = {"name": "urgent"} | fields
    response = api_client.post(TAGS, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_returns_the_tag(api_client: TestClient) -> None:
    body = create(api_client, color="#E74C3C")

    assert body["name"] == "urgent"
    assert body["color"] == "#E74C3C"
    assert body["archived_at"] is None


def test_tags_are_listed_by_name(api_client: TestClient) -> None:
    create(api_client, name="review")
    create(api_client, name="admin")

    names = [t["name"] for t in api_client.get(TAGS).json()]

    assert names == ["admin", "review"]


def test_a_tag_can_be_read_back(api_client: TestClient) -> None:
    created = create(api_client)

    assert api_client.get(f"{TAGS}/{created['id']}").json()["name"] == "urgent"


def test_an_unknown_tag_is_not_found(api_client: TestClient) -> None:
    response = api_client.get(f"{TAGS}/{UNKNOWN}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_a_malformed_colour_is_rejected(api_client: TestClient) -> None:
    response = api_client.post(TAGS, json={"name": "x", "color": "red"})

    assert response.status_code == 422


def test_a_tag_can_be_renamed(api_client: TestClient) -> None:
    created = create(api_client)

    body = api_client.patch(f"{TAGS}/{created['id']}", json={"name": "critical"}).json()

    assert body["name"] == "critical"
    assert body["color"] == created["color"]


def test_clearing_the_name_is_rejected(api_client: TestClient) -> None:
    created = create(api_client)

    response = api_client.patch(f"{TAGS}/{created['id']}", json={"name": None})

    assert response.status_code == 422


def test_archiving_hides_a_tag_but_keeps_it(api_client: TestClient) -> None:
    created = create(api_client)

    api_client.post(f"{TAGS}/{created['id']}/archive")

    assert api_client.get(TAGS).json() == []
    assert api_client.get(f"{TAGS}/{created['id']}").status_code == 200
    assert len(api_client.get(TAGS, params={"include_archived": True}).json()) == 1


def test_a_tag_can_be_restored(api_client: TestClient) -> None:
    created = create(api_client)
    api_client.post(f"{TAGS}/{created['id']}/archive")

    restored = api_client.post(f"{TAGS}/{created['id']}/restore").json()

    assert restored["archived_at"] is None
