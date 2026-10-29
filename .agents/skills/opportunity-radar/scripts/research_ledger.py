#!/usr/bin/env python3
"""Coordinator-side guard for Tavily research in an Opportunity Radar run.

Tracks queries, source URLs, operations and estimated credits; blocks duplicate
work; enforces the run's credit budget; records inaccessible sources as coverage
gaps; and audits that claims cite known sources. Standard library only.

Typical use (from the run's coordinator session, never from a subagent):
  python research_ledger.py init  <run> --profile quick --budget 10 --max-operations 12 --max-dossiers 1 --strict-credit-bounds
  python research_ledger.py plan  <run> search "india msme delayed payments" --include-domains rbi.org.in
  python research_ledger.py run   <run> search "india msme delayed payments" --include-domains rbi.org.in
  python research_ledger.py run   <run> extract "https://example.gov/report.pdf"
  python research_ledger.py gap   <run> "https://blocked.example" --reason "HTTP 403" --tried "tavily extract basic"
  python research_ledger.py approve <run> --credits 40 --reason "user approved in chat"
  python research_ledger.py summary <run>
  python research_ledger.py audit <run>
"""
from __future__ import annotations

import argparse
import datetime as _dt
from functools import lru_cache
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from run_lock import run_lock

SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = SKILL_DIR / "config" / "research-budget.json"
LEDGER_NAME = "research-ledger.json"
CACHE_DIR = "research-cache"
USAGE_NAME = "research-usage.md"
OPS = ("search", "extract", "map", "crawl", "research")
# Parameters that change what a query can return; anything else (purpose,
# max_results, chunk counts) does not make a repeated query a new query.
KEY_PARAMS = ("depth", "topic", "time_range", "start_date", "end_date", "include_domains",
              "exclude_domains", "country", "include_raw_content", "query", "instructions",
              "select_paths", "exclude_paths", "max_depth", "limit", "model", "chunks_per_source")
TRACKING_PARAMS = re.compile(r"^(utm_.*|gclid|fbclid|mc_cid|mc_eid|ref|ref_src)$", re.I)
SECRET_PATTERNS = (re.compile(r"tvly-[A-Za-z0-9_\-]{6,}"),
                   re.compile(r"(?i)(api[_-]?key|token|secret|password)(\s*[=:]\s*)\S+|(bearer)(\s+)[A-Za-z0-9._\-]{16,}"))

ALLOW, WARN, DUPLICATE, NEEDS_APPROVAL, STOP, SKIP_KNOWN_GAP = (
    "ALLOW", "WARN", "DUPLICATE", "NEEDS_APPROVAL", "STOP", "SKIP_KNOWN_GAP")
RUNNABLE = (ALLOW, WARN)
LOCAL_FAILURE_STATUSES = {"invocation_failed", "preflight_failed", "not_attempted"}
INVOCATION_ERROR = re.compile(
    r"(?i)(unexpected keyword argument|no such option|unrecognized arguments|invalid choice|usage:)" )
AUTH_CONFIG_ACCESS_ERROR = re.compile(
    r"(?i)(permissionerror|permission denied|access is denied|winerror\s*5|eacces).*\.tavily|"
    r"\.tavily.*(permissionerror|permission denied|access is denied|winerror\s*5|eacces)"
)


def counts_as_provider_attempt(operation: dict) -> bool:
    """Known local failures are logged but did not consume a provider operation."""
    return (operation.get("status") not in LOCAL_FAILURE_STATUSES and operation.get("status") != "not_run"
            and not INVOCATION_ERROR.search(str(operation.get("error") or "")))


def local_invocation_error(operation: dict | None) -> bool:
    return bool(operation and (operation.get("status") in LOCAL_FAILURE_STATUSES
                               or INVOCATION_ERROR.search(str(operation.get("error") or ""))))


def auth_config_access_error(message: str) -> bool:
    """Recognize local Tavily credential-directory access failures, not provider 401/403s."""
    return bool(AUTH_CONFIG_ACCESS_ERROR.search(message or ""))


def safe_print(*values, file=None, sep=" ", end="\n") -> None:
    """Write Unicode normally, but escape unsupported characters on restrictive consoles."""
    stream = file or sys.stdout
    text = sep.join(str(value) for value in values) + end
    try:
        stream.write(text)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "ascii"
        stream.write(text.encode(encoding, errors="backslashreplace").decode(encoding))


def md_cell(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).replace("|", "/").strip()

STATUS_ORDER = ["Insufficient evidence", "Signal detected", "Exploratory hypothesis",
                "Evidence-supported candidate", "Customer-validated", "Commercially validated"]


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def redact(text: str | None) -> str | None:
    """Remove credentials from anything that will be stored or printed."""
    if text is None:
        return None
    text = SECRET_PATTERNS[0].sub("[REDACTED]", text)
    return SECRET_PATTERNS[1].sub(
        lambda m: (m.group(1) or m.group(3)) + (m.group(2) or m.group(4)) + "[REDACTED]", text)


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query or "").strip().lower()


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    port = parts.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    path = parts.path or "/"
    if len(path) > 1:
        path = path.rstrip("/")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                             if not TRACKING_PARAMS.match(k)))
    return urlunsplit((scheme, netloc, path, query, ""))


def load_config(path: Path | None = None) -> dict:
    return json.loads((path or DEFAULT_CONFIG).read_text(encoding="utf-8"))


def choose_operation(need: dict) -> tuple[str, dict, str]:
    """Pick the cheapest Tavily operation that fits the research need.

    need keys (all optional booleans unless noted): has_urls, needs_many_pages_same_site,
    knows_site_not_page, needs_multi_source_synthesis, synthesis_justified,
    needs_bulk_filtering, precision_fact, recent_news.
    """
    if need.get("needs_many_pages_same_site"):
        return ("crawl", {"limit": 20, "max_depth": 1, "instructions": "<focus>", "chunks_per_source": 3},
                "many pages from one site section; crawl with limit + instructions to avoid context flooding")
    if need.get("has_urls"):
        return ("extract", {"depth": "basic"},
                "URL already known; extract the page (basic first, advanced only if content is missing)")
    if need.get("knows_site_not_page"):
        return ("map", {"limit": 30, "instructions": "<page wanted>"},
                "site known but not the page; map then extract the chosen URL")
    if need.get("needs_multi_source_synthesis") and need.get("synthesis_justified"):
        return ("research", {"model": "mini"},
                "justified multi-source synthesis; output is discovery until underlying sources are extracted")
    if need.get("needs_bulk_filtering"):
        return ("dynamic-search", {"depth": "basic", "include_raw_content": True},
                "large raw result sets; filter in Python so only curated output reaches context")
    params = {"depth": "advanced" if need.get("precision_fact") else "basic"}
    if need.get("recent_news"):
        params.update(topic="news", time_range="month")
    return ("search", params, "no URL yet; targeted search for source discovery")


