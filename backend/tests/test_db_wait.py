"""The container waits for PostgreSQL before migrating (app/core/db_wait.py),
so a database that is still starting is not mistaken for a broken setting,
and a broken setting is not waited for."""

from sqlalchemy.exc import OperationalError

from app.core.db_wait import wait_for_database

STARTING = "connection failed: FATAL:  the database system is starting up"
REFUSED = "connection failed: connection refused"
WRONG_PASSWORD = 'connection failed: FATAL:  password authentication failed for user "hextime"'


class Clock:
    """Time that moves only when the code sleeps."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class Server:
    """Fails with the given messages in turn, then answers."""

    def __init__(self, *failures: str) -> None:
        self.failures = list(failures)
        self.tries = 0

    def connect(self) -> None:
        self.tries += 1
        if self.failures:
            raise OperationalError("connect", {}, Exception(self.failures.pop(0)))


def wait(server: Server, timeout: float = 30) -> tuple[bool, Clock]:
    clock = Clock()
    return wait_for_database(server.connect, timeout, sleep=clock.sleep, clock=clock), clock


def test_a_database_that_answers_is_not_waited_for() -> None:
    server = Server()

    ready, clock = wait(server)

    assert ready
    assert (server.tries, clock.now) == (1, 0)


def test_a_starting_database_is_waited_for() -> None:
    server = Server(REFUSED, STARTING, STARTING)

    ready, _ = wait(server)

    assert ready
    assert server.tries == 4


def test_a_wrong_password_is_not_waited_for() -> None:
    """Left for the migration, which then reports it as it is."""
    server = Server(WRONG_PASSWORD, WRONG_PASSWORD)

    ready, clock = wait(server)

    assert ready
    assert (server.tries, clock.now) == (1, 0)


def test_waiting_gives_up_after_the_timeout() -> None:
    server = Server(*[REFUSED] * 1000)

    ready, clock = wait(server, timeout=10)

    assert not ready
    assert 10 <= clock.now <= 12
