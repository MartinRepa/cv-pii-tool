# AGENTS.md — CV PII Anonymisation Tool (Standalone)

> **For Codex.** Read this file completely before writing any code.
> Build only what is described in the **Scope** section. Do not invent
> features beyond it.

---

## 1. Project Goal

Build a **standalone Python CLI tool** that takes a folder of CVs (PDF, DOCX, TXT)
and produces, for each CV, a set of JSON files containing extracted PII and an
anonymised text version safe to send to a downstream LLM scoring service.

**No cloud services. No database. No external APIs.** Everything runs locally
on the developer's laptop or a single VPS.

This is **Phase 1** of a larger CV screening pipeline. Phase 1 is privacy and
anonymisation only. Future phases (scoring, decisions, dashboard, Zoho integration,
Azure SQL) are explicitly out of scope here.

---

## 2. Scope

### In Scope (DO build)

- File extraction layer (PDF via `pdfplumber`, DOCX via `python-docx`, plain text)
- Three-layer PII detection pipeline:
  - L0: CV text normaliser (handles OCR/spacing damage)
  - L1: Pattern recogniser (regex — emails, phones, IDs, URLs, dates)
  - L2: NER recogniser (multilingual — names, organisations, locations, addresses)
  - L3: LLM verification (local Ollama for contextual PII)
- Pipeline orchestrator with deduplication and token replacement
- Pydantic schemas for all JSON outputs
- CLI runner with argparse
- YAML configuration
- Comprehensive test suite with regression gate
- Six bundled CV fixtures with curated ground truth

### Out of Scope (DO NOT build)

- Scoring (JD match, per-se domain profiling)
- HR decision engine, reason codes, state machine
- HR dashboard (Streamlit / web UI)
- Database integration (SQLite, Azure SQL, any DB)
- Zoho Recruit ingestion
- Azure OpenAI integration
- Email notifications
- Authentication / user management

If you find yourself building something not listed in "In Scope", stop and ask.

---

## 3. Architecture

```
INPUT: a folder containing CV files
       ./input/cv_1.pdf
       ./input/cv_2.docx
       ./input/cv_3.txt

                 │
                 ▼
    ┌────────────────────────────┐
    │  EXTRACTION                │
    │  PDF / DOCX / TXT → text   │
    └─────────────┬──────────────┘
                  ▼
    ┌────────────────────────────┐
    │  L0 NORMALISER             │
    │  (conditional — only if    │
    │   OCR damage detected)     │
    └─────────────┬──────────────┘
                  ▼
    ┌────────────────────────────┐
    │  L1 PATTERN                │ ← regex (emails, phones, IDs)
    └─────────────┬──────────────┘
                  ▼
    ┌────────────────────────────┐
    │  L2 NER                    │ ← GLiNER-Multi (multilingual)
    └─────────────┬──────────────┘
                  ▼
    ┌────────────────────────────┐
    │  L3 LLM VERIFY             │ ← Ollama llama3.1:8b
    └─────────────┬──────────────┘
                  ▼
    ┌────────────────────────────┐
    │  DEDUPLICATION             │
    │  TOKEN REPLACEMENT         │
    └─────────────┬──────────────┘
                  ▼
OUTPUT: ./output/run_<timestamp>/<cv_name>/
        ├── pii_record.json        ← structured PII for HR vault
        ├── anonymised_cv.txt      ← safe to send to LLM scorer
        └── detection_log.json     ← full audit trail

        ./output/run_<timestamp>/batch_summary.json
```

### Critical Rule

**PII never leaves local environment.** This means no `requests.post()` to any
non-localhost URL during PII detection. Ollama must be `http://localhost:11434`.
GLiNER models are downloaded once and cached locally. There is no telemetry.

---

## 4. Folder Structure

Create exactly this structure. No additional folders.

```
cv-pii-tool/
├── README.md
├── AGENTS.md                          ← this file (do not modify)
├── pyproject.toml
├── requirements.txt
├── .gitignore
├── .env.example
│
├── config/
│   └── settings.yaml
│
├── src/
│   ├── __init__.py
│   ├── runner.py                      ← CLI entry point
│   │
│   ├── pii/
│   │   ├── __init__.py
│   │   ├── normaliser.py              ← provided in section 9
│   │   ├── pipeline.py                ← provided in section 9 (extend it)
│   │   ├── schemas.py                 ← BUILD THIS
│   │   └── recognisers/
│   │       ├── __init__.py            ← provided in section 9
│   │       ├── pattern.py             ← provided in section 9
│   │       ├── ner_heuristic.py       ← provided in section 9 (fallback)
│   │       ├── ner_gliner.py          ← BUILD THIS
│   │       ├── llm_verify.py          ← BUILD THIS
│   │       └── personal_facts.py      ← provided in section 9
│   │
│   └── extraction/
│       ├── __init__.py
│       ├── base.py                    ← BUILD THIS
│       ├── pdf.py                     ← BUILD THIS
│       ├── docx.py                    ← BUILD THIS
│       └── text.py                    ← BUILD THIS
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                    ← BUILD THIS
│   ├── ground_truth.py                ← BUILD THIS (curated PII per fixture)
│   ├── test_normaliser.py             ← BUILD THIS
│   ├── test_recognisers.py            ← BUILD THIS
│   ├── test_pipeline_recall.py        ← BUILD THIS (regression gate)
│   └── fixtures/
│       └── (6 CV files — see section 10)
│
├── input/
│   └── .gitkeep
│
└── output/
    └── .gitkeep
```

---

## 5. JSON Output Contracts

These are the **source of truth** for what the tool produces. The Pydantic
models in `src/pii/schemas.py` must produce exactly these JSON shapes.

### 5.1 `pii_record.json` — One Per CV

```json
{
  "candidate_fingerprint": "a3f5b8c9d4e2f1a7b8c9d4e2f1a7b8c9d4e2f1a7b8c9d4e2f1a7b8c9d4e2f1a7",
  "source_file": "arber_hoxhaj_cv.pdf",
  "extraction_quality": 0.97,
  "was_normalised": false,
  "processed_at": "2025-05-09T14:32:11Z",
  "pipeline_version": "0.1.0",

  "pii_fields": {
    "full_name": "Arbër-Luan Hoxhaj",
    "emails": [
      "arber.hoxhaj1989@gmail.com",
      "a.hoxhaj@finance-consult.al"
    ],
    "phones": ["+355 69 782 4411", "00355 68 332 1900"],
    "addresses": ["Rruga \"Myslym Shyri\", Pallati Edil-AL, Shkalla 2, Ap. 14"],
    "linkedin": "linkedin.com/in/arber-luan-hoxhaj",
    "github": null,
    "date_of_birth": "1989-02-17",
    "place_of_birth": "Kukës",
    "nationality": "Albanian",
    "id_numbers": [
      {"type": "AL_NID", "value": "J90217045L"},
      {"type": "PASSPORT", "value": "BA4589201"}
    ],
    "sensitive_attributes": {
      "marital_status": "Married",
      "gender": "Male",
      "religion": null
    }
  },

  "references_in_cv": [
    {
      "name": "Ilir Metaçi",
      "phone": "+355 67 908 1122",
      "email": "ilir.metaci@ufbank.al"
    }
  ]
}
```

