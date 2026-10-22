"""Offline tests for the Tavily research guard. No network calls and no credits are used.

Run: python -m unittest discover -s core/opportunity-radar/tests -v
"""
from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = next((p for p in Path(__file__).resolve().parents if (p / "opportunity-radar-runs").is_dir()), None)
TEMP_BASE = next((p for p in Path(__file__).resolve().parents if (p / "README.md").is_file()), Path.cwd()) / ".test-tmp"
TEMP_BASE.mkdir(exist_ok=True)

sys.path.insert(0, str(SKILL_DIR / "scripts"))
import research_ledger as rl  # noqa: E402


class FakeRunner:
    """Stands in for the tvly CLI; records calls and returns canned JSON."""

    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [])

    def __call__(self, args, timeout):
        self.calls.append(args)
        if self.responses:
            return self.responses.pop(0)
        return 0, json.dumps({"results": [{"url": "https://example.gov/a", "title": "A", "score": 0.9}]}), ""


class LedgerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = TEMP_BASE / self.id().replace(".", "_")
        if self.tmp.exists():
            shutil.rmtree(self.tmp)
        self.tmp.mkdir(parents=True)
        self.run_dir = self.tmp / "run"
        self.ledger = rl.Ledger.init(self.run_dir, "quick")

    def tearDown(self):
        if self.tmp.exists():
            shutil.rmtree(self.tmp)


class TestOperationRouting(unittest.TestCase):
    def test_search_when_no_url(self):
        op, params, _ = rl.choose_operation({})
        self.assertEqual(op, "search")
        self.assertEqual(params["depth"], "basic")

    def test_advanced_search_only_for_precision(self):
        self.assertEqual(rl.choose_operation({"precision_fact": True})[1]["depth"], "advanced")

    def test_recent_news_uses_news_topic(self):
        self.assertEqual(rl.choose_operation({"recent_news": True})[1]["topic"], "news")

    def test_extract_when_url_known(self):
        self.assertEqual(rl.choose_operation({"has_urls": True})[0], "extract")

    def test_map_before_extract_when_page_unknown(self):
        self.assertEqual(rl.choose_operation({"knows_site_not_page": True})[0], "map")

    def test_crawl_only_for_many_pages_with_limits(self):
        op, params, _ = rl.choose_operation({"needs_many_pages_same_site": True, "has_urls": True})
        self.assertEqual(op, "crawl")
        self.assertLessEqual(params["limit"], 20)
        self.assertIn("instructions", params)

    def test_research_requires_justification(self):
        self.assertEqual(rl.choose_operation({"needs_multi_source_synthesis": True})[0], "search")
        op, params, _ = rl.choose_operation({"needs_multi_source_synthesis": True, "synthesis_justified": True})
        self.assertEqual((op, params["model"]), ("research", "mini"))

    def test_dynamic_search_for_bulk_filtering(self):
        self.assertEqual(rl.choose_operation({"needs_bulk_filtering": True})[0], "dynamic-search")

    def test_cli_args_match_tavily_flags(self):
        self.assertEqual(rl.build_tvly_args("search", ["gst notices"], {"depth": "basic", "max_results": 5}),
                         ["search", "gst notices", "--depth", "basic", "--max-results", "5", "--json"])
        self.assertIn("--extract-depth", rl.build_tvly_args("extract", ["https://a.gov/x"], {"depth": "advanced"}))


class TestCreditEstimates(unittest.TestCase):
    rates = rl.load_config()["credit_rates"]

    def test_documented_vs_estimated_basis(self):
        self.assertEqual(rl.estimate_credits("search", {"depth": "advanced"}, self.rates), (2, "documented"))
        self.assertEqual(rl.estimate_credits("search", {"depth": "basic"}, self.rates)[1], "estimated")
        self.assertEqual(rl.estimate_credits("extract", {}, self.rates, n_urls=6), (2, "estimated"))
        self.assertTrue(rl.estimate_credits("research", {"model": "mini"}, self.rates)[1].startswith("unknown"))

    def test_operations_do_not_all_cost_the_same(self):
        costs = {rl.estimate_credits(op, p, self.rates)[0] for op, p in [
            ("search", {"depth": "basic"}), ("search", {"depth": "advanced"}),
            ("crawl", {"limit": 20, "instructions": "x"}), ("research", {"model": "pro"})]}
        self.assertGreater(len(costs), 2)


