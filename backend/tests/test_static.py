"""Serving the compiled frontend.

FastAPI hands out the single-page app from "/" and the API from "/api/v1".
Because the SPA is a mount on "/", it catches every path nothing else claimed,
so the order the two are registered in is load-bearing. These tests pin that
contract instead of leaving it to whoever next edits create_app.

A fake build directory is used so the outcome never depends on whether
`npm run build` has been run.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from tests.conftest import build_settings, local_test_client

INDEX = "<!doctype html><html data-theme='dark'><title>HexTime</title></html>"


@pytest.fixture
def built_frontend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Stand in for the directory `npm run build` writes."""
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text(INDEX, encoding="utf-8")
    (static / "assets" / "app.js").write_text("export default 1;\n", encoding="utf-8")

    monkeypatch.setattr(main, "STATIC_DIR", static)
    return static


def client(**kwargs: object) -> TestClient:
    return local_test_client(main.create_app(settings=build_settings(), **kwargs))  # type: ignore[arg-type]


def test_the_spa_is_served_at_the_root(built_frontend: Path) -> None:
    response = client().get("/")

    assert response.status_code == 200
    assert "HexTime" in response.text


def test_built_assets_are_served(built_frontend: Path) -> None:
    assert client().get("/assets/app.js").status_code == 200


def test_the_api_still_wins_over_the_catch_all(built_frontend: Path) -> None:
    """The regression this file exists for: mounting the SPA must not shadow
    the API, which is why the router is included before the mount."""
    response = client().get("/api/v1/config")

    assert response.status_code == 200
    assert response.json()["mode"] == "local"


def test_the_docs_still_win_over_the_catch_all(built_frontend: Path) -> None:
    assert client().get("/api/openapi.json").status_code == 200


def test_serve_static_false_leaves_the_root_unclaimed(built_frontend: Path) -> None:
    """What every test fixture uses, so the suite does not change behaviour
    the moment someone builds the frontend."""
    assert client(serve_static=False).get("/").status_code == 404


def test_nothing_is_mounted_when_the_frontend_was_never_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "STATIC_DIR", tmp_path / "never-built")

    assert client().get("/").status_code == 404