**Notes:**
- `candidate_fingerprint` = SHA-256 of (normalised_email + normalised_phone + dob_iso). Falls back to SHA-256 of full CV text if those fields aren't extractable.
- `extraction_quality` = float 0.0–1.0 from the extraction layer. Below 0.4 = warn.
- `was_normalised` = whether L0 normaliser was applied.
- `processed_at` = ISO 8601 UTC.
- `pipeline_version` from `pyproject.toml`.
- All fields are nullable except `candidate_fingerprint`, `source_file`, `processed_at`, `pipeline_version`, `was_normalised`.

### 5.2 `anonymised_cv.txt` — One Per CV

Plain text with PII replaced by typed, indexed tokens:

```
[PERSON_1]
Senior Relationship Manager / SME Banking Officer

PERSONAL INFORMATION
Address: [ADDRESS_1]
Phone: [PHONE_1]
Alternative phone: [PHONE_2]
Email: [EMAIL_1]
Work email: [EMAIL_2]
LinkedIn: [URL_1]
Date of Birth: [DOB_1]
Place of Birth: [LOCATION_1], [LOCATION_2]
...
```

**Token format:** `[<ENTITY_TYPE>_<index>]` where index is 1-based per entity type.

### 5.3 `detection_log.json` — One Per CV

```json
{
  "candidate_fingerprint": "a3f5b8c9d4e2...",
  "source_file": "arber_hoxhaj_cv.pdf",
  "processed_at": "2025-05-09T14:32:11Z",
  "total_detections": 47,

  "by_layer": {
    "L0_normaliser": {"applied": false, "damage_indicators": {"single_letter_density": 0.02, "digit_pair_density": 0.5}},
    "L1_pattern": 18,
    "L2_ner": 23,
    "L3_llm_verify": 6
  },

  "by_entity_type": {
    "PERSON": 3, "EMAIL": 4, "PHONE": 4,
    "ADDRESS": 1, "ID_NUMBER": 2, "ORG": 11,
    "LOCATION": 6, "URL": 1, "DOB": 1
  },

  "low_confidence_flags": [
    {
      "entity_type": "PERSON",
      "text": "Mirela Kodra",
      "confidence": 0.72,
      "reason": "Name not in seed list, weak NER signal"
    }
  ],

  "detections": [
    {
      "entity_type": "PERSON",
      "text": "Arbër-Luan Hoxhaj",
      "start": 0,
      "end": 17,
      "layer": "L2_ner",
      "confidence": 0.98,
      "token_replacement": "[PERSON_1]"
    }
  ]
}
```

### 5.4 `batch_summary.json` — One Per Run

```json
{
  "batch_id": "run_2025-05-09_14-32-11",
  "started_at": "2025-05-09T14:32:11Z",
  "finished_at": "2025-05-09T14:33:48Z",
  "duration_seconds": 97,
  "pipeline_version": "0.1.0",
  "config_hash": "f4a8c9d4e2f1a7b8",

  "cvs_total": 12,
  "cvs_processed": 11,
  "cvs_failed": 1,

  "average_extraction_quality": 0.91,
  "ocr_damaged_count": 1,
  "low_confidence_review_required": 2,
  "total_pii_detected": 487,

  "by_entity_type_total": {
    "PERSON": 18, "EMAIL": 28, "PHONE": 31, "ADDRESS": 12,
    "ID_NUMBER": 9, "ORG": 67, "LOCATION": 41, "URL": 11, "DOB": 8
  },

  "failures": [
    {
      "file": "corrupted.pdf",
      "stage": "extraction",
      "error": "PDF is password-protected"
    }
  ],

  "per_cv": [
    {
      "file": "arber_hoxhaj_cv.pdf",
      "fingerprint": "a3f5b8c9...",
      "extraction_quality": 0.97,
      "was_normalised": false,
      "total_detections": 47,
      "low_confidence_count": 0,
      "duration_ms": 4231,
      "status": "success"
    }
  ]
}
```

---

## 6. CLI Specification

```bash
python -m src.runner --input <input_dir> --output <output_dir> [options]
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--input PATH` | `./input` | Folder of CV files |
| `--output PATH` | `./output` | Where results land |
| `--config PATH` | `config/settings.yaml` | Override config |
| `--normalise MODE` | `auto` | `auto` \| `always` \| `never` |
| `--ner MODE` | `gliner` | `gliner` \| `heuristic` (fallback) |
| `--llm-verify` | True | Disable with `--no-llm-verify` |
| `--ollama-url URL` | `http://localhost:11434` | |
| `--ollama-model NAME` | `llama3.1:8b` | |
| `--confidence-threshold FLOAT` | 0.85 | Below this → low_confidence_flag |
| `--quiet` | False | Reduce log verbosity |
| `--dry-run` | False | Run pipeline but write no files |

**Exit codes:**
- 0 — all CVs processed successfully
- 1 — some CVs failed (see `batch_summary.json`)
- 2 — fatal error (config invalid, no CVs found, etc.)

**Console output (default verbosity):**

```
PII Anonymisation Tool v0.1.0
Loading GLiNER model... done (2.3s)
Connecting to Ollama at http://localhost:11434... ok

Processing 6 CVs from ./input/
  ✓ astrit_patozi.pdf      | quality 0.98 | 27 detections
  ✓ qerime_dallku.pdf      | quality 0.97 | 24 detections
  ⚠ eliona_shkurti.txt     | quality 0.71 | 39 detections | NORMALISED
  ✓ arber_hoxhaj.txt       | quality 1.00 | 47 detections
  ✓ blerina_koci.pdf       | quality 0.96 | 31 detections
  ✓ zgjatje_ndregjoni.pdf  | quality 0.95 | 22 detections

Done. 6/6 succeeded. Output: ./output/run_2025-05-09_14-32-11/
```

---

## 7. Configuration File

`config/settings.yaml`:

