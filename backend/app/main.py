"""FastAPI application factory.

The factory exists so tests can build an app with their own settings instead of
whatever happens to be in the environment.
"""

import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.auth import email_form_limiter
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.csrf import add_csrf_check, add_local_host_check
from app.core.errors import register_error_handlers
from app.core.startup import prepare_local_database

log = logging.getLogger("hextime")

#: `npm run build` writes the compiled frontend here. Absent during backend dev.
STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    settings: Settings | None = None,
    *,
    serve_static: bool = True,
    extra_routers: Sequence[APIRouter] = (),
) -> FastAPI:
    """Build the application.

    Pass ``settings`` to override the environment. Pass ``serve_static=False``
    to leave the compiled frontend unmounted — see the mount below for why a
    test almost always wants that.
    """
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # One command to start: the desktop user never runs a migration.
        if resolved.auto_migrate:
            prepare_local_database(resolved)
        yield

    app = FastAPI(
        title="HexTime",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: settings

    register_error_handlers(app)
    app.state.email_form_limiter = email_form_limiter()
    add_csrf_check(app)
    if not resolved.is_server:
        add_local_host_check(app)
    elif "time_zone" not in resolved.model_fields_set:
        # A server set up before TIME_ZONE existed: its team reports
        # would quietly count UTC days.
        log.warning(
            "TIME_ZONE is not set; team reports count whole days in UTC. "
            "Run the installation script again, or set e.g. TIME_ZONE=Europe/Helsinki."
        )
    app.include_router(api_router)
    # Routes only one way of running needs, such as the desktop window's.
    # They have to be in before the static mount below to be reachable.
    for router in extra_routers:
        app.include_router(router)

    # Mounted last, because a mount on "/" catches every path that no earlier
    # route claimed. The API is included above, so it still wins — but nothing
    # can be added to the app *after* this call and still be reachable.
    #
    # It is also why tests pass serve_static=False: otherwise the suite would
    # behave differently depending on whether anyone had run `npm run build`.
    if serve_static and STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app


app = create_app()