def estimate_credits(op: str, params: dict, rates: dict, n_urls: int = 1) -> tuple[int, str]:
    """Return (credits, basis) where basis is documented, estimated or unknown."""
    r = rates[op]
    if op == "search":
        row = r.get(params.get("depth") or "basic", r["basic"])
        return row["credits"], row["basis"].split(" ")[0]
    if op == "extract":
        row = r[params.get("depth") or "basic"]
        return math.ceil(max(n_urls, 1) / 5) * row["credits_per_5_urls"], "estimated"
    if op == "crawl":
        pages = int(params.get("limit") or 50)
        row = r[params.get("depth") or "basic"]
        credits = math.ceil(pages / 5) * row["credits_per_5_pages"]
        if params.get("instructions"):
            credits += math.ceil(pages / 10) * r["instructions"]["credits_per_10_pages"]
        return credits, "documented rate, upper bound from --limit"
    if op == "map":
        pages = int(params.get("limit") or 50)
        credits = math.ceil(pages / 10) * r["base"]["credits_per_10_pages"]
        if params.get("instructions"):
            credits += math.ceil(pages / 10) * r["instructions"]["credits_per_10_pages"]
        return credits, "estimated"
    if op == "research":
        row = r[params.get("model") or "auto"]
        return row["reserve_credits"], "unknown (reservation)"
    raise ValueError(f"unknown operation {op}")