```yaml
pipeline_version: "0.1.0"

normaliser:
  mode: auto                          # auto | always | never
  ocr_damage_thresholds:
    single_letter_density: 0.08
    digit_pair_density: 4.0

recognisers:
  pattern:
    enabled: true
  ner:
    backend: gliner                   # gliner | heuristic
    gliner:
      model_id: "urchade/gliner_multi_pii-v1"
      threshold: 0.5
      labels:
        - "person name"
        - "full name"
        - "email address"
        - "phone number"
        - "home address"
        - "street address"
        - "city"
        - "country"
        - "date of birth"
        - "nationality"
        - "linkedin profile"
        - "github profile"
        - "id number"
        - "passport number"
        - "organisation"
        - "company"
        - "school"
        - "university"
  llm_verify:
    enabled: true
    ollama_url: "http://localhost:11434"
    model: "llama3.1:8b"
    timeout_seconds: 60
    max_retries: 2
  personal_facts:
    enabled: true

deduplication:
  strategy: longest_match              # longest_match | first_seen

output:
  write_anonymised_text: true
  write_pii_record: true
  write_detection_log: true
  pretty_print_json: true

extraction:
  pdf:
    use_layout_aware: true
  ocr_fallback:
    enabled: false                     # require explicit opt-in
    tesseract_lang: "sqp+eng+ita"

confidence:
  global_threshold: 0.85
  per_layer_minimum:
    L1_pattern: 0.99                   # regex matches always high confidence
    L2_ner: 0.5
    L3_llm_verify: 0.7
```

---

## 8. Coding Conventions

Follow these strictly:

- **Python 3.11+** — use modern syntax (`X | Y` for unions, `list[str]` not `List[str]`).
- **Type hints everywhere** — every function signature, every dataclass field.
- **Pydantic v2** for all data models. Use `BaseModel`, `Field`, `model_dump()`, `model_validate()`.
- **`pathlib.Path` everywhere** — never use string paths.
- **`structlog` for logging** — never `print()`. Configure once in `runner.py`.
- **`pytest` for tests** — no `unittest`. Use fixtures, parametrize where useful.
- **No global state.** Pass dependencies explicitly. Pipeline takes config as constructor arg.
- **Adapter pattern** for external services (Ollama, GLiNER): abstract base class + concrete impl. Makes testing trivial.
- **Fail loudly, fail early.** Validate config at startup. Refuse to run on malformed input.
- **Idempotent runs.** Running twice on the same input must produce byte-identical output (modulo timestamps).

---

## 9. Existing Code (Already Built — Drop In As-Is)

The following modules are battle-tested against 6 real Albanian CVs.
Drop them into the project unchanged. **Do not rewrite them.**

### 9.1 `src/pii/normaliser.py`

```python
"""
CV Text Normaliser
==================

Pre-processes raw CV text to repair OCR/spacing damage commonly found in
real-world CV uploads (Europass templates, scanned PDFs, copy-paste from
formatted documents).

Why this matters
----------------
Without normalisation, a CV with letter-spaced names like "E l i o n a"
or broken emails like "user . name @ g mail . com" causes 78%+ PII leak
to downstream LLM scoring. With normalisation, that drops to <12%.

Public API
----------
    normalise_cv_text(text: str) -> str
        Apply all normalisation passes. Idempotent.

    is_ocr_damaged(text: str) -> bool
        Heuristic detector. Use to apply normaliser conditionally.
"""
import re
from typing import Final

__all__ = ["normalise_cv_text", "is_ocr_damaged"]


# ──────────────────────────────────────────────────────────────────────
# OCR damage detection
# ──────────────────────────────────────────────────────────────────────
def is_ocr_damaged(text: str, sample_size: int = 2000) -> bool:
    """
    Heuristic: detect if a CV has letter/digit spacing damage typical of
    bad OCR or copy-paste from formatted PDFs.

    Returns True if either:
      - density of single-letter tokens is > 8%
      - density of single-digit tokens (in 'digit space digit' patterns) is > 4%
    """
    sample = text[:sample_size]
    tokens = sample.split()
    if not tokens:
        return False

    single_letter_count = sum(1 for t in tokens if len(t) == 1 and t.isalpha())
    single_letter_density = single_letter_count / len(tokens)

    digit_pair_count = len(re.findall(r"\d \d", sample))
    digit_pair_density = digit_pair_count / max(len(sample.split("\n")), 1)

    return single_letter_density > 0.08 or digit_pair_density > 4.0


# ──────────────────────────────────────────────────────────────────────
# Normalisation passes
# ──────────────────────────────────────────────────────────────────────
def _merge_spaced_letters(text: str) -> str:
    """
    Merge sequences of single letters separated by single spaces into words.
    Multiple spaces are preserved as word boundaries.

    Examples:
        'E l i o n a'              → 'Eliona'
        'A r d i a n   L e s k a'  → 'Ardian Leska'   (preserves multi-space)
        'Normal sentence'          → 'Normal sentence' (untouched)
    """
    def _merge(m: re.Match) -> str:
        s = m.group(0)
        # Collapse only single spaces between letters; preserve multi-space gaps
        return re.sub(r"(?<=[A-Za-zÇËçëÄä]) (?=[A-Za-zÇËçëÄä])", "", s)

    pattern = r"\b(?:[A-Za-zÇËçëÄä]\s+){2,}[A-Za-zÇËçëÄä]\b"
    return re.sub(pattern, _merge, text)


def _fix_broken_emails(text: str) -> str:
    """
    Reconstruct emails fragmented by spaces.

    Example:
        'eliona . shk urti @ g mail . com' → 'eliona.shkurti@gmail.com'
    """
    def _try_fix(m: re.Match) -> str:
        candidate = m.group(0)
        cleaned = re.sub(r"\s+", "", candidate)
        if re.match(r"^[\w.\-]+@[\w.\-]+\.[a-z]{2,}$", cleaned, re.IGNORECASE):
            return cleaned
        return candidate

    pattern = (
        r"[\w][\w\s.\-]*?"
        r"\s*@\s*"
        r"[\w][\w\s\-]*?"
        r"\s*\.\s*"
        r"[\w][\w\s\-]*?"
        r"(?:\s*\.\s*[\w]+)*"
        r"(?=[\s,;]|$)"
    )
    return re.sub(pattern, _try_fix, text)


def _merge_spaced_digits(text: str) -> str:
    """
    Collapse whitespace within digit sequences and re-introduce structural
    spacing for known formats (Albanian phones, dates, IDs, passports).
    """
    # Strip "+ " before digits
    text = re.sub(r"\+\s+(?=\d)", "+", text)

    # Iteratively merge single-space-separated digits
    prev = None
    cur = text
    for _ in range(20):
        if prev == cur:
            break
        prev = cur
        cur = re.sub(r"(\d) (\d)", r"\1\2", cur)
    text = cur

    # Multi-space-separated digits (continuing the merge for longer gaps)
    prev = None
    cur = text
    for _ in range(20):
        if prev == cur:
            break
        prev = cur
        cur = re.sub(r"(\d)\s{2,3}(\d)", r"\1\2", cur)
    text = cur

    # Strip "(0)" artifacts in international Albanian numbers: +355 (0) 67 → +355 67
    text = re.sub(r"\+355\s*\(\s*0\s*\)\s*", "+355 ", text)

    # Re-introduce structural spacing — Albanian mobile +355 6X XXX XXXX
    text = re.sub(r"\+355(\d{2})(\d{3})(\d{4})\b", r"+355 \1 \2 \3", text)
    text = re.sub(r"\b(0[6-9]\d)(\d{3})(\d{4})\b", r"\1 \2 \3", text)

    # Date slashes: '04 / 09 / 1996' → '04/09/1996'
    text = re.sub(r"(\d{1,4})\s*/\s*(\d{1,4})\s*/\s*(\d{1,4})", r"\1/\2/\3", text)

    # Albanian Personal ID: K 60904123 M → K60904123M
    text = re.sub(r"\b([A-Z])\s*(\d{6,9})\s*([A-Z])\b", r"\1\2\3", text)

    # Passport: 'B A 1193308' → 'BA1193308'
    text = re.sub(r"\b([A-Z])\s+([A-Z])\s+(\d{6,9})\b", r"\1\2\3", text)
    text = re.sub(r"\b([A-Z]{2})\s+(\d{6,9})\b", r"\1\2", text)

    # Phone with dashes: '068 - 227 - 9810' → '068-227-9810'
    text = re.sub(r"(\d)\s*-\s*(\d)", r"\1-\2", text)

    return text


def _fix_broken_urls(text: str) -> str:
    """Reconstruct URLs broken by spaces (LinkedIn, GitHub)."""
    patterns: Final = [
        (r"linked\s*in\s*\.\s*com\s*/\s*in\s*/\s*[\w\s\-]+",
         lambda m: re.sub(r"\s+", "", m.group(0))),
        (r"git\s*hub\s*\.\s*com\s*/\s*[\w\s\-/]+",
         lambda m: re.sub(r"\s+", "", m.group(0))),
    ]
    for pat, fixer in patterns:
        text = re.sub(pat, fixer, text, flags=re.IGNORECASE)
    return text


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────
def normalise_cv_text(text: str) -> str:
    """
    Apply the full normalisation pipeline.

    Order matters:
      1. Emails (use @ as anchor — easiest to identify)
      2. URLs (specific keywords are anchors)
      3. Digits (phones, IDs, dates)
      4. Letters (most aggressive — apply last)
    """
    text = _fix_broken_emails(text)
    text = _fix_broken_urls(text)
    text = _merge_spaced_digits(text)
    text = _merge_spaced_letters(text)
    return text

```

