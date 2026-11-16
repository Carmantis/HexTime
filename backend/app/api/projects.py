"""Project and task routes.

Tasks hang off a project when they are listed or created, but are addressed
directly once they exist, which is why there are two routers here.
"""

from uuid import UUID

from fastapi import APIRouter, status

from app.core.deps import CurrentUser, DbSession
from app.schemas.project import (
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    TaskCreate,
    TaskRead,
    TaskUpdate,
)
from app.services import projects

router = APIRouter(prefix="/projects", tags=["projects"])
task_router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[ProjectRead])
def read_projects(user: CurrentUser, db: DbSession, include_archived: bool = False) -> object:
    """The user's own projects and their teams', archived ones hidden by default."""
    return projects.list_projects(db, user=user, include_archived=include_archived)


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def add_project(payload: ProjectCreate, user: CurrentUser, db: DbSession) -> object:
    return projects.create_project(db, user=user, **payload.model_dump())


@router.get("/{project_id}", response_model=ProjectRead)
def read_project(project_id: UUID, user: CurrentUser, db: DbSession) -> object:
    return projects.get_project(db, project_id, user)


@router.patch("/{project_id}", response_model=ProjectRead)
def edit_project(
    project_id: UUID, payload: ProjectUpdate, user: CurrentUser, db: DbSession
) -> object:
    project = projects.get_changeable_project(db, project_id, user)
    return projects.update_project(db, project=project, **payload.model_dump(exclude_unset=True))


@router.post("/{project_id}/archive", response_model=ProjectRead)
def archive_project(project_id: UUID, user: CurrentUser, db: DbSession) -> object:
    """Archive instead of delete, so old time entries keep their context."""
    project = projects.get_changeable_project(db, project_id, user)
    return projects.archive_project(db, project=project)


@router.post("/{project_id}/restore", response_model=ProjectRead)
def restore_project(project_id: UUID, user: CurrentUser, db: DbSession) -> object:
    project = projects.get_changeable_project(db, project_id, user)
    return projects.restore_project(db, project=project)


@router.get("/{project_id}/tasks", response_model=list[TaskRead])
def read_tasks(
    project_id: UUID, user: CurrentUser, db: DbSession, include_archived: bool = False
) -> object:
    project = projects.get_project(db, project_id, user)
    return projects.list_tasks(db, project=project, include_archived=include_archived)


@router.post("/{project_id}/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def add_task(project_id: UUID, payload: TaskCreate, user: CurrentUser, db: DbSession) -> object:
    project = projects.get_changeable_project(db, project_id, user)
    return projects.create_task(db, project=project, name=payload.name)


@task_router.patch("/{task_id}", response_model=TaskRead)
def edit_task(task_id: UUID, payload: TaskUpdate, user: CurrentUser, db: DbSession) -> object:
    task = projects.get_changeable_task(db, task_id, user)
    return projects.update_task(db, task=task, **payload.model_dump(exclude_unset=True))


@task_router.post("/{task_id}/archive", response_model=TaskRead)
def archive_task(task_id: UUID, user: CurrentUser, db: DbSession) -> object:
    task = projects.get_changeable_task(db, task_id, user)
    return projects.archive_task(db, task=task)
