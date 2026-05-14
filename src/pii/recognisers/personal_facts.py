"""
Layer 3 — Personal Facts recogniser.

Detects sensitive personal attributes that are often missed by standard
NER but are GDPR Article 9 special-category data: marital status,
gender, religion, sexual orientation, etc.

In production, this layer is augmented by a local LLM verification pass
(Ollama llama3.2:3b) that catches contextual personal information not
captured by patterns.
"""
import re
from typing import List, Tuple

__all__ = ["PersonalFactsRecogniser"]


class PersonalFactsRecogniser:
    """Detects sensitive personal facts that bias LLM scoring."""

    PATTERNS = {
        "MARITAL": [
            r"\b(?:Single|Married|Divorced|Widowed|"
            r"i\s+martuar|beqar|beqare|i\s+divorcuar|i\s+ve)\b",
            r"Marital\s+status\s*[:\.]?\s*(\w+)",
        ],
        "GENDER": [
            r"\bGender\s*[:\.]?\s*(Male|Female|Mashkull|Femër|Femer)\b",
            r"\bSex\s*[:\.]?\s*(M|F|Male|Female)\b",
            # Standalone gender word on its own line (Europass format)
            r"(?<=\n)(Male|Female|Mashkull|Femër|Femer)(?=\s*\n)",
        ],
        "RELIGION": [
            r"\bReligion\s*[:\.]?\s*\w+",
            r"\b(?:Muslim|Christian|Catholic|Orthodox|Protestant|"
            r"Jewish|Muslim|Atheist|Bektashi)\b",
        ],
        "FAMILY": [
            r"\b\d+\s+(?:children|kids|fëmijë)\b",
            r"\b(?:single\s+parent|prind\s+i\s+vetëm)\b",
        ],
    }

    def detect(self, text: str) -> List[Tuple[str, str, int, int]]:
        results: List[Tuple[str, str, int, int]] = []
        for ent_type, patterns in self.PATTERNS.items():
            for pat in patterns:
                for m in re.finditer(pat, text, re.IGNORECASE):
                    results.append((ent_type, m.group(), m.start(), m.end()))
        return results
