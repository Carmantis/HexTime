"""Who can see whose rows, at the service level.

Two users without any team between them. What team membership opens up is
tested over HTTP in test_teams.py.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Project, Tag, Team, User
from app.services import entries
from app.services import projects as projects_service
from app.services import tags as tags_service


def make_team(db: Session, owner: User) -> Team:
    """A team the `owner` created but is *not* a member of.

    The membership rules themselves are tested over HTTP in test_teams.py.
    """
    team = Team(name="Devs", created_by=owner.id)
    db.add(team)
    db.commit()
    return team


def test_a_project_is_invisible_to_another_user(db: Session, user: User, other_user: User) -> None:
    mine = projects_service.create_project(db, user=user, name="Mine")

    with pytest.raises(NotFoundError):
        projects_service.get_project(db, mine.id, other_user)


def test_listing_never_shows_another_users_projects(
    db: Session, user: User, other_user: User
) -> None:
    projects_service.create_project(db, user=user, name="Mine")

    assert projects_service.list_projects(db, user=other_user) == []


def test_a_tag_is_invisible_to_another_user(db: Session, user: User, other_user: User) -> None:
    mine = tags_service.create_tag(db, user=user, name="urgent")

    with pytest.raises(NotFoundError):
        tags_service.get_tag(db, mine.id, other_user)


def test_a_team_owned_project_is_invisible_outside_the_team(db: Session, user: User) -> None:
    """A team-owned row is hidden from anyone not in the team, rather than
    open to all — even from the person who created the team."""
    team = make_team(db, user)
    project = Project(name="Team site", owner_team_id=team.id)
    db.add(project)
    db.commit()

    with pytest.raises(NotFoundError):
        projects_service.get_project(db, project.id, user)


def test_a_team_owned_tag_is_invisible_too(db: Session, user: User) -> None:
    team = make_team(db, user)
    tag = Tag(name="team-tag", owner_team_id=team.id)
    db.add(tag)
    db.commit()

    with pytest.raises(NotFoundError):
        tags_service.get_tag(db, tag.id, user)


def test_time_cannot_be_booked_on_another_teams_project(db: Session, user: User) -> None:
    """Guards the gap that used to exist: the old ownership check skipped
    team-owned projects entirely, so anyone could book hours on them."""
    team = make_team(db, user)
    project = Project(name="Team site", owner_team_id=team.id)
    db.add(project)
    db.commit()

    with pytest.raises(NotFoundError):
        entries.create_entry(
            db,
            user=user,
            started_at=datetime(2026, 5, 4, 10, tzinfo=UTC),
            ended_at=datetime(2026, 5, 4, 11, tzinfo=UTC),
            project_id=project.id,
        )


def test_time_cannot_be_booked_on_another_users_project(
    db: Session, user: User, other_user: User
) -> None:
    theirs = projects_service.create_project(db, user=other_user, name="Theirs")

    with pytest.raises(NotFoundError):
        entries.create_entry(
            db,
            user=user,
            started_at=datetime(2026, 5, 4, 10, tzinfo=UTC),
            ended_at=datetime(2026, 5, 4, 11, tzinfo=UTC),
            project_id=theirs.id,
        )


def test_a_task_is_invisible_when_its_project_is(db: Session, user: User, other_user: User) -> None:
    theirs = projects_service.create_project(db, user=other_user, name="Theirs")
    task = projects_service.create_task(db, project=theirs, name="Design")

    with pytest.raises(NotFoundError):
        projects_service.get_task(db, task.id, user)
