"""Editing an entry must never rewrite its rate snapshot by accident.

The entry form re-sends every field on save, including a project_id that did
not change. If that counted as "moving to a project", fixing a typo in an old
entry's description would copy in today's rate and quietly change what that
entry is worth.
"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Project, Task, User
from app.services import entries


def at(hour: int) -> datetime:
    return datetime(2026, 5, 4, hour, tzinfo=UTC)


def test_resending_the_same_project_keeps_the_old_rate(
    db: Session, user: User, project: Project
) -> None:
    entry = entries.create_entry(
        db, user=user, started_at=at(10), ended_at=at(11), project_id=project.id
    )
    project.hourly_rate_cents = 12000
    db.commit()

    entries.update_entry(
        db, entry=entry, actor=user, project_id=project.id, description="fixed a typo"
    )

    assert entry.rate_snapshot_cents == 8500


def test_resending_the_same_project_keeps_the_task(
    db: Session, user: User, project: Project
) -> None:
    task = Task(project_id=project.id, name="Design")
    db.add(task)
    db.commit()
    entry = entries.create_entry(
        db,
        user=user,
        started_at=at(10),
        ended_at=at(11),
        project_id=project.id,
        task_id=task.id,
    )

    entries.update_entry(db, entry=entry, actor=user, project_id=project.id)

    assert entry.task_id == task.id


def test_actually_moving_to_another_project_still_rereads_the_rate(
    db: Session, user: User, project: Project
) -> None:
    other = Project(name="Other", owner_user_id=user.id, hourly_rate_cents=5000)
    db.add(other)
    db.commit()
    entry = entries.create_entry(
        db, user=user, started_at=at(10), ended_at=at(11), project_id=project.id
    )

    entries.update_entry(db, entry=entry, actor=user, project_id=other.id)

    assert entry.rate_snapshot_cents == 5000


def test_the_form_round_trip_through_the_api_keeps_the_rate(
    api_client: TestClient,
) -> None:
    """The exact sequence the UI performs: create, change the project rate,
    then save the form again with every field re-sent."""
    project = api_client.post(
        "/api/v1/projects", json={"name": "Client", "hourly_rate_cents": 8500}
    ).json()
    entry = api_client.post(
        "/api/v1/entries",
        json={
            "started_at": "2026-05-04T10:00:00+00:00",
            "ended_at": "2026-05-04T11:00:00+00:00",
            "project_id": project["id"],
        },
    ).json()
    api_client.patch(f"/api/v1/projects/{project['id']}", json={"hourly_rate_cents": 12000})

    saved = api_client.patch(
        f"/api/v1/entries/{entry['id']}",
        json={
            "started_at": "2026-05-04T10:00:00+00:00",
            "ended_at": "2026-05-04T11:00:00+00:00",
            "project_id": project["id"],
            "description": "edited in the form",
            "billable": False,
            "tag_ids": [],
        },
    ).json()

    assert saved["rate_snapshot_cents"] == 8500
