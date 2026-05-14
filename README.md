# CV PII Anonymisation Tool

> Standalone Python tool that takes a folder of CVs (PDF, DOCX, TXT) and produces
> anonymised text plus structured PII as JSON files — fully local, no cloud
> services required.

---

## What it does

For each CV you drop into `./input/`, this tool produces:

- **`anonymised_cv.txt`** — the CV with all personal information replaced by typed tokens (`[PERSON_1]`, `[EMAIL_1]`, etc.). Safe to send to any downstream LLM.
- **`pii_record.json`** — structured personal information extracted from the CV (name, emails, phones, address, etc.). Stored locally only.
- **`detection_log.json`** — full audit trail of every detection (which layer caught it, confidence score, position).
- **`batch_summary.json`** — aggregate KPIs for the whole run.

---

## Why this exists

If you're building any pipeline that sends CVs to an LLM (for scoring, parsing,
matching), GDPR requires that you anonymise PII before the data leaves your
trusted environment. This tool is that anonymisation step — designed to be
**robust against real-world Albanian CVs**, including OCR-damaged Europass
templates, multilingual content, and Albanian-specific identifiers (NIPT, NUIS,
+355 phone formats).

It's the foundation layer of a larger CV screening pipeline. Future phases
(scoring, decision engine, HR dashboard, Zoho integration, Azure SQL) build
on top of this — but this layer is **standalone and complete on its own**.

---

## Architecture

A 4-stage pipeline runs entirely on your machine:

```
CV file → Extract → Normalise → Detect PII → Anonymise → JSON output
```

PII detection uses three independent layers stacked for high recall:

| Layer | Tool | Catches |
|---|---|---|
| **L0 Normaliser** | Custom (regex) | OCR/spacing damage in raw text |
| **L1 Pattern** | Regex + Albanian recognisers | Emails, phones, IDs, URLs, dates |
| **L2 NER** | GLiNER-Multi (multilingual) | Names, organisations, locations, addresses |
| **L3 LLM Verify** | Local Ollama (llama3.1:8b) | Contextual / implicit PII |

Each layer is independent — the pipeline degrades gracefully if a layer is
unavailable (e.g. no Ollama installed → still runs, just lower recall).

---

## Quick start

### Prerequisites

- **Python 3.11+**
- **Optional but recommended:** Ollama installed locally with `llama3.1:8b` pulled
- **Optional but recommended:** ~2GB free disk for GLiNER model cache

### Setup

```bash
git clone <your-repo>
cd cv-pii-tool
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Run the test suite

```bash
pytest                              # Should pass with built-in fixtures
```

### Run on your CVs

```bash
# Drop files in input/
cp ~/path/to/cvs/*.pdf ./input/

# Run with defaults (heuristic NER, no LLM verify)
python -m src.runner

# Run with full pipeline (requires GLiNER + Ollama)
python -m src.runner --ner gliner --llm-verify

# Output lands in ./output/run_<timestamp>/
```

---

## Configuration

Edit `config/settings.yaml` to control:

- Which recognisers run
- Confidence thresholds
- GLiNER model and labels
- Ollama URL and model
- Output formats

Defaults are sensible — only edit if you know why.

---

## Directory layout

```
cv-pii-tool/
├── README.md                       This file
├── CLAUDE.md                       Build spec (don't modify)
├── pyproject.toml
├── requirements.txt
├── config/settings.yaml            Pipeline configuration
├── src/                            Source code
│   ├── pii/                        Detection pipeline
│   ├── extraction/                 PDF/DOCX/TXT readers
│   └── runner.py                   CLI entry point
├── tests/                          Test suite + fixtures
├── input/                          Drop CVs here
└── output/                         Results land here
```

---

## CLI reference

```bash
python -m src.runner [options]

Options:
  --input PATH                Folder of CV files (default: ./input)
  --output PATH               Output folder (default: ./output)
  --config PATH               Override config (default: config/settings.yaml)
  --normalise {auto,always,never}   Normaliser mode (default: auto)
  --ner {gliner,heuristic}    NER backend (default: gliner)
  --llm-verify / --no-llm-verify    Toggle Ollama verification
  --ollama-url URL            Ollama endpoint (default: http://localhost:11434)
  --ollama-model NAME         Ollama model (default: llama3.1:8b)
  --confidence-threshold X    Below this → low_confidence_flag (default: 0.85)
  --workers N                 Parallel CV workers (default: 4)
  --quiet                     Reduce log verbosity
  --dry-run                   Run pipeline but write no files
```

---

## Adding a new test fixture

When a real CV breaks the pipeline in production, capture it:

1. Drop the CV (or a representative anonymised version) into `tests/fixtures/`
2. Add ground truth to `tests/ground_truth.py`
3. Run `pytest tests/test_pipeline_recall.py -v`
4. Tune recognisers until it passes

The fixture set should grow over time — never shrink.

---

## Privacy posture

- **Nothing leaves localhost.** No telemetry, no external API calls during PII detection.
- **GLiNER model is downloaded once and cached** in `~/.cache/huggingface/`.
- **Ollama runs on `http://localhost:11434`** — never accept a non-localhost URL in production.
- **PII is in plaintext** in the output JSON files. **Encryption at rest is out of scope for v0.1.0** — protect the output folder with filesystem permissions or encrypt the disk.
- **For real production** (processing real candidates), wrap this tool with proper key management (Azure Key Vault, AWS KMS, etc.) and column-level encryption before storing PII long-term.

---

## Limitations (v0.1.0)

- Single-machine, no multi-user
- No real-time / API mode (CLI only)
- No Zoho or Azure integration (by design — that's a future phase)
- PII output is plaintext (encryption is a future phase)
- Albanian-tuned (works for other languages, but recognisers are calibrated for Albanian formats)

---

## Roadmap

- **v0.1.0 (this release)** — standalone PII pipeline, CLI, JSON outputs
- **v0.2.0** — JD parser + CV structured parser (still local Ollama)
- **v0.3.0** — Scoring engines (JD match + per-se domain profile)
- **v0.4.0** — HR decision engine, reason codes, state machine
- **v0.5.0** — HR dashboard (Streamlit)
- **v1.0.0** — Azure SQL + Azure OpenAI + Zoho Recruit integration

---

## License

Proprietary. All rights reserved.
