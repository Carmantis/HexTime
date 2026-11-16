"""Wait for the database server before migrating; the container's entrypoint
runs this first:

    python -m app.core.db_wait --timeout 90

PostgreSQL may still be starting when HexTime starts (the first time, after
a power cut, while `podman auto-update` restarts it). Waiting fixes that, but
not a wrong password or a missing database, so for those it stops at once and
leaves the migration to report the real error.

A module of its own, so a start does not import the whole app twice.
"""

import argparse
import sys
import time
from collections.abc import Callable

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

#: What PostgreSQL says when a setting is wrong rather than the server not
#: ready yet. psycopg gives connection errors no SQLSTATE, so the message is
#: all there is; an unknown one is simply waited for until the timeout.
NOT_WORTH_WAITING = (
    "password authentication failed",
    "does not exist",
    "no pg_hba.conf entry",
)


def worth_waiting(error: Exception) -> bool:
    """True while the error looks like a server that is not ready yet."""
    message = str(error)
    return not any(phrase in message for phrase in NOT_WORTH_WAITING)


def wait_for_database(
    connect: Callable[[], None],
    timeout: float,
    *,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> bool:
    """Try ``connect`` until it works or the error is not worth waiting for.

    False only when the timeout ran out first.
    """
    deadline = clock() + timeout
    while True:
        try:
            connect()
        except OperationalError as error:
            if not worth_waiting(error):
                return True
            if clock() >= deadline:
                return False
            sleep(2)
        else:
            return True


def _connector(url: str) -> Callable[[], None]:
    engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 3})

    def connect() -> None:
        with engine.connect():
            pass

    return connect


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.core.db_wait")
    parser.add_argument("--timeout", type=float, default=90, help="seconds (default 90)")
    args = parser.parse_args(argv)

    url = get_settings().resolved_database_url
    if make_url(url).get_backend_name() == "sqlite":
        return  # a file, nothing to wait for
    if not wait_for_database(_connector(url), args.timeout):
        sys.exit(f"hextime: the database did not answer in {args.timeout:g} s.")


if __name__ == "__main__":
    main()
