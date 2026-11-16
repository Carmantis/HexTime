"""A role column may only hold a real role.

The gap these close: the original test only checked that a valid role is
stored in lower case. Nothing checked that an invalid one is refused, and it
was not — Enum(native_enum=False) does not create its CHECK constraint unless
asked, so the column accepted any string for several pieces of work.

test_postgres.py checks the same rule on PostgreSQL.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Team, TeamMember, TeamRole, User


def team_and_user(db: Session) -> tuple[Team, User]:
    user = User(display_name="Test User")
    db.add(user)
    db.commit()
    team = Team(name="Devs", created_by=user.id)
    db.add(team)
    db.commit()
    return team, user


@pytest.mark.parametrize("role", list(TeamRole))
def test_every_real_role_is_accepted(db: Session, role: TeamRole) -> None:
    team, user = team_and_user(db)

    db.add(TeamMember(team_id=team.id, user_id=user.id, role=role))
    db.commit()

    assert db.execute(text("SELECT role FROM team_members")).scalar_one() == role.value


def test_a_made_up_membership_role_is_refused(db: Session) -> None:
    team, user = team_and_user(db)

    # Through the ORM, so the column's own type handles the timestamp. Raw SQL
    # would bypass UtcDateTime and fail on binding instead of on the CHECK.
    db.add(TeamMember(team_id=team.id, user_id=user.id, role="overlord"))  # type: ignore[arg-type]

    with pytest.raises(IntegrityError):
        db.commit()
