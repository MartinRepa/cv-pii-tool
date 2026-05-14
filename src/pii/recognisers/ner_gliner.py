"""
Layer 2 — GLiNER-Multi NER recogniser (Phase 2).

Built in step 12. Until then, GLiNERRecogniser raises ImportError on init
so the pipeline falls back to HeuristicNERRecogniser gracefully.
"""
from __future__ import annotations

__all__ = ["GLiNERRecogniser"]

LABEL_MAP: dict[str, str] = {
    "person name": "PERSON",
    "full name": "PERSON",
    "email address": "EMAIL",
    "phone number": "PHONE",
    "home address": "ADDRESS",
    "street address": "ADDRESS",
    "city": "LOCATION",
    "country": "LOCATION",
    "date of birth": "DOB",
    "nationality": "LOCATION",
    "linkedin profile": "URL",
    "github profile": "URL",
    "id number": "ID_NUMBER",
    "passport number": "ID_NUMBER",
    "organisation": "ORG",
    "company": "ORG",
    "school": "ORG",
    "university": "ORG",
}


class GLiNERRecogniser:
    def __init__(self, model_id: str, threshold: float, labels: list[str]) -> None:
        try:
            from gliner import GLiNER  # type: ignore[import]
            self.model = GLiNER.from_pretrained(model_id)
        except Exception as exc:
            raise ImportError(f"GLiNER not available: {exc}") from exc
        self.threshold = threshold
        self.labels = labels

    def detect(self, text: str) -> list[tuple[str, str, int, int, float]]:
        entities = self.model.predict_entities(text, self.labels, threshold=self.threshold)
        results: list[tuple[str, str, int, int, float]] = []
        for ent in entities:
            matched = ent["text"]
            # Multi-line spans are GLiNER hallucinations — skip them.
            # They span paragraph boundaries and kill narrower correct detections.
            if "\n" in matched:
                continue
            canonical = LABEL_MAP.get(ent["label"].lower(), ent["label"].upper())
            results.append((canonical, matched, ent["start"], ent["end"], ent["score"]))
        return results
