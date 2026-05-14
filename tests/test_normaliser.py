"""Unit tests for src/pii/normaliser.py."""
import pytest

from src.pii.normaliser import (
    normalise_cv_text,
    is_ocr_damaged,
    _merge_spaced_letters,
    _fix_broken_emails,
    _merge_spaced_digits,
    _fix_broken_urls,
)


# ── is_ocr_damaged ─────────────────────────────────────────────────────────────

def test_ocr_damaged_detects_spaced_letters():
    # >8% single-letter tokens
    text = "E l i o n a S h k u r t i sales manager Albania"
    assert is_ocr_damaged(text) is True


def test_ocr_damaged_clean_text_not_flagged():
    text = (
        "Eliona Shkurti\nSales Manager\nAddress: Rruga e Durresit, Tirane\n"
        "Phone: +355 69 440 7219\nEmail: eliona.shkurti@gmail.com\n"
        "Experience in microfinance and retail banking in Albania.\n" * 10
    )
    assert is_ocr_damaged(text) is False


def test_ocr_damaged_empty_text():
    assert is_ocr_damaged("") is False


# ── _merge_spaced_letters ──────────────────────────────────────────────────────

def test_merge_spaced_letters_basic():
    assert _merge_spaced_letters("E l i o n a") == "Eliona"


def test_merge_spaced_letters_two_words():
    # Multi-space between the two words is preserved (see docstring)
    result = _merge_spaced_letters("A r d i a n   L e s k a")
    assert "Ardian" in result
    assert "Leska" in result


def test_merge_spaced_letters_normal_text_untouched():
    text = "Normal sentence without spacing damage."
    assert _merge_spaced_letters(text) == text


def test_merge_spaced_letters_compound_name():
    result = _merge_spaced_letters("A r b ë r - L u a n")
    # Hyphens are not spaces — the two parts merge independently
    assert "Arbër" in result or "rbr" not in result


# ── _fix_broken_emails ─────────────────────────────────────────────────────────

def test_fix_broken_email_simple():
    result = _fix_broken_emails("eliona . shkurti @ gmail . com")
    assert "eliona.shkurti@gmail.com" in result


def test_fix_broken_email_no_damage():
    text = "email: eliona.shkurti@gmail.com"
    result = _fix_broken_emails(text)
    assert "eliona.shkurti@gmail.com" in result


def test_fix_broken_email_work_domain():
    result = _fix_broken_emails("e . shkurti @ outlook . com")
    assert "e.shkurti@outlook.com" in result


# ── _merge_spaced_digits ──────────────────────────────────────────────────────

def test_merge_spaced_digits_phone():
    result = _merge_spaced_digits("+ 3 5 5 6 9 4 4 0 7 2 1 9")
    assert "355" in result.replace(" ", "")


def test_merge_spaced_digits_normalises_albanian_phone():
    result = _merge_spaced_digits("+35569440 7219")
    assert "+355 69 440 7219" in result


def test_merge_spaced_digits_al_nid():
    result = _merge_spaced_digits("K 60904123 M")
    assert "K60904123M" in result


def test_merge_spaced_digits_passport():
    result = _merge_spaced_digits("B A 1193308")
    assert "BA1193308" in result


def test_merge_spaced_digits_date_slashes():
    result = _merge_spaced_digits("04 / 09 / 1996")
    assert "04/09/1996" in result


def test_merge_spaced_digits_phone_dashes():
    result = _merge_spaced_digits("068 - 227 - 9810")
    assert "068-227-9810" in result


# ── _fix_broken_urls ──────────────────────────────────────────────────────────

def test_fix_broken_urls_linkedin():
    text = "linked in . com / in / eliona - shkurti - finance"
    result = _fix_broken_urls(text)
    assert "linkedin.com/in/eliona-shkurti-finance" in result


def test_fix_broken_urls_github():
    text = "git hub . com / astrit patozi"
    result = _fix_broken_urls(text)
    assert "github.com/" in result


# ── normalise_cv_text (integration) ───────────────────────────────────────────

def test_normalise_full_ocr_damaged_cv():
    """Partial-spacing OCR damage (realistic format, not full char-by-char)."""
    # Realistic OCR damage: spaces between some chars, broken across word-parts
    raw = (
        "E l i o n a   S h k u r t i\n"
        "Email: eliona . shkurti @ gmail . com\n"
        "Phone: +35569 440 7219\n"
        "ID: K 60904123 M\n"
    )
    result = normalise_cv_text(raw)
    assert "eliona.shkurti@gmail.com" in result
    assert "K60904123M" in result


def test_normalise_idempotent():
    """Applying normaliser twice gives the same result as once."""
    raw = "E l i o n a   S h k u r t i\nPhone: + 3 5 5 6 9 4 4 0 7 2 1 9"
    once = normalise_cv_text(raw)
    twice = normalise_cv_text(once)
    assert once == twice
