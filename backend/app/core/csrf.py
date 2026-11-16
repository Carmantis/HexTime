"""Keeping other web sites out (cross-site request forgery and DNS rebinding).

Any page open in the user's browser can send requests to HexTime:

* In server mode the session lives in a cookie, and a browser attaches
  cookies whatever page made the request. The cookie is SameSite=Lax, so
  browsers leave it off most cross-site requests.
* In local mode there is no sign-in at all: the desktop server on
  127.0.0.1 answers anyone who can reach it, and every page in the user's
  browser can.

So in both modes every state-changing API request must carry a custom
header. A page on another site cannot add a custom header without CORS
permission, which HexTime never grants; our own frontend always sends it,
and so do other programs that use the local API (HexStickyNote).

Local mode also answers only requests addressed to 127.0.0.1 or localhost.
Otherwise a site could make its own name point at 127.0.0.1 (DNS rebinding)
and then read the answers as if they were its own. A server is reached by
its own name through Caddy, which routes only that name.
"""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.errors import CsrfMissingError

CSRF_HEADER = "X-HexTime-CSRF"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

#: The names the desktop server answers to (it listens on 127.0.0.1 only).
LOCAL_HOSTS = ("127.0.0.1", "localhost")


def needs_csrf_header(method: str, path: str) -> bool:
    return method not in SAFE_METHODS and path.startswith("/api/")


def add_csrf_check(app: FastAPI) -> None:
    @app.middleware("http")
    async def require_csrf_header(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if (
            needs_csrf_header(request.method, request.url.path)
            and request.headers.get(CSRF_HEADER) != "1"
        ):
            error = CsrfMissingError(f"state-changing requests need the {CSRF_HEADER} header")
            return JSONResponse(
                status_code=error.status_code,
                content={"error": {"code": error.code, "message": error.message}},
            )
        return await call_next(request)


def add_local_host_check(app: FastAPI) -> None:
    """Local mode: refuse requests addressed to any other name (400)."""
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(LOCAL_HOSTS))
