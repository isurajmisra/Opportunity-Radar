#!/usr/bin/env python3
"""Create a non-overwriting Opportunity Radar run folder from bundled templates."""
from __future__ import annotations
import argparse, datetime, re, shutil, sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = SKILL_DIR / "templates"
DEFAULT_ROOT = Path.cwd() / "opportunity-radar-runs"
TEMPLATE_MAP = {
    "00-executive-summary.md": "00-executive-summary.md",
    "01-country-snapshot.md": "01-country-snapshot.md",
    "02-signal-inventory.md": "02-signal-inventory.md",
    "03-opportunity-shortlist.md": "03-opportunity-shortlist.md",
    "evidence-ledger.md": "evidence-ledger.md",
    "red-team-review.md": "red-team-review.md",
    "validation-plan.md": "validation-plan.md",
    "founder-review.md": "founder-review.md",
    "sources.md": "sources.md",
    "run-log.md": "run-log.md",
    "research-usage.md": "research-usage.md",
}

def slugify(value: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return s or "research-run"

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("countries", help="Country name or comma-separated countries")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--date", default=datetime.date.today().isoformat())
    args = parser.parse_args()
    country_slug = slugify(args.countries.replace(",", "-"))
    base = args.output_root / f"{args.date}-{country_slug}"
    dest = base
    suffix = 2
    while dest.exists():
        dest = base.with_name(f"{base.name}-{suffix:02d}")
        suffix += 1
    dest.mkdir(parents=True)
    (dest / "opportunities").mkdir()
    (dest / "research-notes").mkdir()
    for target_name, source_name in TEMPLATE_MAP.items():
        source = TEMPLATE_DIR / source_name
        if not source.is_file():
            print(f"ERROR: required template missing: {source}", file=sys.stderr)
            return 2
        shutil.copyfile(source, dest / target_name)
    run_log = dest / "run-log.md"
    text = run_log.read_text(encoding="utf-8").replace("{{RUN_ID}}", dest.name)
    text = text.replace("{{DATE}}", args.date).replace("{{COUNTRIES}}", args.countries)
    run_log.write_text(text, encoding="utf-8")
    summary = dest / "00-executive-summary.md"
    text = summary.read_text(encoding="utf-8").replace("{{RUN_NAME}}", dest.name)
    text = text.replace("{{DATE}}", args.date).replace("{{COUNTRIES}}", args.countries)
    summary.write_text(text, encoding="utf-8")
    print(dest.resolve())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