class TestDeduplication(LedgerTestCase):
    def test_identical_query_is_not_repeated(self):
        runner = FakeRunner()
        rl.run_operation(self.ledger, "search", ["India GST notices"], {"depth": "basic"}, runner)
        res = rl.run_operation(self.ledger, "search", ["  india   gst NOTICES "], {"depth": "basic"}, runner)
        self.assertFalse(res["executed"])
        self.assertEqual(res["decision"]["status"], rl.DUPLICATE)
        self.assertTrue(res["decision"]["reuse"].startswith(rl.CACHE_DIR))
        self.assertEqual(len(runner.calls), 1)

    def test_different_filters_are_a_new_query(self):
        runner = FakeRunner()
        rl.run_operation(self.ledger, "search", ["india gst notices"], {}, runner)
        res = rl.run_operation(self.ledger, "search", ["india gst notices"], {"include_domains": "cbic.gov.in"}, runner)
        self.assertTrue(res["executed"])

    def test_url_normalisation_and_extract_reuse(self):
        self.assertEqual(rl.normalize_url("https://WWW.Example.gov/report/?utm_source=x#top"),
                         rl.normalize_url("https://example.gov/report"))
        runner = FakeRunner([(0, json.dumps({"results": [
            {"url": "https://example.gov/report", "raw_content": "text"}]}), "")])
        rl.run_operation(self.ledger, "extract", ["https://example.gov/report"], {}, runner)
        res = rl.run_operation(self.ledger, "extract",
                               ["https://www.example.gov/report/?utm_campaign=y", "https://other.gov/b"], {}, runner)
        self.assertEqual(res["decision"]["target"], ["https://other.gov/b"])  # only the new URL is fetched
        self.assertIn("https://other.gov/b", runner.calls[-1])
        self.assertNotIn("https://www.example.gov/report/?utm_campaign=y", runner.calls[-1])


class TestBudget(LedgerTestCase):
    def test_stops_before_exceeding_budget(self):
        runner = FakeRunner([(0, json.dumps({"results": []}), "")] * 100)
        executed = 0
        for i in range(100):
            res = rl.run_operation(self.ledger, "search", [f"query {i}"], {"depth": "advanced"}, runner)
            if not res["executed"]:
                break
            executed += 1
        self.assertLessEqual(self.ledger.spent, self.ledger.limit)
        self.assertEqual(executed, 20)  # the quick-profile Tavily call guardrail is stricter than the 60-credit budget
        self.assertIn(res["decision"]["status"], (rl.NEEDS_APPROVAL, rl.STOP))
        self.assertEqual(len(runner.calls), executed)

    def test_research_needs_approval_in_quick_profile(self):
        runner = FakeRunner()
        res = rl.run_operation(self.ledger, "research", ["india msme payments"], {"model": "mini"}, runner)
        self.assertEqual(res["decision"]["status"], rl.NEEDS_APPROVAL)
        self.assertEqual(runner.calls, [])
        self.ledger.approve(credits=30, research_calls=1, reason="user approved in chat")
        res = rl.run_operation(self.ledger, "research", ["india msme payments"], {"model": "mini"}, runner)
        self.assertTrue(res["executed"])

    def test_oversized_single_operation_needs_approval(self):
        d = self.ledger.plan("map", ["https://big.gov"], {"limit": 200, "instructions": "x"})
        self.assertEqual(d["status"], rl.NEEDS_APPROVAL)

    def test_crawl_needs_approval_in_quick_but_not_deep(self):
        self.assertEqual(self.ledger.plan("crawl", ["https://a.gov"], {"limit": 10})["status"], rl.NEEDS_APPROVAL)
        deep = rl.Ledger.init(self.run_dir / "deep", "deep")
        self.assertIn(deep.plan("crawl", ["https://a.gov"], {"limit": 10})["status"], rl.RUNNABLE)

    def test_custom_budget_override(self):
        led = rl.Ledger.init(self.run_dir / "custom", "quick", budget=5)
        self.assertEqual(led.limit, 5)

    def test_plan_limit_error_stops_tavily_use(self):
        runner = FakeRunner([(3, json.dumps({"error": "usage limit exceeded"}), "")])
        res = rl.run_operation(self.ledger, "search", ["x"], {}, runner)
        self.assertTrue(res["stop"])
        self.assertEqual(res["entry"]["status"], "blocked_by_plan_or_auth")


