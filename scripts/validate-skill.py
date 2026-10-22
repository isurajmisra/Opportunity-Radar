#!/usr/bin/env python3
"""Validate canonical metadata, host packages, adapter files, and build freshness."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core" / "opportunity-radar"
ERRORS: list[str] = []


def check(ok: bool, message: str) -> None:
    if not ok:
        ERRORS.append(message)


def frontmatter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return ""
    return text.split("---", 2)[1]


def file_map(directory: Path) -> dict[str, bytes]:
    return {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob("*") if p.is_file()}


def main() -> int:
    main_skill = CORE / "SKILL.md"
    fm = frontmatter(main_skill)
    check(bool(fm), "Canonical SKILL.md needs YAML frontmatter")
    check(bool(re.search(r"(?m)^name:\s*opportunity-radar\s*$", fm)), "Canonical name must be opportunity-radar")
    check(bool(re.search(r"(?m)^description:\s*.+", fm)), "Canonical description is required")
    canonical_body = main_skill.read_text(encoding="utf-8")
    for forbidden in ("${CLAUDE_SKILL_DIR}", "$ARGUMENTS", ".claude/skills/"):
        check(forbidden not in canonical_body, f"Canonical methodology contains host-specific token: {forbidden}")

    agent_files = list((ROOT / "adapters" / "claude-code" / "agents").glob("*.md"))
    check(len(agent_files) == 6, f"Expected six preserved Claude specialist agents; found {len(agent_files)}")
    for agent in agent_files:
        afm = frontmatter(agent)
        check(bool(re.search(r"(?m)^name:\s*\S+", afm)), f"Agent missing name: {agent.name}")
        check(bool(re.search(r"(?m)^description:\s*.+", afm)), f"Agent missing description: {agent.name}")

    cases = (ROOT / "evals" / "cases.md").read_text(encoding="utf-8")
    check(len(re.findall(r"(?m)^## Case \d+", cases)) >= 10, "At least ten evaluation scenarios are required")
    for enum in (ROOT / "evals" / "cross-platform").glob("*.json"):
        try:
            json.loads(enum.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            ERRORS.append(f"Invalid fixture {enum}: {exc}")

    cmd = [sys.executable, str(ROOT / "scripts" / "build-distributions.py"), "--check"]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        ERRORS.append((result.stdout + result.stderr).strip() or "Generated distributions are stale")
    else:
        print(result.stdout.strip())

    for host, skill_rel, adapter_rel in (
        ("claude-code", ".claude/skills/opportunity-radar", ".claude/agents"),
        ("codex", ".agents/skills/opportunity-radar", "AGENTS.md"),
        ("github-copilot", ".github/skills/opportunity-radar", ".github/copilot-instructions.md"),
    ):
        package = ROOT / "dist" / host
        check((package / skill_rel / "SKILL.md").is_file(), f"Missing {host} skill entry point")
        check((package / adapter_rel).exists(), f"Missing {host} adapter file(s)")
        if (package / skill_rel / "SKILL.md").is_file():
            nested = subprocess.run(
                [sys.executable, str(package / skill_rel / "scripts" / "validate_package.py")],
                cwd=ROOT, capture_output=True, text=True,
            )
            if nested.returncode:
                ERRORS.append(f"{host} package validation failed:\n{nested.stdout}{nested.stderr}")

    installed = (
        ("Claude Code project adapter", ROOT / ".claude/skills/opportunity-radar", ROOT / "dist/claude-code/.claude/skills/opportunity-radar"),
        ("Claude Code specialist agents", ROOT / ".claude/agents", ROOT / "dist/claude-code/.claude/agents"),
        ("Codex project adapter", ROOT / ".agents/skills/opportunity-radar", ROOT / "dist/codex/.agents/skills/opportunity-radar"),
        ("Codex project instructions", ROOT / "AGENTS.md", ROOT / "dist/codex/AGENTS.md"),
        ("Copilot project adapter", ROOT / ".github/skills/opportunity-radar", ROOT / "dist/github-copilot/.github/skills/opportunity-radar"),
        ("Copilot project instructions", ROOT / ".github/copilot-instructions.md", ROOT / "dist/github-copilot/.github/copilot-instructions.md"),
    )
    for label, actual, expected in installed:
        if actual.is_dir() and expected.is_dir():
            check(file_map(actual) == file_map(expected), f"{label} is stale; rebuild and reinstall its project adapter")
        elif actual.is_file() and expected.is_file():
            check(actual.read_bytes() == expected.read_bytes(), f"{label} is stale; reinstall its project adapter")
        else:
            check(False, f"Missing {label}; install the project adapter")

    if ERRORS:
        print("VALIDATION ERRORS:")
        for error in ERRORS:
            print(f"- {error}")
        return 1
    print("Canonical skill, six Claude agents, generated packages, resource paths, and eval coverage passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
