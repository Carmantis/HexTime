"""Demo data for trying out server mode on one machine. Never for a real server.

    APP_MODE=server ... uv run python -m scripts.dev_seed   (from backend/)

Run by scripts/dev-server.sh. Safe to run again: if the demo administrator
exists already, nothing is added.

The cast, all with the same password (see PASSWORD):

- Anna, the organisation administrator, in no team
- Liisa, lead of the team "Verkkotiimi"
- Mikko, a member of it
- Olli, invited to it and not answered yet
"""

import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.models import TeamMember, TeamRole, User
from app.services import entries, projects, teams
from app.services.auth import find_user_by_email
from app.services.users import make_admin

#: Long enough for the 12-character rule; known so nobody needs a link.
PASSWORD = "hextime-dev-123"

PEOPLE = [
    ("anna@example.org", "Anna Admin", True),
    ("liisa@example.org", "Liisa Lead", False),
    ("mikko@example.org", "Mikko Member", False),
    ("olli@example.org", "Olli Ulkopuolinen", False),
]


def _person(db: Session, email: str, name: str, admin: bool) -> User:
    user = make_admin(db, email=email, display_name=name, password=PASSWORD)
    user.is_admin = admin
    db.commit()
    return user


def _workdays(count: int) -> list[datetime]:
    """The last `count` weekdays before today, at 06:00 UTC (09:00 Helsinki)."""
    days: list[datetime] = []
    day = datetime.now(UTC).replace(hour=6, minute=0, second=0, microsecond=0)
    while len(days) < count:
        day -= timedelta(days=1)
        if day.weekday() < 5:
            days.append(day)
    return days


def main() -> None:
    settings = get_settings()
    if not settings.is_server:
        sys.exit("dev_seed.py is for server mode (APP_MODE=server).")

    with get_session_factory()() as db:
        if find_user_by_email(db, PEOPLE[0][0]) is not None:
            print("Demo data is there already.")
            return

        _anna, liisa, mikko, olli = (_person(db, *person) for person in PEOPLE)

        team = teams.create_team(db, user=liisa, name="Verkkotiimi")
        # Straight in, as if Mikko had said yes already.
        db.add(TeamMember(team_id=team.id, user_id=mikko.id, role=TeamRole.MEMBER))
        db.commit()
        # Olli has not answered yet: signing in as him shows the question.
        teams.invite(db, actor=liisa, team=team, user_id=olli.id)

        site = projects.create_project(
            db,
            user=liisa,
            name="Asiakassivut",
            color="#4A90D9",
            billable_default=True,
            hourly_rate_cents=8500,
            team_id=team.id,
        )
        projects.create_task(db, project=site, name="Kehitys")
        projects.create_task(db, project=site, name="Palaveri")
        liisas_own = projects.create_project(db, user=liisa, name="Liisan omat", color="#9B59B6")
        mikkos_own = projects.create_project(db, user=mikko, name="Opiskelu", color="#2ECC71")

        for day in _workdays(5):
            for user, project, hours, text in (
                (mikko, site, 4, "Etusivun toteutus"),
                (mikko, mikkos_own, 2, "Kurssi"),
                (liisa, site, 3, "Suunnittelu"),
                (liisa, liisas_own, 2, "Hallinto"),
            ):
                # Team work in the morning, own work after lunch.
                start = day + timedelta(hours=0 if project is site else 5)
                entries.create_entry(
                    db,
                    user=user,
                    started_at=start,
                    ended_at=start + timedelta(hours=hours),
                    project_id=project.id,
                    description=text,
                )

    print("Demo data added.")


if __name__ == "__main__":
    main()
