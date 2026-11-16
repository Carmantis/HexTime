"""Projects and their tasks ("nimikkeet").

Projects are archived, never deleted, so that old time entries keep the name,
colour and client they were booked against.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationFailedError
from app.models import Project, Task, User
from app.models.base import utc_now
from app.models.project import DEFAULT_PROJECT_COLOR
from app.services import ownership
from app.services.sentinel import UNSET, Unset


def _guard_rate(cents: int | None) -> None:
    """Money is integer cents and can never be negative."""
    if cents is not None and cents < 0:
        raise ValidationFailedError("hourly_rate_cents must not be negative")


def _guard_name(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        raise ValidationFailedError("name must not be empty")
    return stripped


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def create_project(
    db: Session,
    *,
    user: User,
    name: str,
    color: str = DEFAULT_PROJECT_COLOR,
    client_name: str | None = None,
    billable_default: bool = False,
    hourly_rate_cents: int | None = None,
    currency: str = "EUR",
    team_id: UUID | None = None,
) -> Project:
    """The caller's own project, or with `team_id` the team's (leads only)."""
    _guard_rate(hourly_rate_cents)
    if team_id is not None:
        ownership.require_team_manager(db, user, team_id)

    project = Project(
        owner_user_id=None if team_id else user.id,
        owner_team_id=team_id,
        name=_guard_name(name),
        color=color,
        client_name=client_name,
        billable_default=billable_default,
        hourly_rate_cents=hourly_rate_cents,
        currency=currency,
    )
    db.add(project)
    db.commit()
    return project


def list_projects(db: Session, *, user: User, include_archived: bool = False) -> list[Project]:
    stmt = select(Project).where(ownership.visible_to(Project, user))
    if not include_archived:
        stmt = stmt.where(Project.archived_at.is_(None))
    return list(db.scalars(stmt.order_by(Project.name)))


def get_project(db: Session, project_id: UUID, user: User) -> Project:
    return ownership.require_visible(db, db.get(Project, project_id), user, "project")


def get_changeable_project(db: Session, project_id: UUID, user: User) -> Project:
    """A project the user may edit, archive or add tasks to."""
    return ownership.require_changeable(db, db.get(Project, project_id), user, "project")


def update_project(
    db: Session,
    *,
    project: Project,
    name: str | Unset = UNSET,
    color: str | Unset = UNSET,
    client_name: str | Unset | None = UNSET,
    billable_default: bool | Unset = UNSET,
    hourly_rate_cents: int | Unset | None = UNSET,
    currency: str | Unset = UNSET,
) -> Project:
    """Apply only the fields the caller mentioned.

    Changing the rate here never touches existing time entries: each of those
    froze its own rate_snapshot_cents when it was created.
    """
    # Only client_name and hourly_rate_cents are nullable. Explicitly sending
    # null for any other field is a mistake, not a request to clear it.
    for field, value in (
        ("name", name),
        ("color", color),
        ("billable_default", billable_default),
        ("currency", currency),
    ):
        if value is None:
            raise ValidationFailedError(f"{field} must not be null")

    if not isinstance(name, Unset):
        project.name = _guard_name(name)
    if not isinstance(color, Unset):
        project.color = color
    if not isinstance(client_name, Unset):
        project.client_name = client_name
    if not isinstance(billable_default, Unset):
        project.billable_default = billable_default
    if not isinstance(hourly_rate_cents, Unset):
        _guard_rate(hourly_rate_cents)
        project.hourly_rate_cents = hourly_rate_cents
    if not isinstance(currency, Unset):
        project.currency = currency

    db.commit()
    return project


def archive_project(db: Session, *, project: Project) -> Project:
    """Hide a project from the pickers without touching its time entries."""
    if project.archived_at is None:
        project.archived_at = utc_now()
        db.commit()
    return project


def restore_project(db: Session, *, project: Project) -> Project:
    project.archived_at = None
    db.commit()
    return project


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


def create_task(db: Session, *, project: Project, name: str) -> Task:
    """Add a task to a project the caller has already been granted."""
    task = Task(project_id=project.id, name=_guard_name(name))
    db.add(task)
    db.commit()
    return task


def list_tasks(db: Session, *, project: Project, include_archived: bool = False) -> list[Task]:
    stmt = select(Task).where(Task.project_id == project.id)
    if not include_archived:
        stmt = stmt.where(Task.archived_at.is_(None))
    return list(db.scalars(stmt.order_by(Task.name)))


def get_task(db: Session, task_id: UUID, user: User) -> Task:
    """A task is visible exactly when its project is."""
    task = db.get(Task, task_id)
    if task is None:
        raise NotFoundError("task not found")
    # Raises NotFound if the project is not the caller's, which is the same
    # answer an unknown task gets — no probing for real ids.
    get_project(db, task.project_id, user)
    return task


def get_changeable_task(db: Session, task_id: UUID, user: User) -> Task:
    """A task the user may rename or archive: its project is changeable."""
    task = get_task(db, task_id, user)
    get_changeable_project(db, task.project_id, user)
    return task


def update_task(db: Session, *, task: Task, name: str | Unset = UNSET) -> Task:
    if not isinstance(name, Unset):
        task.name = _guard_name(name)
    db.commit()
    return task


def archive_task(db: Session, *, task: Task) -> Task:
    if task.archived_at is None:
        task.archived_at = utc_now()
        db.commit()
    return task
