"""
Layer 3 — Ollama LLM verification pass (Phase 3).

Built in step 13. Until then, OllamaVerifier raises ConnectionError on
verify() so the pipeline skips it gracefully.
"""
from __future__ import annotations

import json
import logging

import requests
from pydantic import BaseModel, ValidationError

__all__ = ["OllamaVerifier"]

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a PII detection auditor. Your only task is to identify any
personally identifiable information remaining in the provided text.

Look for:
- Names of people (first, last, full)
- Email addresses
- Phone numbers
- Physical addresses
- Organisation names (employers, schools, banks)
- Government ID numbers
- LinkedIn / GitHub profile URLs
- Dates of birth

Some PII has already been replaced with tokens like [PERSON_1] or [EMAIL_2].
Do not flag those — they are already anonymised.

Return ONLY valid JSON in this exact shape:
{"remaining_pii": [
  {"text": "<exact substring>", "type": "<PERSON|EMAIL|PHONE|ADDRESS|ORG|ID_NUMBER|URL|DOB|LOCATION>"}
]}

If no PII remains, return: {"remaining_pii": []}

TEXT TO REVIEW:
<<<
{text}
>>>"""


class _PIIItem(BaseModel):
    text: str
    type: str


class _OllamaResponse(BaseModel):
    remaining_pii: list[_PIIItem]


class OllamaVerifier:
    def __init__(self, ollama_url: str, model: str, timeout: int = 60) -> None:
        self.ollama_url = ollama_url
        self.model = model
        self.timeout = timeout

    def _call(self, prompt: str) -> _OllamaResponse | None:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }
        try:
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "{}")
            return _OllamaResponse.model_validate(json.loads(raw))
        except (requests.RequestException, json.JSONDecodeError, ValidationError) as exc:
            logger.warning("Ollama call failed: %s", exc)
            return None

    def verify(self, partially_anonymised_text: str) -> list[tuple[str, str, int, int, float]]:
        prompt = SYSTEM_PROMPT.format(text=partially_anonymised_text)
        result = self._call(prompt)
        if result is None:
            # Retry once
            result = self._call(prompt)
        if result is None:
            logger.warning("OllamaVerifier: both attempts failed, returning empty")
            return []

        detections: list[tuple[str, str, int, int, float]] = []
        for item in result.remaining_pii:
            idx = partially_anonymised_text.find(item.text)
            if idx == -1:
                continue
            detections.append((item.type, item.text, idx, idx + len(item.text), 0.85))
        return detections
