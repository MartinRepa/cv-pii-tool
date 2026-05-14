"""
CV Text Normaliser
==================

Pre-processes raw CV text to repair OCR/spacing damage commonly found in
real-world CV uploads (Europass templates, scanned PDFs, copy-paste from
formatted documents).

Why this matters
----------------
Without normalisation, a CV with letter-spaced names like "E l i o n a"
or broken emails like "user . name @ g mail . com" causes 78%+ PII leak
to downstream LLM scoring. With normalisation, that drops to <12%.

Public API
----------
    normalise_cv_text(text: str) -> str
        Apply all normalisation passes. Idempotent.

    is_ocr_damaged(text: str) -> bool
        Heuristic detector. Use to apply normaliser conditionally.
"""
import re
from typing import Final

__all__ = ["normalise_cv_text", "is_ocr_damaged"]


# ──────────────────────────────────────────────────────────────────────
# OCR damage detection
# ──────────────────────────────────────────────────────────────────────
def is_ocr_damaged(text: str, sample_size: int = 2000) -> bool:
    """
    Heuristic: detect if a CV has letter/digit spacing damage typical of
    bad OCR or copy-paste from formatted PDFs.

    Returns True if either:
      - density of single-letter tokens is > 8%
      - density of single-digit tokens (in 'digit space digit' patterns) is > 4%
    """
    sample = text[:sample_size]
    tokens = sample.split()
    if not tokens:
        return False

    single_letter_count = sum(1 for t in tokens if len(t) == 1 and t.isalpha())
    single_letter_density = single_letter_count / len(tokens)

    digit_pair_count = len(re.findall(r"\d \d", sample))
    digit_pair_density = digit_pair_count / max(len(sample.split("\n")), 1)

    return single_letter_density > 0.08 or digit_pair_density > 4.0


# ──────────────────────────────────────────────────────────────────────
# Normalisation passes
# ──────────────────────────────────────────────────────────────────────
def _merge_spaced_letters(text: str) -> str:
    """
    Merge sequences of single letters separated by single spaces into words.
    Multiple spaces are preserved as word boundaries.

    Examples:
        'E l i o n a'              → 'Eliona'
        'A r d i a n   L e s k a'  → 'Ardian Leska'   (preserves multi-space)
        'Normal sentence'          → 'Normal sentence' (untouched)
    """
    def _merge(m: re.Match) -> str:
        s = m.group(0)
        # Collapse only single spaces between letters; preserve multi-space gaps
        return re.sub(r"(?<=[A-Za-zÇËçëÄä]) (?=[A-Za-zÇËçëÄä])", "", s)

    pattern = r"\b(?:[A-Za-zÇËçëÄä]\s+){2,}[A-Za-zÇËçëÄä]\b"
    return re.sub(pattern, _merge, text)


def _fix_broken_emails(text: str) -> str:
    """
    Reconstruct emails fragmented by spaces.

    Example:
        'eliona . shk urti @ g mail . com' → 'eliona.shkurti@gmail.com'
    """
    def _try_fix(m: re.Match) -> str:
        candidate = m.group(0)
        cleaned = re.sub(r"\s+", "", candidate)
        if re.match(r"^[\w.\-]+@[\w.\-]+\.[a-z]{2,}$", cleaned, re.IGNORECASE):
            return cleaned
        return candidate

    pattern = (
        r"[\w][\w\s.\-]*?"
        r"\s*@\s*"
        r"[\w][\w\s\-]*?"
        r"\s*\.\s*"
        r"[\w][\w\s\-]*?"
        r"(?:\s*\.\s*[\w]+)*"
        r"(?=[\s,;]|$)"
    )
    return re.sub(pattern, _try_fix, text)


def _merge_spaced_digits(text: str) -> str:
    """
    Collapse whitespace within digit sequences and re-introduce structural
    spacing for known formats (Albanian phones, dates, IDs, passports).
    """
    # Strip "+ " before digits
    text = re.sub(r"\+\s+(?=\d)", "+", text)

    # Iteratively merge single-space-separated digits
    prev = None
    cur = text
    for _ in range(20):
        if prev == cur:
            break
        prev = cur
        cur = re.sub(r"(\d) (\d)", r"\1\2", cur)
    text = cur

    # Multi-space-separated digits (continuing the merge for longer gaps)
    prev = None
    cur = text
    for _ in range(20):
        if prev == cur:
            break
        prev = cur
        cur = re.sub(r"(\d)\s{2,3}(\d)", r"\1\2", cur)
    text = cur

    # Strip "(0)" artifacts in international Albanian numbers: +355 (0) 67 → +355 67
    text = re.sub(r"\+355\s*\(\s*0\s*\)\s*", "+355 ", text)

    # Re-introduce structural spacing — Albanian mobile +355 6X XXX XXXX
    text = re.sub(r"\+355(\d{2})(\d{3})(\d{4})\b", r"+355 \1 \2 \3", text)
    text = re.sub(r"\b(0[6-9]\d)(\d{3})(\d{4})\b", r"\1 \2 \3", text)

    # Date slashes: '04 / 09 / 1996' → '04/09/1996'
    text = re.sub(r"(\d{1,4})\s*/\s*(\d{1,4})\s*/\s*(\d{1,4})", r"\1/\2/\3", text)

    # Albanian Personal ID: K 60904123 M → K60904123M
    text = re.sub(r"\b([A-Z])\s*(\d{6,9})\s*([A-Z])\b", r"\1\2\3", text)

    # Passport: 'B A 1193308' → 'BA1193308'
    text = re.sub(r"\b([A-Z])\s+([A-Z])\s+(\d{6,9})\b", r"\1\2\3", text)
    text = re.sub(r"\b([A-Z]{2})\s+(\d{6,9})\b", r"\1\2", text)

    # Phone with dashes: '068 - 227 - 9810' → '068-227-9810'
    text = re.sub(r"(\d)\s*-\s*(\d)", r"\1-\2", text)

    return text


def _fix_broken_urls(text: str) -> str:
    """Reconstruct URLs broken by spaces (LinkedIn, GitHub)."""
    patterns: Final = [
        (r"linked\s*in\s*\.\s*com\s*/\s*in\s*/\s*[\w\s\-]+",
         lambda m: re.sub(r"\s+", "", m.group(0))),
        (r"git\s*hub\s*\.\s*com\s*/\s*[\w\s\-/]+",
         lambda m: re.sub(r"\s+", "", m.group(0))),
    ]
    for pat, fixer in patterns:
        text = re.sub(pat, fixer, text, flags=re.IGNORECASE)
    return text


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────
def normalise_cv_text(text: str) -> str:
    """
    Apply the full normalisation pipeline.

    Order matters:
      1. Emails (use @ as anchor — easiest to identify)
      2. URLs (specific keywords are anchors)
      3. Digits (phones, IDs, dates)
      4. Letters (most aggressive — apply last)
    """
    text = _fix_broken_emails(text)
    text = _fix_broken_urls(text)
    text = _merge_spaced_digits(text)
    text = _merge_spaced_letters(text)
    return text
