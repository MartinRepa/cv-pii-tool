"""PDF extractor using pdfplumber."""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from .base import Extractor, ExtractionResult

__all__ = ["PDFExtractor"]

# Rough set of common English/Albanian dictionary words for quality scoring
_COMMON_WORDS = {
    "the", "and", "for", "with", "from", "this", "that", "have", "has",
    "been", "will", "are", "was", "were", "not", "but", "can", "all",
    "work", "year", "years", "experience", "education", "skills", "email",
    "phone", "address", "date", "name", "position", "company", "university",
    "me", "my", "i", "in", "of", "to", "a", "an", "is", "it", "as", "at",
    "by", "on", "or", "be", "do", "if", "we", "he", "she", "they",
    # Albanian common words
    "dhe", "ne", "per", "nga", "me", "te", "si", "ku", "jam", "ka",
    "jane", "eshte", "nga", "nje", "shqiperi", "punë", "arsim",
}


def _char_density_score(text: str, file_size: int) -> float:
    """Ratio of text chars to file bytes, clamped 0–1."""
    if file_size == 0:
        return 0.0
    ratio = len(text.strip()) / file_size
    # PDFs typically 0.05–0.5 chars/byte when well-extracted
    return min(ratio / 0.3, 1.0)


def _dictionary_match_score(text: str) -> float:
    """Fraction of tokens that look like real words."""
    tokens = re.findall(r"[a-zA-ZçëÇËäÄ]{2,}", text.lower())
    if not tokens:
        return 0.0
    hits = sum(1 for t in tokens if t in _COMMON_WORDS or len(t) >= 3)
    return min(hits / len(tokens), 1.0)


def _layout_score(text: str) -> float:
    """Penalise heavy single-character line fragmentation."""
    lines = text.splitlines()
    if not lines:
        return 1.0
    single_char_lines = sum(1 for ln in lines if len(ln.strip()) == 1)
    frag_ratio = single_char_lines / len(lines)
    return max(1.0 - frag_ratio * 3, 0.0)


class PDFExtractor(Extractor):
    def extract(self, path: Path) -> ExtractionResult:
        file_size = path.stat().st_size
        pages_text: list[str] = []

        with pdfplumber.open(path) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                page_text = page.extract_text(layout=True) or ""
                pages_text.append(page_text)

        text = "\n".join(pages_text)

        if not text.strip():
            return ExtractionResult(
                text="",
                quality=0.0,
                metadata={"pages": page_count, "extractor": "pdfplumber"},
            )

        q_char = _char_density_score(text, file_size)
        q_dict = _dictionary_match_score(text)
        q_layout = _layout_score(text)
        quality = round(q_char * q_dict * q_layout, 4)
        # Floor at 0.1 for non-empty PDFs so they aren't skipped unfairly
        quality = max(quality, 0.1) if text.strip() else 0.0

        return ExtractionResult(
            text=text,
            quality=quality,
            metadata={
                "pages": page_count,
                "extractor": "pdfplumber",
                "q_char_density": q_char,
                "q_dictionary_match": q_dict,
                "q_layout": q_layout,
            },
        )
