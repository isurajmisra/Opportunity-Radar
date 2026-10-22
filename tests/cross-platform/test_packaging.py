from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMP_BASE = ROOT / ".test-tmp"
TEMP_BASE.mkdir(exist_ok=True)


class CrossPlatformPackagingTests(unittest.TestCase):
    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, capture_output=True, text=True)

    def test_generated_distributions_are_current(self) -> None:
        result = self.run_script(ROOT / "scripts" / "build-distributions.py", "--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_host_skill_paths_and_metadata(self) -> None:
        packages = {
            "claude-code": ".claude/skills/opportunity-radar",
            "codex": ".agents/skills/opportunity-radar",
            "github-copilot": ".github/skills/opportunity-radar",
        }
        for host, rel in packages.items():
            with self.subTest(host=host):
                skill = ROOT / "dist" / host / rel / "SKILL.md"
                text = skill.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\n"))
                self.assertIn("name: opportunity-radar", text.split("---", 2)[1])
                self.assertIn("description:", text.split("---", 2)[1])
                self.assertTrue((skill.parent / "references" / "scoring-rubric.md").is_file())
                self.assertTrue((skill.parent / "scripts" / "provider_usage.py").is_file())

    def test_capability_states_and_synthetic_schema_fixture(self) -> None:
        values = json.loads((ROOT / "evals/cross-platform/capability-matrix.json").read_text(encoding="utf-8"))
        allowed = set(values["status_values"])
        for features in values["hosts"].values():
            self.assertEqual(set(features.values()) - allowed, set())
        schema = json.loads((ROOT / "core/opportunity-radar/templates/source-record.schema.json").read_text(encoding="utf-8"))
        fixture = json.loads((ROOT / "evals/cross-platform/source-record-fixture.json").read_text(encoding="utf-8"))
        self.assertTrue(set(schema["required"]).issubset(fixture))
        self.assertEqual(set(fixture) - set(schema["properties"]), set())

    def test_dry_run_and_install_do_not_clobber_without_force(self) -> None:
        target = TEMP_BASE / "installer-project"
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
        try:
            dry = self.run_script(ROOT / "scripts/install.py", "--platform", "codex", "--project", "--target-root", str(target), "--dry-run")
            self.assertEqual(dry.returncode, 0, dry.stdout + dry.stderr)

            old_agents = target / "AGENTS.md"
            old_agents.write_text("keep me\n", encoding="utf-8")
            denied = self.run_script(ROOT / "scripts/install.py", "--platform", "codex", "--project", "--target-root", str(target))
            self.assertEqual(denied.returncode, 3, denied.stdout + denied.stderr)
            self.assertEqual(old_agents.read_text(encoding="utf-8"), "keep me\n")

            updated = self.run_script(ROOT / "scripts/install.py", "--platform", "codex", "--project", "--target-root", str(target), "--force")
            self.assertEqual(updated.returncode, 0, updated.stdout + updated.stderr)
            self.assertTrue((target / ".agents/skills/opportunity-radar/SKILL.md").is_file())
            self.assertTrue(list((target / ".opportunity-radar-backups").rglob("AGENTS.md")))
        finally:
            shutil.rmtree(target)


if __name__ == "__main__":
    unittest.main()
