#!/usr/bin/env python3
"""Install one generated Opportunity Radar package with explicit safe updates."""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def default_root(platform: str) -> Path:
    home = Path.home()
    if platform == "claude-code":
        return home / ".claude"
    if platform == "codex":
        return Path(__import__("os").environ.get("CODEX_HOME", str(home / ".codex"))).expanduser()
    return home / ".copilot"


def components(platform: str, package: Path, root: Path, project: bool) -> list[tuple[Path, Path]]:
    if platform == "claude-code":
        prefix = Path(".claude") if project else Path()
        return [
            (package / ".claude" / "skills" / "opportunity-radar", root / prefix / "skills" / "opportunity-radar"),
            (package / ".claude" / "agents", root / prefix / "agents"),
        ]
    if platform == "codex":
        if project:
            return [
                (package / ".agents" / "skills" / "opportunity-radar", root / ".agents" / "skills" / "opportunity-radar"),
                (package / "AGENTS.md", root / "AGENTS.md"),
            ]
        return [(package / ".agents" / "skills" / "opportunity-radar", root / "skills" / "opportunity-radar")]
    if project:
        return [
            (package / ".github" / "skills" / "opportunity-radar", root / ".github" / "skills" / "opportunity-radar"),
            (package / ".github" / "copilot-instructions.md", root / ".github" / "copilot-instructions.md"),
        ]
    return [(package / ".github" / "skills" / "opportunity-radar", root / "skills" / "opportunity-radar")]


def safe_relative(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return path.resolve() != root.resolve()
    except ValueError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, choices=("claude-code", "codex", "github-copilot"))
    parser.add_argument("--target-root", type=Path, help="configuration root (personal) or project root")
    parser.add_argument("--project", action="store_true", help="install project-scoped skill and host routing files")
    parser.add_argument("--dry-run", action="store_true", help="show actions without writing")
    parser.add_argument("--force", action="store_true", help="back up and replace existing destination paths")
    parser.add_argument("--show-version", action="store_true", help="show package or installed version")
    args = parser.parse_args()
    root = (args.target_root or default_root(args.platform)).expanduser().resolve()
    package = DIST / args.platform
    if args.show_version:
        version_path = (root / ".claude" / "skills" / "opportunity-radar" if args.project and args.platform == "claude-code"
                        else root / ".agents" / "skills" / "opportunity-radar" if args.project and args.platform == "codex"
                        else root / ".github" / "skills" / "opportunity-radar" if args.project and args.platform == "github-copilot"
                        else root / "skills" / "opportunity-radar" if not args.project and args.platform != "claude-code"
                        else root / "skills" / "opportunity-radar")
        candidate = version_path / "VERSION"
        if candidate.is_file():
            print(f"{args.platform}: {candidate.read_text(encoding='utf-8').strip()} ({version_path})")
        else:
            print(f"No installed Opportunity Radar version found at {version_path}")
            return 1
        return 0

    if not package.is_dir():
        print(f"Distribution not found: {package}. Run python scripts/build-distributions.py first.", file=sys.stderr)
        return 2
    pairs = components(args.platform, package, root, args.project)
    for source, target in pairs:
        if not source.exists():
            print(f"Package component missing: {source}", file=sys.stderr)
            return 2
        if not safe_relative(target, root):
            print(f"Refusing destination outside target root: {target}", file=sys.stderr)
            return 2
    conflicts = [(src, dst) for src, dst in pairs if dst.exists()]
    if conflicts and not args.force and not args.dry_run:
        print("Existing destination(s); no files changed. Review and rerun with --force to back up and replace:")
        for _, target in conflicts:
            print(f"- {target}")
        return 3
    for source, target in pairs:
        print(f"{'Would install' if args.dry_run else 'Install'}: {source} -> {target}")
    if args.dry_run and conflicts and not args.force:
        print("Existing paths will be left untouched. Pass --force to back them up and replace them.")
    if args.dry_run:
        print("Dry run complete; no files changed.")
        return 0

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    for source, target in pairs:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            backup = root / ".opportunity-radar-backups" / stamp / target.relative_to(root)
            if not safe_relative(backup, root):
                print(f"Refusing backup path outside target root: {backup}", file=sys.stderr)
                return 2
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(target, backup) if target.is_dir() else shutil.copy2(target, backup)
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            print(f"Backup: {backup}")
        shutil.copytree(source, target) if source.is_dir() else shutil.copy2(source, target)

    skill = next(dst for _, dst in pairs if dst.is_dir() and (dst / "SKILL.md").is_file())
    result = __import__("subprocess").run([sys.executable, str(skill / "scripts" / "validate_package.py")], capture_output=True, text=True)
    print(result.stdout.strip())
    if result.returncode:
        print(result.stderr.strip(), file=sys.stderr)
        return result.returncode
    print(f"Installed version { (skill / 'VERSION').read_text(encoding='utf-8').strip() }")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