class Ledger:
    def __init__(self, run_dir: Path, data: dict):
        self.run_dir = Path(run_dir)
        self.data = data

    # ---------- persistence ----------
    @classmethod
    def init(cls, run_dir: Path, profile: str = "quick", budget: int | None = None,
             config: dict | None = None, max_operations: int | None = None,
             max_dossiers: int | None = None, strict_credit_bounds: bool = False) -> "Ledger":
        config = config or load_config()
        settings = dict(config["profiles"][profile])
        provider_policy = json.loads((SKILL_DIR / "config" / "provider-policy.json").read_text(encoding="utf-8"))
        global_operation_cap = int(provider_policy["total_operations"][profile])
        if max_operations is not None and not 1 <= int(max_operations) <= global_operation_cap:
            raise ValueError(f"max_operations must be between 1 and the {profile} global cap ({global_operation_cap}).")
        dossier_limit = int(settings["max_candidates_to_dossier"])
        if max_dossiers is not None and not 0 <= int(max_dossiers) <= dossier_limit:
            raise ValueError(f"max_dossiers must be between 0 and the {profile} profile limit ({dossier_limit}).")
        if budget is not None:
            if int(budget) < 1:
                raise ValueError("budget must be at least 1 credit.")
            settings["budget_credits"] = int(budget)
        settings["total_operation_cap"] = int(max_operations) if max_operations is not None else None
        settings["max_candidates_to_dossier"] = int(max_dossiers) if max_dossiers is not None else dossier_limit
        settings["require_documented_credit_bounds"] = bool(strict_credit_bounds)
        settings["hard_credit_cap"] = int(settings["budget_credits"]) if strict_credit_bounds else None
        settings["report_reconciliation_version"] = 1
        data = {"created_at": now(), "profile": profile, "settings": settings,
                "rates": config["credit_rates"], "approved_extra_credits": 0,
                "approved_research_calls": 0, "approved_crawl": False, "approvals": [],
                "operations": [], "sources": {}, "coverage_gaps": []}
        ledger = cls(run_dir, data)
        ledger.save()
        return ledger

    @classmethod
    def load(cls, run_dir: Path) -> "Ledger":
        path = Path(run_dir) / LEDGER_NAME
        if not path.is_file():
            raise SystemExit(f"No {LEDGER_NAME} in {run_dir}. Run `init` first.")
        return cls(run_dir, json.loads(path.read_text(encoding="utf-8")))

    def save(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / LEDGER_NAME).write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    # ---------- accounting ----------
    @property
    def limit(self) -> int:
        limit = self.data["settings"]["budget_credits"] + self.data["approved_extra_credits"]
        hard_cap = self.data["settings"].get("hard_credit_cap")
        return min(limit, int(hard_cap)) if hard_cap is not None else limit

    @property
    def spent(self) -> int:
        return sum(op.get("actual_credits") if op.get("actual_credits") is not None else op["est_credits"]
                   for op in self.data["operations"] if counts_as_provider_attempt(op))

    def op_key(self, op: str, target: list[str], params: dict) -> str:
        if op == "extract":
            subject = sorted(normalize_url(u) for u in target)
        elif op in ("map", "crawl"):
            subject = [normalize_url(target[0])]
        else:
            subject = [normalize_query(" ".join(target))]
        relevant = {k: (normalize_query(v) if isinstance(v, str) else v)
                    for k, v in sorted(params.items()) if k in KEY_PARAMS and v not in (None, False, "")}
        return json.dumps([op, subject, relevant], sort_keys=True)

    def local_operation_guard(self) -> str | None:
        """Enforce the configured local total and Tavily call caps in addition to credit limits."""
        policy_path = SKILL_DIR / "config" / "provider-policy.json"
        try:
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            usage_path = self.run_dir / "provider-usage.json"
            usage = json.loads(usage_path.read_text(encoding="utf-8")) if usage_path.exists() else {
                "operations": [], "approvals": []}
        except (OSError, json.JSONDecodeError) as exc:
            return f"local provider budget could not be read ({type(exc).__name__}); refusing to run."
        if usage.get("profile", self.data["profile"]) != self.data["profile"]:
            return "local provider usage profile differs from the Tavily profile; synchronize profiles before continuing."
        approvals = usage.get("approvals", [])
        extra_total = sum(x.get("extra_total_operations", 0) for x in approvals)
        extra_tavily = sum(x.get("extra_provider_operations", 0) for x in approvals if x.get("provider") == "tavily")
        other_calls = sum(counts_as_provider_attempt(x) and x.get("provider") != "tavily"
                          for x in usage.get("operations", []))
        tavily_calls = sum(counts_as_provider_attempt(x) for x in self.data["operations"])
        total = other_calls + tavily_calls
        profile_cap = policy["total_operations"][self.data["profile"]]
        profile_total_limit = profile_cap + extra_total
        run_total_limit = self.data["settings"].get("total_operation_cap")
        if run_total_limit is not None:
            try:
                run_total_limit = int(run_total_limit)
            except (TypeError, ValueError):
                return "local run operation cap is invalid; refusing to run."
            if not 1 <= run_total_limit <= profile_cap:
                return "local run operation cap is invalid; refusing to run."
        total_limit = min(profile_total_limit, run_total_limit) if run_total_limit is not None else profile_total_limit
        tavily_limit = policy["provider_operations"][self.data["profile"]]["tavily"] + extra_tavily
        if total >= total_limit or tavily_calls >= tavily_limit:
            label = "per-run hard operation cap" if run_total_limit is not None and total >= run_total_limit else "local call guardrail"
            return (f"{label} reached (total {total}/{total_limit}; "
                    f"Tavily {tavily_calls}/{tavily_limit}); ask the user before continuing.")
        return None

    # ---------- decisions ----------
    def plan(self, op: str, target: list[str], params: dict) -> dict:
        target = [redact(t) for t in target]
        params = {k: redact(v) if isinstance(v, str) else v for k, v in params.items()}
        settings = self.data["settings"]
        decision = {"op": op, "target": target, "params": params, "notes": []}
        if op == "extract":
            pending, done, gaps, retry_blocked = [], [], [], []
            method = f"tavily extract {params.get('depth') or 'basic'}"
            for url in target:
                n = normalize_url(url)
                src = self.data["sources"].get(n)
                if src and src.get("extracted"):
                    done.append(url)
                elif any(g["normalized_url"] == n and g.get("method") == method
                         and g.get("status", "source_access_failed") == "source_access_failed"
                         for g in self.data["coverage_gaps"]):
                    gaps.append(url)
                elif src and any(a.get("method") == method and "status unknown" in a.get("status", "")
                                 for a in src.get("attempts", [])[-1:]):
                    retry_blocked.append(url)
                else:
                    pending.append(url)
            if done:
                decision["notes"].append(f"already extracted, reuse cache: {done}")
            if gaps:
                decision["notes"].append(f"known coverage gaps with this method, try a permitted alternative: {gaps}")
            if retry_blocked:
                decision["notes"].append(f"same-method retry refused for sources with unknown status; change method/configuration first: {retry_blocked}")
            if not pending:
                if gaps:
                    for gap in self.data["coverage_gaps"]:
                        if gap["normalized_url"] in {normalize_url(url) for url in gaps}:
                            gap["retry_status"] = "intentionally skipped; use a different permitted method"
                    self.save()
                if retry_blocked:
                    decision.update(status=STOP, reason="retry requires a corrected command/configuration or a different permitted method")
                else:
                    decision.update(status=SKIP_KNOWN_GAP if gaps and not done else DUPLICATE,
                                    est_credits=0, basis="n/a")
                return decision
            target = decision["target"] = pending
        key = self.op_key(op, target, params)
        for prior in self.data["operations"]:
            if prior["key"] == key and prior["status"] == "in_progress":
                decision.update(status=STOP, reason=("a previous provider operation was interrupted with unknown outcome; "
                                                     "review the ledger before attempting a retry"))
                return decision
            if prior["key"] == key and prior["status"] == "invocation_failed":
                decision.update(status=STOP, reason=("the same CLI invocation already failed locally; "
                                                     "correct the command/configuration before retrying"))
                return decision
            if prior["key"] == key and prior["status"] == "ok" and op != "extract":
                wanted = params.get("max_results") or 0
                if wanted <= (prior["params"].get("max_results") or 0) or op != "search":
                    decision.update(status=DUPLICATE, est_credits=0, basis="n/a",
                                    reuse=prior.get("cache_file"), prior_id=prior["id"])
                    return decision
                decision["notes"].append("expands an earlier identical query to more results")
        local_limit = self.local_operation_guard()
        if local_limit:
            status = STOP if local_limit.startswith("per-run hard operation cap") else NEEDS_APPROVAL
            decision.update(status=status, reason=local_limit)
            return decision
        est, basis = estimate_credits(op, params, self.data["rates"], n_urls=len(target))
        decision.update(est_credits=est, basis=basis, key=key)
        if settings.get("require_documented_credit_bounds") and (
                not isinstance(est, int) or est < 0 or "unknown" in basis.casefold()):
            decision.update(status=STOP, reason=(f"strict run budget requires a finite configured estimate or "
                                                 f"documented pre-call bound; {op} cost is {basis}. "
                                                 "No provider call was made."))
            return decision
        if settings.get("require_documented_credit_bounds") and self.spent + est > self.limit:
            decision.update(status=STOP, reason=(f"operation's documented bound would exceed the strict run credit cap: "
                                                 f"{self.spent} + {est} > {self.limit}. No provider call was made."))
            return decision
        if self.spent >= self.limit:
            decision.update(status=STOP, reason=f"budget exhausted ({self.spent}/{self.limit} est. credits); ask the user")
            return decision
        if op == "research":
            used = sum(1 for o in self.data["operations"] if o["op"] == "research" and o["status"] != "not_run")
            if used >= settings["research_calls_allowed"] + self.data["approved_research_calls"]:
                decision.update(status=NEEDS_APPROVAL, reason="research calls not allowed (or exhausted) in this profile")
                return decision
        if op == "crawl" and not (settings["crawl_allowed_without_approval"] or self.data["approved_crawl"]):
            decision.update(status=NEEDS_APPROVAL, reason="crawl needs approval in this profile; try map + extract first")
            return decision
        if est > settings["max_single_operation_credits"] + self.data["approved_extra_credits"]:
            decision.update(status=NEEDS_APPROVAL, reason=f"single operation estimated at {est} credits exceeds the per-operation cap")
            return decision
        if self.spent + est > self.limit:
            decision.update(status=NEEDS_APPROVAL,
                            reason=f"would exceed budget: {self.spent} + {est} > {self.limit} est. credits")
            return decision
        if self.spent + est > settings["warn_at_fraction"] * self.limit:
            decision.update(status=WARN, reason=f"over {int(settings['warn_at_fraction'] * 100)}% of budget after this call")
            return decision
        decision.update(status=ALLOW)
        return decision

    # ---------- recording ----------
    def record(self, decision: dict, status: str, result_items: list[dict] | None = None,
               cache_file: str | None = None, error: str | None = None,
               actual_credits: int | None = None, tool: str = "tavily") -> dict:
        reserved_id = decision.get("reserved_id")
        entry = next((x for x in self.data["operations"] if x["id"] == reserved_id), None) if reserved_id else None
        if entry is None:
            op_id = f"Q{len(self.data['operations']) + 1:03d}"
            entry = {"id": op_id, "tool": tool, "op": decision["op"], "target": decision["target"],
                     "params": decision["params"], "key": decision.get("key") or self.op_key(
                         decision["op"], decision["target"], decision["params"]),
                     "status": status, "est_credits": 0 if tool != "tavily" else decision.get("est_credits", 0),
                     "credit_basis": decision.get("basis"), "actual_credits": actual_credits,
                     "retrieved_at": now(), "cache_file": cache_file, "error": redact(error),
                     "provider_reached": counts_as_provider_attempt({"status": status}), "result_urls": []}
        else:
            op_id = entry["id"]
            entry.update(status=status, retrieved_at=now(), cache_file=cache_file or entry.get("cache_file"),
                         error=redact(error), actual_credits=actual_credits,
                         provider_reached=counts_as_provider_attempt({"status": status}))
        for item in result_items or []:
            url = item.get("url")
            if not url:
                continue
            n = normalize_url(url)
            entry["result_urls"].append(url)
            src = self.data["sources"].setdefault(n, {"url": url, "first_seen": op_id, "extracted": False,
                                                    "title": item.get("title"), "published_date": None,
                                                    "retrieved_at": entry["retrieved_at"], "seen_in": [],
                                                    "extraction_status": "snippet only", "attempts": []})
            if op_id not in src["seen_in"]:
                src["seen_in"].append(op_id)
            if item.get("published_date") and not src.get("published_date"):
                src["published_date"] = item["published_date"]
            if item.get("raw_content"):  # full page text retrieved (extract, crawl, or search --include-raw-content)
                src["extracted"] = True
                src["retrieved_at"] = entry["retrieved_at"]
                src["extraction_status"] = "full page"
        if decision["op"] == "extract":
            for url in decision["target"]:
                n = normalize_url(url)
                src = self.data["sources"].setdefault(n, {"url": url, "first_seen": op_id, "extracted": False,
                                                          "published_date": None, "retrieved_at": entry["retrieved_at"],
                                                          "seen_in": [], "extraction_status": "not attempted", "attempts": []})
                if op_id not in src["seen_in"]:
                    src["seen_in"].append(op_id)
                if src.get("extracted"):
                    attempt_status = "successful extraction"
                    src["extraction_status"] = "full page"
                    for previous in src.get("attempts", []):
                        if previous.get("retry_status") == "retry eligible":
                            previous["retry_status"] = f"retried successfully by {op_id}"
                elif status == "invocation_failed":
                    attempt_status = "command/configuration failure (retry eligible)"
                    src["extraction_status"] = "command failed; retry eligible"
                elif status == "preflight_failed":
                    attempt_status = "preflight failure (not attempted)"
                    src["extraction_status"] = "not attempted; preflight failed"
                elif status == "in_progress":
                    attempt_status = "provider attempt in progress; source status unknown"
                    src["extraction_status"] = "provider attempt in progress; outcome unknown"
                elif status == "source_access_failed":
                    attempt_status = "confirmed source-level access failure"
                    src["extraction_status"] = "source access failed"
                elif status == "provider_failed_unknown":
                    attempt_status = "provider/network failure; source status unknown"
                    src["extraction_status"] = "source status unknown; retry eligible"
                elif status == "ok":
                    attempt_status = "provider returned no full-page content; source status unknown"
                    src["extraction_status"] = "source status unknown; retry eligible"
                else:
                    attempt_status = status
                    src["extraction_status"] = status
                attempt = {"operation_id": op_id,
                    "method": f"tavily extract {decision['params'].get('depth') or 'basic'}",
                    "status": attempt_status, "reason": redact(error), "retrieved_at": entry["retrieved_at"]}
                if attempt_status.endswith("retry eligible") or "status unknown" in attempt_status:
                    attempt["retry_status"] = "retry eligible"
                prior_attempt = next((a for a in src.setdefault("attempts", [])
                                      if a.get("operation_id") == op_id), None)
                if prior_attempt is None:
                    src["attempts"].append(attempt)
                else:
                    prior_attempt.update(attempt)
        if not reserved_id:
            self.data["operations"].append(entry)
        self.save()
        return entry

    def record_gap(self, url: str, reason: str, op_id: str | None = None, method: str | None = None,
                   tried: list[str] | None = None, impact: str | None = None,
                   status: str = "source_access_failed") -> dict:
        normalized = normalize_url(url)
        gap = {"url": url, "normalized_url": normalize_url(url), "reason": redact(reason),
               "operation": op_id, "method": method, "alternatives_tried": tried or [],
               "status": status, "retry_status": "alternative method required" if status == "source_access_failed" else "retry eligible",
               "impact": redact(impact) or "not yet assessed", "recorded_at": now(),
               "note": "Coverage limitation only - not evidence that demand or the fact is absent."}
        existing = next((g for g in self.data["coverage_gaps"] if g["normalized_url"] == normalized
                         and g.get("method") == method and g.get("operation") == op_id), None)
        if existing is None:
            self.data["coverage_gaps"].append(gap)
        else:
            existing.update(gap)
            gap = existing
        src = self.data["sources"].setdefault(normalized, {"url": url, "first_seen": op_id,
                                                           "extracted": False, "published_date": None,
                                                           "retrieved_at": now(), "seen_in": [], "attempts": []})
        src["extraction_status"] = "source access failed" if status == "source_access_failed" else status
        src.setdefault("attempts", [])
        if op_id and not any(a.get("operation_id") == op_id for a in src["attempts"]):
            src["attempts"].append({"operation_id": op_id, "method": method,
                "status": "confirmed source-level access failure" if status == "source_access_failed" else status,
                "reason": redact(reason), "retrieved_at": gap["recorded_at"],
                "retry_status": gap["retry_status"]})
        self.save()
        return gap

    def approve(self, credits: int = 0, research_calls: int = 0, allow_crawl: bool = False,
                reason: str = "") -> None:
        self.data["approved_extra_credits"] += int(credits)
        self.data["approved_research_calls"] += int(research_calls)
        self.data["approved_crawl"] = self.data["approved_crawl"] or allow_crawl
        self.data["approvals"].append({"credits": credits, "research_calls": research_calls,
                                       "allow_crawl": allow_crawl, "reason": redact(reason), "at": now()})
        self.save()

    def set_profile(self, profile: str, reason: str, budget: int | None = None,
                    config: dict | None = None) -> None:
        """Switch scan mode mid-run (e.g. quick -> deep) after the user explicitly asks for it.
        Spending so far is kept; approvals already granted stay in force."""
        config = config or load_config()
        settings = dict(config["profiles"][profile])
        if budget is not None:
            settings["budget_credits"] = int(budget)
        old = self.data["profile"]
        for key in ("total_operation_cap", "max_candidates_to_dossier", "require_documented_credit_bounds", "hard_credit_cap"):
            if key in self.data["settings"]:
                settings[key] = self.data["settings"][key]
        self.data["profile"], self.data["settings"] = profile, settings
        self.data["approvals"].append({"credits": 0, "research_calls": 0, "allow_crawl": False,
                                       "reason": redact(f"profile {old} -> {profile}: {reason}"), "at": now()})
        self.save()

    @property
    def remaining(self) -> int:
        return max(self.limit - self.spent, 0)

    # ---------- reporting ----------
    def summary_markdown(self) -> str:
        d, s = self.data, self.data["settings"]
        op_limit = s.get("total_operation_cap") or "profile default"
        lines = ["# Research usage", "",
                 f"- Profile: **{d['profile']}**; budget {s['budget_credits']} credits"
                 f" + approved extra {d['approved_extra_credits']} = **{self.limit}**",
                 f"- Run limits: **{op_limit} total operations**, "
                 f"**{s.get('max_candidates_to_dossier', 'profile default')} dossiers maximum**; "
                 f"documented credit bounds only: **{'yes' if s.get('require_documented_credit_bounds') else 'no'}**",
                 f"- Credits used: **{self.spent} (estimated** unless an operation lists actual credits; "
                 "the Tavily CLI does not report usage, see `config/research-budget.json` for the basis of each rate)",
                 f"- Remaining: **{self.remaining} (estimated)**",
                 f"- Operation attempts: {len(d['operations'])} ({sum(counts_as_provider_attempt(x) for x in d['operations'])} provider attempts); "
                 f"unique sources seen: {len(d['sources'])}; "
                 f"extracted: {sum(1 for x in d['sources'].values() if x.get('extracted'))}",
                 "- Research volume is recorded for audit only and never raises an opportunity's score.", "",
                 "## Operations", "",
                 "| ID | Tool | Op | Query / URLs | Status | Est. credits | Basis | Retrieved (UTC) | Results |",
                 "|---|---|---|---|---|---:|---|---|---:|"]
        for o in d["operations"]:
            target = "; ".join(o["target"])[:120].replace("|", "/")
            display_status = "invocation_failed (retry eligible)" if local_invocation_error(o) else o['status']
            lines.append(f"| {o['id']} | {o['tool']} | {o['op']} | {target} | {display_status} | {o['est_credits']} | "
                         f"{o.get('credit_basis') or ''} | {o['retrieved_at']} | {len(o['result_urls'])} |")
        lines += ["", "## Sources seen", "",
                  "Snippet-only sources are discovery leads; extract the page before using them for a material claim.", "",
                  "| URL | Fetched / status | Published | First retrieved (UTC) | Seen in | Attempt history |",
                  "|---|---|---|---|---|---|"]
        operation_by_id = {o["id"]: o for o in d["operations"]}
        true_gaps = [g for g in d["coverage_gaps"] if not local_invocation_error(
            operation_by_id.get(g.get("operation")))]
        gap_urls = {g["normalized_url"] for g in true_gaps}
        for n, src in d["sources"].items():
            source_local_error = next((operation_by_id.get(g.get("operation")) for g in d["coverage_gaps"]
                                       if g["normalized_url"] == n and local_invocation_error(
                                           operation_by_id.get(g.get("operation")))), None)
            fetched = src.get("extraction_status") or (
                "full page" if src.get("extracted") else
                "command failed; retry eligible" if source_local_error else
                "source access failed" if n in gap_urls else "snippet only")
            attempt_rows = list(src.get("attempts", []))
            if not attempt_rows and source_local_error:
                attempt_rows = [{"operation_id": source_local_error.get("id"),
                                 "status": "command/configuration failure", "reason": source_local_error.get("error"),
                                 "retry_status": "retry eligible"}]
            attempts = "; ".join(
                f"{a.get('operation_id')} {md_cell(a.get('status'))}: {md_cell(a.get('reason') or 'no error')}"
                f" [{a.get('retry_status')}]" if a.get("retry_status") else
                f"{a.get('operation_id')} {md_cell(a.get('status'))}: {md_cell(a.get('reason') or 'no error')}"
                for a in attempt_rows) or "none"
            lines.append(f"| {src['url']} | {fetched} | {src.get('published_date') or 'unknown'} | "
                         f"{src.get('retrieved_at')} | {', '.join(src.get('seen_in', []))} | {attempts} |")
        lines += ["", "## Coverage gaps", ""]
        if not true_gaps:
            lines.append("None recorded.")
        else:
            lines += ["Inaccessible sources are coverage limitations, **not evidence that demand is absent**.", "",
                      "| URL | Status | Reason | Method | Retry status | Alternatives tried | Impact on research |",
                      "|---|---|---|---|---|---|---|"]
            for g in true_gaps:
                lines.append(f"| {g['url']} | {md_cell(g.get('status', 'source_access_failed'))} | {md_cell(g['reason'])} | "
                             f"{md_cell(g.get('method'))} | {md_cell(g.get('retry_status', 'alternative method required'))} | "
                             f"{md_cell(', '.join(g['alternatives_tried']) or 'none yet')} | {md_cell(g.get('impact', 'not yet assessed'))} |")
        lines += ["", "## Approvals", ""]
        lines += [f"- {a['at']}: +{a['credits']} credits, +{a['research_calls']} research calls, "
                  f"crawl={a['allow_crawl']} — {a['reason']}" for a in d["approvals"]] or ["None."]
        return "\n".join(lines) + "\n"

    def dossier_capacity(self) -> tuple[bool, str]:
        """Pre-write guard used by the coordinator before creating each dossier."""
        try:
            limit = int(self.data["settings"]["max_candidates_to_dossier"])
        except (KeyError, TypeError, ValueError):
            return False, "Run dossier limit is missing or invalid; refusing to create a dossier."
        directory = self.run_dir / "opportunities"
        current = len(list(directory.glob("*.md"))) if directory.is_dir() else 0
        if current >= limit:
            return False, f"Run dossier limit reached ({current}/{limit}); do not create another dossier."
        return True, f"Dossier slot available ({current}/{limit}); one dossier may be created."