### 9.2 `src/pii/recognisers/__init__.py`

```python
"""PII recogniser implementations — one per layer."""
from .pattern import PatternRecogniser
from .ner_heuristic import HeuristicNERRecogniser
from .personal_facts import PersonalFactsRecogniser

__all__ = [
    "PatternRecogniser",
    "HeuristicNERRecogniser",
    "PersonalFactsRecogniser",
]

```

### 9.3 `src/pii/recognisers/pattern.py`

```python
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

```

### 9.4 `src/pii/recognisers/ner_heuristic.py`

```python
"""
Layer 2 — Heuristic NER recogniser.

Simulates GLiNER-Multi for the test environment. In production this module
is replaced by a real multilingual NER:

    from gliner import GLiNER
    model = GLiNER.from_pretrained("urchade/gliner_multi_pii-v1")
    entities = model.predict_entities(text, labels=[
        "person name", "home address", "city", "organisation", ...
    ])

This implementation uses curated lists + heuristics, which is sufficient
for regression testing but should NOT be used in production. Production
needs the actual multilingual NER for unseen names and contextual
understanding.
"""
import re
from typing import List, Tuple

__all__ = ["HeuristicNERRecogniser"]


class HeuristicNERRecogniser:
    """
    Fallback NER for environments where the GLiNER model can't be loaded.

    Catches:
      - Albanian first/last names from a curated seed list
      - Location names from a static city list
      - Address blocks anchored on Albanian street keywords
      - Organisations with Albanian/EU legal-form suffixes
      - Education institutions
    """

    # Albanian + regional cities (extend as needed)
    AL_CITIES = {
        "Tirana", "Tiranë", "Tirane", "Durrës", "Durres", "Vlorë", "Vlore",
        "Shkodër", "Shkoder", "Elbasan", "Korçë", "Korce", "Fier", "Berat",
        "Lushnjë", "Pogradec", "Kavajë", "Gjirokastër", "Sarandë", "Saranda",
        "Koplik", "Lezhë", "Kukës", "Përmet", "Permet", "Bual", "Tropojë",
        "Prishtinë", "Pristina", "Prizren", "Peja",
        "Albania", "Albanian", "Shqipëri", "Shqiperi",
        # Tirana neighbourhoods (frequently appear in CVs)
        "Kombinat", "Astir", "Zogu i Zi", "Komuna e Parisit", "Blloku",
        "21 Dhjetori", "Don Bosko", "Lapraka",
    }

    AL_ADDRESS_TOKENS = {
        "rruga", "rr.", "rr ", "pallati", "pall.", "apartamenti", "ap.",
        "ap ", "lagjja", "lagja", "lagje", "njësia", "njesia", "blloku",
        "shesh", "sheshi", "kati", "shkalla", "hyrja",
    }

    AL_FIRST_NAMES = {
        "astrit", "qerime", "blerina", "zgjatje", "ardit", "besnik", "bujar",
        "dritan", "edmond", "endrit", "enver", "fatmir", "florian", "gentian",
        "ilir", "jorgo", "klodian", "luan", "mentor", "petrit", "saimir",
        "agim", "albert", "alfred", "altin", "armand", "arben", "arta",
        "blerta", "diana", "drita", "edi", "elona", "ermal", "fatos",
        "festim", "gentiana", "halil", "ilirjana", "klodiana", "lindita",
        "manjola", "merita", "miranda", "nora", "olta", "pranvera", "rezarta",
        "sara", "shpresa", "valbona", "vera", "vjollca", "yllka",
        "eliona", "ardian", "migena", "arber", "arbër", "mirela",
    }

    AL_LAST_NAMES = {
        "patozi", "dallku", "koçi", "koci", "ndregjoni", "hoxha", "hoxhaj",
        "krasniqi", "berisha", "kelmendi", "shehu", "sula", "frashëri",
        "frasheri", "gjoni", "marku", "kola", "luka", "leka", "leska",
        "noli", "rexhepi", "selmani", "tafa", "veliu", "xhafa", "ymeri",
        "zeneli", "shkurti", "braho", "metaçi", "metaci", "kodra",
    }

    ORG_SUFFIXES = [
        r"sh\.?p\.?k\.?", r"sh\.?a\.?", r"L\.?L\.?C\.?", r"Ltd\.?",
        r"Inc\.?", r"S\.?p\.?A\.?", r"GmbH",
    ]

    KNOWN_ORG_KEYWORDS = {
        # Banking / finance / telecoms — common employers
        "bank", "banka", "telecom", "albtelecom", "credins", "raiffeisen",
        "intesa", "abi", "tirana", "alpha", "bkt", "kombetare", "kombëtare",
        "softec", "century", "imobiliare", "consult", "konsult", "solutions",
        "albania", "shqiperi", "shqipëri", "albasoft", "ict",
        # Government / public sector
        "bashkia", "ministria", "ministry", "qkb", "ashk", "drejtoria",
        "spitali", "spitalit", "prefektura",
    }

    EDU_KEYWORDS = {
        "university", "universiteti", "polytechnic", "politechnic",
        "gjimnazi", "shkolla", "fakulteti", "akademia", "instituti",
        "school", "academy", "institute", "college", "kolegji",
    }

    def detect(self, text: str) -> List[Tuple[str, str, int, int]]:
        results: List[Tuple[str, str, int, int]] = []

        # Cities → LOCATION
        for city in self.AL_CITIES:
            for m in re.finditer(rf"\b{re.escape(city)}\b", text):
                results.append(("LOCATION", m.group(), m.start(), m.end()))

        # Address blocks
        addr_pattern = re.compile(
            r"\b(?:Rruga|Rr\.?)\s+[^\n,]+(?:,\s*[^\n,]+){0,4}",
            re.IGNORECASE,
        )
        for m in addr_pattern.finditer(text):
            results.append(("ADDRESS", m.group().strip(), m.start(), m.end()))

        # Person names — heuristic: TitleCase pair where one token is in
        # Albanian first/last name list. Compound names (hyphenated) supported.
        name_pattern = re.compile(
            r"\b[A-ZÇËÄ][a-zçëä]+(?:[-'][A-ZÇËÄ][a-zçëä]+)?"
            r"(?:\s+[A-ZÇËÄ][a-zçëä']+){1,3}\b"
        )
        for m in name_pattern.finditer(text):
            tokens_lower = [t.lower().rstrip("'") for t in re.split(r"[\s\-]", m.group())]
            if any(t in self.AL_FIRST_NAMES for t in tokens_lower) or \
               any(t in self.AL_LAST_NAMES for t in tokens_lower):
                results.append(("PERSON", m.group(), m.start(), m.end()))

        # Organisations — legal-form suffix
        for suffix in self.ORG_SUFFIXES:
            org_pat = re.compile(rf"\b[A-Z][\w\-&.\s]{{2,40}}\s+{suffix}", re.IGNORECASE)
            for m in org_pat.finditer(text):
                results.append(("ORG", m.group().strip(), m.start(), m.end()))

        # Organisations — TitleCase with known keyword
        title_phrase = re.compile(
            r"\b[A-Z][\w&]{2,}(?:\s+(?:[A-Z][\w&]{1,}|[a-z]{2,3}\.?|of|the|de|al))?"
            r"(?:\s+[A-Z][\w&]{2,})?(?:\s+[A-Z][\w&]{2,})?\b"
        )
        for m in title_phrase.finditer(text):
            phrase = m.group()
            tokens = phrase.lower().split()
            if any(t.rstrip(".,") in self.KNOWN_ORG_KEYWORDS for t in tokens):
                # Skip if it looks like an address line
                if not any(addr in phrase.lower() for addr in ["rruga", "pall.", "pallati"]):
                    results.append(("ORG", phrase, m.start(), m.end()))

        # Education institutions
        for kw in self.EDU_KEYWORDS:
            edu_pat = re.compile(
                rf"\b(?:{kw})\s+(?:of\s+|i\s+|e\s+|'[^']+'\s*)?[\w\s,\-']{{3,80}}?"
                rf"(?=\s*[—,|\n])",
                re.IGNORECASE,
            )
            for m in edu_pat.finditer(text):
                value = m.group().strip().rstrip(",|—-")
                if len(value) > 8:
                    results.append(("ORG", value, m.start(), m.end()))

        return results

```

