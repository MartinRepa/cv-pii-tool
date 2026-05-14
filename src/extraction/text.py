"""Plain-text extractor."""
from __future__ import annotations

from pathlib import Path

from .base import Extractor, ExtractionResult

__all__ = ["TextExtractor"]


class TextExtractor(Extractor):
    def extract(self, path: Path) -> ExtractionResult:
        text = path.read_text(encoding="utf-8", errors="replace")
        quality = 1.0 if text.strip() else 0.0
        return ExtractionResult(
            text=text,
            quality=quality,
            metadata={"extractor": "text", "bytes": path.stat().st_size},
        )
