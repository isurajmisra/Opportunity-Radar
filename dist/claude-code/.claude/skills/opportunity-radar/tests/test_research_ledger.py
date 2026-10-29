"""Offline tests for the Tavily research guard. No network calls and no credits are used.

Run: python -m unittest discover -s core/opportunity-radar/tests -v
"""
from __future__ import annotations

import json
import io
import shutil
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

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


class TestCliCompatibilityAndCoverage(LedgerTestCase):
    def test_extract_arguments_match_installed_cli_option_conventions(self):
        args = rl.build_tvly_args("extract", ["https://example.gov/report"], {
            "depth": "basic", "query": "find revenue and costs", "chunks_per_source": 3})
        self.assertEqual(args, ["extract", "https://example.gov/report", "--extract-depth", "basic",
                                "--query", "find revenue and costs", "--chunks-per-source", "3", "--json"])
        runner = FakeRunner([(0, json.dumps({"results": [{"url": "https://example.gov/report",
                                                           "raw_content": "mocked extract"}]}), "")])
        rl.run_operation(self.ledger, "extract", ["https://example.gov/report"], {
            "depth": "basic", "query": "find revenue and costs", "chunks_per_source": 3}, runner)
        self.assertEqual(runner.calls[0], args)
        with self.assertRaisesRegex(ValueError, "requires --query"):
            rl.build_tvly_args("extract", ["https://example.gov/report"], {"chunks_per_source": 3})

    def test_missing_version_option_is_removed_after_local_help_probe(self):
        completed = mock.Mock(returncode=0, stdout='{"results": []}', stderr="")
        with mock.patch.object(rl.shutil, "which", return_value="tvly.exe"), \
             mock.patch.object(rl, "_extract_cli_options", return_value={"--query", "--extract-depth"}), \
             mock.patch.object(rl.subprocess, "run", return_value=completed) as process:
            result = rl._subprocess_runner(["extract", "https://example.gov", "--query", "q",
                                            "--chunks-per-source", "3", "--json"], 30)
        self.assertEqual(result[0], 0)
        self.assertNotIn("--chunks-per-source", process.call_args.args[0])
        self.assertIn("--query", process.call_args.args[0])

    def test_cli_argument_error_does_not_create_gap_and_corrected_retry_succeeds(self):
        url = "https://example.gov/report"
        runner = FakeRunner([
            (1, "", "ValidationError: unexpected keyword argument chunks_per_source"),
            (0, json.dumps({"results": [{"url": url, "raw_content": "Verified report text"}]}), ""),
        ])
        failed = rl.run_operation(self.ledger, "extract", [url],
                                  {"depth": "basic", "query": "find the official data", "chunks_per_source": 3}, runner)
        self.assertEqual(failed["entry"]["status"], "invocation_failed")
        self.assertFalse(failed["entry"]["provider_reached"])
        self.assertEqual(self.ledger.data["coverage_gaps"], [])
        self.assertEqual(self.ledger.spent, 0)
        same = self.ledger.plan("extract", [url],
                                {"depth": "basic", "query": "find the official data", "chunks_per_source": 3})
        self.assertEqual(same["status"], rl.STOP)
        retry = rl.run_operation(self.ledger, "extract", [url],
                                 {"depth": "basic", "query": "find the official data"}, runner)
        self.assertTrue(retry["executed"])
        self.assertTrue(self.ledger.data["sources"][rl.normalize_url(url)]["extracted"])
        self.assertEqual(len(self.ledger.data["coverage_gaps"]), 0)
        attempts = self.ledger.data["sources"][rl.normalize_url(url)]["attempts"]
        self.assertEqual(len(attempts), 2)
        self.assertIn("retry eligible", attempts[0]["status"])
        self.assertIn("successful", attempts[1]["status"])
        self.assertEqual(sum(rl.counts_as_provider_attempt(x) for x in self.ledger.data["operations"]), 1)

    def test_report_distinguishes_real_access_denial_from_unknown_failure(self):
        runner = FakeRunner([(0, json.dumps({"results": [], "failed_results": [
            {"url": "https://denied.example", "error": "HTTP 403 Forbidden"},
            {"url": "https://unknown.example", "error": "upstream timeout"}]}), "")])
        rl.run_operation(self.ledger, "extract", ["https://denied.example", "https://unknown.example"], {}, runner)
        summary = self.ledger.summary_markdown()
        self.assertIn("source access failed", summary)
        self.assertIn("source status unknown; retry eligible", summary)
        self.assertEqual([g["url"] for g in self.ledger.data["coverage_gaps"]], ["https://denied.example"])
        self.assertIn("attempt history", summary.casefold())
        retry_same = self.ledger.plan("extract", ["https://unknown.example"], {"depth": "basic"})
        self.assertEqual(retry_same["status"], rl.STOP)
        retry_corrected = self.ledger.plan("extract", ["https://unknown.example"], {"depth": "advanced"})
        self.assertIn(retry_corrected["status"], rl.RUNNABLE)
        for operation in self.ledger.data["operations"]:
            self.assertIn(f"| {operation['id']} |", summary)
            self.assertIn(f"| {operation['status']} |", summary)
        for operation in self.ledger.data["operations"]:
            self.assertIn(f"| {operation['id']} |", summary)
            self.assertIn(f"| {operation['status']} |", summary)

    def test_legacy_invocation_error_is_not_rendered_as_source_access_failure(self):
        url = "https://example.gov/legacy"
        normalized = rl.normalize_url(url)
        error = "ValidationError: unexpected keyword argument chunks_per_source"
        self.ledger.data["operations"].append({"id": "Q001", "tool": "tavily", "op": "extract",
            "target": [url], "params": {"depth": "basic"}, "key": "old", "status": "failed",
            "est_credits": 1, "credit_basis": "estimated", "actual_credits": None,
            "retrieved_at": rl.now(), "cache_file": None, "error": error, "result_urls": []})
        self.ledger.data["sources"][normalized] = {"url": url, "first_seen": "Q001", "extracted": False,
            "published_date": None, "retrieved_at": rl.now(), "seen_in": ["Q001"]}
        self.ledger.data["coverage_gaps"].append({"url": url, "normalized_url": normalized,
            "reason": error, "operation": "Q001", "method": "tavily extract basic", "alternatives_tried": [],
            "impact": "not yet assessed", "recorded_at": rl.now()})
        summary = self.ledger.summary_markdown()
        self.assertIn("invocation_failed (retry eligible)", summary)
        self.assertIn("command failed; retry eligible", summary)
        self.assertNotIn("source access failed", summary)
        self.assertIn("0 provider attempts", summary)
        self.assertEqual(self.ledger.spent, 0)


