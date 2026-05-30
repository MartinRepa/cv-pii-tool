"""
Layer 2 — GLiNER-Multi NER recogniser.

Wraps ``urchade/gliner_multi_pii-v1`` (or any compatible GLiNER model) and
maps its labels onto the canonical entity types used throughout the pipeline.

Corporate / offline requirements (section 12.1)
-----------------------------------------------
- ``GLINER_MODEL_PATH``       load model from a local folder instead of HF Hub
- ``HTTP_PROXY`` / ``HTTPS_PROXY``  route HF Hub downloads through a proxy
- ``REQUESTS_CA_BUNDLE`` / ``SSL_CERT_FILE``  corporate CA certificate
- ``HF_HUB_OFFLINE=1``        never make network calls (local cache only)
- ``TRANSFORMERS_OFFLINE=1``  same for the transformers sub-library

All env vars are applied **before** any huggingface_hub / torch import so that
TLS and proxy settings take effect at the socket level.
"""
from __future__ import annotations

import logging
import os
import warnings
from pathlib import Path

import structlog

# ── Suppress cosmetic upstream warnings ───────────────────────────────────────
# mDeBERTa ships with a known-bad regex pattern in its tokenizer config.
# The warning is harmless — tokenization is unaffected — but it pollutes
# stderr on every model load.
#
# Two suppression layers are needed because different versions of transformers
# route this message differently:
#   - older versions: warnings.warn() → caught by filterwarnings
#   - newer versions: logger.warning_once() → caught by logging filter

warnings.filterwarnings("ignore", message=r".*incorrect regex pattern.*", category=UserWarning)
warnings.filterwarnings("ignore", message=r".*Sentence of length.*has been truncated.*", category=UserWarning)


class _SubstringFilter(logging.Filter):
    """Drop any log record whose message contains one of the given substrings."""
    def __init__(self, *substrings: str) -> None:
        super().__init__()
        self._blocked = substrings

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(s in msg for s in self._blocked)


_NOISE_FILTER = _SubstringFilter(
    "incorrect regex pattern",
    "has been truncated to",
    "fix_mistral_regex",
)

# Attach to the transformers loggers that emit these messages
for _noisy_logger in (
    "transformers.tokenization_utils_base",
    "transformers.tokenization_utils",
    "gliner.data_processing.processor",
):
    logging.getLogger(_noisy_logger).addFilter(_NOISE_FILTER)

# ── Apply offline-mode flags before any HuggingFace import ────────────────────
# These must be set as early as possible — setting them after the first HF
# import is too late because internal caches are already populated.
if os.getenv("HF_HUB_OFFLINE") == "1":
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
if os.getenv("TRANSFORMERS_OFFLINE") == "1":
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def _configure_corporate_network() -> None:
    """
    Configure the HuggingFace Hub HTTP backend for corporate proxy / CA use.

    Supports both huggingface_hub generations:
      - 0.x (requests-based): injects a custom Session via configure_http_backend
      - 1.x (httpx-based):    relies on env vars (HTTP_PROXY, SSL_CERT_FILE)
        that httpx respects automatically when trust_env=True (the default).

    In practice, if the user has HTTP_PROXY / REQUESTS_CA_BUNDLE set in their
    environment, this function makes sure those values are also visible under
    the names that requests AND httpx both recognise.
    """
    proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    ca_bundle = os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("SSL_CERT_FILE")
    if not proxy and not ca_bundle:
        return  # clean dev environment — nothing to configure

    # ── Attempt 1: huggingface_hub 0.x API (requests-based) ──────────────────
    try:
        from huggingface_hub import configure_http_backend  # type: ignore[attr-defined]
        import requests

        def _requests_factory() -> requests.Session:
            session = requests.Session()
            if proxy:
                session.proxies = {
                    "http": os.getenv("HTTP_PROXY", proxy),
                    "https": os.getenv("HTTPS_PROXY", proxy),
                }
            if ca_bundle:
                session.verify = ca_bundle
            return session

        configure_http_backend(backend_factory=_requests_factory)
        return  # done — old API worked
    except (ImportError, AttributeError):
        pass  # huggingface_hub >= 1.0 removed this function

    # ── Attempt 2: huggingface_hub 1.x API (httpx-based) ─────────────────────
    # httpx.Client respects HTTP_PROXY, HTTPS_PROXY, SSL_CERT_FILE when
    # trust_env=True (the default).  Ensure the relevant env vars are set.
    if proxy:
        os.environ.setdefault("HTTP_PROXY", proxy)
        os.environ.setdefault("HTTPS_PROXY", proxy)
    if ca_bundle:
        # httpx reads SSL_CERT_FILE; requests reads REQUESTS_CA_BUNDLE
        os.environ.setdefault("SSL_CERT_FILE", ca_bundle)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_bundle)

    # Also try patching the live session object (best-effort for 1.x)
    try:
        import ssl
        import httpx
        from huggingface_hub import get_session  # type: ignore[attr-defined]

        session = get_session()
        if ca_bundle and isinstance(session, httpx.Client):
            ssl_ctx = ssl.create_default_context(cafile=str(ca_bundle))
            # Rebuild the default transport with our SSL context
            transport = httpx.HTTPTransport(
                verify=ssl_ctx,
                proxy=httpx.Proxy(proxy) if proxy else None,
            )
            # httpx.Client._transport is the default mount; replace it
            session._transport = transport
            session._mounts = {
                "https://": transport,
                "http://": transport,
                "": transport,
            }
    except Exception:  # noqa: BLE001 — best-effort, never crash the pipeline
        pass


