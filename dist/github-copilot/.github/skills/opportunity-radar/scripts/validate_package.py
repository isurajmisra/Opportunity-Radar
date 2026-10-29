#!/usr/bin/env python3
"""Dependency-free structural validation for a self-contained skill package."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []
WARNINGS: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        ERRORS.append(message)


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        ERRORS.append(f"Cannot read {path}: {exc}")
        return ""


def main() -> int:
    main_skill = SKILL / "SKILL.md"
    text = read(main_skill)
    check(text.startswith("---\n"), "Main skill missing YAML frontmatter")
    front = text.split("---", 2)[1] if text.startswith("---\n") and text.count("---") >= 2 else ""
    for key in ("name:", "description:"):
        check(key in front, f"Main skill missing required frontmatter field {key}")
    check("name: opportunity-radar" in front, "Skill name must be opportunity-radar")

    for path in SKILL.rglob("*.md"):
        body = read(path)
        for target in re.findall(r"\]\(([^)]+)\)", body):
            if re.match(r"^[a-zA-Z]+://", target) or target.startswith("#"):
                continue
            candidate = (path.parent / target.split("#", 1)[0]).resolve()
            if target.split("#", 1)[0] and not candidate.exists():
                WARNINGS.append(f"Link may be unresolved in {path.relative_to(SKILL)}: {target}")

    required = [
        "references/source-hierarchy.md", "references/country-research-playbook.md",
        "references/signal-taxonomy.md", "references/scoring-rubric.md",
        "references/unit-economics-playbook.md", "references/founder-skill-integration.md",
        "references/validation-experiment-playbook.md", "references/privacy-and-research-safety.md",
        "references/source-catalog.md", "references/report-quality-checklist.md",
        "references/tavily-research-routing.md", "config/research-budget.json",
        "config/provider-policy.json", "scripts/brave_search.py", "scripts/init_run.py",
        "references/research-workstreams.md", "references/provider-adapters.md",
        "scripts/provider_usage.py", "scripts/research_ledger.py", "scripts/run_lock.py", "scripts/validate_run.py",
        "templates/source-record.schema.json", "templates/research-usage.md",
        "templates/opportunity-brief.md", "templates/sources.md", "templates/evidence-ledger.md",
        "templates/validation-plan.md", "tests/test_research_ledger.py",
    ]
    for rel in required:
        check((SKILL / rel).is_file(), f"Missing required package file: {rel}")

    schema = SKILL / "templates" / "source-record.schema.json"
    if schema.is_file():
        try:
            json.loads(read(schema))
        except json.JSONDecodeError as exc:
            ERRORS.append(f"Source-record schema is not valid JSON: {exc}")

    for filename in ("research-budget.json", "provider-policy.json"):
        path = SKILL / "config" / filename
        if not path.is_file():
            continue
        try:
            config = json.loads(read(path))
            for profile in ("quick", "deep"):
                check(profile in config.get("profiles", config.get("total_operations", {})),
                      f"{filename}: missing {profile} profile")
        except json.JSONDecodeError as exc:
            ERRORS.append(f"{filename} is not valid JSON: {exc}")

    print(f"Skill directory: {SKILL}")
    if WARNINGS:
        print("\nWARNINGS:")
        for item in WARNINGS:
            print(f"- {item}")
    if ERRORS:
        print("\nERRORS:")
        for item in ERRORS:
            print(f"- {item}")
        return 1
    print("\nSelf-contained skill package checks passed. Runtime tool availability is environment-specific.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