class TestWindowsConsoleReporting(LedgerTestCase):
    class RestrictiveStream:
        encoding = "cp1252"

        def __init__(self):
            self.parts = []

        def write(self, value):
            value.encode(self.encoding, errors="strict")
            self.parts.append(value)

    def test_unicode_report_escapes_safely_on_restrictive_console(self):
        stream = self.RestrictiveStream()
        rl.safe_print("Cost ₹100 💸; extraction failed: upstream timeout", file=stream)
        rendered = "".join(stream.parts)
        self.assertIn("Cost", rendered)
        self.assertIn("upstream timeout", rendered)
        self.assertIn("\\u20b9", rendered)
        self.assertTrue("\\U0001f4b8" in rendered or "\\u" in rendered)

    def test_summary_is_saved_and_console_output_is_safe(self):
        url = "https://example.gov/₹-💸"
        self.ledger.record(self.ledger.plan("search", ["report"], {}), "ok", [{"url": url, "title": "₹ 💸"}])
        stream = self.RestrictiveStream()
        with mock.patch.object(rl.sys, "stdout", stream):
            status = rl.main(["summary", str(self.run_dir)])
        self.assertEqual(status, 0)
        report = (self.run_dir / rl.USAGE_NAME).read_text(encoding="utf-8")
        self.assertIn(url, report)
        self.assertIn("Wrote", "".join(stream.parts))

    def test_useful_failure_text_is_printed_but_credentials_are_redacted(self):
        stream = self.RestrictiveStream()
        message = rl.redact("extract failed: timeout api_key=DO_NOT_SHOW tvly-ABCDEF123456")
        rl.safe_print(message, file=stream)
        rendered = "".join(stream.parts)
        self.assertIn("extract failed: timeout", rendered)
        self.assertNotIn("DO_NOT_SHOW", rendered)
        self.assertNotIn("tvly-ABCDEF123456", rendered)


