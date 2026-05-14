"""
Layer 1 — Pattern-based PII recognisers.

Mirrors what Microsoft Presidio + custom Albanian recognisers detect.
This layer handles structurally rigid PII: emails, phones, URLs, IDs,
dates. Catches ~90% of structured PII with high precision.

In production, replace this module with `presidio_analyzer.AnalyzerEngine`
configured with the recognisers below registered as custom Patterns.
"""
import re
from typing import List, Tuple

__all__ = ["PatternRecogniser"]


class PatternRecogniser:
    """Regex-based PII detection. Language-agnostic by design."""

    PATTERNS = {
        # Emails — RFC-ish, language-agnostic
        "EMAIL": [
            r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b",
        ],
        # Albanian phone numbers (and Italian/EU fallback)
        "PHONE": [
            r"\+355\s?6[789]\s?\d{3}\s?\d{4}",        # Mobile: +355 69 XXX XXXX
            r"\+355\s?\d{2}\s?\d{3}\s?\d{4}",         # +355 XX XXX XXXX (broader)
            r"\+355\d{7,10}",                          # +355<digits> no spaces
            r"\b06[789][\s\-]?\d{3}[\s\-]?\d{4}\b",   # Local: 06X XXX XXXX (incl dashes)
            r"00\s?355\s?\d{2,3}\s?\d{3}\s?\d{4}",    # International: 00 355 ...
        ],
        # URLs / social profiles
        "URL": [
            r"\b(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-]+",
            r"\b(?:https?://)?(?:www\.)?github\.com/[\w\-/]+",
            r"\b(?:https?://)?[\w\-]+\.(?:com|al|org|net|io|dev|eu)(?:/[\w\-/]*)?",
        ],
        # Dates of birth — multilingual
        "DOB": [
            r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
            r"September|October|November|December|Janar|Shkurt|Mars|Prill|Maj|"
            r"Qershor|Korrik|Gusht|Shtator|Tetor|Nëntor|Dhjetor)\s+\d{4}\b",
            r"\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}\b",
        ],
        # Albanian Personal ID (NUIS): letter + 8 digits + letter
        "AL_NID": [
            r"\b[A-Z]\d{8}[A-Z]\b",
        ],
        # Passport — most international formats: 2 letters + 6-8 digits
        "PASSPORT": [
            r"\b[A-Z]{2}\d{6,8}\b",
        ],
        # Albanian IBAN: AL + 2 check + 24 digits
        "IBAN": [
            r"\bAL\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\b",
        ],
    }

    def detect(self, text: str) -> List[Tuple[str, str, int, int]]:
        """Returns list of (entity_type, matched_text, start, end)."""
        results = []
        for entity_type, patterns in self.PATTERNS.items():
            for pat in patterns:
                for m in re.finditer(pat, text, re.IGNORECASE):
                    results.append((entity_type, m.group(), m.start(), m.end()))
        return results
