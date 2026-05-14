"""Shared pytest fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.pii.pipeline import PIIPipeline


@pytest.fixture
def pipeline_heuristic() -> PIIPipeline:
    """Pipeline with heuristic NER only, no LLM verify."""
    return PIIPipeline(normalise="auto")


@pytest.fixture(scope="session")
def pipeline_full() -> PIIPipeline:
    """Pipeline with GLiNER NER. Skips if model unavailable or fails to load."""
    from src.pii.recognisers.ner_gliner import LABEL_MAP
    try:
        from src.pii.recognisers.ner_gliner import GLiNERRecogniser
        recogniser = GLiNERRecogniser(
            model_id="urchade/gliner_multi_pii-v1",
            threshold=0.5,
            labels=list(LABEL_MAP.keys()),
        )
    except Exception as exc:
        pytest.skip(f"GLiNER unavailable: {exc}")
    return PIIPipeline(normalise="auto", ner_recogniser=recogniser)


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