### 9.5 `src/pii/recognisers/personal_facts.py`

```python
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

```

### 9.6 `src/pii/pipeline.py`

```python
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

    def __init__(self, normalise: str = "auto"):
        """
        Args:
            normalise: 'auto' (only if damaged), 'always', or 'never'
        """
        self.pattern = PatternRecogniser()
        self.ner = HeuristicNERRecogniser()
        self.personal = PersonalFactsRecogniser()
        self.normalise_mode = normalise

    # ────────────────────────────────────────────────────────────────
    def _preprocess(self, text: str) -> str:
        """Fix common PDF extraction artifacts (e.g. 'user @gmail')."""
        # Email split by space around @
        text = re.sub(r"(\w)\s*\n?\s*@\s*\n?\s*(\w)", r"\1@\2", text)
        # URL split mid-path
        text = re.sub(r"(linkedin\.com|github\.com)/\s*\n\s*(\w)", r"\1/\2", text)
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
            all_detections.append(PIIDetection(ent, val, s, e, "L1_pattern"))
        for ent, val, s, e in self.ner.detect(text):
            all_detections.append(PIIDetection(ent, val, s, e, "L2_ner"))
        for ent, val, s, e in self.personal.detect(text):
            all_detections.append(PIIDetection(ent, val, s, e, "L3_personal"))

        return self._dedupe(all_detections)

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

    # ────────────────────────────────────────────────────────────────
    def anonymise(self, text: str) -> AnonymisationResult:
        """
        Run the full pipeline. Returns anonymised text + reversible token map.

        Critical: pii_map must be encrypted before persistence (Always Encrypted
        in Azure SQL or column-level KMS encryption equivalent).
        """
        normalised_text, was_normalised = self._maybe_normalise(text)
        detections = self.detect(normalised_text)

        # Sort by position descending so replacements don't shift indices
        sorted_dets = sorted(detections, key=lambda d: -d.start)

        token_map: Dict[str, str] = {}
        counter: Dict[str, int] = defaultdict(int)
        result = normalised_text

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

```

---

## 10. What You Must Build

### 10.1 `src/pii/schemas.py`

Pydantic v2 models matching the JSON contracts in section 5.

Required classes:

- `IDNumber(BaseModel)` — fields: `type: Literal["AL_NID","PASSPORT","NIPT","TAX_ID","OTHER"]`, `value: str`
- `SensitiveAttributes(BaseModel)` — `marital_status: str | None`, `gender: str | None`, `religion: str | None`
- `PIIFields(BaseModel)` — all fields per section 5.1
- `Reference(BaseModel)` — `name: str | None`, `phone: str | None`, `email: str | None`
- `PIIRecord(BaseModel)` — top-level for `pii_record.json`
- `LayerStats(BaseModel)` — applied/count per layer
- `LowConfidenceFlag(BaseModel)`
- `Detection(BaseModel)` — single detection in audit log
- `DetectionLog(BaseModel)` — top-level for `detection_log.json`
- `PerCVSummary(BaseModel)`, `Failure(BaseModel)`, `BatchSummary(BaseModel)`

