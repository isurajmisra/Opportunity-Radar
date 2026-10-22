#!/usr/bin/env python3
"""Per-run call guardrails and usage accounting for non-Tavily providers."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
POLICY_PATH = SKILL_DIR / "config" / "provider-policy.json"
LEDGER_NAME = "provider-usage.json"
KNOWN = {"brave", "github", "builtin_web", "public_api", "exa", "tavily"}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).casefold()


def redact(text: str) -> str:
    text = re.sub(r"tvly-[A-Za-z0-9_-]{6,}", "[REDACTED]", text)
    text = re.sub(r"(?i)(api[_-]?key|token|secret|password)(\s*[=:]\s*)\S+",
                  lambda m: m.group(1) + m.group(2) + "[REDACTED]", text)
    return re.sub(r"(?i)bearer\s+[A-Za-z0-9._-]{16,}", "Bearer [REDACTED]", text)


class Usage:
    def __init__(self, run: Path, profile: str, policy: dict):
        self.run, self.profile, self.policy = run, profile, policy
        self.path = run / LEDGER_NAME
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
            if self.data["profile"] != profile:
                raise ValueError(f"Run profile is {self.data['profile']}, not {profile}.")
        else:
            self.data = {"created_at": now(), "profile": profile, "operations": [], "approvals": []}
            self.save()

    def save(self) -> None:
        self.run.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def check(self, provider: str, operation: str, query: str,
              estimated_cost_usd: float | None = None,
              ignore_expired_burst_snapshot: bool = False) -> tuple[str, str]:
        if provider not in KNOWN:
            return "STOP", f"Unknown provider {provider!r}."
        if not self.policy.get("providers", {}).get(provider, {}).get("enabled", False):
            return "STOP", f"Provider {provider} is disabled or unavailable."
        key = (provider, operation, norm(redact(query)))
        if any((x["provider"], x["operation"], norm(x["query"])) == key for x in self.data["operations"]):
            return "DUPLICATE", "This provider/operation/query is already logged in this run; do not repeat it."
        if provider == "brave":
            latest = next((x for x in reversed(self.data["operations"])
                           if x["provider"] == "brave" and x.get("provider_headers", {}).get("X-RateLimit-Remaining")), None)
            if latest:
                try:
                    remaining = [int(x.strip()) for x in latest["provider_headers"]["X-RateLimit-Remaining"].split(",")]
                    reset = [int(x.strip()) for x in latest["provider_headers"].get("X-RateLimit-Reset", "").split(",") if x.strip()]
                except ValueError:
                    remaining, reset = [], []
                if len(remaining) > 1 and any(n == 0 for n in remaining[1:]):
                    return "STOP", "Brave reported an exhausted non-burst quota window; wait for provider reset. No call was made."
                if remaining and remaining[0] == 0 and not ignore_expired_burst_snapshot:
                    delay = reset[0] if reset else 1
                    return "WAIT", f"Brave's first rate window is exhausted; wait {delay} seconds then recheck."
        tavily_path = self.run / "research-ledger.json"
        tavily_calls = 0
        if tavily_path.exists():
            try:
                tavily_calls = len(json.loads(tavily_path.read_text(encoding="utf-8")).get("operations", []))
            except (json.JSONDecodeError, OSError):
                return "STOP", "Tavily usage ledger could not be read; refusing to bypass the overall call guardrail."
        used_total = len(self.data["operations"]) + tavily_calls
        used_provider = sum(x["provider"] == provider for x in self.data["operations"])
        if provider == "tavily":
            used_provider += tavily_calls
        total_cap = self.policy["total_operations"][self.profile]
        provider_cap = self.policy["provider_operations"][self.profile].get(provider, 0)
        extra_total = sum(a["extra_total_operations"] for a in self.data["approvals"])
        extra_provider = sum(a["extra_provider_operations"] for a in self.data["approvals"] if a["provider"] == provider)
        used_usd = sum((x.get("actual_cost") if x.get("actual_cost") is not None else x.get("estimated_cost") or 0)
                       for x in self.data["operations"] if (x.get("currency") or "USD").upper() == "USD")
        usd_cap = self.policy.get("estimated_cost_budget_usd", {}).get(self.profile, 0)
        extra_usd = sum(a.get("extra_cost_usd", 0) for a in self.data["approvals"])
        projected_usd = used_usd + (estimated_cost_usd or 0)
        if estimated_cost_usd is not None and projected_usd > usd_cap + extra_usd:
            return "NEEDS_APPROVAL", (f"Estimated USD cost would exceed the local estimate ceiling: "
                                       f"${projected_usd:.4f} > ${usd_cap + extra_usd:.4f}. "
                                       "This is a list-price estimate, not actual billing.")
        if used_total >= total_cap + extra_total or used_provider >= provider_cap + extra_provider:
            return "NEEDS_APPROVAL", (f"Local call guardrail reached (overall {used_total}/{total_cap + extra_total}; "
                                       f"{provider} {used_provider}/{provider_cap + extra_provider}).")
        return "ALLOW", (f"Local call guardrails: overall {used_total}/{total_cap + extra_total}; "
                         f"{provider} {used_provider}/{provider_cap + extra_provider}; "
                         f"estimated USD ${used_usd:.4f}/${usd_cap + extra_usd:.4f}. "
                         "These are not provider quotas or cost estimates.")

    def record(self, provider: str, operation: str, query: str, status: str,
               actual_cost: float | None = None, currency: str | None = None,
               actual_credits: float | None = None, estimated_cost: float | None = None,
               estimate_basis: str | None = None, provider_headers: dict | None = None,
               ignore_expired_burst_snapshot: bool = False) -> dict:
        decision, detail = self.check(provider, operation, query, estimated_cost,
                                      ignore_expired_burst_snapshot)
        if decision not in ("ALLOW", "NEEDS_APPROVAL"):
            raise ValueError(detail)
        if decision == "NEEDS_APPROVAL":
            raise PermissionError(detail + " Ask for approval; do not record a new external call yet.")
        entry = {"operation_id": f"P{len(self.data['operations']) + 1:03d}", "provider": provider,
                 "operation": operation, "query": redact(query), "query_count": 1, "status": status,
                 "retrieved_at": now(), "actual_cost": actual_cost, "currency": currency,
                 "actual_credits": actual_credits, "estimated_cost": estimated_cost,
                 "estimate_basis": estimate_basis,
                 "provider_headers": provider_headers or {},
                 "cost_status": "reported_actual" if actual_cost is not None else
                     "reported_credits" if actual_credits is not None else
                     "estimated" if estimated_cost is not None else "unknown"}
        self.data["operations"].append(entry)
        self.save()
        return entry


def load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("check", "record"):
        q = sub.add_parser(name)
        q.add_argument("run", type=Path)
        q.add_argument("provider", choices=sorted(KNOWN))
        q.add_argument("operation")
        q.add_argument("query")
        q.add_argument("--profile", choices=("quick", "deep"), default="quick")
        if name == "record":
            q.add_argument("--status", default="ok")
            q.add_argument("--actual-cost", type=float)
            q.add_argument("--currency")
            q.add_argument("--actual-credits", type=float)
            q.add_argument("--estimated-cost", type=float)
            q.add_argument("--estimate-basis")
            if name == "check":
                q.add_argument("--estimated-cost-usd", type=float)
    a = sub.add_parser("approve")
    a.add_argument("run", type=Path)
    a.add_argument("provider", choices=sorted(KNOWN))
    a.add_argument("--operations", type=int, required=True)
    a.add_argument("--estimated-cost-usd", type=float, default=0)
    a.add_argument("--reason", required=True, help="Record the user's explicit approval and its scope")
    a.add_argument("--profile", choices=("quick", "deep"), default="quick")
    s = sub.add_parser("summary")
    s.add_argument("run", type=Path)
    s.add_argument("--profile", choices=("quick", "deep"), default="quick")
    mode = sub.add_parser("set-profile")
    mode.add_argument("run", type=Path)
    mode.add_argument("profile", choices=("quick", "deep"))
    mode.add_argument("--reason", required=True)
    args = p.parse_args()
    if args.command == "set-profile":
        path = args.run / LEDGER_NAME
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = {"created_at": now(), "operations": [], "approvals": []}
        old = data.get("profile", args.profile)
        data["profile"] = args.profile
        data.setdefault("profile_changes", []).append({"from": old, "to": args.profile,
                                                        "reason": redact(args.reason), "at": now()})
        args.run.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Provider usage profile recorded: {old} -> {args.profile}.")
        return 0
    usage = Usage(args.run, args.profile, load_policy())
    if args.command == "check":
        decision, detail = usage.check(args.provider, args.operation, args.query,
                                       getattr(args, "estimated_cost_usd", None))
        print(f"{decision}: {detail}")
        return 0 if decision == "ALLOW" else 2
    if args.command == "record":
        try:
            item = usage.record(args.provider, args.operation, args.query, args.status,
                                args.actual_cost, args.currency, args.actual_credits,
                                args.estimated_cost, args.estimate_basis)
        except (ValueError, PermissionError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"Recorded {item['operation_id']} ({item['cost_status']}).")
        return 0
    if args.command == "approve":
        if args.operations < 1 or args.estimated_cost_usd < 0 or not args.reason.strip():
            print("Approval requires positive operations and a reason.", file=sys.stderr)
            return 2
        usage.data["approvals"].append({"provider": args.provider, "extra_provider_operations": args.operations,
                                        "extra_total_operations": args.operations,
                                        "extra_cost_usd": args.estimated_cost_usd,
                                        "reason": redact(args.reason), "at": now()})
        usage.save()
        print(f"Recorded scoped approval for {args.operations} additional {args.provider} operation(s).")
        return 0
    ops = usage.data["operations"]
    tavily_path = args.run / "research-ledger.json"
    tavily_ops = len(json.loads(tavily_path.read_text(encoding="utf-8")).get("operations", [])) if tavily_path.exists() else 0
    total_ops = len(ops) + tavily_ops
    extra_total = sum(x["extra_total_operations"] for x in usage.data["approvals"])
    total_cap = usage.policy["total_operations"][args.profile] + extra_total
    usd_cap = usage.policy.get("estimated_cost_budget_usd", {}).get(args.profile, 0)
    usd_cap += sum(x.get("extra_cost_usd", 0) for x in usage.data["approvals"])
    used_usd = sum((x.get("actual_cost") if x.get("actual_cost") is not None else x.get("estimated_cost") or 0)
                   for x in ops if (x.get("currency") or "USD").upper() == "USD")
    print(f"Profile: {args.profile}; tracked operations: {total_ops} including {tavily_ops} Tavily "
          f"(local guardrail {total_cap}; {max(total_cap-total_ops, 0)} remaining)")
    print("Actual charges/credits are unknown unless provider-reported. Estimates are shown separately.")
    print(f"Estimated USD budget: ${used_usd:.4f}/${usd_cap:.4f}; ${max(usd_cap-used_usd,0):.4f} remaining "
          "(provider-specific estimates only; excludes unknown costs and Tavily credits).")
    for provider in sorted(KNOWN):
        rows = [x for x in ops if x["provider"] == provider]
        if rows:
            print(f"{provider}: {len(rows)} operations; " + ", ".join(f"{k}={sum(x['operation']==k for x in rows)}" for k in sorted({x['operation'] for x in rows})))
    print(f"Detailed ledger: {usage.path}")
    quota_notes = []
    for provider in sorted({x["provider"] for x in ops}):
        snapshot = next((x for x in reversed(ops) if x["provider"] == provider and x.get("provider_headers")), None)
        if snapshot:
            headers = snapshot["provider_headers"]
            quota_notes.append(f"- {provider} quota snapshot at {snapshot['retrieved_at']}: "
                               f"limit={headers.get('X-RateLimit-Limit', 'not returned')}; "
                               f"remaining={headers.get('X-RateLimit-Remaining', 'not returned')}; "
                               f"reset={headers.get('X-RateLimit-Reset', 'not returned')} (provider-reported)")
    section = ["<!-- PROVIDER_USAGE_START -->", "## Other provider usage", "",
               f"- Local profile: **{args.profile}**; tracked operations: **{total_ops}** "
               f"(including {tavily_ops} Tavily; local guardrail: {total_cap} total, "
               f"{max(total_cap-total_ops, 0)} remaining).",
               f"- Estimated USD: **${used_usd:.4f} / ${usd_cap:.4f}**; **${max(usd_cap-used_usd, 0):.4f} estimated remaining** "
               "(known-price providers only; unknown costs and Tavily credits are separate).",
               "- These operation caps are local safeguards, not provider quotas, rates, or cost estimates.",
               "- Actual monetary charge/credits: **unknown** unless provider-reported. Estimates are not actual usage.", "",
               "| Provider | Operation | Calls/queries | Status | Actual cost/credits | Estimated cost and basis |", "|---|---|---:|---|---|---|"]
    if quota_notes:
        section += ["", "### Provider-reported quota snapshots", ""] + quota_notes
    provider_remaining = []
    for provider in sorted(KNOWN):
        cap = usage.policy["provider_operations"][args.profile].get(provider, 0)
        extra = sum(x["extra_provider_operations"] for x in usage.data["approvals"] if x["provider"] == provider)
        used = sum(x["provider"] == provider for x in ops)
        if provider == "tavily":
            used += tavily_ops
        if cap or extra:
            provider_remaining.append(f"- {provider}: {max(cap + extra - used, 0)} local operation(s) remaining.")
    if provider_remaining:
        section += ["", "### Local per-provider guardrails", ""] + provider_remaining
    for provider, operation in sorted({(x["provider"], x["operation"]) for x in ops}):
        rows = [x for x in ops if x["provider"] == provider and x["operation"] == operation]
        known = [f"{x['actual_cost']} {x['currency'] or ''}" if x.get("actual_cost") is not None
                 else f"{x['actual_credits']} credits" for x in rows
                 if x.get("actual_cost") is not None or x.get("actual_credits") is not None]
        estimated_rows = [x for x in rows if x.get("estimated_cost") is not None]
        estimates = (f"{sum(x['estimated_cost'] for x in estimated_rows):.6f} "
                     f"{estimated_rows[0].get('currency') or 'USD'} total across {len(estimated_rows)} operations "
                     f"({'; '.join(sorted({x.get('estimate_basis') or 'basis unknown' for x in estimated_rows}))})") if estimated_rows else "unknown"
        section.append(f"| {provider} | {operation} | {sum(x.get('query_count', 1) for x in rows)} | "
                       f"{', '.join(sorted({x['status'] for x in rows}))} | {', '.join(known) if known else 'unknown'} | "
                       f"{estimates} |")
    if not ops:
        section.append("| None | None | 0 | n/a | unknown | unknown |")
    section += ["", "<!-- PROVIDER_USAGE_END -->"]
    report = args.run / "research-usage.md"
    old = report.read_text(encoding="utf-8") if report.exists() else "# Research usage\n"
    start, end = "<!-- PROVIDER_USAGE_START -->", "<!-- PROVIDER_USAGE_END -->"
    if start in old and end in old:
        left, rest = old.split(start, 1)
        _, right = rest.split(end, 1)
        updated = left.rstrip() + "\n\n" + "\n".join(section) + right
    else:
        updated = old.rstrip() + "\n\n" + "\n".join(section) + "\n"
    report.write_text(updated, encoding="utf-8")
    print(f"Combined report updated: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
