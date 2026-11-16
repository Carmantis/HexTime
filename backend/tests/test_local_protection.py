"""The desktop server answers its own UI, not other web sites (app/core/csrf.py)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import AppMode
from app.core.csrf import CSRF_HEADER
from app.core.db import get_db
from app.main import create_app
from tests.conftest import build_settings


@pytest.fixture
def local_app(db: Session) -> TestClient:
    """A desktop-mode server on the in-memory database, sending no headers of its own."""
    app = create_app(settings=build_settings(app_mode=AppMode.LOCAL), serve_static=False)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, base_url="http://127.0.0.1:47612")


def test_a_change_without_the_header_is_refused(local_app: TestClient) -> None:
    # What a page on another site can send: a plain POST, no custom headers
    response = local_app.post(
        "/api/v1/timer/stop",
        headers={"Origin": "https://evil.example", "Content-Type": "text/plain"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_missing"


def test_reading_works_without_the_header(local_app: TestClient) -> None:
    assert local_app.get("/api/v1/config").status_code == 200


def test_another_name_for_this_machine_is_refused(local_app: TestClient) -> None:
    # DNS rebinding: a site's own name made to point at 127.0.0.1
    assert (
        local_app.get("/api/v1/config", headers={"Host": "evil.example:47612"}).status_code == 400
    )
    assert local_app.get("/api/v1/config", headers={"Host": "localhost:47612"}).status_code == 200


def test_the_header_lets_the_ui_change_things(local_app: TestClient) -> None:
    response = local_app.post("/api/v1/timer/stop", headers={CSRF_HEADER: "1"})

    # Past the check: with no timer running the service answers on its own
    assert response.json().get("error", {}).get("code") != "csrf_missing"
    assert response.status_code != 400
