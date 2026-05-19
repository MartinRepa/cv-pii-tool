#!/usr/bin/env python3
"""
Download GLiNER model for offline / air-gapped deployment.

Usage
-----
# Download from Hugging Face (default):
    python scripts/download_models_offline.py

# Download from a corporate mirror zip instead:
    GLINER_MODEL_SOURCE=https://mirror.corp/gliner_multi_pii-v1.zip \\
    GLINER_MODEL_PATH=/opt/models/gliner_multi_pii-v1 \\
    python scripts/download_models_offline.py

Environment variables
---------------------
GLINER_MODEL_SOURCE
    URL to a .zip archive containing the model files.
    If set, the script downloads the zip and extracts it to GLINER_MODEL_PATH.
    Falls back to huggingface_hub.snapshot_download if the download fails.

GLINER_MODEL_PATH
    Local directory where the model will be stored.
    Default: ``./models/gliner_multi_pii-v1``

GLINER_MODEL_ID
    Hugging Face model identifier.
    Default: ``urchade/gliner_multi_pii-v1``

HTTP_PROXY / HTTPS_PROXY
    Proxy URL for corporate networks.

REQUESTS_CA_BUNDLE / SSL_CERT_FILE
    Path to corporate CA certificate bundle.

Behaviour
---------
- Idempotent: exits success if ``config.json`` already exists in the target dir.
- Prints download progress in MB.
- Verifies ``config.json`` is present before reporting success.
- Exit code 0 = success, 1 = failure.
"""
from __future__ import annotations

import os
import sys
import zipfile
import tempfile
from pathlib import Path

# ── defaults ──────────────────────────────────────────────────────────────────
DEFAULT_MODEL_ID = "urchade/gliner_multi_pii-v1"
DEFAULT_MODEL_PATH = Path("models") / "gliner_multi_pii-v1"

MODEL_SOURCE = os.getenv("GLINER_MODEL_SOURCE", "")
MODEL_PATH = Path(os.getenv("GLINER_MODEL_PATH", str(DEFAULT_MODEL_PATH)))
MODEL_ID = os.getenv("GLINER_MODEL_ID", DEFAULT_MODEL_ID)


# ── helpers ───────────────────────────────────────────────────────────────────

def _is_already_present(dest: Path) -> bool:
    """Return True if the model folder already contains config.json."""
    return (dest / "config.json").exists()


def _make_session():
    """Return a requests.Session honouring corporate proxy / CA settings."""
    import requests

    session = requests.Session()
    proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    ca_bundle = os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("SSL_CERT_FILE")
    if proxy:
        session.proxies = {
            "http": os.getenv("HTTP_PROXY", proxy),
            "https": os.getenv("HTTPS_PROXY", proxy),
        }
    if ca_bundle:
        session.verify = ca_bundle
    return session


def _download_zip(url: str, dest: Path) -> bool:
    """
    Download a zip from *url* and extract to *dest*.

    Returns True on success, False on any error (caller falls back to HF Hub).
    """
    try:
        import requests  # noqa: F401 (checked at top of function)
    except ImportError:
        print("ERROR: 'requests' is not installed. Run: pip install requests", file=sys.stderr)
        return False

    session = _make_session()

    print(f"Downloading model zip from: {url}")
    try:
        resp = session.get(url, stream=True, timeout=300)
        resp.raise_for_status()
    except Exception as exc:
        print(f"WARNING: Download failed ({exc}) — falling back to Hugging Face Hub.", file=sys.stderr)
        return False

    total_bytes = int(resp.headers.get("Content-Length", 0))
    total_mb = total_bytes / 1_048_576 if total_bytes else 0
    downloaded = 0

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        for chunk in resp.iter_content(chunk_size=1_048_576):  # 1 MB chunks
            if chunk:
                tmp.write(chunk)
                downloaded += len(chunk)
                done_mb = downloaded / 1_048_576
                if total_mb:
                    pct = downloaded / total_bytes * 100
                    print(f"\r  {done_mb:.1f} / {total_mb:.1f} MB  ({pct:.0f}%)", end="", flush=True)
                else:
                    print(f"\r  {done_mb:.1f} MB downloaded", end="", flush=True)
    print()  # newline after progress

    # Extract
    print(f"Extracting to {dest} …")
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(tmp_path) as zf:
            # Strip a single top-level directory if present (common in GitHub zips)
            members = zf.namelist()
            prefix = ""
            if members and all(m.startswith(members[0].split("/")[0] + "/") for m in members if "/" in m):
                prefix = members[0].split("/")[0] + "/"

            for member in members:
                target_name = member[len(prefix):] if prefix else member
                if not target_name:  # skip the top-level dir entry itself
                    continue
                target = dest / target_name
                if member.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        dst.write(src.read())
    except zipfile.BadZipFile as exc:
        print(f"ERROR: Downloaded file is not a valid zip: {exc}", file=sys.stderr)
        tmp_path.unlink(missing_ok=True)
        return False
    finally:
        tmp_path.unlink(missing_ok=True)

    return True


