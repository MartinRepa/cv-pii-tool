"""
PII Pipeline — orchestrates all layers and produces anonymised output
with a reversible token map (stored locally only, never sent to cloud).
"""
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .normaliser import normalise_cv_text, is_ocr_damaged
from .recognisers import (
    PatternRecogniser,
    HeuristicNERRecogniser,
    PersonalFactsRecogniser,
)

__all__ = ["PIIPipeline", "PIIDetection", "AnonymisationResult"]


@dataclass
class PIIDetection:
    entity_type: str
    text: str
    start: int
    end: int
    layer: str  # which layer detected it — useful for debugging
    confidence: float | None = None


@dataclass
class AnonymisationResult:
    """Result of running the pipeline against a CV."""
    anonymised_text: str
    pii_map: Dict[str, str]          # token → original PII (encrypt before storing!)
    detections: List[PIIDetection]   # full detection log for audit
    was_normalised: bool             # was the text OCR-damaged?


class PIIPipeline:
    """
    Orchestrates the full PII detection and anonymisation flow.

    Pipeline stages:
        0. Normalise (conditional — only if OCR damage detected)
        1. Pattern matching (regex)
        2. Heuristic NER (replace with GLiNER-Multi in production)
        3. Personal facts detection
        4. Deduplicate overlapping detections
        5. Replace with typed tokens

    Usage:
        pipeline = PIIPipeline()
        result = pipeline.anonymise(raw_cv_text)
        # send result.anonymised_text to Azure OpenAI
        # encrypt and store result.pii_map locally for re-identification
    """

    def __init__(self, normalise: str = "auto", ner_recogniser=None):
        """
        Args:
            normalise: 'auto' (only if damaged), 'always', or 'never'
            ner_recogniser: Optional secondary NER (e.g. GLiNERRecogniser).
                            The heuristic NER always runs for Albanian-specific
                            patterns; ner_recogniser adds contextual/multilingual
                            coverage on top.
        """
        self.pattern = PatternRecogniser()
        self.heuristic_ner = HeuristicNERRecogniser()
        self.gliner_ner = ner_recogniser  # None → heuristic-only mode
        self.personal = PersonalFactsRecogniser()
        self.normalise_mode = normalise

    # ────────────────────────────────────────────────────────────────
    def _preprocess(self, text: str) -> str:
        """Fix common PDF extraction artifacts (e.g. 'user @gmail')."""
        # Email split by space around @
        text = re.sub(r"(\w)\s*\n?\s*@\s*\n?\s*(\w)", r"\1@\2", text)
        # URL split mid-path
        text = re.sub(r"(linkedin\.com|github\.com)/\s*\n\s*(\w)", r"\1/\2", text)
        # Parenthesised country codes: (+355) 67… → +355 67…
        text = re.sub(r"\(\s*(\+\d{1,4})\s*\)", r"\1", text)
        return text

    def _maybe_normalise(self, text: str) -> Tuple[str, bool]:
        """Apply CV normaliser if needed/configured."""
        if self.normalise_mode == "always":
            return normalise_cv_text(text), True
        if self.normalise_mode == "never":
            return text, False
        # auto: detect and apply
        if is_ocr_damaged(text):
            return normalise_cv_text(text), True
        return text, False

    # ────────────────────────────────────────────────────────────────
    def detect(self, text: str) -> List[PIIDetection]:
        """Run all recogniser layers and return deduplicated detections."""
        text = self._preprocess(text)

        all_detections: List[PIIDetection] = []
        for ent, val, s, e in self.pattern.detect(text):
            all_detections.append(PIIDetection(ent, val, s, e, "L1_pattern", 0.99))
        # Heuristic NER always runs — it has Albanian-specific city/name/address knowledge
        for ent, val, s, e in self.heuristic_ner.detect(text):
            all_detections.append(PIIDetection(ent, val, s, e, "L2_ner", None))
        # GLiNER runs on top when configured — adds contextual + multilingual coverage
        if self.gliner_ner is not None:
            for row in self.gliner_ner.detect(text):
                ent, val, s, e, conf = row
                all_detections.append(PIIDetection(ent, val, s, e, "L2_gliner", conf))
        for ent, val, s, e in self.personal.detect(text):
            all_detections.append(PIIDetection(ent, val, s, e, "L3_personal", 0.99))

        per_type_deduped = self._dedupe(all_detections)
        header_names = self._detect_header_name(text, per_type_deduped)
        return self._dedupe_global(per_type_deduped + header_names)

    @staticmethod
    def _dedupe(detections: List[PIIDetection]) -> List[PIIDetection]:
        """Remove overlapping detections of the same type — keep widest match."""
        by_type: Dict[str, List[PIIDetection]] = defaultdict(list)
        for d in detections:
            by_type[d.entity_type].append(d)

        result: List[PIIDetection] = []
        for items in by_type.values():
            items.sort(key=lambda x: (x.start, -(x.end - x.start)))
            kept: List[PIIDetection] = []
            for item in items:
                # Skip if contained within already-kept item
                if any(k.start <= item.start and k.end >= item.end for k in kept):
                    continue
                kept.append(item)
            result.extend(kept)
        return result

    @staticmethod
    def _dedupe_global(detections: List[PIIDetection]) -> List[PIIDetection]:
        """Remove cross-type overlapping detections — widest span wins."""
        if not detections:
            return []
        # Sort widest first; ties broken by position
        sorted_dets = sorted(detections, key=lambda d: (-(d.end - d.start), d.start))
        kept: List[PIIDetection] = []
        for d in sorted_dets:
            if not any(d.start < k.end and d.end > k.start for k in kept):
                kept.append(d)
        return kept

    @staticmethod
    def _detect_header_name(text: str, existing: List[PIIDetection]) -> List[PIIDetection]:
        """
        Detect a person name on the first non-empty line of a CV.

        Many CVs open with the candidate's name before any labelled field.
        The heuristic NER only knows Albanian seed names, so non-Albanian
        names (e.g. 'Martin Repa') are missed. This pass adds a fallback:
        if the first non-empty line looks like 'Firstname Lastname' (TitleCase,
        2-4 tokens, no digits, not an existing detection), tag it as PERSON.
        """
        results: List[PIIDetection] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            tokens = stripped.split()
            if not (2 <= len(tokens) <= 4):
                break
            # All tokens TitleCase, no digits, no special chars except hyphens/apostrophes
            if not all(re.match(r"^[A-ZÇËÄ][a-zA-ZçëäÇËÄ'\-]+$", t) for t in tokens):
                break
            start = text.find(stripped)
            end = start + len(stripped)
            # Skip if already covered by an existing detection
            if any(d.start <= start and d.end >= end for d in existing):
                break
            results.append(PIIDetection("PERSON", stripped, start, end, "L0_header"))
            break
        return results

    # ────────────────────────────────────────────────────────────────
    def anonymise(self, text: str) -> AnonymisationResult:
        """
        Run the full pipeline. Returns anonymised text + reversible token map.

        Critical: pii_map must be encrypted before persistence (Always Encrypted
        in Azure SQL or column-level KMS encryption equivalent).
        """
        normalised_text, was_normalised = self._maybe_normalise(text)
        # Preprocess here so anonymise() and detect() work on the same string.
        # detect() also calls _preprocess() internally; since _preprocess is
        # idempotent this is safe. The key point: replacement indices must align
        # with the text that was actually used during detection.
        preprocessed_text = self._preprocess(normalised_text)
        detections = self.detect(normalised_text)

        # Sort by position descending so replacements don't shift indices
        sorted_dets = sorted(detections, key=lambda d: -d.start)

        token_map: Dict[str, str] = {}
        counter: Dict[str, int] = defaultdict(int)
        result = preprocessed_text

        for d in sorted_dets:
            counter[d.entity_type] += 1
            token = f"[{d.entity_type}_{counter[d.entity_type]}]"
            token_map[token] = d.text
            result = result[:d.start] + token + result[d.end:]

        return AnonymisationResult(
            anonymised_text=result,
            pii_map=token_map,
            detections=detections,
            was_normalised=was_normalised,
        )
