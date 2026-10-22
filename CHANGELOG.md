# Changelog

## 1.4.0 — Cross-platform canonical skill and distributions

- Established `core/opportunity-radar/` as the host-independent source for the skill, evidence methodology, provider policy, scripts, references, templates and schemas.
- Preserved all six Claude Code specialist agents as host-specific adapters and generated self-contained Claude Code, Codex and GitHub Copilot packages.
- Added documented, surface-aware capability matrix and portable invocation/fallback guidance; no cross-host MCP access is assumed.
- Added reproducible distribution build/check, safe dry-run installers with explicit timestamped backups for updates, installed-version lookup, and report/skill validators.
- Added cross-platform packaging tests, synthetic fixtures, and evaluation scenarios for developer demand, manufacturing/trade data, missing evidence, conflicts, zero finalists and low-cost validation.
- Historical research runs and the weighted scoring methodology remain unchanged.

## 1.3.0 — Multi-source routing and usage accounting

- Added question-specific routing for Tavily, conditionally available Exa, optional Brave, GitHub and relevant public datasets.
- Added local configurable per-provider/overall call guardrails and append-only provider usage tracking. Caps are explicitly local policy; costs remain unknown unless provider-reported.
- Added an optional Brave Web Search API adapter using `X-Subscription-Token`, existing environment variables, credential-safe errors, per-run deduplication, published-price estimates and plan quota headers. It does not persist Brave Search Results, per Brave's terms.
- Added a compatible JSON source-record schema and extended source/evidence templates while preserving the Markdown ledger and existing run history.
- Recorded the tool/environment audit and confirmed the existing scoring gates remain unchanged.

## 1.2.0 — Tavily integration hardening

- **New commands:**
  - `research_ledger.py check` preflight: actionable install and sign-in messages with no secrets, and never asks for an API key in chat.
  - `set-profile` for a user-requested switch from quick to deep.
  - `gap --impact` to record how a blocked source affects the research.
- **Reporting:** remaining budget, and per-source fetch status (full page / snippet only / blocked) in `research-usage.md`.
- **Defined scan modes:** Quick Scan (≤2 dossiers, early rejection) and Deep Scan (≤5 dossiers, full red team).
- **Stricter evidence gate:**
  - snippet-only and Tier D sources don't count toward independence;
  - unresolved contradictions block promotion;
  - validation labels require real behaviour with a sample;
  - `founder_skills_allowed()` encodes the founder rule.
- **Templates:** a "Corroborated by (independent)" column in the evidence ledger, and a "Fetched" column in sources.
- **Audit warnings** for FACT claims resting only on snippets, and for missing corroboration. Warnings are non-blocking, so existing runs still pass.
- **Routing policy:** credential rules, precedence over conflicting Tavily-skill instructions, and impact of coverage gaps.
- **Tests:** 46 offline tests, including credentials, founder gating, existing run scaffold/validation and package structure. Manual evaluation case 8 added.

## 1.1.0 — Tavily research routing

- When the Tavily CLI is installed and authenticated, the skill uses it through a single coordinator. Routing policy: `references/tavily-research-routing.md`.
- Added `scripts/research_ledger.py`, run per research run:
  - configurable quick/deep credit budgets (`config/research-budget.json`), with documented vs estimated rates kept separate;
  - approval gates for research, crawl and oversized calls;
  - query and URL dedupe, with a local result cache;
  - coverage-gap logging;
  - credential redaction;
  - a claims-to-sources audit;
  - a volume-blind evidence-gate ceiling.
- Agents get a "Shared evidence" section: reuse the ledger and cache, return extra query requests instead of repeating searches.
- Scoring rubric: research volume never raises a rating; blocked sources are coverage gaps.
- Added offline unit tests (`tests/test_research_ledger.py`). Evidence gates, templates and the founder workflow are unchanged.

## 1.0.0 — Full workflow package

- Added comprehensive country-to-opportunity research workflow.
- Added six specialist Claude Code subagents.
- Added evidence hierarchy, country playbook, signal taxonomy, scoring rubric, unit-economics guidance, founder-skill integration and validation playbook.
- Added full report templates, evaluation cases, package/run validators and personal installers.
- Reaffirmed evidence labels and the requirement to accept zero qualifying opportunities.
