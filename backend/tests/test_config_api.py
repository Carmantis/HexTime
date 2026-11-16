"""GET /api/v1/config — how the frontend learns which mode it is running in."""

from fastapi.testclient import TestClient

from tests.conftest import build_client


def test_local_mode_config(local_client: TestClient) -> None:
    response = local_client.get("/api/v1/config")

    assert response.status_code == 200
    assert response.json() == {
        "mode": "local",
        "locales": ["fi", "en"],
        "default_locale": "fi",
        "allowed_email_domain": None,
        "allow_self_registration": False,
    }


def test_server_mode_exposes_the_allowed_domain(server_client: TestClient) -> None:
    body = server_client.get("/api/v1/config").json()

    assert body["mode"] == "server"
    assert body["allowed_email_domain"] == "example.org"


def test_local_mode_hides_the_allowed_domain() -> None:
    """Local mode has no registration, so the domain must not leak into the UI."""
    client = build_client(allowed_email_domain="example.org")

    assert client.get("/api/v1/config").json()["allowed_email_domain"] is None


def test_the_endpoint_is_versioned(local_client: TestClient) -> None:
    """Every route lives under /api/v1; an unversioned path must not answer."""
    assert local_client.get("/config").status_code == 404


def test_openapi_docs_are_served(local_client: TestClient) -> None:
    assert local_client.get("/api/openapi.json").status_code == 200
