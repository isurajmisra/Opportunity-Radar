#!/usr/bin/env python3
"""Check required sections, obvious evidence gaps and links in a completed run."""
from __future__ import annotations
import re, sys
from pathlib import Path

REQUIRED = ["00-executive-summary.md", "01-country-snapshot.md", "02-signal-inventory.md", "03-opportunity-shortlist.md", "evidence-ledger.md", "red-team-review.md", "validation-plan.md", "founder-review.md", "sources.md", "run-log.md"]
WARNINGS: list[str] = []
ERRORS: list[str] = []

def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_run.py <run-folder>")
        return 2
    run = Path(sys.argv[1]).resolve()
    if not run.is_dir():
        print(f"Not a directory: {run}")
        return 2
    for name in REQUIRED:
        p = run / name
        if not p.is_file(): ERRORS.append(f"Missing required file: {name}")
    if not (run / "research-usage.md").is_file():
        WARNINGS.append("research-usage.md missing; required for runs created with the multi-source workflow")
    for name in REQUIRED:
        p = run / name
        if p.is_file():
            text = p.read_text(encoding="utf-8", errors="replace")
            if "{{" in text and "}}" in text:
                WARNINGS.append(f"Unfilled template token(s): {name}")
            if name in ("00-executive-summary.md", "03-opportunity-shortlist.md") and len(text.strip()) < 80:
                WARNINGS.append(f"Very short report file: {name}")
    dossiers = list((run / "opportunities").glob("*.md")) if (run / "opportunities").is_dir() else []
    if not dossiers:
        print("No opportunity dossiers found; this is acceptable if no candidates passed the evidence gate.")
    sources = (run / "sources.md").read_text(encoding="utf-8", errors="replace") if (run / "sources.md").exists() else ""
    if len(re.findall(r"https?://", sources)) < 3:
        WARNINGS.append("Fewer than three source URLs in sources.md; verify source threshold or record insufficient evidence.")
    all_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in run.rglob("*.md"))
    for suspicious in ("proven business", "guaranteed success", "will definitely succeed"):
        if suspicious.lower() in all_text.lower():
            WARNINGS.append(f"Review potentially overconfident phrase: {suspicious}")
    print(f"Run folder: {run}")
    print(f"Opportunity dossiers: {len(dossiers)}")
    if WARNINGS:
        print("\nWARNINGS:")
        for w in WARNINGS: print(f"- {w}")
    if ERRORS:
        print("\nERRORS:")
        for e in ERRORS: print(f"- {e}")
        return 1
    print("\nStructural checks passed. Human review is still required for source correctness, dates, evidence independence and reasoning.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
