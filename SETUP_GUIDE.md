# Laptop Setup Guide — Step by Step

> When you sit down at your ThinkPad or HP laptop, follow this guide
> in order. It takes ~20 minutes for Phase 1 to be running, then ~30
> minutes more for Phases 2 & 3.

---

## 0. Prerequisites Check

Open a terminal and verify:

```bash
python --version          # Need 3.11 or higher
git --version             # Any recent version
```

If Python is < 3.11:
- **Windows:** download from python.org or use `winget install Python.Python.3.12`
- **Linux:** `sudo apt install python3.12 python3.12-venv` (Ubuntu) or equivalent

---

## 1. Create the Project (5 min)

```bash
# Pick a folder you'll remember
cd ~/Documents
mkdir cv-pii-tool
cd cv-pii-tool
git init
```

Now drop these files into the folder root:
- `CLAUDE.md` (the big spec — do not modify)
- `README.md`
- `pyproject.toml`
- `requirements.txt`
- `.gitignore`
- `.env.example`

And create the subfolder:
```bash
mkdir -p config input output
```

Then drop `settings.yaml` into `config/`.

Copy the template:
```bash
cp .env.example .env
```

---

## 2. Set Up Python Environment (3 min)

```bash
python -m venv .venv

# Activate (Linux/Mac)
source .venv/bin/activate

# Activate (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Activate (Windows cmd)
.venv\Scripts\activate.bat

# You should see (.venv) in your prompt now

pip install --upgrade pip
pip install -r requirements.txt
```

This installs everything: pdfplumber, python-docx, pydantic, pyyaml,
structlog, pytest, ruff. GLiNER and torch will also install — these
are bigger (~2GB total) so it takes a few minutes on first install.

---

## 3. Open Claude Code (1 min)

In the same terminal:

```bash
claude code
```

(Or however you launch Claude Code on your machine. Check
https://docs.claude.com if unsure.)

---

## 4. Hand the Spec to Claude Code (the big moment)

Type this exact prompt into Claude Code:

```
Read CLAUDE.md completely before doing anything.

Build the project as specified there. Follow the build order in
section 13 strictly. After step 11 (test_pipeline_recall.py passing
with heuristic NER ≥80%), STOP and tell me. Do not proceed to
Phase 2 (GLiNER) or Phase 3 (Ollama) until I confirm.

The 6 existing modules in section 9 are battle-tested. Drop them
in unchanged. Do not rewrite them.
```

Claude Code will:
1. Read the spec
2. Build the folder structure
3. Drop in the 6 existing modules verbatim
4. Build schemas, extraction, runner, and tests
5. Run the test suite
6. Stop and ask you to drop in your real CVs

---

## 5. Drop Your Real CVs Into `tests/fixtures/` (5 min)

The 6 reference CVs from earlier conversations should go in
`tests/fixtures/` with these exact names:

```
tests/fixtures/
├── cv_clean_backend.pdf           # Astrit Patozi
├── cv_clean_it_support.pdf        # Qerime Dallku
├── cv_clean_sales.pdf             # Blerina Koçi
├── cv_clean_bank_teller.pdf       # Zgjatje Ndregjoni
├── cv_dense_sme_banker.txt        # Arbër-Luan Hoxhaj
└── cv_ocr_damaged_sales.txt       # Eliona Shkurti
```

(I generated all 6 in the earlier conversation — they're in your
download history as PDF/text files.)

Now run:
```bash
pytest tests/ -v
```

Expected: all green, with overall recall ≥80% reported.

---

## 6. Test on a Real CV (2 min)

Drop a real CV (any PDF or DOCX) into `input/`:

```bash
cp ~/Downloads/some_cv.pdf input/
python -m src.runner
```

Look at `output/run_<timestamp>/`:
- Read the `anonymised_cv.txt` — verify your eyes can't find any PII
- Read `pii_record.json` — verify all your personal info is captured
- Read `detection_log.json` — see which layer caught what

If anything is wrong, ask Claude Code to fix it. **This is the
iteration phase.**

---

## 7. (Optional) Install Ollama for Phase 3 (15 min)

Only after Phase 1 is solid.

### Linux/Mac:
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b              # ~5GB download
ollama serve                          # leave running in another terminal
```

### Windows:
Download installer from https://ollama.com/download

Then verify:
```bash
curl http://localhost:11434/api/tags
# Should return JSON with llama3.1:8b listed
```

---

## 8. Tell Claude Code to Build Phase 2 + 3

```
Phase 1 works on my real CVs. Proceed with Phase 2 (GLiNER) and
Phase 3 (Ollama llama3.1:8b) per section 13. Run the test suite
after each phase and report recall numbers.
```

Claude Code adds the GLiNER and Ollama recognisers, runs the tests,
and reports final recall.

---

## 9. Verify the Final Pipeline

```bash
python -m src.runner --ner gliner --llm-verify
```

Open `output/run_<timestamp>/batch_summary.json`. Look for:
- `total_pii_detected` — should match reality
- `low_confidence_review_required` — should be small
- Per-CV `extraction_quality` — should mostly be > 0.9

If recall is below 95%, drop the failing CV into `tests/fixtures/`
with ground truth and ask Claude Code to tune until it passes.

---

## 10. Commit and Move On

```bash
git add .
git commit -m "Phase 1: standalone PII pipeline complete"
```

You now have a battle-tested, locally-running PII anonymisation tool.
Future phases (scoring, decisions, dashboard, Zoho, Azure) will build
on top — but this layer is locked.

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'gliner'`
→ Run `pip install gliner` again. Sometimes it fails silently on first install.

### `torch` install fails on Windows
→ Try `pip install torch --index-url https://download.pytorch.org/whl/cpu`
(skips GPU build, faster install)

### Ollama returns timeout errors
→ Check it's actually running: `curl http://localhost:11434/api/tags`
→ Increase timeout in `.env`: `OLLAMA_TIMEOUT_SECONDS=120`

### Tests fail with "fixture not found"
→ Make sure all 6 CVs are in `tests/fixtures/` with the exact filenames.
→ Run `ls tests/fixtures/` to verify.

### "Recall below 80%" on heuristic test
→ This is expected for OCR-damaged CVs without GLiNER. Add `--ner gliner`
or proceed to Phase 2 to fix.

### Claude Code won't follow the spec
→ Re-prompt: "Read CLAUDE.md again. Section 16 lists anti-goals.
Section 13 is the build order. Stick to them."

---

## What Success Looks Like

After completing this guide, you can:

```bash
cp ~/any_cv.pdf input/
python -m src.runner
cat output/run_*/cv_*/anonymised_cv.txt    # No PII visible
cat output/run_*/cv_*/pii_record.json      # All PII captured
```

That's the foundation of your CV screening pipeline. Future work
(scoring, dashboard, Azure, Zoho) builds on top — but this part
is done.
