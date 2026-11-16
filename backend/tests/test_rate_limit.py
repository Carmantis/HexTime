"""How often one network address may use the forms that send email."""

from app.core.rate_limit import RateLimiter


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_calls_over_the_limit_are_refused_until_the_window_passes() -> None:
    clock = Clock()
    limiter = RateLimiter(3, 60, clock=clock)

    assert [limiter.allow("10.0.0.1") for _ in range(4)] == [True, True, True, False]
    clock.now += 61
    assert limiter.allow("10.0.0.1") is True


def test_each_address_has_its_own_count() -> None:
    limiter = RateLimiter(1, 60, clock=Clock())

    assert limiter.allow("10.0.0.1") is True
    assert limiter.allow("10.0.0.1") is False
    assert limiter.allow("10.0.0.2") is True


def test_refused_calls_do_not_extend_the_wait() -> None:
    clock = Clock()
    limiter = RateLimiter(1, 60, clock=clock)
    limiter.allow("10.0.0.1")
    clock.now += 30
    limiter.allow("10.0.0.1")  # refused, and not counted

    clock.now += 31
    assert limiter.allow("10.0.0.1") is True
