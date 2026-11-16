"""Numbers, money and dates as a printed report shows them.

These mirror the frontend's formatting (format.ts, money.ts) so a figure looks
the same on screen and on paper. Nothing here computes a total; the values
come finished from app/services/reports.py.
"""

import re
import unicodedata
from datetime import date, datetime

EN_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

#: No-break space: Finnish groups thousands with a space, and this one never
#: lets "1 234,50 €" wrap onto two lines.
NBSP = "\u00a0"
#: Ranges are written with an en dash, as typography (and Finnish) expects.
EN_DASH = "\u2013"

CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£", "SEK": "kr"}


def format_duration(seconds: int, locale: str) -> str:
    """Seconds as "1 t 30 min" / "1 h 30 min", rounded to the minute."""
    minutes = round(max(0, seconds) / 60)
    hours, rest = divmod(minutes, 60)
    unit = "t" if locale == "fi" else "h"
    if hours == 0:
        return f"{rest} min"
    if rest == 0:
        return f"{hours} {unit}"
    return f"{hours} {unit} {rest} min"


def format_money(cents: int, currency: str, locale: str) -> str:
    """Integer cents as "1 234,50 €" (fi) or "€1,234.50" (en).

    Works on the integer, never through a float: cents are already rounded.
    """
    sign = "-" if cents < 0 else ""
    whole, fraction = divmod(abs(cents), 100)
    symbol = CURRENCY_SYMBOLS.get(currency, currency)

    if locale == "fi":
        grouped = f"{whole:,}".replace(",", NBSP)
        return f"{sign}{grouped},{fraction:02d}{NBSP}{symbol}"
    return f"{sign}{symbol}{whole:,}.{fraction:02d}"


def format_date(day: date, locale: str) -> str:
    """ "6.10.2026" (fi) or "6 Oct 2026" (en) — never ambiguous on paper."""
    if locale == "fi":
        return f"{day.day}.{day.month}.{day.year}"
    return f"{day.day} {EN_MONTHS[day.month - 1]} {day.year}"


def format_date_range(first: date, last: date, locale: str) -> str:
    """Both ends inclusive, or a single date when they are the same day."""
    if first == last:
        return format_date(first, locale)
    return f"{format_date(first, locale)} {EN_DASH} {format_date(last, locale)}"


def format_time(moment: datetime) -> str:
    """A local time of day, 24-hour: "09:30"."""
    return moment.strftime("%H:%M")


def format_time_range(start: datetime, end: datetime) -> str:
    """A local start and end joined by an en dash, e.g. 09:30 to 11:00."""
    return f"{format_time(start)}{EN_DASH}{format_time(end)}"


def slugify(text: str) -> str:
    """A safe file-name part: "Asiakas Öljy Oy" → "asiakas-oljy-oy".

    Accents are dropped to their base letter and everything else that is not a
    letter or digit becomes a hyphen, so the name works in any file system and
    in a Content-Disposition header without escaping.
    """
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")
    return slug or "report"