All models use `model_config = ConfigDict(extra="forbid")` to fail on unknown fields.

JSON serialisation: use `model_dump_json(indent=2)` for pretty output.
Datetimes: ISO 8601 UTC with `Z` suffix.

### 10.2 `src/extraction/`

- `base.py` — abstract `Extractor` class with `extract(path: Path) -> ExtractionResult`. `ExtractionResult` is a dataclass with `text: str`, `quality: float`, `metadata: dict`.
- `pdf.py` — `PDFExtractor` using `pdfplumber`. Computes quality score from char density × dictionary match × layout consistency.
- `docx.py` — `DOCXExtractor` using `python-docx`. Reads paragraphs + tables.
- `text.py` — `TextExtractor` for `.txt` files. Quality always 1.0 if non-empty.
- Dispatcher function `get_extractor(path: Path) -> Extractor` based on suffix.

Quality score components (each 0–1, multiplicative):
- char_density: `len(text.strip()) / file_size_bytes` normalised to a sensible range
- dictionary_match: fraction of tokens that look like real words (basic check)
- layout_score: 1.0 unless text is heavily fragmented (lots of single-character lines)

### 10.3 `src/pii/recognisers/ner_gliner.py`

GLiNER-Multi wrapper. Same interface as `HeuristicNERRecogniser` (the `detect` method).

```python
class GLiNERRecogniser:
    def __init__(self, model_id: str, threshold: float, labels: list[str]):
        from gliner import GLiNER
        self.model = GLiNER.from_pretrained(model_id)
        self.threshold = threshold
        self.labels = labels

    def detect(self, text: str) -> list[tuple[str, str, int, int, float]]:
        # Returns (entity_type, text, start, end, confidence)
        # Map GLiNER labels to canonical types: "person name" → "PERSON", etc.
        ...
```

Label mapping (GLiNER label → canonical entity type):

| GLiNER label | Canonical |
|---|---|
| person name, full name | PERSON |
| email address | EMAIL |
| phone number | PHONE |
| home address, street address | ADDRESS |
| city, country | LOCATION |
| date of birth | DOB |
| nationality | LOCATION |
| linkedin profile, github profile | URL |
| id number, passport number | ID_NUMBER |
| organisation, company, school, university | ORG |

The pipeline must work with **either** GLiNER **or** the heuristic NER —
configurable via settings.yaml. If GLiNER fails to load (no model, no torch),
log a warning and fall back to heuristic.

### 10.4 `src/pii/recognisers/llm_verify.py`

Ollama wrapper. Sends partially-anonymised text and asks for any remaining PII.

```python
class OllamaVerifier:
    def __init__(self, ollama_url: str, model: str, timeout: int = 60):
        self.ollama_url = ollama_url
        self.model = model
        self.timeout = timeout

    def verify(self, partially_anonymised_text: str) -> list[tuple[str, str, int, int, float]]:
        # Returns same shape as other recognisers
        ...
```

System prompt template (use this verbatim, no creativity):

```
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
{{"remaining_pii": [
  {{"text": "<exact substring>", "type": "<PERSON|EMAIL|PHONE|ADDRESS|ORG|ID_NUMBER|URL|DOB|LOCATION>"}}
]}}

If no PII remains, return: {{"remaining_pii": []}}

TEXT TO REVIEW:
<<<
{text}
>>>
```

Use Ollama's `format: "json"` mode to enforce JSON output. Validate the response
against a Pydantic schema. On parse failure, retry once with a stricter prompt;
if it still fails, log warning and return empty list (graceful degradation —
never crash the pipeline because of LLM flakiness).

### 10.5 `src/runner.py`

The CLI entry point. Wires everything together.

Responsibilities:
1. Parse args via `argparse`
2. Load and validate config (`pyyaml` + Pydantic config model)
3. Configure `structlog`
4. Create timestamped run folder under `--output`
5. Discover CV files in `--input` (`.pdf`, `.docx`, `.txt` recursively)
6. For each CV: extract → pipeline.anonymise() → write 3 output files
7. Aggregate `batch_summary.json`
8. Print human-readable summary to stdout
9. Exit with proper code

Use `concurrent.futures.ProcessPoolExecutor` for parallelism (default workers = `min(4, cpu_count())`). Disable with `--workers 1` for debugging.

### 10.6 Test Suite

**`tests/conftest.py`** — fixtures:
- `pipeline_heuristic` — pipeline configured with heuristic NER, no LLM verify
- `pipeline_full` — pipeline with GLiNER + LLM verify (skip if model not available)
- `fixtures_dir` — path to `tests/fixtures/`

**`tests/ground_truth.py`** — exhaustive PII ground truth per fixture. Provided in section 11 below.

**`tests/test_normaliser.py`** — unit tests for each normaliser function:
- spaced letters merge correctly
- spaced digits merge correctly
- broken emails reconstruct
- multi-space gaps preserved as word boundaries
- normal text untouched

**`tests/test_recognisers.py`** — unit tests per recogniser:
- pattern: emails, Albanian phones (all formats), passport, NID, IBAN
- heuristic NER: known names, cities, addresses
- personal facts: marital status, gender variants

**`tests/test_pipeline_recall.py`** — the regression gate.

For each fixture: run pipeline, compute per-category recall against ground truth.

**Required pass thresholds:**

| Metric | Threshold |
|---|---|
| Overall recall (heuristic only) | ≥ 80% |
| Overall recall (with GLiNER) | ≥ 95% |
| Overall recall (with GLiNER + LLM) | ≥ 98% |
| EMAIL recall | 100% (zero tolerance) |
| PHONE recall | ≥ 95% |
| ID_NUMBER recall | 100% (zero tolerance) |
| OCR-damaged CV recall | ≥ 80% |

Test must produce a recall report (printed to stdout when run with `pytest -s`):

```
PII Recall Report
=================
Fixture                     Items  Found  Recall
arber_hoxhaj.txt              26     25    96.2%
eliona_shkurti.txt            32     30    93.8%
...
─────────────────────────────────────────────────
OVERALL                      113    109    96.5%

GATE: PASS
```

---

## 11. Test Fixtures

Six fixtures must be placed in `tests/fixtures/`:

1. `cv_clean_backend.pdf` — Astrit Patozi (.NET dev)
2. `cv_clean_it_support.pdf` — Qerime Dallku
3. `cv_clean_sales.pdf` — Blerina Koçi (Europass single-column)
4. `cv_clean_bank_teller.pdf` — Zgjatje Ndregjoni (Europass two-column)
5. `cv_dense_sme_banker.txt` — Arbër-Luan Hoxhaj (PII-dense, 26 items)
6. `cv_ocr_damaged_sales.txt` — Eliona Shkurti (OCR-damaged formatting)