# ---------- running the Tavily CLI ----------

def build_tvly_args(op: str, target: list[str], params: dict) -> list[str]:
    flag = {"max_results": "--max-results", "topic": "--topic", "time_range": "--time-range",
            "start_date": "--start-date", "end_date": "--end-date", "include_domains": "--include-domains",
            "exclude_domains": "--exclude-domains", "country": "--country", "query": "--query",
            "chunks_per_source": "--chunks-per-source", "instructions": "--instructions", "limit": "--limit",
            "max_depth": "--max-depth", "select_paths": "--select-paths", "exclude_paths": "--exclude-paths",
            "model": "--model"}
    if params.get("chunks_per_source") is not None:
        if op not in ("extract", "crawl"):
            raise ValueError("--chunks-per-source is supported only for extract/crawl operations")
        if not params.get("query"):
            raise ValueError("Tavily CLI requires --query when --chunks-per-source is used")
        chunks = int(params["chunks_per_source"])
        if not 1 <= chunks <= 5:
            raise ValueError("Tavily CLI --chunks-per-source must be between 1 and 5")
    args = [op] + ([" ".join(target)] if op in ("search", "research") else list(target))
    for k, v in params.items():
        if v in (None, False, ""):
            continue
        if k == "depth":
            args += ["--depth" if op == "search" else "--extract-depth", str(v)]
        elif k == "include_raw_content":
            args += ["--include-raw-content", "markdown"]
        elif k in flag:
            args += [flag[k], str(v)]
    return args + ["--json"]