class TestSourceReferences(LedgerTestCase):
    def test_results_keep_url_title_dates(self):
        runner = FakeRunner([(0, json.dumps({"results": [
            {"url": "https://rbi.org.in/x", "title": "RBI", "published_date": "2026-08-01"}]}), "")])
        entry = rl.run_operation(self.ledger, "search", ["rbi"], {}, runner)["entry"]
        src = self.ledger.data["sources"][rl.normalize_url("https://rbi.org.in/x")]
        self.assertEqual(src["published_date"], "2026-08-01")
        self.assertEqual(src["first_seen"], entry["id"])
        self.assertTrue(entry["retrieved_at"])
        self.assertTrue((self.run_dir / entry["cache_file"]).is_file())

    def test_audit_flags_claims_without_valid_sources(self):
        (self.run_dir / "sources.md").write_text(
            "# Sources\n\n| Source ID | Title |\n|---|---|\n| S001 | Report |\n", encoding="utf-8")
        (self.run_dir / "evidence-ledger.md").write_text(
            "# Ledger\n\n| Evidence ID | Claim | Source ID(s) |\n|---|---|---|\n"
            "| E01 | supported | S001 |\n| E02 | orphan |  |\n| E03 | bad ref | S999 |\n", encoding="utf-8")
        problems = rl.audit_run(self.run_dir)
        self.assertTrue(any("E02" in p for p in problems))
        self.assertTrue(any("E03" in p and "S999" in p for p in problems))
        self.assertFalse(any("E01" in p for p in problems))

    def test_credentials_are_redacted(self):
        d = self.ledger.plan("search", ["leak tvly-abcdef123456 api_key=hunter2"], {})
        stored = json.dumps(d)
        self.assertNotIn("tvly-abcdef123456", stored)
        self.assertNotIn("hunter2", stored)


class TestCoverageGaps(LedgerTestCase):
    def test_failed_extraction_becomes_coverage_gap(self):
        runner = FakeRunner([(0, json.dumps({"results": [{"url": "https://ok.gov/a", "raw_content": "t"}],
                                             "failed_results": [{"url": "https://blocked.gov/b",
                                                                 "error": "403 Forbidden"}]}), "")])
        rl.run_operation(self.ledger, "extract", ["https://ok.gov/a", "https://blocked.gov/b"], {}, runner)
        gaps = self.ledger.data["coverage_gaps"]
        self.assertEqual([g["url"] for g in gaps], ["https://blocked.gov/b"])
        self.assertIn("not evidence", gaps[0]["note"])
        summary = self.ledger.summary_markdown()
        self.assertIn("https://blocked.gov/b", summary)
        self.assertIn("not evidence that demand is absent", summary)

    def test_known_gap_is_not_retried_with_same_method(self):
        self.ledger.record_gap("https://blocked.gov/b", "403", method="tavily extract basic")
        d = self.ledger.plan("extract", ["https://blocked.gov/b"], {})
        self.assertEqual(d["status"], rl.SKIP_KNOWN_GAP)
        self.assertIn(self.ledger.plan("extract", ["https://blocked.gov/b"], {"depth": "advanced"})["status"],
                      rl.RUNNABLE)  # a different permitted method may be tried

    def test_gap_does_not_change_evidence_status(self):
        cand = {"specific_payer": True, "problem_evidence": True,
                "sources": [{"id": "S1", "cluster": "a", "type": "official"}]}
        before = rl.evidence_gate(cand)["max_status"]
        self.ledger.record_gap("https://competitor.example", "HTTP 403")
        self.assertEqual(rl.evidence_gate(cand)["max_status"], before)


