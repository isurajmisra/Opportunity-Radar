#!/usr/bin/env python3
"""Check required sections, obvious evidence gaps and links in a completed run."""
from __future__ import annotations
import json
import re, sys
from pathlib import Path

REQUIRED = ["00-executive-summary.md", "01-country-snapshot.md", "02-signal-inventory.md", "03-opportunity-shortlist.md", "evidence-ledger.md", "red-team-review.md", "validation-plan.md", "founder-review.md", "sources.md", "run-log.md"]
WARNINGS: list[str] = []
ERRORS: list[str] = []
LOCAL_FAILURE_STATUSES = {"invocation_failed", "preflight_failed", "not_attempted", "not_run"}
INVOCATION_ERROR = re.compile(r"(?i)(unexpected keyword argument|no such option|unrecognized arguments|invalid choice|usage:)")
RECONCILIATION_MARKERS = ("<!-- OPPORTUNITY_RADAR_USAGE_START -->", "<!-- OPPORTUNITY_RADAR_USAGE_END -->")


def counts_as_provider_attempt(operation: dict) -> bool:
    """Mirror the ledgers' distinction between local failures and provider attempts."""
    return (operation.get("status") not in LOCAL_FAILURE_STATUSES
            and not INVOCATION_ERROR.search(str(operation.get("error") or "")))


def reconciliation_values(text: str) -> dict[str, int] | None:
    """Read the explicit machine-check block; free-form prose is deliberately ignored."""
    start, end = RECONCILIATION_MARKERS
    if start not in text or end not in text:
        return None
    block = text.split(start, 1)[1].split(end, 1)[0]
    labels = {
        "ledger_entries": r"Ledger entries \(all providers\)",
        "provider_attempts": r"Provider attempts \(all providers\)",
        "tavily_credits": r"Tavily credits charged to run budget",
    }
    values = {}
    for key, label in labels.items():
        matches = re.findall(rf"(?m)^- {label}:\s*(\d+)\s*$", block)
        if len(matches) != 1:
            return None
        values[key] = int(matches[0])
    return values


def validate_usage_reconciliation(run: Path, ledger_data: dict | None,
                                  provider_data: dict | None) -> None:
    tavily_ops = (ledger_data or {}).get("operations", [])
    other_ops = [op for op in (provider_data or {}).get("operations", [])
                 if op.get("provider") != "tavily"]
    expected = {
        "ledger_entries": len(tavily_ops) + len(other_ops),
        "provider_attempts": sum(counts_as_provider_attempt(op) for op in tavily_ops + other_ops),
        "tavily_credits": sum(
            op.get("actual_credits") if op.get("actual_credits") is not None else op.get("est_credits", 0)
            for op in tavily_ops if counts_as_provider_attempt(op)),
    }
    settings = (ledger_data or {}).get("settings", {})
    strict = max(int(settings.get("report_reconciliation_version", 0) or 0),
                 int((provider_data or {}).get("report_reconciliation_version", 0) or 0)) >= 1
    for filename in ("00-executive-summary.md", "run-log.md"):
        path = run / filename
        if not path.is_file():
            continue
        values = reconciliation_values(path.read_text(encoding="utf-8", errors="replace"))
        if values is None:
            message = f"{filename} is missing a complete usage reconciliation block."
            (ERRORS if strict else WARNINGS).append(message)
            continue
        for key, expected_value in expected.items():
            if values[key] != expected_value:
                ERRORS.append(f"{filename} usage reconciliation {key} is {values[key]}, "
                              f"but the ledgers record {expected_value}.")

    usage_path = run / "research-usage.md"
    if ledger_data and tavily_ops:
        if not usage_path.is_file():
            ERRORS.append("research-usage.md is required when research-ledger.json contains operations.")
        else:
            usage = usage_path.read_text(encoding="utf-8", errors="replace")
            operations_match = re.search(r"(?m)^- Operation attempts:\s*(\d+)\s+\((\d+) provider attempts\);", usage)
            credits_match = re.search(r"(?m)^- Credits used:\s*\*\*(\d+)", usage)
            tavily_attempts = sum(counts_as_provider_attempt(op) for op in tavily_ops)
            tavily_credits = expected["tavily_credits"]
            if not operations_match or tuple(map(int, operations_match.groups())) != (len(tavily_ops), tavily_attempts):
                ERRORS.append("research-usage.md Tavily operation totals do not match research-ledger.json.")
            if not credits_match or int(credits_match.group(1)) != tavily_credits:
                ERRORS.append("research-usage.md Tavily credits do not match research-ledger.json.")

    if provider_data and other_ops:
        if not usage_path.is_file():
            ERRORS.append("research-usage.md is required when provider-usage.json contains operations.")
        else:
            usage = usage_path.read_text(encoding="utf-8", errors="replace")
            combined = re.search(r"(?m)^- Local profile: .*?tracked operations:\s*\*\*(\d+)\*\*\s+\(including (\d+) Tavily", usage)
            total_attempts = expected["provider_attempts"]
            tavily_attempts = sum(counts_as_provider_attempt(op) for op in tavily_ops)
            if not combined or tuple(map(int, combined.groups())) != (total_attempts, tavily_attempts):
                ERRORS.append("research-usage.md combined provider totals do not match the usage ledgers.")

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
    ledger_path = run / "research-ledger.json"
    ledger_data = None
    provider_data = None
    if ledger_path.is_file():
        try:
            ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))
            settings = ledger_data.get("settings", {})
            dossier_limit = settings.get("max_candidates_to_dossier")
            if dossier_limit is not None and len(dossiers) > int(dossier_limit):
                ERRORS.append(f"Dossier limit exceeded: {len(dossiers)} found, run limit is {dossier_limit}.")
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            ERRORS.append("research-ledger.json has invalid run limits; dossier cap could not be verified.")
    provider_path = run / "provider-usage.json"
    if provider_path.is_file():
        try:
            provider_data = json.loads(provider_path.read_text(encoding="utf-8"))
            if not isinstance(provider_data.get("operations", []), list):
                raise ValueError("operations must be a list")
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            ERRORS.append("provider-usage.json is invalid; report operation totals could not be verified.")
    if ledger_data or provider_data:
        validate_usage_reconciliation(run, ledger_data, provider_data)
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
