"""Abstract base for all CV extractors."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["ExtractionResult", "Extractor", "get_extractor"]


@dataclass
class ExtractionResult:
    text: str
    quality: float          # 0.0 – 1.0
    metadata: dict = field(default_factory=dict)


class Extractor(ABC):
    @abstractmethod
    def extract(self, path: Path) -> ExtractionResult: ...


def get_extractor(path: Path) -> Extractor:
    """Dispatch to the right extractor based on file suffix."""
    from .pdf import PDFExtractor
    from .docx import DOCXExtractor
    from .text import TextExtractor

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return PDFExtractor()
    if suffix in (".docx", ".doc"):
        return DOCXExtractor()
    if suffix == ".txt":
        return TextExtractor()
    raise ValueError(f"Unsupported file type: {suffix!r} ({path.name})")