class TestVolumeCannotPromote(unittest.TestCase):
    passing = {"specific_payer": True, "problem_evidence": True, "commercial_evidence": True,
               "plausible_monetisation": True, "reachable_buyers": True, "fits_constraints": True,
               "no_blocking_barrier": True, "cheap_test": True, "red_team_fatal_unresolved": False,
               "sources": [{"id": "S1", "cluster": "gov", "type": "official"},
                           {"id": "S2", "cluster": "press", "type": "press"},
                           {"id": "S3", "cluster": "reviews", "type": "review"}]}

    def test_many_sources_from_one_origin_do_not_pass(self):
        cand = dict(self.passing, queries_run=400, search_results=8000,
                    sources=[{"id": f"S{i}", "cluster": "same-press-release", "type": "press"} for i in range(60)])
        result = rl.evidence_gate(cand)
        self.assertNotEqual(result["max_status"], "Evidence-supported candidate")
        self.assertEqual(result["independent_clusters"], 1)

    def test_volume_without_commercial_evidence_stays_exploratory(self):
        cand = dict(self.passing, commercial_evidence=False, search_results=10000, queries_run=500)
        self.assertEqual(rl.evidence_gate(cand)["max_status"], "Exploratory hypothesis")

    def test_volume_fields_are_ignored(self):
        low = rl.evidence_gate(dict(self.passing, plausible_monetisation=False))
        high = rl.evidence_gate(dict(self.passing, plausible_monetisation=False,
                                     queries_run=999, search_results=99999, sources_seen=500))
        self.assertEqual(low, high)

    def test_validation_labels_need_real_behaviour(self):
        self.assertEqual(rl.evidence_gate(self.passing)["max_status"], "Evidence-supported candidate")
        for fake in (True, {"kind": "simulated_panel", "sample": 100}, {"kind": "desk_research", "sample": 40},
                     {"kind": "ai_opinion", "sample": 3}, {"kind": "interview_recent_incident"}):  # last: no sample
            self.assertEqual(rl.evidence_gate(dict(self.passing, customer_behaviour_evidence=fake))["max_status"],
                             "Evidence-supported candidate", fake)
        real = {"kind": "interview_recent_incident", "sample": "8 owners, Oct 2026"}
        self.assertEqual(rl.evidence_gate(dict(self.passing, customer_behaviour_evidence=real))["max_status"],
                         "Customer-validated")
        paid = {"kind": "deposit", "sample": "2 deposits of Rs 10k"}
        self.assertEqual(rl.evidence_gate(dict(self.passing, commercial_commitment=paid))["max_status"],
                         "Commercially validated")


