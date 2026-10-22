#!/usr/bin/env python3
"""Optional Brave Search adapter; results are displayed transiently, never stored or cached."""
from __future__ import annotations

import argparse
import json
import os
import sys
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from provider_usage import Usage, load_policy, redact

API = "https://api.search.brave.com/res/v1/web/search"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run", type=Path)
    p.add_argument("query")
    p.add_argument("--profile", choices=("quick", "deep"), default="quick")
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--country", help="Brave's two-character country code, if useful")
    a = p.parse_args()
    if not 1 <= a.count <= 20:
        p.error("--count must be between 1 and 20")
    if not a.query.strip() or len(a.query) > 600 or len(a.query.split()) > 75:
        p.error("query must be non-empty, at most 600 characters and at most 75 words")
    if redact(a.query) != a.query:
        print("Query appears to contain a credential; refusing to send it to Brave.", file=sys.stderr)
        return 2
    token = os.environ.get("BRAVE_API_KEY") or os.environ.get("BRAVE_SEARCH_API_KEY")
    if not token:
        print("Brave unavailable: configure BRAVE_API_KEY or BRAVE_SEARCH_API_KEY locally. No call was made.", file=sys.stderr)
        return 3
    usage = Usage(a.run, a.profile, load_policy())
    price = load_policy()["providers"]["brave"]["cost_model"]
    estimated_cost = price["list_price_usd_per_1000_requests"] / 1000
    decision, reason = usage.check("brave", "search", a.query, estimated_cost)
    if decision == "WAIT":
        match = re.search(r"wait (\d+) seconds", reason)
        delay = int(match.group(1)) if match else 1
        if delay > 5:
            print(f"WAIT: {reason} No call was made.", file=sys.stderr)
            return 2
        time.sleep(delay)
        decision, reason = usage.check("brave", "search", a.query, estimated_cost,
                                       ignore_expired_burst_snapshot=True)
    if decision != "ALLOW":
        print(f"{decision}: {reason}", file=sys.stderr)
        return 2
    params = {"q": a.query, "count": str(a.count)}
    if a.country:
        params["country"] = a.country
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers={
        "Accept": "application/json", "X-Subscription-Token": token, "User-Agent": "OpportunityRadar/1.0"
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
            headers = {k: response.headers.get(k) for k in
                       ("X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset")
                       if response.headers.get(k) is not None}
        rate_info = json.dumps(headers, sort_keys=True) if headers else ""
        usage_entry = usage.record("brave", "search", a.query, "ok",
                                   estimated_cost=estimated_cost,
                                   estimate_basis=price["basis"], provider_headers=headers,
                                   ignore_expired_burst_snapshot=True)
    except urllib.error.HTTPError as exc:
        headers = {k: exc.headers.get(k) for k in
                   ("X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset")
                   if exc.headers and exc.headers.get(k) is not None}
        try:
            usage.record("brave", "search", a.query, f"http_{exc.code}", provider_headers=headers,
                         ignore_expired_burst_snapshot=True)
        except (ValueError, PermissionError):
            pass
        detail = str(exc).replace(token, "[REDACTED]")
        print(f"Brave request failed: {detail}; result content was not saved.", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        # Brave's rate-limit documentation says failed HTTP requests are not billed;
        # keep the attempt in the local guardrail ledger with cost explicitly unknown.
        try:
            usage.record("brave", "search", a.query, "failed", estimate_basis=None,
                         ignore_expired_burst_snapshot=True)
        except (ValueError, PermissionError):
            pass
        detail = str(exc).replace(token, "[REDACTED]")
        print(f"Brave request failed: {detail}; no result content was saved.", file=sys.stderr)
        return 1

    # Brave's Search API terms prohibit storing/caching any part of Search Results.
    # Do not write titles, URLs, snippets or payloads to the run directory.
    results = (payload.get("web", {}) or {}).get("results", [])
    print(f"Brave search completed ({usage_entry['operation_id']}); list-price estimate: "
          f"${estimated_cost:.3f} USD; actual account charge unknown.")
    print(f"Plan quota headers (provider-reported): {rate_info or 'not returned'}")
    print("Search-result links below are transient discovery leads. Open the original pages and record those pages independently.")
    for row in results:
        if row.get("url"):
            print(row["url"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
