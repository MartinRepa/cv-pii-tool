"""
CV PII Anonymisation Tool — CLI entry point.

Usage:
    python -m src.runner [options]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path as _Path

# Ensure the project root is in sys.path so `src.*` imports work whether the
# script is run from the project root, from inside src/, or from a subprocess
# worker spawned by ProcessPoolExecutor (Windows uses 'spawn', not 'fork').
_PROJECT_ROOT = str(_Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Load .env file early so GLINER_MODEL_PATH, HF_HUB_OFFLINE, etc. are visible
# to all subsequent imports (including GLiNER / HuggingFace).
# python-dotenv is optional - silently skipped if not installed.
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(_Path(_PROJECT_ROOT) / ".env", override=False)
except ImportError:
    pass  # dotenv not installed - rely on shell environment

# CRITICAL: HuggingFace reads these env vars at IMPORT time, not runtime.
# We must (1) resolve relative paths to absolute, (2) ensure they're in
# os.environ, BEFORE any gliner / transformers / huggingface_hub import.

# Resolve relative cache paths to absolute (HF requires absolute paths on Windows)
for _hf_var in ("HF_HOME", "TRANSFORMERS_CACHE", "HUGGINGFACE_HUB_CACHE"):
    _val = os.environ.get(_hf_var)
    if _val:
        os.environ[_hf_var] = str(_Path(_val).expanduser().resolve())

# Force offline mode if requested in .env
if os.environ.get("HF_HUB_OFFLINE") == "1":
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    # Belt and suspenders — also stop telemetry attempts
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["DISABLE_TELEMETRY"] = "1"

# Resolve GLINER_MODEL_PATH to absolute path too
if _gliner_path := os.environ.get("GLINER_MODEL_PATH"):
    os.environ["GLINER_MODEL_PATH"] = str(_Path(_gliner_path).expanduser().resolve())

from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import structlog
import yaml
from pydantic import BaseModel, ConfigDict, Field

from src.extraction.base import ExtractionResult, get_extractor
from src.pii.pipeline import PIIPipeline, PIIDetection, AnonymisationResult
from src.pii.sanitiser import CVSanitiser
from src.pii.schemas import (
    BatchSummary, ByLayerStats, Detection, DetectionLog, Failure,
    LayerStats, LowConfidenceFlag, PerCVSummary, PIIFields, PIIRecord,
)

# ── version ───────────────────────────────────────────────────────────────────
VERSION = "0.1.0"

# ── config model ──────────────────────────────────────────────────────────────

class _NormaliserCfg(BaseModel):
    model_config = ConfigDict(extra="ignore")
    mode: str = "auto"


class _GLiNERCfg(BaseModel):
    model_config = ConfigDict(extra="ignore")
    model_id: str = "urchade/gliner_multi_pii-v1"
    model_path: str | None = None
    threshold: float = 0.5
    labels: list[str] = Field(default_factory=list)


class _NERCfg(BaseModel):
    model_config = ConfigDict(extra="ignore")
    backend: str = "heuristic"
    gliner: _GLiNERCfg = Field(default_factory=_GLiNERCfg)


class _LLMVerifyCfg(BaseModel):
    model_config = ConfigDict(extra="ignore")
    enabled: bool = False
    ollama_url: str = "http://localhost:11434"
    model: str = "llama3.1:8b"
    timeout_seconds: int = 60


class _RecognisersCfg(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ner: _NERCfg = Field(default_factory=_NERCfg)
    llm_verify: _LLMVerifyCfg = Field(default_factory=_LLMVerifyCfg)


class _ConfidenceCfg(BaseModel):
    model_config = ConfigDict(extra="ignore")
    global_threshold: float = 0.85


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    pipeline_version: str = VERSION
    normaliser: _NormaliserCfg = Field(default_factory=_NormaliserCfg)
    recognisers: _RecognisersCfg = Field(default_factory=_RecognisersCfg)
    confidence: _ConfidenceCfg = Field(default_factory=_ConfidenceCfg)


def _load_config(path: Path) -> AppConfig:
    if not path.exists():
        return AppConfig()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(raw)


def _config_hash(path: Path) -> str:
    if not path.exists():
        return "00000000"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest[:16]


# ── fingerprint ───────────────────────────────────────────────────────────────

def _fingerprint(pii: PIIRecord) -> str:
    emails = "".join(sorted(e.lower().strip() for e in pii.pii_fields.emails))
    phones = "".join(sorted(p.strip() for p in pii.pii_fields.phones))
    seed = emails + phones
    if not seed.strip():
        seed = pii.source_file
    return hashlib.sha256(seed.encode()).hexdigest()


# ── PII field extraction from pipeline result ─────────────────────────────────

def _build_pii_fields(result: AnonymisationResult) -> PIIFields:
    emails: list[str] = []
    phones: list[str] = []
    linkedin: str | None = None
    persons: list[str] = []

    for d in result.detections:
        etype = d.entity_type
        val = d.text.strip()
        if etype == "EMAIL":
            if val not in emails:
                emails.append(val)
        elif etype == "PHONE":
            if val not in phones:
                phones.append(val)
        elif etype == "URL":
            if "linkedin" in val.lower() and linkedin is None:
                linkedin = val
        elif etype == "PERSON":
            if val not in persons:
                persons.append(val)

    return PIIFields(
        full_name=" ".join(persons[0].split()) if persons else None,
        emails=emails,
        phones=phones,
        linkedin=linkedin,
    )


# ── per-CV processing (runs in worker process) ────────────────────────────────

# Module-level cache: GLiNER is expensive to load — share across CVs in the
# same worker process.  Populated once by _worker_init or by the first call to
# _get_gliner() in single-worker mode.
_GLINER_CACHE: "GLiNERRecogniser | None" = None  # type: ignore[name-defined]


def _get_gliner(gliner_cfg: dict) -> "GLiNERRecogniser | None":  # type: ignore[name-defined]
    """Return the cached GLiNER recogniser, loading it on first call."""
    global _GLINER_CACHE
    if _GLINER_CACHE is not None:
        return _GLINER_CACHE
    try:
        from src.pii.recognisers.ner_gliner import GLiNERRecogniser
        model_path = gliner_cfg.get("model_path") or os.getenv("GLINER_MODEL_PATH")
        _GLINER_CACHE = GLiNERRecogniser(
            model_id=gliner_cfg["model_id"],
            threshold=gliner_cfg["threshold"],
            labels=gliner_cfg["labels"],
            model_path=model_path,
        )
    except Exception as exc:
        print(
            f"\nWARNING: GLiNER failed to load — falling back to heuristic NER.\n"
            f"  Reason : {exc}\n"
            f"  Fix    : set GLINER_MODEL_PATH to the local model folder, or\n"
            f"           run:  python scripts/download_models_offline.py\n",
            file=sys.stderr,
        )
        _GLINER_CACHE = None  # type: ignore[assignment]
    return _GLINER_CACHE


def _worker_init(project_root: str, gliner_cfg: dict | None = None) -> None:
    """
    Called once per worker process by ProcessPoolExecutor.

    Sets up sys.path and pre-loads the GLiNER model so that every CV
    processed by this worker reuses the already-loaded model.
    """
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    if gliner_cfg:
        _get_gliner(gliner_cfg)  # warm the cache for this worker


def _process_cv(
    cv_path: Path,
    run_dir: Path,
    normalise_mode: str,
    confidence_threshold: float,
    dry_run: bool,
    ner_mode: str = "heuristic",
    gliner_cfg: dict | None = None,
    llm_verify_enabled: bool = False,
    ollama_url: str = "http://localhost:11434",
    ollama_model: str = "llama3.1:8b",
    ollama_timeout: int = 60,
) -> dict:
    t0 = time.monotonic()
    source_file = cv_path.name

    try:
        extractor = get_extractor(cv_path)
        extraction: ExtractionResult = extractor.extract(cv_path)
    except Exception as exc:
        return {
            "file": source_file,
            "status": "failed",
            "stage": "extraction",
            "error": str(exc),
        }

    # Reuse the worker-level cached model (loaded once per process)
    ner_recogniser = _get_gliner(gliner_cfg) if (ner_mode == "gliner" and gliner_cfg) else None

    pipeline = PIIPipeline(normalise=normalise_mode, ner_recogniser=ner_recogniser)

    try:
        result: AnonymisationResult = pipeline.anonymise(extraction.text)
    except Exception as exc:
        return {
            "file": source_file,
            "status": "failed",
            "stage": "pipeline",
            "error": str(exc),
        }

    # ── L3: Ollama LLM verification pass ──────────────────────────────────────
    llm_verify_count = 0
    if llm_verify_enabled:
        try:
            from src.pii.recognisers.llm_verify import OllamaVerifier
            verifier = OllamaVerifier(ollama_url, ollama_model, ollama_timeout)
            llm_raw = verifier.verify(result.anonymised_text)

            if llm_raw:
                # Find current max token index per entity type
                counters: dict[str, int] = defaultdict(int)
                for tok in result.pii_map:
                    inner = tok.strip("[]")          # "PERSON_1"
                    parts = inner.rsplit("_", 1)
                    if len(parts) == 2 and parts[1].isdigit():
                        etype = parts[0]
                        counters[etype] = max(counters[etype], int(parts[1]))

                # Apply replacements descending so indices stay valid
                anon_text = result.anonymised_text
                pii_map = dict(result.pii_map)
                extra: list[PIIDetection] = []
                for ent, val, s, e, conf in sorted(llm_raw, key=lambda x: -x[2]):
                    counters[ent] += 1
                    token = f"[{ent}_{counters[ent]}]"
                    pii_map[token] = val
                    anon_text = anon_text[:s] + token + anon_text[e:]
                    extra.append(PIIDetection(ent, val, s, e, "L3_llm_verify", conf))

                llm_verify_count = len(extra)
                result = AnonymisationResult(
                    anonymised_text=anon_text,
                    pii_map=pii_map,
                    detections=result.detections + extra,
                    was_normalised=result.was_normalised,
                )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "OllamaVerifier skipped (%s) — LLM layer unavailable", exc
            )

    now_utc = datetime.now(timezone.utc)
    pii_fields = _build_pii_fields(result)

    # Build PIIRecord
    pii_record = PIIRecord(
        candidate_fingerprint="placeholder",
        source_file=source_file,
        extraction_quality=extraction.quality,
        was_normalised=result.was_normalised,
        processed_at=now_utc,
        pipeline_version=VERSION,
        pii_fields=pii_fields,
    )
    pii_record = pii_record.model_copy(
        update={"candidate_fingerprint": _fingerprint(pii_record)}
    )
    fingerprint = pii_record.candidate_fingerprint

    # Build DetectionLog
    by_layer_counts: dict[str, int] = defaultdict(int)
    for d in result.detections:
        by_layer_counts[d.layer] += 1

    detections_schema = []
    low_flags = []
    for d in result.detections:
        if d.confidence is not None:
            confidence = d.confidence
        elif d.layer == "L1_pattern":
            confidence = 0.99
        else:
            confidence = 0.75
        tok = next(
            (k for k, v in result.pii_map.items() if v == d.text),
            None,
        )
        detections_schema.append(Detection(
            entity_type=d.entity_type,
            text=d.text,
            start=d.start,
            end=d.end,
            layer=d.layer,
            confidence=confidence,
            token_replacement=tok,
        ))
        if confidence < confidence_threshold:
            low_flags.append(LowConfidenceFlag(
                entity_type=d.entity_type,
                text=d.text,
                confidence=confidence,
                reason="Below confidence threshold",
            ))

    by_entity: dict[str, int] = defaultdict(int)
    for d in result.detections:
        by_entity[d.entity_type] += 1

    detection_log = DetectionLog(
        candidate_fingerprint=fingerprint,
        source_file=source_file,
        processed_at=now_utc,
        total_detections=len(result.detections),
        by_layer=ByLayerStats(
            L0_normaliser=LayerStats(
                applied=result.was_normalised,
                damage_indicators={},
            ),
            L1_pattern=by_layer_counts.get("L1_pattern", 0),
            # Combine heuristic NER, GLiNER, and header-name detections under L2
            L2_ner=(
                by_layer_counts.get("L2_ner", 0)
                + by_layer_counts.get("L2_gliner", 0)
                + by_layer_counts.get("L0_header", 0)
            ),
            L3_llm_verify=by_layer_counts.get("L3_llm_verify", 0),
        ),
        by_entity_type=dict(by_entity),
        low_confidence_flags=low_flags,
        detections=detections_schema,
    )

    duration_ms = int((time.monotonic() - t0) * 1000)

    if not dry_run:
        cv_out_dir = run_dir / cv_path.stem
        cv_out_dir.mkdir(parents=True, exist_ok=True)

        (cv_out_dir / "pii_record.json").write_text(
            pii_record.model_dump_json(indent=2), encoding="utf-8"
        )
        (cv_out_dir / "detection_log.json").write_text(
            detection_log.model_dump_json(indent=2), encoding="utf-8"
        )
        (cv_out_dir / "anonymised_cv.txt").write_text(
            result.anonymised_text, encoding="utf-8"
        )

        sanitised = CVSanitiser().sanitise(result.anonymised_text, result.pii_map)
        (cv_out_dir / "sanitised_cv.txt").write_text(sanitised, encoding="utf-8")

    return {
        "file": source_file,
        "fingerprint": fingerprint,
        "extraction_quality": extraction.quality,
        "was_normalised": result.was_normalised,
        "total_detections": len(result.detections),
        "low_confidence_count": len(low_flags),
        "duration_ms": duration_ms,
        "status": "success",
        "by_entity": dict(by_entity),
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="cv-pii-tool",
        description=f"CV PII Anonymisation Tool v{VERSION}",
    )
    parser.add_argument("--input", type=Path, default=Path("./input"))
    parser.add_argument("--output", type=Path, default=Path("./output"))
    parser.add_argument("--config", type=Path, default=Path("config/settings.yaml"))
    parser.add_argument("--normalise", choices=["auto", "always", "never"], default="auto")
    parser.add_argument("--ner", choices=["gliner", "heuristic"], default="heuristic")
    parser.add_argument("--llm-verify", dest="llm_verify", action="store_true", default=False)
    parser.add_argument("--no-llm-verify", dest="llm_verify", action="store_false")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--ollama-model", default="llama3.1:8b")
    parser.add_argument("--confidence-threshold", type=float, default=0.85)
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--quiet", action="store_true", default=False)
    parser.add_argument("--dry-run", action="store_true", default=False)
    return parser.parse_args(argv)


def _configure_logging(quiet: bool) -> None:
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            20 if quiet else 10  # INFO if quiet, DEBUG otherwise
        ),
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _configure_logging(args.quiet)
    log = structlog.get_logger()

    if not args.quiet:
        print(f"PII Anonymisation Tool v{VERSION}")

    # Validate config
    cfg = _load_config(args.config)
    cfg_hash = _config_hash(args.config)

    # Validate input dir
    if not args.input.exists() or not args.input.is_dir():
        print(f"ERROR: Input directory not found: {args.input}", file=sys.stderr)
        return 2

    cv_files = sorted(
        f for f in args.input.rglob("*")
        if f.suffix.lower() in (".pdf", ".docx", ".txt") and f.is_file()
    )

    if not cv_files:
        print(f"ERROR: No CV files found in {args.input}", file=sys.stderr)
        return 2

    if not args.quiet:
        print(f"\nProcessing {len(cv_files)} CVs from {args.input}/")

    # Create timestamped run folder
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    batch_id = f"run_{ts}"
    run_dir = args.output / batch_id
    if not args.dry_run:
        run_dir.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc)
    t_batch_start = time.monotonic()

    per_cv_results: list[dict] = []
    failures: list[dict] = []

    workers = args.workers
    normalise_mode = args.normalise
    confidence_threshold = args.confidence_threshold
    dry_run = args.dry_run
    ner_mode = args.ner
    gliner_cfg: dict | None = None
    if ner_mode == "gliner":
        # model_path: YAML value wins; GLINER_MODEL_PATH env var is the fallback
        model_path = cfg.recognisers.ner.gliner.model_path or os.getenv("GLINER_MODEL_PATH")
        gliner_cfg = {
            "model_id": cfg.recognisers.ner.gliner.model_id,
            "model_path": model_path,
            "threshold": cfg.recognisers.ner.gliner.threshold,
            "labels": list(cfg.recognisers.ner.gliner.labels),
        }
        if not args.quiet:
            if model_path:
                print(f"Loading GLiNER model from local path: {model_path}")
            else:
                print("Loading GLiNER model (first run downloads ~500 MB)...")

    # LLM verify settings
    llm_verify_enabled = args.llm_verify
    ollama_url = args.ollama_url
    ollama_model = args.ollama_model
    ollama_timeout = cfg.recognisers.llm_verify.timeout_seconds
    if llm_verify_enabled and not args.quiet:
        print(f"LLM verification: Ollama {ollama_url} ({ollama_model})")

    _cv_kwargs = dict(
        normalise_mode=normalise_mode,
        confidence_threshold=confidence_threshold,
        dry_run=dry_run,
        ner_mode=ner_mode,
        gliner_cfg=gliner_cfg,
        llm_verify_enabled=llm_verify_enabled,
        ollama_url=ollama_url,
        ollama_model=ollama_model,
        ollama_timeout=ollama_timeout,
    )

    if workers == 1:
        for cv_path in cv_files:
            r = _process_cv(cv_path, run_dir, **_cv_kwargs)
            per_cv_results.append(r)
    else:
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_worker_init,
            initargs=(_PROJECT_ROOT, gliner_cfg),
        ) as executor:
            futures = {
                executor.submit(_process_cv, cv, run_dir, **_cv_kwargs): cv
                for cv in cv_files
            }
            for future in as_completed(futures):
                r = future.result()
                per_cv_results.append(r)

    # Sort by file name for deterministic output
    per_cv_results.sort(key=lambda x: x["file"])

    # Print per-CV summary
    if not args.quiet:
        for r in per_cv_results:
            if r["status"] == "success":
                symbol = "!" if r["was_normalised"] else "+"
                norm_tag = " | NORMALISED" if r["was_normalised"] else ""
                print(
                    f"  {symbol} {r['file']:<35} "
                    f"| quality {r['extraction_quality']:.2f} "
                    f"| {r['total_detections']} detections"
                    f"{norm_tag}"
                )
            else:
                print(f"  x {r['file']:<35} | FAILED: {r.get('error', '?')}")

    # Aggregate batch summary
    successes = [r for r in per_cv_results if r["status"] == "success"]
    fails = [r for r in per_cv_results if r["status"] == "failed"]

    avg_quality = (
        sum(r["extraction_quality"] for r in successes) / len(successes)
        if successes else 0.0
    )
    ocr_count = sum(1 for r in successes if r["was_normalised"])
    low_conf_count = sum(r.get("low_confidence_count", 0) for r in successes)
    total_pii = sum(r.get("total_detections", 0) for r in successes)

    by_entity_total: dict[str, int] = defaultdict(int)
    for r in successes:
        for etype, cnt in r.get("by_entity", {}).items():
            by_entity_total[etype] += cnt

    finished_at = datetime.now(timezone.utc)
    duration_seconds = time.monotonic() - t_batch_start

    batch_summary = BatchSummary(
        batch_id=batch_id,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=round(duration_seconds, 2),
        pipeline_version=VERSION,
        config_hash=cfg_hash,
        cvs_total=len(cv_files),
        cvs_processed=len(successes),
        cvs_failed=len(fails),
        average_extraction_quality=round(avg_quality, 4),
        ocr_damaged_count=ocr_count,
        low_confidence_review_required=low_conf_count,
        total_pii_detected=total_pii,
        by_entity_type_total=dict(by_entity_total),
        failures=[
            Failure(file=f["file"], stage=f.get("stage", "unknown"), error=f.get("error", ""))
            for f in fails
        ],
        per_cv=[
            PerCVSummary(
                file=r["file"],
                fingerprint=r.get("fingerprint", ""),
                extraction_quality=r["extraction_quality"],
                was_normalised=r["was_normalised"],
                total_detections=r["total_detections"],
                low_confidence_count=r.get("low_confidence_count", 0),
                duration_ms=r.get("duration_ms", 0),
                status="success",
            )
            for r in successes
        ],
    )

    if not args.dry_run:
        (run_dir / "batch_summary.json").write_text(
            batch_summary.model_dump_json(indent=2), encoding="utf-8"
        )

    if not args.quiet:
        print(
            f"\nDone. {len(successes)}/{len(cv_files)} succeeded. "
            f"Output: {run_dir}/"
        )

    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