class TestBudget(LedgerTestCase):
    def test_concurrent_requests_cannot_oversubscribe_last_operation(self):
        from concurrent.futures import ThreadPoolExecutor
        led = rl.Ledger.init(self.run_dir, "quick", max_operations=1)
        started = threading.Barrier(3)
        calls = []

        def worker(query):
            started.wait(timeout=3)
            def runner(args, timeout):
                calls.append(args)
                time.sleep(0.05)
                return 0, json.dumps({"results": []}), ""
            return rl.run_operation(rl.Ledger.load(self.run_dir), "search", [query], {"depth": "advanced"}, runner)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, "last-slot-a"), pool.submit(worker, "last-slot-b")]
            started.wait(timeout=3)
            results = [f.result(timeout=5) for f in futures]
        self.assertEqual(sum(bool(x["executed"]) for x in results), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(sum(rl.counts_as_provider_attempt(x) for x in rl.Ledger.load(self.run_dir).data["operations"]), 1)

    def test_interrupted_reserved_operation_keeps_slot_consumed(self):
        led = rl.Ledger.init(self.run_dir, "quick", max_operations=1)
        decision = led.plan("search", ["interrupted call"], {"depth": "advanced"})
        reserved = led.record(decision, "in_progress")
        self.assertTrue(reserved["provider_reached"])
        runner = FakeRunner()
        blocked = rl.run_operation(led, "search", ["another call"], {"depth": "advanced"}, runner)
        self.assertEqual(blocked["decision"]["status"], rl.STOP)
        self.assertEqual(runner.calls, [])

    def test_concurrent_tavily_and_other_provider_share_the_same_cap(self):
        from concurrent.futures import ThreadPoolExecutor
        from provider_usage import Usage, load_policy
        led = rl.Ledger.init(self.run_dir, "quick", max_operations=1)
        start = threading.Barrier(3)
        calls = []

        def tavily():
            start.wait(timeout=3)
            def runner(args, timeout):
                calls.append("tavily")
                time.sleep(0.05)
                return 0, json.dumps({"results": []}), ""
            return rl.run_operation(rl.Ledger.load(self.run_dir), "search", ["shared tavily"],
                                    {"depth": "advanced"}, runner)

        def other_provider():
            start.wait(timeout=3)
            with rl.run_lock(self.run_dir):
                usage = Usage(self.run_dir, "quick", load_policy())
                try:
                    entry = usage.reserve("builtin_web", "search", "shared other-provider query")
                    calls.append("builtin_web")
                    return entry
                except PermissionError:
                    return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(tavily), pool.submit(other_provider)]
            start.wait(timeout=3)
            results = [f.result(timeout=5) for f in futures]
        self.assertEqual(len(calls), 1)
        self.assertEqual(sum(bool(x is not None and (x.get("executed") or x.get("operation_id")))
                             for x in results), 1)

    def test_run_specific_total_operation_cap_blocks_later_provider_calls(self):
        from provider_usage import Usage, load_policy
        led = rl.Ledger.init(self.run_dir, "quick", budget=10, max_operations=1,
                             max_dossiers=1, strict_credit_bounds=True)
        runner = FakeRunner([(0, json.dumps({"results": []}), "")])
        first = rl.run_operation(led, "search", ["first query"], {"depth": "advanced"}, runner)
        self.assertTrue(first["executed"])
        second = rl.run_operation(led, "search", ["second query"], {"depth": "advanced"}, runner)
        self.assertFalse(second["executed"])
        self.assertEqual(second["decision"]["status"], rl.STOP)
        self.assertIn("per-run hard operation cap", second["decision"]["reason"])
        usage = Usage(self.run_dir, "quick", load_policy())
        decision, _ = usage.check("builtin_web", "search", "external follow-up")
        self.assertEqual(decision, "STOP")
        usage.data["approvals"].append({"provider": "builtin_web", "extra_provider_operations": 5,
                                         "extra_total_operations": 5, "extra_cost_usd": 0})
        usage.save()
        decision, _ = usage.check("builtin_web", "search", "follow-up after approval")
        self.assertEqual(decision, "STOP")
        self.assertEqual(len(runner.calls), 1)

    def test_strict_run_credit_bound_refuses_estimate_that_would_exceed_budget(self):
        led = rl.Ledger.init(self.run_dir, "quick", budget=3, max_operations=12,
                             max_dossiers=1, strict_credit_bounds=True)
        runner = FakeRunner([(0, json.dumps({"results": []}), "")])
        first = rl.run_operation(led, "search", ["first advanced query"], {"depth": "advanced"}, runner)
        self.assertTrue(first["executed"])
        second = rl.run_operation(led, "search", ["second advanced query"], {"depth": "advanced"}, runner)
        self.assertFalse(second["executed"])
        self.assertEqual(second["decision"]["status"], rl.STOP)
        self.assertIn("strict run credit cap", second["decision"]["reason"])
        led.approve(credits=100, reason="test that approval cannot override strict cap")
        self.assertEqual(led.limit, 3)
        self.assertEqual(len(runner.calls), 1)

    def test_estimated_tavily_operation_that_would_exceed_budget_is_blocked(self):
        led = rl.Ledger.init(self.run_dir, "quick", budget=2)
        runner = FakeRunner([(0, json.dumps({"results": []}), "")])
        first = rl.run_operation(led, "search", ["documented-cost query"], {"depth": "advanced"}, runner)
        self.assertTrue(first["executed"])
        second = rl.run_operation(led, "search", ["estimated-cost query"], {"depth": "basic"}, runner)
        self.assertFalse(second["executed"])
        self.assertEqual(second["decision"]["status"], rl.STOP)
        self.assertEqual(led.spent, 2)
        self.assertEqual(len(runner.calls), 1)

    def test_strict_run_allows_configured_estimate_but_refuses_unknown_costs(self):
        led = rl.Ledger.init(self.run_dir, "quick", budget=10, strict_credit_bounds=True)
        runner = FakeRunner()
        estimated = rl.run_operation(led, "search", ["estimated rate"], {"depth": "basic"}, runner)
        self.assertTrue(estimated["executed"])
        self.assertEqual(estimated["decision"]["basis"], "estimated")
        result = rl.run_operation(led, "research", ["unknown cost"], {"model": "mini"}, runner)
        self.assertFalse(result["executed"])
        self.assertEqual(result["decision"]["status"], rl.STOP)
        self.assertIn("finite configured estimate or documented pre-call bound", result["decision"]["reason"])
        self.assertEqual(len(runner.calls), 1)

    def test_failed_tavily_operation_consumes_operation_slot_and_blocks_next_call(self):
        led = rl.Ledger.init(self.run_dir, "quick", max_operations=1)
        runner = FakeRunner([(1, "", "temporary provider failure"), (0, "{}", "")])
        failed = rl.run_operation(led, "search", ["first failed query"], {"depth": "advanced"}, runner)
        self.assertTrue(failed["executed"])
        self.assertEqual(failed["entry"]["status"], "provider_failed_unknown")
        blocked = rl.run_operation(led, "search", ["next query"], {"depth": "advanced"}, runner)
        self.assertFalse(blocked["executed"])
        self.assertEqual(blocked["decision"]["status"], rl.STOP)
        self.assertEqual(len(runner.calls), 1)

    def test_failed_non_tavily_operation_is_counted_before_next_check(self):
        from provider_usage import Usage, load_policy
        rl.Ledger.init(self.run_dir, "quick", max_operations=1)
        usage = Usage(self.run_dir, "quick", load_policy())
        with rl.run_lock(self.run_dir):
            reserved = usage.reserve("builtin_web", "search", "first provider query")
            decision, _ = usage.check("builtin_web", "search", "second provider query")
            self.assertEqual(decision, "STOP")
            usage.finish(reserved["operation_id"], "failed")
        decision, _ = usage.check("builtin_web", "search", "second provider query")
        self.assertEqual(decision, "STOP")
        self.assertEqual(len(usage.data["operations"]), 1)

    def test_run_specific_limits_do_not_change_global_budgets(self):
        from provider_usage import load_policy
        config = rl.load_config()
        policy = load_policy()
        led = rl.Ledger.init(self.run_dir, "quick", budget=10, max_operations=12,
                             max_dossiers=1, strict_credit_bounds=True)
        self.assertEqual(led.limit, 10)
        self.assertEqual(led.data["settings"]["total_operation_cap"], 12)
        self.assertEqual(led.data["settings"]["max_candidates_to_dossier"], 1)
        self.assertEqual(config["profiles"]["quick"]["budget_credits"], 60)
        self.assertEqual(config["profiles"]["deep"]["budget_credits"], 250)
        self.assertEqual(policy["total_operations"]["quick"], 30)
        self.assertEqual(policy["total_operations"]["deep"], 90)

    def test_run_specific_caps_cannot_raise_profile_limits(self):
        with self.assertRaises(ValueError):
            rl.Ledger.init(self.run_dir / "too-many-ops", "quick", max_operations=31)
        with self.assertRaises(ValueError):
            rl.Ledger.init(self.run_dir / "too-many-dossiers", "quick", max_dossiers=3)

    def test_dossier_prewrite_guard_blocks_second_dossier(self):
        led = rl.Ledger.init(self.run_dir, "quick", max_dossiers=1)
        self.assertTrue(led.dossier_capacity()[0])
        (self.run_dir / "opportunities").mkdir()
        (self.run_dir / "opportunities" / "first.md").write_text("fixture", encoding="utf-8")
        allowed, message = led.dossier_capacity()
        self.assertFalse(allowed)
        self.assertIn("limit reached", message)

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
        self.assertEqual(res["entry"]["status"], "preflight_failed")


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

    def test_preflight_permission_error_is_not_misreported_as_authentication_failure(self):
        runner = FakeRunner([(1, "", "PermissionError: [WinError 5] Access is denied")])
        ok, msg = rl.preflight(runner)
        self.assertFalse(ok)
        self.assertIn("could not access", msg)
        self.assertIn("authentication status was not verified", msg)
        self.assertNotIn("WinError", msg)

    def test_auth_config_permission_error_during_run_is_not_a_provider_attempt(self):
        error = "[WinError 5] Access is denied: 'C:\\\\Users\\\\test\\\\.tavily'"
        runner = FakeRunner([(1, "", error)])
        res = rl.run_operation(self.ledger, "search", ["India cloud costs"], {"depth": "basic"}, runner)
        self.assertEqual(res["entry"]["status"], "preflight_failed")
        self.assertTrue(res["stop"])
        self.assertFalse(res["entry"]["provider_reached"])
        self.assertEqual(self.ledger.spent, 0)
        self.assertEqual(sum(rl.counts_as_provider_attempt(x) for x in self.ledger.data["operations"]), 0)
        self.assertIn("no provider request was made", res["message"])

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

    def test_incidental_snippet_word_does_not_mark_full_source_as_snippet_only(self):
        (self.run_dir / "sources.md").write_text(
            "| Source ID | Fetched | Limitations |\n|---|---|---|\n"
            "| S001 | Full page | Earlier search snippet was not used. |\n", encoding="utf-8")
        (self.run_dir / "evidence-ledger.md").write_text(
            "| Evidence ID | Evidence class | Source ID(s) | Corroborated by (independent) |\n|---|---|---|---|\n"
            "| E01 | FACT | S001 | none found |\n", encoding="utf-8")
        self.assertFalse(any("E01" in warning and "snippet-only" in warning
                             for warning in rl.audit_warnings(self.run_dir)))


