"""Translations for text the backend writes itself: PDFs and, later, emails.

The UI has its own strings in the frontend. These files only hold what leaves
the server as a finished document, where the frontend cannot translate it.
Keys are grouped like the frontend's ("pdf.totalHours") and both languages
must have the same set; a test checks that.
"""

import json
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from app.core.config import SUPPORTED_LOCALES

I18N_DIR = Path(__file__).parent.parent / "i18n"

Translate = Callable[..., str]


def _flatten(tree: dict[str, object], prefix: str = "") -> dict[str, str]:
    """{"pdf": {"title": "x"}} → {"pdf.title": "x"}."""
    flat: dict[str, str] = {}
    for key, value in tree.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{name}."))
        else:
            flat[name] = str(value)
    return flat


@lru_cache
def messages(locale: str) -> dict[str, str]:
    """Every string of one language, read once per process."""
    with (I18N_DIR / f"{locale}.json").open(encoding="utf-8") as file:
        return _flatten(json.load(file))


def resolve_locale(requested: str | None, fallback: str) -> str:
    """The requested language if we have it, else the fallback."""
    if requested in SUPPORTED_LOCALES:
        return requested
    return fallback if fallback in SUPPORTED_LOCALES else SUPPORTED_LOCALES[0]


def translator(locale: str) -> Translate:
    """A ``t(key, **params)`` function for one language.

    A missing key comes back as the key itself, so a gap shows up in the
    document instead of crashing the export.
    """
    table = messages(locale)

    def t(key: str, **params: object) -> str:
        text = table.get(key, key)
        for name, value in params.items():
            text = text.replace(f"{{{name}}}", str(value))
        return text

    return t
