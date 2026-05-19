"""
Download GLiNER models for offline/air-gapped use.

Sources (tried in order):
  1. GLINER_MODEL_SOURCE env var (URL to zip in GitHub release or Azure Blob)
  2. Direct from Hugging Face (requires internet)

Usage:
  python scripts/download_models_offline.py
"""
import os
import sys
import zipfile
from pathlib import Path

import requests


GLINER_MODEL_ID = "urchade/gliner_multi_pii-v1"
DEFAULT_DEST = Path("./models/gliner_multi_pii-v1")


def download_from_url(url: str, dest: Path) -> bool:
    """Download a zip from URL and extract to dest."""
    print(f"Trying: {url}")
    try:
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"  failed: {e}")
        return False
    
    total = int(response.headers.get("content-length", 0))
    zip_path = dest.parent / "model_download.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    downloaded = 0
    with open(zip_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = downloaded * 100 / total
                print(f"\r  {downloaded/1024**2:.0f}/{total/1024**2:.0f} MB ({pct:.0f}%)", end="")
    print()
    
    print(f"  extracting to {dest}")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(dest.parent)
    zip_path.unlink()
    return True


def download_from_huggingface(model_id: str, dest: Path) -> bool:
    """Fallback: direct from Hugging Face Hub."""
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("huggingface_hub not installed. Run: pip install huggingface_hub")
        return False
    
    print(f"Trying Hugging Face direct: {model_id}")
    try:
        snapshot_download(
            repo_id=model_id,
            local_dir=str(dest),
            local_dir_use_symlinks=False,
        )
        return True
    except Exception as e:
        print(f"  failed: {e}")
        return False


def main() -> int:
    dest = Path(os.getenv("GLINER_MODEL_PATH", str(DEFAULT_DEST)))
    
    if (dest / "config.json").exists():
        print(f"✓ Model already present at {dest}")
        return 0
    
    sources = []
    
    # Custom source via env var (your GitHub release, Azure Blob URL, etc.)
    if custom := os.getenv("GLINER_MODEL_SOURCE"):
        sources.append(("custom", custom))
    
    # Try Hugging Face direct as fallback
    sources.append(("huggingface", GLINER_MODEL_ID))
    
    for source_type, source in sources:
        if source_type == "huggingface":
            if download_from_huggingface(source, dest):
                print(f"\n✓ Model downloaded to {dest}")
                print(f"\nNow set in your .env:")
                print(f"  GLINER_MODEL_PATH={dest.resolve()}")
                return 0
        else:
            if download_from_url(source, dest):
                print(f"\n✓ Model downloaded to {dest}")
                print(f"\nNow set in your .env:")
                print(f"  GLINER_MODEL_PATH={dest.resolve()}")
                return 0
    
    print("\n✗ All sources failed.")
    print("Manual fallback:")
    print("  1. Download from another machine with internet")
    print("  2. Copy the folder to ./models/gliner_multi_pii-v1/")
    print("  3. Set GLINER_MODEL_PATH in .env")
    return 1


if __name__ == "__main__":
    sys.exit(main())