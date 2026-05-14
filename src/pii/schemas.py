"""
Pydantic v2 schemas for all JSON output contracts (section 5 of CLAUDE.md).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal  # used by PerCVSummary

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "PIIFields",
    "PIIRecord",
    "LayerStats",
    "LowConfidenceFlag",
    "Detection",
    "DetectionLog",
    "PerCVSummary",
    "Failure",
    "BatchSummary",
]


# ── shared config ──────────────────────────────────────────────────────────────
_cfg = ConfigDict(extra="forbid")


# ── pii_record.json ────────────────────────────────────────────────────────────

class PIIFields(BaseModel):
    model_config = _cfg
    full_name: str | None = None
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    linkedin: str | None = None


class PIIRecord(BaseModel):
    model_config = _cfg
    candidate_fingerprint: str
    source_file: str
    extraction_quality: float
    was_normalised: bool
    processed_at: datetime
    pipeline_version: str
    pii_fields: PIIFields = Field(default_factory=PIIFields)


# ── detection_log.json ─────────────────────────────────────────────────────────

class LayerStats(BaseModel):
    model_config = _cfg
    applied: bool
    damage_indicators: dict[str, float] = Field(default_factory=dict)


class LowConfidenceFlag(BaseModel):
    model_config = _cfg
    entity_type: str
    text: str
    confidence: float
    reason: str


class Detection(BaseModel):
    model_config = _cfg
    entity_type: str
    text: str
    start: int
    end: int
    layer: str
    confidence: float
    token_replacement: str | None = None


class ByLayerStats(BaseModel):
    model_config = _cfg
    L0_normaliser: LayerStats
    L1_pattern: int
    L2_ner: int
    L3_llm_verify: int


class DetectionLog(BaseModel):
    model_config = _cfg
    candidate_fingerprint: str
    source_file: str
    processed_at: datetime
    total_detections: int
    by_layer: ByLayerStats
    by_entity_type: dict[str, int] = Field(default_factory=dict)
    low_confidence_flags: list[LowConfidenceFlag] = Field(default_factory=list)
    detections: list[Detection] = Field(default_factory=list)


# ── batch_summary.json ─────────────────────────────────────────────────────────

class PerCVSummary(BaseModel):
    model_config = _cfg
    file: str
    fingerprint: str
    extraction_quality: float
    was_normalised: bool
    total_detections: int
    low_confidence_count: int
    duration_ms: int
    status: Literal["success", "failed"]


class Failure(BaseModel):
    model_config = _cfg
    file: str
    stage: str
    error: str


class BatchSummary(BaseModel):
    model_config = _cfg
    batch_id: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    pipeline_version: str
    config_hash: str

    cvs_total: int
    cvs_processed: int
    cvs_failed: int

    average_extraction_quality: float
    ocr_damaged_count: int
    low_confidence_review_required: int
    total_pii_detected: int

    by_entity_type_total: dict[str, int] = Field(default_factory=dict)
    failures: list[Failure] = Field(default_factory=list)
    per_cv: list[PerCVSummary] = Field(default_factory=list)