The user will provide these files. Use the ground truth definitions in
`tests/ground_truth.py` (build that file from these specs):

### Ground Truth — Fixture 1: cv_clean_backend.pdf
```python
"cv_clean_backend": {
    "PERSON": ["Astrit Patozi"],
    "EMAIL": ["astrit.patozi@gmail.com"],
    "PHONE": ["+355 69 234 5678"],
    "URL": ["linkedin.com/in/astritpatozi", "github.com/astritpatozi"],
    "ADDRESS": ["Rruga Myslym Shyri, Pallati 7, Ap. 12"],
    "ORG": ["FinBridge Solutions", "Softec Albania", "AlbaSoft", "Polytechnic University of Tirana"],
    "LOCATION": ["Tirana", "Albania"],
}
```

### Ground Truth — Fixture 2: cv_clean_it_support.pdf
```python
"cv_clean_it_support": {
    "PERSON": ["Qerime Dallku"],
    "EMAIL": ["qerime.dallku@gmail.com"],
    "PHONE": ["+355 68 512 3490"],
    "URL": ["linkedin.com/in/qerimedallku"],
    "ADDRESS": ["Rruga e Kavajes, Pallati 14, Ap. 5"],
    "ORG": ["Credins Bank", "Albtelecom", "ICT Solutions Albania", "University of Tirana"],
    "LOCATION": ["Tirana", "Tiranë", "Albania"],
}
```

### Ground Truth — Fixture 3: cv_clean_sales.pdf
```python
"cv_clean_sales": {
    "PERSON": ["Blerina Koçi"],
    "EMAIL": ["blerina.koci@gmail.com"],
    "PHONE": ["+355 67 389 2145"],
    "URL": ["linkedin.com/in/blerinakoci"],
    "ADDRESS": ["Rruga Sami Frasheri, Pallati 3, Ap. 8"],
    "ORG": ["Koleka Imobiliare", "Pro-Konsult", "Century 21 Albania", "University of Tirana"],
    "LOCATION": ["Tirana", "Tiranë", "Albania"],
    "DOB": ["14 March 2000"],
}
```

### Ground Truth — Fixture 4: cv_clean_bank_teller.pdf
```python
"cv_clean_bank_teller": {
    "PERSON": ["Zgjatje Ndregjoni"],
    "EMAIL": ["zgjatje.ndregjoni@gmail.com"],
    "PHONE": ["+355 69 471 8823"],
    "ADDRESS": ["Rruga Skenderbej, Pall. 2, Ap. 4"],
    "LOCATION": ["Koplik", "Shkodër", "Albania"],
    "ORG": ["Banka Kombëtare Tregtare", "BKT", "Bashkia Koplik", "Universiteti 'Luigj Gurakuqi'"],
    "DOB": ["22 July 2001"],
}
```

### Ground Truth — Fixture 5: cv_dense_sme_banker.txt
```python
"cv_dense_sme_banker": {
    "PERSON": ["Arbër-Luan Hoxhaj", "Ilir Metaçi", "Mirela Kodra"],
    "EMAIL": [
        "arber.hoxhaj1989@gmail.com", "a.hoxhaj@finance-consult.al",
        "ilir.metaci@ufbank.al", "m.kodra@smefinance.al",
    ],
    "PHONE": [
        "+355 69 782 4411", "00355 68 332 1900",
        "+355 67 908 1122", "068 441 2233",
    ],
    "URL": ["linkedin.com/in/arber-luan-hoxhaj"],
    "ADDRESS": ["Rruga \"Myslym Shyri\", Pallati Edil-AL, Shkalla 2, Ap. 14"],
    "DOB": ["17 February 1989"],
    "ID_NUMBER": ["J90217045L", "BA4589201"],
    "ORG": [
        "Banka e Shqipërisë Tregtare", "Union Financial Bank",
        "CrediPlus Microfinance", "University of Tirana",
        "European University of Tirana", "Albanian Association of Banks",
        "Vienna Banking Institute", "AAB Training Centre",
    ],
    "LOCATION": ["Tirana", "Tiranë", "Albania", "Kukës", "Durrës"],
    "PERSONAL_FACT": ["Married", "Male"],
}
```

### Ground Truth — Fixture 6: cv_ocr_damaged_sales.txt
```python
"cv_ocr_damaged_sales": {
    "PERSON": ["Eliona Shkurti", "Ardian Leska", "Migena Braho"],
    "EMAIL": [
        "eliona.shkurti@gmail.com", "e.shkurti@outlook.com",
        "ardian.leska@tmc.al", "m.braho@finance-team.al",
    ],
    "PHONE": [
        "+355 69 440 7219", "068-227-9810",
        "+355 67 555 9011", "069 889 1222",
    ],
    "URL": ["linkedin.com/in/eliona-shkurti-finance"],
    "ADDRESS": ["Rruga e Durrësit, Pall. 88, Hyrja B, Ap. 21"],
    "DOB": ["04/09/1996"],
    "ID_NUMBER": ["K60904123M", "BA1193308"],
    "ORG": [
        "Tirana Micro Credit", "MoneyPay Albania",
        "Municipality Finance Office", "University of Tirana",
        "tmc.al", "finance-team.al",
    ],
    "LOCATION": [
        "Tiranë", "Tirana", "Durrës", "Albanian", "Albania",
        "Kombinat", "Astir", "Zogu i Zi",
    ],
    "PERSONAL_FACT": ["Female", "Single"],
}
```

Use **fuzzy matching** when checking ground truth (lowercase, strip whitespace,
substring or 70%+ token overlap). The provided heuristic from the test report
works well — adapt it.

---

## 12. Dependencies

`requirements.txt`:

```
pdfplumber>=0.11.0
python-docx>=1.1.0
pydantic>=2.5.0
pyyaml>=6.0
structlog>=24.1.0
gliner>=0.2.0          # for Phase 2
requests>=2.31.0       # for Ollama
pytest>=8.0.0
```

`pyproject.toml`:

```toml
[project]
name = "cv-pii-tool"
version = "0.1.0"
description = "Standalone CV PII anonymisation tool"
requires-python = ">=3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short"

[tool.ruff]
line-length = 100
target-version = "py311"
```

---

## 12.1 Corporate Network & Offline Model Support

The tool MUST work in corporate environments with HTTP proxies, TLS inspection,
and air-gapped (no-internet) networks.

### Required Behaviour

**Proxy support:**
- Read `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` env vars
- Read `REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE` for corporate CA certificates
- Apply both BEFORE importing `gliner` or `transformers`
- Use `huggingface_hub.configure_http_backend()` to inject a requests Session
  with proxy and CA bundle configured

