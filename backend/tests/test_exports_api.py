"""The PDF export route."""

from fastapi.testclient import TestClient

EXPORT = "/api/v1/exports/pdf"
OCTOBER = {
    "from": "2026-09-30T21:00:00+00:00",
    "to": "2026-10-31T22:00:00+00:00",
    "tz": "Europe/Helsinki",
}


def book(client: TestClient, **fields: object) -> None:
    response = client.post(
        "/api/v1/entries",
        json={
            "started_at": "2026-10-05T06:00:00+00:00",
            "ended_at": "2026-10-05T07:30:00+00:00",
            **fields,
        },
    )
    assert response.status_code == 201, response.text


def test_the_period_pdf_is_a_downloadable_pdf(api_client: TestClient) -> None:
    project = api_client.post(
        "/api/v1/projects", json={"name": "Äänitys & Öljy", "hourly_rate_cents": 6000}
    ).json()
    book(api_client, project_id=project["id"], billable=True, description="<b>ei markupia</b>")

    response = api_client.get(EXPORT, params={**OCTOBER, "locale": "fi"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        'attachment; filename="hextime-2026-10-01-2026-10-31.pdf"'
    )
    assert response.content.startswith(b"%PDF-")
    # The font travels inside the file, so ä and ö print on any machine.
    assert b"Inter" in response.content


def test_an_empty_period_still_gives_a_pdf(api_client: TestClient) -> None:
    response = api_client.get(EXPORT, params={**OCTOBER, "locale": "en"})

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF-")


def test_an_unknown_language_falls_back_instead_of_failing(api_client: TestClient) -> None:
    response = api_client.get(EXPORT, params={**OCTOBER, "locale": "sv"})

    assert response.status_code == 200


def test_a_team_report_needs_an_id(api_client: TestClient) -> None:
    response = api_client.get(EXPORT, params={**OCTOBER, "scope": "team"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_an_unknown_scope_is_a_422(api_client: TestClient) -> None:
    response = api_client.get(EXPORT, params={**OCTOBER, "scope": "everything"})

    assert response.status_code == 422


def test_the_range_is_required(api_client: TestClient) -> None:
    assert api_client.get(EXPORT).status_code == 422


def test_the_project_pdf_is_named_after_the_project(api_client: TestClient) -> None:
    project = api_client.post(
        "/api/v1/projects", json={"name": "Asiakas Öljy Oy", "hourly_rate_cents": 6000}
    ).json()
    task = api_client.post(
        f"/api/v1/projects/{project['id']}/tasks", json={"name": "Suunnittelu"}
    ).json()
    book(api_client, project_id=project["id"], task_id=task["id"], billable=True)

    response = api_client.get(
        EXPORT, params={**OCTOBER, "scope": "project", "id": project["id"], "locale": "fi"}
    )

    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        'attachment; filename="hextime-asiakas-oljy-oy-2026-10-01-2026-10-31.pdf"'
    )
    assert response.content.startswith(b"%PDF-")


def test_a_project_report_needs_an_id(api_client: TestClient) -> None:
    response = api_client.get(EXPORT, params={**OCTOBER, "scope": "project"})

    assert response.status_code == 422


def test_an_unknown_project_is_a_404(api_client: TestClient) -> None:
    response = api_client.get(
        EXPORT,
        params={**OCTOBER, "scope": "project", "id": "00000000-0000-0000-0000-000000000000"},
    )

    assert response.status_code == 404
