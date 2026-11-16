"""The time zone database has to be there.

Reports group by the user's local day, so every report needs a real IANA zone
database. Linux usually has one in /usr/share/zoneinfo; Windows has none, and
slim containers often drop it. When it is missing, zoneinfo raises and every
report turns into a 422 — a whole class of failures that only shows up on
someone else's machine. The `tzdata` package removes the question, and these
tests make its absence a build failure instead of a support ticket.
"""

import importlib.util
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

#: Zones the application is actually used in, plus the two extremes that
#: exercise a positive and a negative offset.
ZONES = ["Europe/Helsinki", "UTC", "America/New_York", "Pacific/Auckland"]


def test_tzdata_is_installed() -> None:
    """Without this package the Windows build has no zones at all."""
    assert importlib.util.find_spec("tzdata") is not None


@pytest.mark.parametrize("name", ZONES)
def test_the_zone_resolves(name: str) -> None:
    assert ZoneInfo(name) is not None


def test_helsinki_knows_about_summer_time() -> None:
    """The offset has to actually change, not just be a fixed +02:00."""
    helsinki = ZoneInfo("Europe/Helsinki")
    winter = datetime(2026, 1, 15, 12, tzinfo=UTC).astimezone(helsinki)
    summer = datetime(2026, 7, 15, 12, tzinfo=UTC).astimezone(helsinki)

    assert winter.utcoffset() != summer.utcoffset()
    assert summer.utcoffset() is not None
    assert summer.utcoffset().total_seconds() == 3 * 3600
