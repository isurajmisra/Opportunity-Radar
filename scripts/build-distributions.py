#!/usr/bin/env python3
"""Build reproducible, self-contained Claude Code, Codex, and Copilot packages."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core" / "opportunity-radar"
DIST = ROOT / "dist"
MARKER = ".opportunity-radar-generated.json"


def skill_text(host: str) -> str:
    text = (CORE / "SKILL.md").read_text(encoding="utf-8")
    if host == "claude-code":
        text = text.replace(
            "description: Research one or more countries to discover and rigorously challenge business opportunities across software, services, ecommerce, physical products, manufacturing, distribution and local markets. Use when asked what business to start or what opportunity is emerging in a country.\n---",
            "description: Research one or more countries to discover and rigorously challenge business opportunities across software, services, ecommerce, physical products, manufacturing, distribution and local markets. Use when asked what business to start or what opportunity is emerging in a country.\nargument-hint: \"<country or countries> [optional constraints]\"\nuser-invocable: true\n---",
            1,
        )
        text = text.replace(
            "Use the user's request as the input. Host-specific invocation details belong in the adapter, not in this methodology.",
            "Treat the text after `/opportunity-radar` as the user's request and parse it as the input. Host-specific invocation details belong in the adapter, not in this methodology.",
            1,
        )
    return text


def package_files(host: str) -> dict[str, bytes]:
    skill_root = {
        "claude-code": ".claude/skills/opportunity-radar",
        "codex": ".agents/skills/opportunity-radar",
        "github-copilot": ".github/skills/opportunity-radar",
    }[host]
    files = {
        f"{skill_root}/{path.relative_to(CORE).as_posix()}": path.read_bytes()
        for path in CORE.rglob("*") if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }
    files[f"{skill_root}/SKILL.md"] = skill_text(host).encode("utf-8")
    files[f"{skill_root}/VERSION"] = (ROOT / "VERSION").read_bytes()
    adapter_root = ROOT / "adapters" / host
    files["README.md"] = (adapter_root / "README.md").read_bytes()
    if host == "claude-code":
        agent_root = ROOT / "adapters" / "claude-code" / "agents"
        for path in agent_root.glob("*.md"):
            files[f".claude/agents/{path.name}"] = path.read_bytes()
    elif host == "codex":
        files["AGENTS.md"] = (adapter_root / "AGENTS.md").read_bytes()
    else:
        files[".github/copilot-instructions.md"] = (adapter_root / "copilot-instructions.md").read_bytes()
    files[MARKER] = json.dumps({"generated_by": "scripts/build-distributions.py", "host": host}, indent=2).encode("utf-8") + b"\n"
    return files


def tree_digest(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name, data in sorted(files.items()):
        digest.update(name.encode("utf-8"))
        digest.update(data)
    return digest.hexdigest()


def disk_digest(directory: Path) -> tuple[dict[str, bytes], str]:
    files = {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
    return files, tree_digest(files)


def build_all() -> list[Path]:
    outputs = []
    layouts = {
        "claude-code": ".claude/skills/opportunity-radar",
        "codex": ".agents/skills/opportunity-radar",
        "github-copilot": ".github/skills/opportunity-radar",
    }
    for host, skill_root in layouts.items():
        output = DIST / host
        if output.exists():
            if not (output / MARKER).is_file():
                raise RuntimeError(f"Refusing to replace unmarked output directory: {output}")
            shutil.rmtree(output)
        files = package_files(host)
        for relative, contents in files.items():
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contents)
        outputs.append(output)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check whether generated packages match canonical sources")
    args = parser.parse_args()
    if not (CORE / "SKILL.md").is_file():
        parser.error(f"Canonical skill missing: {CORE / 'SKILL.md'}")
    if args.check:
        stale = []
        for host in ("claude-code", "codex", "github-copilot"):
            expected = package_files(host)
            existing = DIST / host
            if not existing.is_dir() or disk_digest(existing)[1] != tree_digest(expected):
                stale.append(host)
        if stale:
            print("Stale or missing distributions: " + ", ".join(stale))
            return 1
        print("Generated distributions match canonical sources.")
        return 0
    outputs = build_all()
    print(f"Built distributions in {DIST}")
    for output in outputs:
        _, digest = disk_digest(output)
        print(f"- {output.relative_to(ROOT)} ({digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
