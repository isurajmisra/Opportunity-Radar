#!/usr/bin/env python3
"""Run the bundled report validator over historical runs without editing them."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "core" / "opportunity-radar" / "scripts" / "validate_run.py"
RUNS = ROOT / "opportunity-radar-runs"


def main() -> int:
    folders = sorted(p for p in RUNS.iterdir() if p.is_dir()) if RUNS.is_dir() else []
    if not folders:
        print(f"No research runs found under {RUNS}")
        return 0
    failed = []
    for folder in folders:
        result = subprocess.run([sys.executable, str(VALIDATOR), str(folder)], cwd=ROOT, capture_output=True, text=True)
        print(f"[{ 'PASS' if result.returncode == 0 else 'FAIL' }] {folder.name}")
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.stderr.strip():
            print(result.stderr.strip())
        if result.returncode:
            failed.append(folder.name)
    if failed:
        print("Runs requiring repair: " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