class TestExistingWorkflowsStillWork(unittest.TestCase):
    skill = SKILL_DIR

    def _run(self, *args):
        import subprocess
        return subprocess.run([sys.executable, "-I", *map(str, args)], capture_output=True, text=True)

    def test_package_structure_checks_pass(self):
        res = self._run(self.skill / "scripts" / "validate_package.py")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_run_validator_enforces_run_specific_dossier_limit(self):
        tmp = TEMP_BASE / "dossier-cap"
        if tmp.exists():
            shutil.rmtree(tmp)
        (tmp / "opportunities").mkdir(parents=True)
        (tmp / "opportunities" / "one.md").write_text("one", encoding="utf-8")
        (tmp / "opportunities" / "two.md").write_text("two", encoding="utf-8")
        (tmp / "research-ledger.json").write_text(json.dumps({
            "settings": {"max_candidates_to_dossier": 1}
        }), encoding="utf-8")
        try:
            res = self._run(self.skill / "scripts" / "validate_run.py", tmp)
            self.assertEqual(res.returncode, 1)
            self.assertIn("Dossier limit exceeded", res.stdout)
        finally:
            shutil.rmtree(tmp)

    def test_run_validator_reconciles_summary_and_log_totals_with_both_ledgers(self):
        tmp = TEMP_BASE / "usage-reconciliation"
        if tmp.exists():
            shutil.rmtree(tmp)
        run = tmp / "run"
        (run / "opportunities").mkdir(parents=True)
        (run / "research-ledger.json").write_text(json.dumps({
            "settings": {"max_candidates_to_dossier": 1, "report_reconciliation_version": 1},
            "operations": [
                {"id": "Q001", "status": "ok", "est_credits": 1, "actual_credits": None},
                {"id": "Q002", "status": "invocation_failed", "est_credits": 1, "actual_credits": None},
            ],
        }), encoding="utf-8")
        (run / "provider-usage.json").write_text(json.dumps({"operations": [
            {"operation_id": "P001", "provider": "brave", "status": "ok"},
            {"operation_id": "P002", "provider": "brave", "status": "invocation_failed"},
        ]}), encoding="utf-8")
        block = ("<!-- OPPORTUNITY_RADAR_USAGE_START -->\n"
                 "- Ledger entries (all providers): 4\n"
                 "- Provider attempts (all providers): 2\n"
                 "- Tavily credits charged to run budget: 1\n"
                 "<!-- OPPORTUNITY_RADAR_USAGE_END -->\n")
        for name in ("00-executive-summary.md", "run-log.md"):
            (run / name).write_text("# Report\n\n" + block, encoding="utf-8")
        for name in ("01-country-snapshot.md", "02-signal-inventory.md", "03-opportunity-shortlist.md",
                     "evidence-ledger.md", "red-team-review.md", "validation-plan.md", "founder-review.md"):
            (run / name).write_text("# Report\n", encoding="utf-8")
        (run / "sources.md").write_text(
            "https://one.example https://two.example https://three.example\n", encoding="utf-8")
        (run / "research-usage.md").write_text(
            "- Operation attempts: 2 (1 provider attempts); unique sources seen: 0; extracted: 0\n"
            "- Credits used: **1 (estimated** unless provider-reported\n"
            "- Local profile: **quick**; tracked operations: **2** (including 1 Tavily; local guardrail: 30 total)\n",
            encoding="utf-8")
        try:
            script = self.skill / "scripts" / "validate_run.py"
            good = self._run(script, run)
            self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
            log = run / "run-log.md"
            log.write_text(log.read_text(encoding="utf-8").replace(
                "Provider attempts (all providers): 2", "Provider attempts (all providers): 9"), encoding="utf-8")
            bad = self._run(script, run)
            self.assertEqual(bad.returncode, 1)
            self.assertIn("run-log.md usage reconciliation provider_attempts is 9", bad.stdout)
        finally:
            shutil.rmtree(tmp)

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