class TestWeakOrContradictoryEvidence(unittest.TestCase):
    base = TestVolumeCannotPromote.passing

    def test_snippet_only_and_tier_d_sources_do_not_count(self):
        cand = dict(self.base, sources=[
            {"id": "S1", "cluster": "gov", "type": "official"},
            {"id": "S2", "cluster": "blog", "type": "vendor", "tier": "D"},
            {"id": "S3", "cluster": "news", "type": "press", "snippet_only": True}])
        result = rl.evidence_gate(cand)
        self.assertEqual(result["independent_clusters"], 1)
        self.assertNotEqual(result["max_status"], "Evidence-supported candidate")

    def test_unresolved_contradiction_blocks_promotion(self):
        cand = dict(self.base, unresolved_contradictions=["free incumbent covers the job (S7)"])
        result = rl.evidence_gate(cand)
        self.assertNotEqual(result["max_status"], "Evidence-supported candidate")
        self.assertTrue(any(g.startswith("9 ") for g in result["failed_gates"]))

    def test_founder_skills_only_after_gate(self):
        self.assertTrue(rl.founder_skills_allowed(rl.evidence_gate(self.base)))
        self.assertFalse(rl.founder_skills_allowed(rl.evidence_gate(dict(self.base, commercial_evidence=False))))
        self.assertFalse(rl.founder_skills_allowed(rl.evidence_gate(
            dict(self.base, unresolved_contradictions=["x"], queries_run=1000))))


class TestCredentials(LedgerTestCase):
    SECRET = "tvly-SECRETabc123456789"

    def test_missing_cli_gives_actionable_message(self):
        ok, msg = rl.preflight(lambda args, t: (127, "", rl.INSTALL_HELP))
        self.assertFalse(ok)
        self.assertIn("pip install --user tavily-cli", msg)
        self.assertNotIn("| bash", msg.replace("`curl | bash`", ""))  # only mentioned as a prohibition

    def test_unauthenticated_message_never_leaks_or_requests_key(self):
        runner = lambda args, t: (0, json.dumps({"version": "0.1.8", "authenticated": False}),
                                  f"bad key {self.SECRET} api_key=hunter2")
        ok, msg = rl.preflight(runner)
        self.assertFalse(ok)
        self.assertIn("tvly login", msg)
        self.assertIn("Never ask the user to paste an API key", msg)
        self.assertNotIn(self.SECRET, msg)
        self.assertNotIn("hunter2", msg)

    def test_authenticated_preflight_passes_without_credits(self):
        runner = FakeRunner([(0, json.dumps({"version": "0.1.8", "authenticated": True}), "")])
        ok, msg = rl.preflight(runner)
        self.assertTrue(ok)
        self.assertIn("ready", msg)
        self.assertEqual(runner.calls, [["--status", "--json"]])  # status only: no search, no credits

    def test_auth_error_during_run_is_redacted_and_stops(self):
        runner = FakeRunner([(3, "", f"Unauthorized: key {self.SECRET}")])
        res = rl.run_operation(self.ledger, "search", ["india"], {}, runner)
        self.assertTrue(res["stop"])
        self.assertIn("tvly login", res["message"])
        self.assertNotIn(self.SECRET, (self.run_dir / rl.LEDGER_NAME).read_text(encoding="utf-8"))
        self.assertNotIn(self.SECRET, res["message"])

    def test_ordinary_words_are_not_redacted(self):
        self.assertEqual(rl.redact("crypto token prices india"), "crypto token prices india")
        self.assertNotEqual(self.ledger.op_key("search", [rl.redact("token prices")], {}),
                            self.ledger.op_key("search", [rl.redact("token supply")], {}))


class TestBudgetReportingAndModes(LedgerTestCase):
    def test_remaining_budget_and_fetch_status_reported(self):
        runner = FakeRunner([(0, json.dumps({"results": [{"url": "https://a.gov/x", "title": "x"}]}), "")])
        rl.run_operation(self.ledger, "search", ["q"], {"depth": "advanced"}, runner)
        self.assertEqual(self.ledger.remaining, 58)
        summary = self.ledger.summary_markdown()
        self.assertIn("Remaining: **58 (estimated)**", summary)
        self.assertIn("snippet only", summary)  # search hit without page text is not 'fetched'

    def test_user_requested_deep_scan_raises_budget_and_keeps_spend(self):
        runner = FakeRunner()
        rl.run_operation(self.ledger, "search", ["q"], {}, runner)
        spent = self.ledger.spent
        self.ledger.set_profile("deep", reason="user asked for a deep scan")
        self.assertEqual(self.ledger.limit, 250)
        self.assertEqual(self.ledger.spent, spent)
        self.assertIn("quick -> deep", self.ledger.data["approvals"][-1]["reason"])

    def test_gap_impact_is_reported(self):
        self.ledger.record_gap("https://x.gov/r", "HTTP 403", tried=["extract advanced", "press release"],
                               impact="pricing claim for candidate A now unverified")
        self.assertIn("pricing claim for candidate A now unverified", self.ledger.summary_markdown())


