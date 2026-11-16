"""Backend translations (PDFs, later emails)."""

from app.core.config import SUPPORTED_LOCALES
from app.core.i18n import messages, resolve_locale, translator


def test_every_language_has_the_same_keys() -> None:
    """A key added to one file only would print as a raw key in the other."""
    keys = {locale: set(messages(locale)) for locale in SUPPORTED_LOCALES}
    reference = keys[SUPPORTED_LOCALES[0]]
    for locale, found in keys.items():
        assert found == reference, f"{locale}: {found ^ reference}"


def test_no_string_is_empty() -> None:
    for locale in SUPPORTED_LOCALES:
        assert all(text.strip() for text in messages(locale).values()), locale


def test_parameters_are_filled_in() -> None:
    assert translator("fi")("pdf.page", n=3) == "Sivu 3"
    assert translator("en")("pdf.page", n=3) == "Page 3"


def test_a_missing_key_comes_back_as_itself() -> None:
    assert translator("fi")("pdf.nothingHere") == "pdf.nothingHere"


def test_an_unknown_language_falls_back() -> None:
    assert resolve_locale("sv", "en") == "en"
    assert resolve_locale(None, "fi") == "fi"
    assert resolve_locale("en", "fi") == "en"
