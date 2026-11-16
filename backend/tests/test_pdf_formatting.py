"""How numbers and dates are printed. Mirrors the frontend's formatting."""

from datetime import date, datetime

import pytest

from app.reports.formatting import (
    EN_DASH,
    NBSP,
    format_date,
    format_date_range,
    format_duration,
    format_money,
    format_time_range,
    slugify,
)


@pytest.mark.parametrize(
    ("seconds", "fi", "en"),
    [
        (0, "0 min", "0 min"),
        (45 * 60, "45 min", "45 min"),
        (3600, "1 t", "1 h"),
        (5400, "1 t 30 min", "1 h 30 min"),
        (89, "1 min", "1 min"),
    ],
)
def test_durations(seconds: int, fi: str, en: str) -> None:
    assert format_duration(seconds, "fi") == fi
    assert format_duration(seconds, "en") == en


def test_money_in_finnish() -> None:
    assert format_money(123450, "EUR", "fi") == f"1{NBSP}234,50{NBSP}€"


def test_money_in_english() -> None:
    assert format_money(123450, "EUR", "en") == "€1,234.50"


def test_money_keeps_single_cents_and_signs() -> None:
    assert format_money(5, "EUR", "fi") == f"0,05{NBSP}€"
    assert format_money(-150, "EUR", "en") == "-€1.50"


def test_dates() -> None:
    assert format_date(date(2026, 10, 6), "fi") == "6.10.2026"
    assert format_date(date(2026, 10, 6), "en") == "6 Oct 2026"


def test_a_one_day_range_is_one_date() -> None:
    day = date(2026, 10, 6)
    assert format_date_range(day, day, "fi") == "6.10.2026"
    assert format_date_range(day, date(2026, 10, 7), "fi") == f"6.10.2026 {EN_DASH} 7.10.2026"


def test_time_range_is_24_hour() -> None:
    start = datetime(2026, 10, 6, 9, 5)
    assert format_time_range(start, datetime(2026, 10, 6, 17, 30)) == f"09:05{EN_DASH}17:30"


def test_slugs_are_plain_ascii() -> None:
    assert slugify("Asiakas Öljy Oy") == "asiakas-oljy-oy"
    assert slugify("  R&D / 2026  ") == "r-d-2026"


def test_a_name_with_nothing_usable_still_gives_a_slug() -> None:
    assert slugify("???") == "report"
