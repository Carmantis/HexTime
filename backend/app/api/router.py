"""The single router that carries the /api/v1 prefix.

Every new router is included here, never mounted on the app directly, so the
version prefix is written in exactly one place.
"""

from fastapi import APIRouter

from app.api import (
    admin,
    auth,
    config,
    entries,
    exports,
    me,
    projects,
    reports,
    tags,
    teams,
    timer,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(config.router)
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(admin.router)
api_router.include_router(teams.router)
api_router.include_router(teams.invitations_router)
api_router.include_router(teams.people_router)
api_router.include_router(timer.router)
api_router.include_router(entries.router)
api_router.include_router(projects.router)
api_router.include_router(projects.task_router)
api_router.include_router(tags.router)
api_router.include_router(reports.router)
api_router.include_router(exports.router)