# Run once at module-load time — before any GLiNER / torch import.
_configure_corporate_network()

logger = structlog.get_logger(__name__)

__all__ = ["GLiNERRecogniser"]

# ── Chunking constants ─────────────────────────────────────────────────────────
# GLiNER / mDeBERTa has a hard 384-token limit.  At ~4 chars/token for
# Latin-script text, 1 000 chars ≈ 250 tokens — safely under the limit.
# Overlap re-processes the boundary zone so entities that straddle a chunk
# boundary are still caught in full by the adjacent chunk.
_CHUNK_CHARS: int = 1_000
_OVERLAP_CHARS: int = 150


def _chunk_text(text: str) -> list[tuple[str, int]]:
    """
    Split *text* into (chunk, start_offset) pairs.

    Snaps each split point to the nearest preceding newline so we don't cut
    mid-word / mid-entity.  The last chunk always reaches the end of the text.
    """
    chunks: list[tuple[str, int]] = []
    n = len(text)
    start = 0
    while start < n:
        end = min(start + _CHUNK_CHARS, n)
        # Snap to nearest newline before the hard cut (avoids mid-entity splits)
        if end < n:
            nl = text.rfind("\n", start + _CHUNK_CHARS // 2, end)
            if nl != -1:
                end = nl + 1          # include the newline in this chunk
        chunks.append((text[start:end], start))
        if end >= n:
            break
        start = end - _OVERLAP_CHARS  # back up so the next chunk overlaps
    return chunks


# ── GLiNER label → pipeline canonical type ────────────────────────────────────
LABEL_MAP: dict[str, str] = {
    "person name":      "PERSON",
    "full name":        "PERSON",
    "email address":    "EMAIL",
    "phone number":     "PHONE",
    "home address":     "ADDRESS",
    "street address":   "ADDRESS",
    "city":             "LOCATION",
    "country":          "LOCATION",
    "date of birth":    "DOB",
    "nationality":      "LOCATION",
    "linkedin profile": "URL",
    "github profile":   "URL",
    "id number":        "ID_NUMBER",
    "passport number":  "ID_NUMBER",
    "organisation":     "ORG",
    "company":          "ORG",
    "school":           "ORG",
    "university":       "ORG",
}


class GLiNERRecogniser:
    """
    Multilingual NER using GLiNER-Multi.

    Parameters
    ----------
    model_id:
        Hugging Face model ID (e.g. ``"urchade/gliner_multi_pii-v1"``).
        Used when no local path is available.
    threshold:
        Minimum confidence score (0–1). 0.5 gives the best precision/recall
        trade-off for PII across Albanian/EN/IT text.
    labels:
        Entity-type strings to recognise. Must be a subset of the keys in
        ``LABEL_MAP``.
    model_path:
        Absolute or relative path to a pre-downloaded model folder that
        contains ``config.json``.  Takes precedence over ``model_id``.
        Also read from the ``GLINER_MODEL_PATH`` environment variable.
    """

    def __init__(
        self,
        model_id: str,
        threshold: float,
        labels: list[str],
        model_path: str | None = None,
    ) -> None:
        try:
            from gliner import GLiNER  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "GLiNER is not installed. Run: pip install gliner torch"
            ) from exc

        # Resolve model path: explicit arg > GLINER_MODEL_PATH env var > HF Hub
        # urchade/gliner_multi_pii-v1 uses gliner_config.json, not config.json.
        # Accept either name so the check works for all GLiNER model variants.
        resolved_path: Path | None = None
        candidate = model_path or os.getenv("GLINER_MODEL_PATH")
        if candidate:
            p = Path(candidate)
            has_config = (p / "config.json").exists() or (p / "gliner_config.json").exists()
            if p.exists() and has_config:
                resolved_path = p
            else:
                logger.warning(
                    "gliner_local_path_not_found_falling_back",
                    path=str(p),
                    fallback_id=model_id,
                )

        # Suppress the mDeBERTa tokenizer regex warning via transformers' own
        # API (set_verbosity_error) — the filter/warnings approaches don't
        # reliably intercept messages emitted by transformers' internal handler.
        try:
            from transformers import logging as _hf_logging
            _prev = _hf_logging.get_verbosity()
            _hf_logging.set_verbosity_error()
        except Exception:
            _prev = None

        try:
            if resolved_path is not None:
                logger.info("loading_gliner_from_local_path", path=str(resolved_path))
                self.model = GLiNER.from_pretrained(str(resolved_path))
            else:
                logger.info("loading_gliner_from_hub", model_id=model_id)
                self.model = GLiNER.from_pretrained(model_id)
        finally:
            # Always restore verbosity so other code isn't silenced
            if _prev is not None:
                try:
                    from transformers import logging as _hf_logging
                    _hf_logging.set_verbosity(_prev)
                except Exception:
                    pass

        self.threshold = threshold
        self.labels = labels

    def detect(self, text: str) -> list[tuple[str, str, int, int, float]]:
        """
        Run GLiNER on *text* and return canonical detections.

        Long texts are split into overlapping chunks so no content exceeds
        GLiNER's 384-token limit.  Detections from the overlap zone are
        deduplicated by (text, start, end) so each entity is returned once.

        Returns
        -------
        list of (entity_type, matched_text, start, end, confidence)
        """
        if len(text) <= _CHUNK_CHARS:
            return self._detect_chunk(text, 0)

        seen: set[tuple[str, int, int]] = set()
        results: list[tuple[str, str, int, int, float]] = []
        for chunk, offset in _chunk_text(text):
            for row in self._detect_chunk(chunk, offset):
                key = (row[1], row[2], row[3])   # (matched_text, start, end)
                if key not in seen:
                    seen.add(key)
                    results.append(row)
        return results

    def _detect_chunk(
        self, chunk: str, offset: int
    ) -> list[tuple[str, str, int, int, float]]:
        """Run GLiNER on a single chunk and return detections with global offsets."""
        entities = self.model.predict_entities(
            chunk, self.labels, threshold=self.threshold
        )
        results: list[tuple[str, str, int, int, float]] = []
        for ent in entities:
            matched = ent["text"]
            # Multi-line spans are GLiNER hallucinations — they span paragraph
            # boundaries and suppress narrower, correct detections.
            if "\n" in matched:
                continue
            canonical = LABEL_MAP.get(ent["label"].lower(), ent["label"].upper())
            results.append((
                canonical,
                matched,
                ent["start"] + offset,   # translate to global text position
                ent["end"] + offset,
                ent["score"],
            ))
        return results