AUTH_HELP = ("Tavily is not signed in, or the plan limit was reached. Ask the user to run `tvly login` "
             "in their own terminal (browser sign-in), then retry. Never ask the user to paste an API key "
             "into the chat. If this is a plan limit, stop Tavily use and tell the user. Under a hard run cap, "
             "use another provider only through an adapter that checks and records against the same run cap; "
             "otherwise stop and report the provider as unavailable.")
INSTALL_HELP = ("The Tavily CLI (`tvly`) was not found on PATH. Ask the user to install it with "
                "`pip install --user tavily-cli` (do not run remote `curl | bash` scripts), add its Scripts "
                "folder to PATH, and run `tvly login`. Until then, use only a provider adapter that enforces "
                "the same run-specific operation cap; do not fall back to an unmetered host tool.")


def _subprocess_runner(args: list[str], timeout: int) -> tuple[int, str, str]:
    exe = shutil.which("tvly")
    if not exe:
        return 127, "", INSTALL_HELP
    command_args = list(args)
    if command_args and command_args[0] == "extract" and "--chunks-per-source" in command_args:
        options = _extract_cli_options(exe)
        if options is None:
            return 126, "", "Could not verify installed Tavily CLI extract options; no provider call was made."
        if "--chunks-per-source" not in options:
            index = command_args.index("--chunks-per-source")
            del command_args[index:index + 2]
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.run([exe] + command_args, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, env=env)
    return proc.returncode, proc.stdout, proc.stderr