**Offline mode:**
- Read `HF_HUB_OFFLINE` and `TRANSFORMERS_OFFLINE` env vars
- When `HF_HUB_OFFLINE=1`, set the env var at process start (before any HF import)
- When offline mode is on, the model loader must NEVER attempt network calls

**Local model loading:**
- Read `GLINER_MODEL_PATH` env var
- If set AND the folder exists AND contains `config.json`, load from that path
- Otherwise fall back to downloading from `GLINER_MODEL_ID` (Hugging Face)
- Log clearly which source was used

### Implementation

**`src/pii/recognisers/ner_gliner.py`** must include this exact preamble
before any `gliner` import:

```python
import os
from pathlib import Path

# Apply offline mode BEFORE any HuggingFace imports
if os.getenv("HF_HUB_OFFLINE") == "1":
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
if os.getenv("TRANSFORMERS_OFFLINE") == "1":
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def _configure_corporate_network() -> None:
    """Configure HTTP backend for corporate proxies with optional CA bundle."""
    proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    ca_bundle = os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("SSL_CERT_FILE")
    if not proxy and not ca_bundle:
        return

    try:
        from huggingface_hub import configure_http_backend
        import requests
    except ImportError:
        return  # huggingface_hub not yet installed

    def backend_factory() -> "requests.Session":
        session = requests.Session()
        if proxy:
            session.proxies = {
                "http": os.getenv("HTTP_PROXY", proxy),
                "https": os.getenv("HTTPS_PROXY", proxy),
            }
        if ca_bundle:
            session.verify = ca_bundle
        return session

    configure_http_backend(backend_factory=backend_factory)


_configure_corporate_network()
```

The `GLiNERRecogniser.__init__` must accept an optional `model_path` and
prefer it over `model_id`:

```python
class GLiNERRecogniser:
    def __init__(
        self,
        model_id: str,
        threshold: float,
        labels: list[str],
        model_path: str | None = None,
    ) -> None:
        from gliner import GLiNER

        if model_path:
            path = Path(model_path)
            if path.exists() and (path / "config.json").exists():
                logger.info("loading_gliner_from_local_path", path=str(path))
                self.model = GLiNER.from_pretrained(str(path))
            else:
                logger.warning(
                    "gliner_local_path_not_found_falling_back",
                    path=str(path),
                    fallback_id=model_id,
                )
                self.model = GLiNER.from_pretrained(model_id)
        else:
            logger.info("loading_gliner_from_hub", model_id=model_id)
            self.model = GLiNER.from_pretrained(model_id)

        self.threshold = threshold
        self.labels = labels
```

### Settings.yaml additions

`config/settings.yaml` must support the new fields:

```yaml
recognisers:
  ner:
    gliner:
      model_id: "urchade/gliner_multi_pii-v1"
      model_path: null              # absolute or relative path; null = use model_id
      threshold: 0.5
      labels: [...]
```

The settings loader reads `GLINER_MODEL_PATH` env var as fallback when
`model_path` is null in the YAML.

### scripts/download_models_offline.py

Build a script with this contract:

- Reads `GLINER_MODEL_SOURCE` env var (URL to a zip)
- If set: download the zip, extract to `GLINER_MODEL_PATH`
- If not set OR download fails: fall back to `huggingface_hub.snapshot_download`
- Verifies the resulting folder contains `config.json` before exiting success
- Prints progress (MB downloaded / total)
- Idempotent — exits success if model already present

## 13. Build Order

Build in this exact sequence. Run tests after each step.

1. Create folder structure + empty `__init__.py` files
2. Write `pyproject.toml`, `requirements.txt`, `.gitignore`
3. Drop in the existing modules from section 9 (no edits)
4. Build `src/pii/schemas.py` (Pydantic models)
5. Build `src/extraction/` (PDF, DOCX, TXT, base, dispatcher)
6. Build `tests/conftest.py` and `tests/ground_truth.py`
7. Build `tests/test_normaliser.py` and run — must pass
8. Build `tests/test_recognisers.py` and run — must pass
9. Build `src/runner.py` (CLI) — runs end-to-end with heuristic NER
10. Build `tests/test_pipeline_recall.py` — heuristic recall ≥ 80%
11. **Pause here. User runs the tool against their real CVs. Iterate.**
12. Build `src/pii/recognisers/ner_gliner.py` — recall ≥ 95%
13. Build `src/pii/recognisers/llm_verify.py` — recall ≥ 98%
14. Final regression: full suite passes all gates

---

## 14. README.md

Generate a `README.md` at the project root covering:

- 30-second project pitch
- Prerequisites (Python 3.11+, optionally Ollama for L3, optionally GPU for GLiNER)
- Quick start: clone, install, drop CVs in input/, run, see output
- Configuration walkthrough (settings.yaml)
- How to add a new test fixture
- Limitations (it's local-only, single-process per CV, no real-time)
- Privacy posture: nothing leaves localhost; PII is encrypted at rest is OUT OF SCOPE for v0.1.0 (mention as future work)

---

## 15. What "Done" Looks Like

A reviewer should be able to:

```bash
git clone <repo>
cd cv-pii-tool
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest                                     # all green
cp ~/some_cvs/*.pdf ./input/
python -m src.runner                       # processes them
ls output/run_*/                           # see the JSON outputs
```

…with no other setup. Ollama and GLiNER are optional — pipeline degrades
gracefully when they're absent, falling back to pattern + heuristic NER.

---

## 16. Anti-Goals

These are tempting but wrong. Do not do them.

- ❌ Add scoring or LLM calls beyond PII verification
- ❌ Wire up to Azure OpenAI even "just for testing"
- ❌ Add a database (the JSON files ARE the storage for v0.1.0)
- ❌ Build a web UI
- ❌ Add async/await unless genuinely needed (it isn't here)
- ❌ Make recognisers configurable via plugins. Just hardcode the three.
- ❌ Over-engineer the CLI with subcommands. One command, flags only.
- ❌ Add metrics export (Prometheus, OpenTelemetry). Not needed.
- ❌ Catch broad `Exception` to "be safe". Catch specific exceptions only.

---

## 17. Questions for the User (ASK if unclear)

If any of these are ambiguous, ask before coding:
- Is the heuristic NER sufficient as a fallback, or must GLiNER be required?
- Is OCR fallback (Tesseract) needed in v0.1.0 or later?
- Should the tool read sub-folders of `--input` recursively or only the top level?
- Should `pii_record.json` include the raw detection list as well, or only the structured fields?

Default answers if no response: heuristic-as-fallback ON, OCR OFF, recursive ON, raw list goes only in `detection_log.json` (not `pii_record.json`).

---

# END OF SPEC

Build the project as specified. Do not deviate. If something seems unclear,
ask before assuming. The existing code in section 9 is the foundation — it
has been validated against 6 real Albanian CVs with measured recall. Build
the rest around it.
