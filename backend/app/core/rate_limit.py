"""A small in-memory limit on how often one network address may do something.

Used for the forms that send email (password reset, signing up): they
record no failures that could be counted in the database, yet without a
limit anyone could make the server send mail to every address in the
organisation, one request after another.

The counts live in this process only and start over when it restarts. That
is enough for one uvicorn process, which is how HexTime runs; failed logins
are counted in the database instead (app/services/auth.py).
"""

import threading
import time
from collections import deque
from collections.abc import Callable

#: Above this many tracked addresses, stale ones are dropped on the next call.
_TIDY_ABOVE = 10_000


class RateLimiter:
    """At most `limit` calls per key within `window_seconds`."""

    def __init__(
        self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Count one call for `key`; False if it went over the limit."""
        now = self._clock()
        with self._lock:
            if len(self._hits) > _TIDY_ABOVE:
                self._drop_stale(now)
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def _drop_stale(self, now: float) -> None:
        stale = [
            key for key, hits in self._hits.items() if not hits or hits[-1] <= now - self.window
        ]
        for key in stale:
            del self._hits[key]
