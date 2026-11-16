"""Tags on time entries.

A tag set is replaced wholesale rather than added to one at a time: the UI
shows all of an entry's tags at once, so "these are the tags now" is the only
operation it ever needs.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import AuditLog, User
from app.services import entries
from app.services import tags as tags_service

ENTRIES = "/api/v1/entries"
TAGS = "/api/v1/tags"
UNKNOWN = "00000000-0000-4000-8000-000000000000"


def at(hour: int) -> datetime:
    return datetime(2026, 5, 4, hour, tzinfo=UTC)


def iso(hour: int) -> str:
    return f"2026-05-04T{hour:02d}:00:00+00:00"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


def test_an_entry_can_be_created_with_tags(db: Session, user: User) -> None:
    urgent = tags_service.create_tag(db, user=user, name="urgent")
    review = tags_service.create_tag(db, user=user, name="review")

    entry = entries.create_entry(
        db, user=user, started_at=at(10), ended_at=at(11), tag_ids=[urgent.id, review.id]
    )

    assert {tag.name for tag in entry.tags} == {"urgent", "review"}


def test_tags_come_back_in_a_stable_order(db: Session, user: User) -> None:
    """Tags are a set, so the order sent in is not preserved. They are sorted
    by name instead, which keeps the UI from reshuffling between renders."""
    zulu = tags_service.create_tag(db, user=user, name="zulu")
    alpha = tags_service.create_tag(db, user=user, name="alpha")

    entry = entries.create_entry(
        db, user=user, started_at=at(10), ended_at=at(11), tag_ids=[zulu.id, alpha.id]
    )

    assert [tag.name for tag in entry.tags] == ["alpha", "zulu"]

    # The same order after a round trip through the database, not just in the
    # list that happened to be assigned.
    db.expire_all()
    assert [tag.name for tag in entry.tags] == ["alpha", "zulu"]


def test_an_entry_starts_with_no_tags(db: Session, user: User) -> None:
    entry = entries.create_entry(db, user=user, started_at=at(10), ended_at=at(11))

    assert entry.tags == []


def test_duplicate_tag_ids_are_collapsed(db: Session, user: User) -> None:
    urgent = tags_service.create_tag(db, user=user, name="urgent")

    entry = entries.create_entry(
        db, user=user, started_at=at(10), ended_at=at(11), tag_ids=[urgent.id, urgent.id]
    )

    assert len(entry.tags) == 1


def test_updating_replaces_the_whole_set(db: Session, user: User) -> None:
    first = tags_service.create_tag(db, user=user, name="first")
    second = tags_service.create_tag(db, user=user, name="second")
    entry = entries.create_entry(
        db, user=user, started_at=at(10), ended_at=at(11), tag_ids=[first.id]
    )

    entries.update_entry(db, entry=entry, actor=user, tag_ids=[second.id])

    assert [tag.name for tag in entry.tags] == ["second"]


def test_omitting_tag_ids_leaves_the_tags_alone(db: Session, user: User) -> None:
    urgent = tags_service.create_tag(db, user=user, name="urgent")
    entry = entries.create_entry(
        db, user=user, started_at=at(10), ended_at=at(11), tag_ids=[urgent.id]
    )

    entries.update_entry(db, entry=entry, actor=user, description="changed")

    assert [tag.name for tag in entry.tags] == ["urgent"]


def test_an_empty_list_clears_the_tags(db: Session, user: User) -> None:
    urgent = tags_service.create_tag(db, user=user, name="urgent")
    entry = entries.create_entry(
        db, user=user, started_at=at(10), ended_at=at(11), tag_ids=[urgent.id]
    )

    entries.update_entry(db, entry=entry, actor=user, tag_ids=[])

    assert entry.tags == []


def test_an_unknown_tag_is_not_found(db: Session, user: User) -> None:
    from uuid import uuid4

    with pytest.raises(NotFoundError):
        entries.create_entry(db, user=user, started_at=at(10), ended_at=at(11), tag_ids=[uuid4()])


def test_another_users_tag_cannot_be_attached(db: Session, user: User, other_user: User) -> None:
    theirs = tags_service.create_tag(db, user=other_user, name="theirs")

    with pytest.raises(NotFoundError):
        entries.create_entry(db, user=user, started_at=at(10), ended_at=at(11), tag_ids=[theirs.id])


def test_archiving_a_tag_keeps_it_on_old_entries(db: Session, user: User) -> None:
    """Archive, never delete: an old entry must not lose its meaning."""
    urgent = tags_service.create_tag(db, user=user, name="urgent")
    entry = entries.create_entry(
        db, user=user, started_at=at(10), ended_at=at(11), tag_ids=[urgent.id]
    )

    tags_service.archive_tag(db, tag=urgent)
    db.expire_all()

    assert [tag.name for tag in entry.tags] == ["urgent"]


def test_the_audit_log_records_the_tag_change(db: Session, user: User) -> None:
    urgent = tags_service.create_tag(db, user=user, name="urgent")
    entry = entries.create_entry(db, user=user, started_at=at(10), ended_at=at(11))

    entries.update_entry(db, entry=entry, actor=user, tag_ids=[urgent.id])

    row = db.scalars(select(AuditLog).where(AuditLog.action == "update")).one()
    assert '"tag_ids": []' in row.before_json
    assert str(urgent.id) in row.after_json


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def make_tag(api_client: TestClient, name: str) -> dict:
    response = api_client.post(TAGS, json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def test_entries_carry_their_tags_in_the_response(api_client: TestClient) -> None:
    tag = make_tag(api_client, "urgent")

    body = api_client.post(
        ENTRIES,
        json={"started_at": iso(10), "ended_at": iso(11), "tag_ids": [tag["id"]]},
    ).json()

    assert [t["name"] for t in body["tags"]] == ["urgent"]
    assert body["tags"][0]["color"] == tag["color"]


def test_an_entry_without_tags_returns_an_empty_list(api_client: TestClient) -> None:
    body = api_client.post(ENTRIES, json={"started_at": iso(10), "ended_at": iso(11)}).json()

    assert body["tags"] == []


def test_patching_tag_ids_replaces_them(api_client: TestClient) -> None:
    first = make_tag(api_client, "first")
    second = make_tag(api_client, "second")
    created = api_client.post(
        ENTRIES,
        json={"started_at": iso(10), "ended_at": iso(11), "tag_ids": [first["id"]]},
    ).json()

    body = api_client.patch(f"{ENTRIES}/{created['id']}", json={"tag_ids": [second["id"]]}).json()

    assert [t["name"] for t in body["tags"]] == ["second"]


def test_patching_without_tag_ids_keeps_them(api_client: TestClient) -> None:
    tag = make_tag(api_client, "urgent")
    created = api_client.post(
        ENTRIES,
        json={"started_at": iso(10), "ended_at": iso(11), "tag_ids": [tag["id"]]},
    ).json()

    body = api_client.patch(f"{ENTRIES}/{created['id']}", json={"billable": True}).json()

    assert [t["name"] for t in body["tags"]] == ["urgent"]


def test_patching_tag_ids_to_null_clears_them(api_client: TestClient) -> None:
    tag = make_tag(api_client, "urgent")
    created = api_client.post(
        ENTRIES,
        json={"started_at": iso(10), "ended_at": iso(11), "tag_ids": [tag["id"]]},
    ).json()

    body = api_client.patch(f"{ENTRIES}/{created['id']}", json={"tag_ids": None}).json()

    assert body["tags"] == []


def test_an_unknown_tag_id_is_rejected(api_client: TestClient) -> None:
    response = api_client.post(
        ENTRIES, json={"started_at": iso(10), "ended_at": iso(11), "tag_ids": [UNKNOWN]}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
