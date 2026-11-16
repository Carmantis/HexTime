"""The shared error envelope every API error is rendered in."""

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.core.errors import AppError, NotFoundError, PermissionDeniedError
from app.main import create_app
from tests.conftest import build_settings, local_test_client


class EntryOverlapError(AppError):
    """Stand-in for a real domain error until time entries exist."""

    code = "entry_overlap"
    status_code = 409


def _client_raising(exc: AppError) -> TestClient:
    # serve_static=False: a mount on "/" would swallow the /boom route added
    # below, because routes registered after a catch-all mount never match.
    app = create_app(settings=build_settings(), serve_static=False)
    router = APIRouter()

    @router.get("/boom")
    def boom() -> None:
        raise exc

    app.include_router(router)
    return local_test_client(app, raise_server_exceptions=False)


def test_domain_error_becomes_the_error_envelope() -> None:
    response = _client_raising(EntryOverlapError("entries overlap")).get("/boom")

    assert response.status_code == 409
    assert response.json() == {"error": {"code": "entry_overlap", "message": "entries overlap"}}


def test_status_code_comes_from_the_error_class() -> None:
    assert _client_raising(NotFoundError()).get("/boom").status_code == 404
    assert _client_raising(PermissionDeniedError()).get("/boom").status_code == 403


def test_message_defaults_to_the_code() -> None:
    """Every error has a message even when the service does not write one."""
    assert NotFoundError().message == "not_found"
    assert EntryOverlapError().message == "entry_overlap"
