#!/usr/bin/env python3
"""
Sanity check — run this BEFORE asking Claude Code to build the project.
Verifies your laptop has everything needed.

Usage:
    python check_environment.py
"""
import importlib
import shutil
import subprocess
import sys
from pathlib import Path


GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"


def check_python():
    """Python 3.11+ required."""
    v = sys.version_info
    ok = v.major == 3 and v.minor >= 11
    status = f"{GREEN}OK{RESET}" if ok else f"{RED}FAIL{RESET}"
    msg = f"  Python {v.major}.{v.minor}.{v.micro}"
    if not ok:
        msg += f" {RED}(need 3.11+){RESET}"
    print(f"{status}  Python version       {msg}")
    return ok


def check_pip():
    """Pip should be functional."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True, text=True, timeout=10
        )
        ok = result.returncode == 0
        status = f"{GREEN}OK{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"{status}  pip                  {result.stdout.strip().split()[1] if ok else 'not found'}")
        return ok
    except Exception as e:
        print(f"{RED}FAIL{RESET}  pip                  {e}")
        return False


def check_git():
    """Git should be installed."""
    git_path = shutil.which("git")
    if git_path:
        print(f"{GREEN}OK{RESET}  git                  {git_path}")
        return True
    print(f"{RED}FAIL{RESET}  git                  not found")
    return False


def check_optional_package(name: str, import_name: str | None = None) -> bool:
    """Check if a package is installed (informational only)."""
    import_name = import_name or name
    try:
        importlib.import_module(import_name)
        print(f"{GREEN}OK{RESET}  {name:20s} installed")
        return True
    except ImportError:
        print(f"{YELLOW}-{RESET}   {name:20s} not installed (will install via requirements.txt)")
        return False


def check_disk_space(min_gb: int = 5):
    """Need ~5GB free for GLiNER + torch + model caches."""
    try:
        path = Path.home()
        usage = shutil.disk_usage(path)
        free_gb = usage.free / (1024 ** 3)
        ok = free_gb >= min_gb
        status = f"{GREEN}OK{RESET}" if ok else f"{YELLOW}WARN{RESET}"
        msg = f"{free_gb:.1f} GB free in {path}"
        if not ok:
            msg += f" {YELLOW}(need ~{min_gb} GB){RESET}"
        print(f"{status}  Disk space           {msg}")
        return ok
    except Exception as e:
        print(f"{YELLOW}?{RESET}   Disk space           {e}")
        return True


def check_ollama_optional():
    """Ollama is optional for Phase 1 but needed for Phase 3."""
    ollama_path = shutil.which("ollama")
    if ollama_path:
        print(f"{GREEN}OK{RESET}  Ollama (optional)    {ollama_path}")
        try:
            result = subprocess.run(
                ["ollama", "list"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                models = [
                    line.split()[0]
                    for line in result.stdout.strip().split("\n")[1:]
                    if line.strip()
                ]
                if "llama3.1:8b" in models or any("llama3.1" in m for m in models):
                    print(f"     llama3.1 model found: {models}")
                else:
                    print(f"{YELLOW}     No llama3.1 model. Run: ollama pull llama3.1:8b{RESET}")
            else:
                print(f"{YELLOW}     Ollama installed but not running. Start with: ollama serve{RESET}")
        except Exception:
            print(f"{YELLOW}     Could not check Ollama models{RESET}")
        return True
    print(f"{YELLOW}-{RESET}   Ollama (optional)    not installed (Phase 3 will degrade gracefully)")
    return False


def check_files_present():
    """Verify all bootstrap files are in the current directory."""
    expected = {
        "CLAUDE.md": "The spec for Claude Code",
        "README.md": "Project README",
        "pyproject.toml": "Project metadata",
        "requirements.txt": "Python dependencies",
        ".gitignore": "Git ignore rules",
        ".env.example": "Env template",
        "config/settings.yaml": "Pipeline config",
    }
    all_ok = True
    print(f"\n{BOLD}Bootstrap files:{RESET}")
    for path, desc in expected.items():
        if Path(path).exists():
            print(f"{GREEN}OK{RESET}  {path:30s} {desc}")
        else:
            print(f"{RED}FAIL{RESET}  {path:30s} {desc}  ← MISSING")
            all_ok = False
    return all_ok


def main():
    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  CV PII Tool — Environment Sanity Check{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}\n")

    print(f"{BOLD}System:{RESET}")
    py_ok = check_python()
    pip_ok = check_pip()
    git_ok = check_git()
    disk_ok = check_disk_space()

    print(f"\n{BOLD}Optional services:{RESET}")
    ollama_ok = check_ollama_optional()

    files_ok = check_files_present()

    print()
    print(f"{BOLD}{'=' * 60}{RESET}")

    blockers = []
    if not py_ok:
        blockers.append("Python 3.11+ required — install from python.org")
    if not pip_ok:
        blockers.append("pip not functional")
    if not git_ok:
        blockers.append("git not installed")
    if not files_ok:
        blockers.append("Bootstrap files missing — re-download from source")

    warnings = []
    if not disk_ok:
        warnings.append("Low disk space — GLiNER + torch need ~3 GB")
    if not ollama_ok:
        warnings.append("Ollama not installed — Phase 3 will be skipped (Phase 1 still works)")

    if blockers:
        print(f"{RED}{BOLD}  ✗ NOT READY — fix blockers first:{RESET}")
        for b in blockers:
            print(f"    {RED}- {b}{RESET}")
        sys.exit(1)
    elif warnings:
        print(f"{YELLOW}{BOLD}  ⚠ READY with warnings:{RESET}")
        for w in warnings:
            print(f"    {YELLOW}- {w}{RESET}")
        print(f"\n{GREEN}  You can proceed. Open Claude Code and hand it CLAUDE.md.{RESET}")
        sys.exit(0)
    else:
        print(f"{GREEN}{BOLD}  ✓ ALL CHECKS PASSED{RESET}")
        print(f"\n{GREEN}  Open Claude Code and hand it CLAUDE.md.{RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
