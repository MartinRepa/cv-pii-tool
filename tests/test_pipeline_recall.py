"""
Regression gate — pipeline recall against ground truth (section 10.6 of CLAUDE.md).

Run with: pytest tests/test_pipeline_recall.py -s

Required thresholds (heuristic-only pipeline):
  - Overall recall ≥ 80%
  - EMAIL recall = 100%
  - PHONE recall ≥ 95%
  - ID_NUMBER recall = 100%
  - OCR-damaged CV recall ≥ 80%
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest

from src.extraction.base import get_extractor
from src.pii.pipeline import PIIPipeline, PIIDetection
from tests.ground_truth import GROUND_TRUTH


# ── Fuzzy match helpers ────────────────────────────────────────────────────────

def _normalise(s: str) -> str:
    s = s.lower().strip()
    # Strip diacritics so ë/e, ç/c, etc. compare equal.
    # PDF extraction often drops Albanian diacritics (fpdf2 font limitation).
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def _token_overlap(a: str, b: str) -> float:
    """Fraction of tokens from `a` that appear in `b` (substring match)."""
    tokens_a = re.split(r"\W+", _normalise(a))
    tokens_a = [t for t in tokens_a if t]
    if not tokens_a:
        return 0.0
    hits = sum(1 for t in tokens_a if t in _normalise(b))
    return hits / len(tokens_a)


def _is_found(expected: str, detections: list[PIIDetection], entity_type: str) -> bool:
    """
    A ground-truth item is found if any detection of the right type matches.
    Match criteria (any one sufficient):
      1. Substring (case-insensitive)
      2. Token overlap ≥ 70%
    """
    exp_norm = _normalise(expected)
    for d in detections:
        if d.entity_type != entity_type:
            continue
        det_norm = _normalise(d.text)
        if exp_norm in det_norm or det_norm in exp_norm:
            return True
        if _token_overlap(expected, d.text) >= 0.70:
            return True
    return False


# ── Canonical entity-type mapping from ground-truth categories ─────────────────

# Ground truth uses categories like PERSONAL_FACT, ID_NUMBER;
# pipeline uses MARITAL / GENDER / AL_NID / PASSPORT.  Map them here.
_GT_TO_PIPELINE: dict[str, list[str]] = {
    "PERSON": ["PERSON"],
    "EMAIL": ["EMAIL"],
    "PHONE": ["PHONE"],
    "URL": ["URL"],
    "ADDRESS": ["ADDRESS"],
    # Domain names (tmc.al etc.) end up as URL detections — treat as equivalent
    "ORG": ["ORG", "URL"],
    "LOCATION": ["LOCATION"],
    "DOB": ["DOB"],
    "ID_NUMBER": ["AL_NID", "PASSPORT", "ID_NUMBER"],
    "PERSONAL_FACT": ["MARITAL", "GENDER", "RELIGION", "FAMILY"],
}


def _find_detections(expected: str, detections: list[PIIDetection], gt_category: str) -> bool:
    pipeline_types = _GT_TO_PIPELINE.get(gt_category, [gt_category])
    return any(_is_found(expected, detections, pt) for pt in pipeline_types)


# ── Main recall computation ────────────────────────────────────────────────────

def _compute_recall(
    fixture_name: str,
    detections: list[PIIDetection],
    gt: dict[str, list[str]],
) -> tuple[int, int, dict[str, tuple[int, int]]]:
    """Returns (found, total, per_category_stats)."""
    total = 0
    found = 0
    per_cat: dict[str, tuple[int, int]] = {}

    for category, items in gt.items():
        cat_total = len(items)
        cat_found = sum(
            1 for item in items
            if _find_detections(item, detections, category)
        )
        total += cat_total
        found += cat_found
        per_cat[category] = (cat_found, cat_total)

    return found, total, per_cat


# ── Fixtures ───────────────────────────────────────────────────────────────────

FIXTURE_DIR = Path(__file__).parent / "fixtures"

FIXTURE_STEMS = list(GROUND_TRUTH.keys())


@pytest.fixture(scope="module")
def pipeline() -> PIIPipeline:
    return PIIPipeline(normalise="auto")


@pytest.fixture(scope="module")
def all_results(pipeline) -> dict[str, tuple[list[PIIDetection], dict]]:
    """Run pipeline over all fixtures once (module-scoped for speed)."""
    results = {}
    for stem in FIXTURE_STEMS:
        # Try known extensions
        cv_file = None
        for ext in (".pdf", ".txt", ".docx"):
            candidate = FIXTURE_DIR / f"{stem}{ext}"
            if candidate.exists():
                cv_file = candidate
                break
        assert cv_file is not None, f"Fixture not found: {stem}"

        extractor = get_extractor(cv_file)
        extraction = extractor.extract(cv_file)
        result = pipeline.anonymise(extraction.text)
        results[stem] = (result.detections, GROUND_TRUTH[stem])
    return results


# ── Per-fixture tests ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("stem", FIXTURE_STEMS)
def test_fixture_recall_above_floor(stem, all_results):
    """Each fixture must achieve ≥ 60% recall individually (floor check)."""
    detections, gt = all_results[stem]
    found, total, _ = _compute_recall(stem, detections, gt)
    recall = found / total if total else 1.0
    assert recall >= 0.60, (
        f"{stem}: recall {recall:.1%} ({found}/{total}) below 60% floor"
    )


# ── Category-level zero-tolerance tests ────────────────────────────────────────

def _collect_category(category: str, all_results) -> tuple[int, int]:
    total = found = 0
    for stem, (detections, gt) in all_results.items():
        if category not in gt:
            continue
        items = gt[category]
        total += len(items)
        found += sum(
            1 for item in items
            if _find_detections(item, detections, category)
        )
    return found, total


def test_email_100_percent(all_results):
    found, total = _collect_category("EMAIL", all_results)
    assert total > 0
    assert found == total, f"EMAIL recall {found}/{total} — must be 100%"


def test_id_number_100_percent(all_results):
    found, total = _collect_category("ID_NUMBER", all_results)
    assert total > 0
    assert found == total, f"ID_NUMBER recall {found}/{total} — must be 100%"


def test_phone_at_least_95_percent(all_results):
    found, total = _collect_category("PHONE", all_results)
    assert total > 0
    recall = found / total
    assert recall >= 0.95, f"PHONE recall {recall:.1%} ({found}/{total}) below 95%"


# ── OCR-damaged fixture test ───────────────────────────────────────────────────

def test_ocr_damaged_cv_recall(all_results):
    stem = "cv_ocr_damaged_sales"
    detections, gt = all_results[stem]
    found, total, _ = _compute_recall(stem, detections, gt)
    recall = found / total if total else 1.0
    assert recall >= 0.80, (
        f"OCR-damaged fixture recall {recall:.1%} ({found}/{total}) below 80%"
    )


# ── GLiNER recall gate (≥ 95%) ────────────────────────────────────────────────

@pytest.fixture(scope="module")
def all_results_gliner(pipeline_full) -> dict[str, tuple[list[PIIDetection], dict]]:
    """Run GLiNER pipeline over all fixtures (module-scoped for speed)."""
    results = {}
    for stem in FIXTURE_STEMS:
        cv_file = None
        for ext in (".pdf", ".txt", ".docx"):
            candidate = FIXTURE_DIR / f"{stem}{ext}"
            if candidate.exists():
                cv_file = candidate
                break
        assert cv_file is not None, f"Fixture not found: {stem}"

        extractor = get_extractor(cv_file)
        extraction = extractor.extract(cv_file)
        result = pipeline_full.anonymise(extraction.text)
        results[stem] = (result.detections, GROUND_TRUTH[stem])
    return results


def test_gliner_overall_recall_gate(all_results_gliner):
    """Gate: overall recall ≥ 95% with GLiNER NER. Prints full report with -s."""
    total_found = 0
    total_items = 0
    rows: list[tuple[str, int, int]] = []

    for stem in FIXTURE_STEMS:
        detections, gt = all_results_gliner[stem]
        found, total, _ = _compute_recall(stem, detections, gt)
        total_found += found
        total_items += total
        rows.append((stem, found, total))

    overall_recall = total_found / total_items if total_items else 1.0

    print("\nPII Recall Report (GLiNER)")
    print("==========================")
    print(f"{'Fixture':<35} {'Items':>6} {'Found':>6} {'Recall':>8}")
    for stem, found, total in rows:
        recall_pct = f"{found/total:.1%}" if total else "N/A"
        print(f"{stem:<35} {total:>6} {found:>6} {recall_pct:>8}")
    print("-" * 57)
    print(f"{'OVERALL':<35} {total_items:>6} {total_found:>6} {overall_recall:.1%}")
    print()
    print(f"GATE: {'PASS' if overall_recall >= 0.95 else 'FAIL'}")

    assert overall_recall >= 0.95, (
        f"GLiNER overall recall {overall_recall:.1%} ({total_found}/{total_items}) below 95% gate"
    )


# ── Overall gate (printed report) ─────────────────────────────────────────────

def test_overall_recall_gate(all_results):
    """Gate: overall recall ≥ 80%. Prints full report when run with -s."""
    total_found = 0
    total_items = 0
    rows: list[tuple[str, int, int]] = []

    for stem in FIXTURE_STEMS:
        detections, gt = all_results[stem]
        found, total, _ = _compute_recall(stem, detections, gt)
        total_found += found
        total_items += total
        rows.append((stem, found, total))

    overall_recall = total_found / total_items if total_items else 1.0

    # Print report
    print("\nPII Recall Report")
    print("=================")
    print(f"{'Fixture':<35} {'Items':>6} {'Found':>6} {'Recall':>8}")
    for stem, found, total in rows:
        recall_pct = f"{found/total:.1%}" if total else "N/A"
        print(f"{stem:<35} {total:>6} {found:>6} {recall_pct:>8}")
    print("-" * 57)
    print(f"{'OVERALL':<35} {total_items:>6} {total_found:>6} {overall_recall:.1%}")
    print()
    print(f"GATE: {'PASS' if overall_recall >= 0.80 else 'FAIL'}")

    assert overall_recall >= 0.80, (
        f"Overall recall {overall_recall:.1%} ({total_found}/{total_items}) below 80% gate"
    )