def _apply_corporate_network() -> None:
    """
    Ensure proxy / CA bundle env vars are set under all known names so that
    both ``requests`` (HF Hub 0.x) and ``httpx`` (HF Hub 1.x) pick them up.
    """
    proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    ca_bundle = os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("SSL_CERT_FILE")
    if proxy:
        os.environ.setdefault("HTTP_PROXY", proxy)
        os.environ.setdefault("HTTPS_PROXY", proxy)
    if ca_bundle:
        os.environ.setdefault("SSL_CERT_FILE", ca_bundle)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_bundle)

    # Try the old huggingface_hub 0.x API as well (no-ops on 1.x)
    try:
        from huggingface_hub import configure_http_backend  # type: ignore[attr-defined]
        import requests

        def _factory() -> requests.Session:
            s = requests.Session()
            if proxy:
                s.proxies = {"http": proxy, "https": proxy}
            if ca_bundle:
                s.verify = ca_bundle
            return s

        configure_http_backend(backend_factory=_factory)
    except (ImportError, AttributeError):
        pass  # huggingface_hub >= 1.0 — env vars handle it


def _download_from_hub(model_id: str, dest: Path) -> bool:
    """
    Use huggingface_hub.snapshot_download to fetch the model.

    Returns True on success, False on failure.
    """
    try:
        from huggingface_hub import snapshot_download  # type: ignore[import]
    except ImportError:
        print(
            "ERROR: 'huggingface_hub' is not installed. Run: pip install huggingface_hub",
            file=sys.stderr,
        )
        return False

    # Configure proxy / CA for both requests and httpx backends
    _apply_corporate_network()

    print(f"Downloading '{model_id}' from Hugging Face Hub …")
    dest.mkdir(parents=True, exist_ok=True)
    try:
        snapshot_download(
            repo_id=model_id,
            local_dir=str(dest),
        )
    except Exception as exc:
        print(f"ERROR: Hugging Face download failed: {exc}", file=sys.stderr)
        return False
    return True


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print(f"GLiNER model downloader")
    print(f"  Target path : {MODEL_PATH.resolve()}")
    print(f"  Model ID    : {MODEL_ID}")
    if MODEL_SOURCE:
        print(f"  Source ZIP  : {MODEL_SOURCE}")
    print()

    # Idempotent check
    if _is_already_present(MODEL_PATH):
        print(f"Model already present at {MODEL_PATH} — nothing to do.")
        return 0

    success = False

    # Path 1: custom mirror zip
    if MODEL_SOURCE:
        success = _download_zip(MODEL_SOURCE, MODEL_PATH)
        if not success:
            print("Falling back to Hugging Face Hub …")

    # Path 2: HF Hub (default or fallback)
    if not success:
        success = _download_from_hub(MODEL_ID, MODEL_PATH)

    if not success:
        print("ERROR: All download methods failed. Check the errors above.", file=sys.stderr)
        return 1

    # Verify
    if not _is_already_present(MODEL_PATH):
        print(
            f"ERROR: Download appeared to succeed but config.json is missing in {MODEL_PATH}",
            file=sys.stderr,
        )
        return 1

    print(f"\nSuccess! Model ready at: {MODEL_PATH.resolve()}")
    print(
        f"\nTo use this local model, set:\n"
        f"  GLINER_MODEL_PATH={MODEL_PATH.resolve()}\n"
        f"  HF_HUB_OFFLINE=1    # optional: prevent any future network calls"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