@lru_cache(maxsize=8)
def _extract_cli_options(exe: str) -> set[str] | None:
    """Read local CLI help once to handle installed-version option differences."""
    try:
        proc = subprocess.run([exe, "extract", "--help"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return set(re.findall(r"--[a-z][a-z0-9-]*", proc.stdout + proc.stderr))


def result_items(op: str, payload: dict) -> list[dict]:
    if op == "map":
        return [{"url": u} if isinstance(u, str) else u for u in payload.get("results", [])]
    if op == "research":
        return [s if isinstance(s, dict) else {"url": s} for s in payload.get("sources", [])]
    return list(payload.get("results", []))


def is_source_access_failure(reason: str) -> bool:
    return bool(re.search(r"(?i)(\bHTTP\s*)?(401|403|404|410)\b|paywall|login required|captcha", reason or ""))


def _run_operation_locked(ledger: Ledger, op: str, target: list[str], params: dict,
                          runner: Callable[[list[str], int], tuple[int, str, str]]) -> dict:
    decision = ledger.plan(op, target, params)
    if decision["status"] not in RUNNABLE:
        return {"decision": decision, "executed": False}
    try:
        args = build_tvly_args(op, decision["target"], params)
    except (TypeError, ValueError) as exc:
        message = redact(str(exc))
        decision.update(status=STOP, reason=f"Local CLI argument validation failed. {message} No provider call was made.")
        entry = ledger.record(decision, "invocation_failed", error=message)
        return {"decision": decision, "executed": False, "entry": entry, "message": message}
    reserved = ledger.record(decision, "in_progress")
    decision["reserved_id"] = reserved["id"]
    try:
        code, out, err = runner(args, 700 if op == "research" else 180)
    except (OSError, subprocess.SubprocessError) as exc:
        code, out, err = 126, "", f"{type(exc).__name__}: local CLI invocation failed"
    payload: dict = {}
    try:
        payload = json.loads(out) if out.strip() else {}
    except json.JSONDecodeError:
        payload = {"error": "non-JSON output"}
    if code != 0 or "error" in payload:
        raw_error = str(payload.get("error") or err or f"exit {code}")
        local_invocation_error = code in (2, 126) or bool(re.search(
            r"(?i)(unexpected keyword argument|no such option|unrecognized arguments|invalid choice|usage:)", raw_error))
        config_access_error = auth_config_access_error(raw_error)
        status = ("preflight_failed" if code in (3, 127) or config_access_error else
                  "invocation_failed" if local_invocation_error else "provider_failed_unknown")
        message = ("Tavily CLI could not read its existing authentication configuration; "
                   "no provider request was made. Retry only after granting the CLI read access."
                   if config_access_error else redact(raw_error))
        entry = ledger.record(decision, status, error=message)
        stop = code in (3, 127) or config_access_error
        help_text = AUTH_HELP if code == 3 else INSTALL_HELP if code == 127 else message
        return {"decision": decision, "executed": True, "entry": entry, "stop": stop, "message": help_text}
    cache_dir = ledger.run_dir / CACHE_DIR
    cache_dir.mkdir(exist_ok=True)
    op_id = decision["reserved_id"]
    cache_file = f"{CACHE_DIR}/{op_id}-{op}.json"
    (ledger.run_dir / cache_file).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    entry = ledger.record(decision, "ok", result_items(op, payload), cache_file)
    for failed in payload.get("failed_results", []) or []:
        url = failed.get("url") if isinstance(failed, dict) else str(failed)
        reason = failed.get("error", "extraction failed") if isinstance(failed, dict) else "extraction failed"
        n = normalize_url(url)
        src = ledger.data["sources"].setdefault(n, {"url": url, "first_seen": entry["id"], "extracted": False,
                                                     "published_date": None, "retrieved_at": entry["retrieved_at"],
                                                     "seen_in": [], "attempts": []})
        if entry["id"] not in src["seen_in"]:
            src["seen_in"].append(entry["id"])
        source_denied = is_source_access_failure(str(reason))
        src["extraction_status"] = "source access failed" if source_denied else "source status unknown; retry eligible"
        attempt = next((a for a in src.setdefault("attempts", []) if a.get("operation_id") == entry["id"]), None)
        if attempt is None:
            attempt = {"operation_id": entry["id"], "method": f"tavily {op} {params.get('depth') or 'basic'}",
                       "retrieved_at": entry["retrieved_at"]}
            src["attempts"].append(attempt)
        attempt.update(
            status="confirmed source-level access failure" if source_denied else "provider returned a source failure; status unknown",
            reason=redact(str(reason)), retrieved_at=entry["retrieved_at"],
            retry_status="alternative method required" if source_denied else "retry eligible")
        if source_denied:
            ledger.record_gap(url, str(reason), entry["id"], f"tavily {op} {params.get('depth') or 'basic'}")
    ledger.save()
    return {"decision": decision, "executed": True, "entry": entry, "payload": payload}


def run_operation(ledger: Ledger, op: str, target: list[str], params: dict,
                  runner: Callable[[list[str], int], tuple[int, str, str]] = _subprocess_runner) -> dict:
    """Serialize Tavily pre-call checks and calls with other provider adapters for this run."""
    with run_lock(ledger.run_dir):
        current = Ledger.load(ledger.run_dir)
        ledger.data = current.data
        return _run_operation_locked(ledger, op, target, params, runner)


def preflight(runner: Callable[[list[str], int], tuple[int, str, str]] = _subprocess_runner) -> tuple[bool, str]:
    """Check that tvly exists and is authenticated, without revealing any credential.

    Uses `tvly --status --json`, which reports only version and auth state. Credits are not consumed.
    """
    try:
        code, out, err = runner(["--status", "--json"], 30)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Could not run tvly ({type(exc).__name__}). {INSTALL_HELP}"
    if code == 127:
        return False, INSTALL_HELP
    try:
        status = json.loads(out) if out.strip() else {}
    except json.JSONDecodeError:
        status = {}
    if code != 0 or not status.get("authenticated"):
        detail = redact((err or "").strip().splitlines()[-1]) if (err or "").strip() else "not authenticated"
        if re.search(r"permissionerror|permission denied|access is denied|winerror\s*5|eacces", detail, re.I):
            return False, ("Tavily CLI could not access its existing authentication configuration. "
                           "Run this no-credit check in a context allowed to read the user configuration; "
                           "authentication status was not verified.")
        return False, f"{AUTH_HELP} (detail: {detail})"
    return True, f"Tavily CLI ready (version {status.get('version', 'unknown')}, authenticated)."


def compact_print(op: str, payload: dict, limit: int = 400) -> None:
    """Print a short digest; full output stays in the cache file."""
    if op == "research":
        safe_print(redact(str(payload.get("content", ""))[:1500]))
    for item in result_items(op, payload)[:30]:
        bits = [f"{item.get('score', 0):.2f}" if isinstance(item.get("score"), (int, float)) else "",
                item.get("published_date") or "", item.get("title") or "", item.get("url", "")]
        safe_print(redact(" | ".join(b for b in bits if b)))
        text = item.get("raw_content") or item.get("content") or ""
        if text and op != "map":
            safe_print(redact("   " + re.sub(r"\s+", " ", text)[:limit]))
    for failed in payload.get("failed_results", []) or []:
        safe_print(f"Extraction results need review; see the coverage status in research-usage.md: {redact(str(failed))}")


# ---------- audits ----------

def _table_rows(text: str) -> list[dict]:
    rows, header = [], None
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = cells
        elif set("".join(cells)) <= set("-: "):
            continue
        else:
            rows.append(dict(zip(header, cells)))
    return rows


def audit_run(run_dir: Path) -> list[str]:
    """Every evidence-ledger claim must cite at least one source ID defined in sources.md."""
    run_dir = Path(run_dir)
    problems: list[str] = []
    sources = (run_dir / "sources.md").read_text(encoding="utf-8") if (run_dir / "sources.md").exists() else ""
    known = {r.get("Source ID", "") for r in _table_rows(sources)}
    ledger_md = run_dir / "evidence-ledger.md"
    if not ledger_md.exists():
        return ["evidence-ledger.md missing"]
    for row in _table_rows(ledger_md.read_text(encoding="utf-8")):
        eid, cited = row.get("Evidence ID", "?"), row.get("Source ID(s)", "")
        ids = re.findall(r"S\d{3,}", cited)
        if not ids:
            problems.append(f"{eid}: claim has no source reference")
        for sid in ids:
            if sid not in known:
                problems.append(f"{eid}: cites {sid}, which is not defined in sources.md")
    return problems


SNIPPET_MARK = re.compile(r"(?i)^\s*(?:snippet only|snippet)(?:\s|$)")


def audit_warnings(run_dir: Path) -> list[str]:
    """Non-blocking checks: FACT claims resting only on snippet-only sources, and missing corroboration."""
    run_dir = Path(run_dir)
    warnings: list[str] = []
    src_path, led_path = run_dir / "sources.md", run_dir / "evidence-ledger.md"
    if not (src_path.exists() and led_path.exists()):
        return warnings
    def is_snippet_only(row: dict) -> bool:
        fetched = next((value for key, value in row.items() if key.strip().casefold().startswith("fetched")), "")
        return bool(SNIPPET_MARK.search(fetched or ""))

    snippet_only = {r.get("Source ID", "") for r in _table_rows(src_path.read_text(encoding="utf-8"))
                    if is_snippet_only(r)}
    for row in _table_rows(led_path.read_text(encoding="utf-8")):
        ids = re.findall(r"S\d{3,}", row.get("Source ID(s)", ""))
        if row.get("Evidence class", "").upper().startswith("FACT") and ids and all(i in snippet_only for i in ids):
            warnings.append(f"{row.get('Evidence ID', '?')}: FACT claim rests only on snippet-only sources "
                            f"{ids}; extract the page or downgrade the claim")
        corroboration = row.get("Corroborated by (independent)")
        if corroboration is not None and not corroboration.strip():
            warnings.append(f"{row.get('Evidence ID', '?')}: corroboration not recorded (write 'none found' if none)")
    return warnings


WEAK_TIERS = {"D"}
REAL_CUSTOMER_EVIDENCE = {"interview_recent_incident", "observed_workaround", "pilot_use", "repeat_use"}
REAL_COMMERCIAL_EVIDENCE = {"payment", "paid_pilot", "deposit", "signed_contract", "signed_loi", "procurement_step"}


def _real(evidence, allowed: set[str]) -> bool:
    """Validation labels need real-world behaviour, never desk research, simulated buyers or AI opinion."""
    items = evidence if isinstance(evidence, list) else [evidence] if evidence else []
    return any(isinstance(e, dict) and e.get("kind") in allowed and e.get("sample") for e in items)


def founder_skills_allowed(gate_result: dict) -> bool:
    """Founder skills run only for candidates at or above the evidence-supported gate."""
    return STATUS_ORDER.index(gate_result["max_status"]) >= STATUS_ORDER.index("Evidence-supported candidate")


def evidence_gate(candidate: dict) -> dict:
    """Highest status the evidence allows, from the rubric's hard gates.

    Research-volume fields (queries_run, search_results, sources_seen, ...) are ignored.
    Only independent origin clusters and source types count, and snippet-only or Tier D
    sources do not count toward independence. Unresolved contradicting evidence blocks the gate.
    The coordinator must set problem_evidence/commercial_evidence true only when the
    evidence applies to the named first-customer market; macro-only or cross-country
    transfer without justification does not satisfy those gates.
    """
    sources = candidate.get("sources", [])
    counted = [s for s in sources if not s.get("snippet_only") and str(s.get("tier", "")).upper() not in WEAK_TIERS]
    clusters = {s.get("cluster") or s.get("id") for s in counted}
    types = {s.get("type") for s in counted if s.get("type")}
    gates = {
        "1 specific user and payer": candidate.get("specific_payer", False),
        "2 problem evidence": candidate.get("problem_evidence", False),
        "3 >=3 independent sources, >=2 types, problem + commercial": (
            len(clusters) >= 3 and len(types) >= 2 and candidate.get("problem_evidence", False)
            and candidate.get("commercial_evidence", False)),
        "4 monetisation over free/status quo": candidate.get("plausible_monetisation", False),
        "5 reachable first buyers": candidate.get("reachable_buyers", False),
        "6 fits constraints": candidate.get("fits_constraints", False),
        "7 no blocking barrier": candidate.get("no_blocking_barrier", False),
        "8 cheap test exists": candidate.get("cheap_test", False),
        "9 no unresolved fatal red-team issue or contradicting evidence": (
            not candidate.get("red_team_fatal_unresolved", True)
            and not candidate.get("unresolved_contradictions")),
    }
    failed = [g for g, ok in gates.items() if not ok]
    if not failed:
        status = "Evidence-supported candidate"
        if _real(candidate.get("customer_behaviour_evidence"), REAL_CUSTOMER_EVIDENCE):
            status = "Customer-validated"
        if _real(candidate.get("commercial_commitment"), REAL_COMMERCIAL_EVIDENCE):
            status = "Commercially validated"
    elif candidate.get("specific_payer") and candidate.get("problem_evidence"):
        status = "Exploratory hypothesis"
    elif sources:
        status = "Signal detected"
    else:
        status = "Insufficient evidence"
    return {"max_status": status, "failed_gates": failed,
            "independent_clusters": len(clusters), "source_types": len(types)}


# ---------- CLI ----------

def _params(ns: argparse.Namespace) -> dict:
    keys = ("depth", "max_results", "topic", "time_range", "start_date", "end_date", "include_domains",
            "exclude_domains", "country", "include_raw_content", "query", "chunks_per_source",
            "instructions", "limit", "max_depth", "select_paths", "exclude_paths", "model")
    return {k: getattr(ns, k) for k in keys if getattr(ns, k, None) not in (None, False)}


def _add_op_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("run_dir", type=Path)
    p.add_argument("op", choices=OPS)
    p.add_argument("target", nargs="+", help="query text (search/research) or URL(s)")
    for name in ("--depth", "--topic", "--time-range", "--start-date", "--end-date", "--include-domains",
                 "--exclude-domains", "--country", "--query", "--instructions", "--select-paths",
                 "--exclude-paths", "--model", "--purpose"):
        p.add_argument(name)
    for name in ("--max-results", "--chunks-per-source", "--limit", "--max-depth"):
        p.add_argument(name, type=int)
    p.add_argument("--include-raw-content", action="store_true")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("run_dir", type=Path)
    p.add_argument("--profile", choices=("quick", "deep"), default="quick")
    p.add_argument("--budget", type=int)
    p.add_argument("--max-operations", type=int, help="per-run total provider-operation ceiling; may only lower the profile cap")
    p.add_argument("--max-dossiers", type=int, help="per-run dossier ceiling; may only lower the profile cap")
    p.add_argument("--strict-credit-bounds", action="store_true",
                   help="refuse Tavily operations without a finite configured estimate or documented pre-call bound")
    _add_op_args(sub.add_parser("plan"))
    _add_op_args(sub.add_parser("run"))
    p = sub.add_parser("record", help="log a non-Tavily lookup (host-provided search/fetch) for dedupe")
    _add_op_args(p)
    p.add_argument("--tool", default="builtin")
    p.add_argument("--status", default="ok")
    p.add_argument("--result-url", action="append", default=[])
    p = sub.add_parser("gap")
    p.add_argument("run_dir", type=Path)
    p.add_argument("url")
    p.add_argument("--reason", required=True)
    p.add_argument("--method")
    p.add_argument("--tried", action="append", default=[])
    p.add_argument("--impact", help="how the missing source affects the research")
    p = sub.add_parser("set-profile", help="switch quick <-> deep only when the user explicitly asks")
    p.add_argument("run_dir", type=Path)
    p.add_argument("profile", choices=("quick", "deep"))
    p.add_argument("--budget", type=int)
    p.add_argument("--reason", required=True)
    sub.add_parser("check", help="preflight: is tvly installed and signed in? (no credits used)")
    p = sub.add_parser("approve", help="only after the user explicitly approves extra spend")
    p.add_argument("run_dir", type=Path)
    p.add_argument("--credits", type=int, default=0)
    p.add_argument("--research-calls", type=int, default=0)
    p.add_argument("--allow-crawl", action="store_true")
    p.add_argument("--reason", required=True)
    for name in ("summary", "audit"):
        sub.add_parser(name).add_argument("run_dir", type=Path)
    sub.add_parser("dossier-check", help="pre-write guard for the run-specific dossier limit").add_argument("run_dir", type=Path)
    ns = ap.parse_args(argv)

    if ns.cmd == "check":
        ok, message = preflight()
        safe_print(message)
        return 0 if ok else 3
    if ns.cmd == "init":
        try:
            led = Ledger.init(ns.run_dir, ns.profile, ns.budget, max_operations=ns.max_operations,
                              max_dossiers=ns.max_dossiers, strict_credit_bounds=ns.strict_credit_bounds)
        except ValueError as exc:
            safe_print(redact(str(exc)), file=sys.stderr)
            return 2
        safe_print(f"Initialised {ns.run_dir / LEDGER_NAME}: profile={ns.profile}, budget={led.limit} credits")
        return 0
    if ns.cmd == "audit":
        problems = audit_run(ns.run_dir)
        safe_print("\n".join(problems) if problems else "All evidence-ledger claims cite defined sources.")
        for w in audit_warnings(ns.run_dir):
            safe_print(w)
        return 1 if problems else 0
    if ns.cmd == "dossier-check":
        allowed, message = Ledger.load(ns.run_dir).dossier_capacity()
        safe_print(message)
        return 0 if allowed else 2
    led = Ledger.load(ns.run_dir)
    if ns.cmd == "plan":
        safe_print(json.dumps(led.plan(ns.op, ns.target, _params(ns)), indent=1, ensure_ascii=True))
        return 0
    if ns.cmd == "run":
        res = run_operation(led, ns.op, ns.target, _params(ns))
        d = res["decision"]
        if not res["executed"]:
            safe_print(redact(f"{d['status']}: not executed. {d.get('reason', '')} {' '.join(d['notes'])}".strip()))
            if d.get("reuse"):
                safe_print(f"Reuse cached result: {ns.run_dir / d['reuse']}")
            return 0 if d["status"] in (DUPLICATE, SKIP_KNOWN_GAP) else 2
        if res.get("payload") is not None:
            compact_print(ns.op, res["payload"])
            safe_print(f"\n[{res['entry']['id']}] {d['status']} est. {d['est_credits']} credits ({d['basis']}); "
                  f"run total {led.spent}/{led.limit}, remaining {led.remaining} (estimated); "
                  f"full output: {ns.run_dir / res['entry']['cache_file']}")
            return 0
        safe_print(redact(f"[{res['entry']['id']}] FAILED: {res['message']}"))
        return 3 if res.get("stop") else 1
    if ns.cmd == "record":
        decision = led.plan(ns.op, ns.target, _params(ns))
        decision.setdefault("est_credits", 0)
        entry = led.record(decision, ns.status, [{"url": u} for u in ns.result_url], tool=ns.tool)
        safe_print(f"Recorded {entry['id']} ({ns.tool}, no Tavily credits)")
        return 0
    if ns.cmd == "gap":
        led.record_gap(ns.url, ns.reason, method=ns.method, tried=ns.tried, impact=ns.impact)
        safe_print("Coverage gap recorded (not evidence of absent demand).")
        return 0
    if ns.cmd == "set-profile":
        led.set_profile(ns.profile, ns.reason, ns.budget)
        safe_print(f"Profile now {ns.profile}; budget {led.limit}, remaining {led.remaining} est. credits.")
        return 0
    if ns.cmd == "approve":
        led.approve(ns.credits, ns.research_calls, ns.allow_crawl, ns.reason)
        safe_print(f"Approval recorded; budget now {led.limit} credits.")
        return 0
    if ns.cmd == "summary":
        (ns.run_dir / USAGE_NAME).write_text(led.summary_markdown(), encoding="utf-8")
        safe_print(f"Wrote {ns.run_dir / USAGE_NAME}: {led.spent}/{led.limit} est. credits, "
              f"{len(led.data['coverage_gaps'])} coverage gap(s)")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