class TestAuditWarnings(LedgerTestCase):
    def test_fact_on_snippet_only_source_warns(self):
        (self.run_dir / "sources.md").write_text(
            "| Source ID | Fetched (full page / snippet only / blocked) |\n|---|---|\n"
            "| S001 | snippet only |\n| S002 | full page |\n", encoding="utf-8")
        (self.run_dir / "evidence-ledger.md").write_text(
            "| Evidence ID | Evidence class | Source ID(s) | Corroborated by (independent) |\n|---|---|---|---|\n"
            "| E01 | FACT | S001 | none found |\n| E02 | FACT | S002 |  |\n| E03 | REPORTED SIGNAL | S001 | S002 |\n",
            encoding="utf-8")
        warnings = rl.audit_warnings(self.run_dir)
        self.assertTrue(any(w.startswith("E01") and "snippet" in w for w in warnings))
        self.assertTrue(any(w.startswith("E02") and "corroboration" in w for w in warnings))
        self.assertFalse(any(w.startswith("E03") for w in warnings))
        self.assertEqual(rl.audit_run(self.run_dir), [])  # warnings never block


class TestExistingWorkflowsStillWork(unittest.TestCase):
    skill = SKILL_DIR

    def _run(self, *args):
        import subprocess
        return subprocess.run([sys.executable, "-I", *map(str, args)], capture_output=True, text=True)

    def test_package_structure_checks_pass(self):
        res = self._run(self.skill / "scripts" / "validate_package.py")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_new_run_scaffold_validates_without_tavily(self):
        tmp = TEMP_BASE / "init-run-scaffold"
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)
        try:
            res = self._run(self.skill / "scripts" / "init_run.py", "Testland", "--output-root", tmp,
                            "--date", "2026-01-01")
            self.assertEqual(res.returncode, 0, res.stderr)
            run = Path(res.stdout.strip())
            self.assertFalse((run / rl.LEDGER_NAME).exists())  # Tavily files are optional
            again = self._run(self.skill / "scripts" / "init_run.py", "Testland", "--output-root", tmp,
                              "--date", "2026-01-01")
            self.assertNotEqual(Path(again.stdout.strip()), run)  # never overwrites a prior run
            self.assertEqual(self._run(self.skill / "scripts" / "validate_run.py", run).returncode, 0)
        finally:
            shutil.rmtree(tmp)

    def test_templates_keep_founder_and_status_structure(self):
        founder = (self.skill / "templates" / "founder-review.md").read_text(encoding="utf-8")
        self.assertIn("Skills actually run", founder)
        brief = (self.skill / "templates" / "opportunity-brief.md").read_text(encoding="utf-8")
        for label in ("Signal detected", "Evidence-supported candidate", "Customer-validated",
                      "Commercially validated"):
            self.assertIn(label, brief)
        integration = (self.skill / "references" / "founder-skill-integration.md").read_text(encoding="utf-8")
        self.assertIn("only on finalists that passed the research gate", integration)

    def test_existing_research_runs_still_audit_cleanly(self):
        runs = PROJECT_ROOT / "opportunity-radar-runs" if PROJECT_ROOT else None
        found = [r for r in runs.glob("*/") if (r / "evidence-ledger.md").exists()] if runs and runs.exists() else []
        if not found:
            self.skipTest("no earlier runs in this checkout")
        for run in found:
            self.assertEqual(rl.audit_run(run), [], run.name)


if __name__ == "__main__":
    unittest.main()
