# Opportunity Radar infrastructure audit

**Reviewed:** 2026-10-23  
**Scope:** Existing package, research history and tools exposed in the current session. No earlier run was modified.

## Existing architecture

- Claude Code slash skill at `.claude/skills/opportunity-radar/SKILL.md`, with country-to-opportunity workflow, dated non-overwriting runs, quick/deep scan modes and a zero-finalist outcome.
- Six bounded specialist agents under `.claude/agents/`: country context, customer pain, competitor economics, business model, skeptical review and validation design. Agents are read-only and share source-ledger rules.
- Ten playbooks cover source hierarchy, country comparison, signals, scoring, unit economics, validation, founder integration, privacy, source catalog and Tavily routing.
- Weighted 100-point rubric and nine hard gates. Evidence status is kept distinct from score; snippet-only/Tier D sources and unresolved contradictions cannot pass the gate.
- Markdown claim ledger and source table already track stable source IDs, dates, source type, independence clusters, access status and limitations.
- Report templates cover executive summary, country snapshot, signal inventory, shortlist, candidate brief, source/evidence ledgers, red team, validation, founder review and run log.
- `init_run.py` creates unique dated folders; `research_ledger.py` handles Tavily preflight, estimates, approvals, deduplication, cache, gaps and claim/source audit; `validate_run.py` checks run structure; `validate_package.py` checks package structure. One offline test module and eight manual evaluation cases are present.
- Founder validation is conditional on installed skills, evidence gates and safe write paths. No founder-specific skill is exposed in this session. Existing reports record no founder overwrite; both India runs remain untouched.
- Two completed run folders dated 2026-10-22 are present, with full reports, ledgers, candidate dossiers and research notes. They remain unchanged.

## Confirmed tools and gaps

- Tavily CLI `tvly` is installed and authenticated through OAuth. Its status check required access to its existing user configuration; no key was printed and no installation or research call was made.
- Tavily skills installed: search, extract, crawl, map, research, dynamic-search, CLI and best-practices. They document operation options and some rates, but not a universal exact charge for every CLI operation. The current ledger correctly marks multiple rates estimated and research as an unknown reservation. API result shapes can optionally carry usage data; CLI output does not currently request/forward exact usage. Budget values are product-local guardrails, not account or provider quotas.
- Exa MCP is not available in the current tool registry. Do not claim it was used; keep Exa an optional route for sessions where tools are exposed.
- Web search is available in-session. GitHub MCP search tools are available. `gh` is installed but not authenticated in this environment. Public unauthenticated GitHub access remains possible where the tool permits it.
- Brave API key variables `BRAVE_API_KEY` and `BRAVE_SEARCH_API_KEY` are unset, and no existing Brave wrapper/config was found. Brave must stay optional and fail closed when no key is configured.
- Current official Brave documentation lists Search at $5 per 1,000 requests and provides plan-specific `X-RateLimit-*` headers. The terms prohibit storing/caching Search Results. The wrapper therefore reports only the published per-call estimate and observed response headers in the usage ledger; it displays result links transiently and persists no Brave result payload, title, URL or snippet. Original pages must be independently retrieved before being added to the evidence ledger.
- Public API integrations (Hacker News, PyPI, World Bank, Eurostat, UN Comtrade, OpenAlex, Adzuna) were not found in this session. No such source is made a mandatory dependency; route to them only when available and relevant.
- No additional founder skill or overlapping framework was installed as part of this audit.

## Overlapping open-source frameworks reviewed

- **GPT Researcher** uses planner/execution agents, source tracking, multi-source search and MCP integrations. It overlaps research orchestration and report assembly, but its default goal is broad sourced reporting rather than this project's hard evidence gates, independent-origin checks, founder constraints, unit economics and real-world falsification workflow.
- **Stanford STORM / Co-STORM** focuses on topic curation, multi-perspective question asking and article/report synthesis. It can structure background exploration, but it is not an opportunity-screening or validation system.
- **LangChain Open Deep Research** provides configurable model/search/MCP components in a LangGraph workflow, but its upstream repository is archived as of this review. It would add runtime dependencies without replacing this project's market evidence and founder-validation rules.

No framework was installed. Their orchestration patterns do not justify replacing the existing skill/agents or adding a mandatory runtime. Official project references: [GPT Researcher repository](https://github.com/assafelovic/gpt-researcher), [STORM repository](https://github.com/stanford-oval/storm), [Open Deep Research repository](https://github.com/langchain-ai/open_deep_research).

## Gaps and conflicts found

- Tavily-only routing and credit accounting existed; other providers had no shared per-run call accounting or explicit opt-in route.
- Source tables already cover most requested fields, but there was no machine-readable compatible source-record shape for other providers. Brave results specifically cannot be persisted under the current API terms; verified original pages, retrieved separately, can still feed the common schema.
- The evidence gate covered problem and commercial evidence, but its written rule did not explicitly tie both to the candidate's first-customer market. The rubric now makes that geographic applicability explicit without adding score weight or lowering any gate.
- Tavily rates mix documented values, estimates and reservations; reports need to keep these distinctions and must not treat a reservation/request count as actual spend.
- The skill asks coordinators to use subagents, while actual availability varies by session. Provider coverage likewise varies; routing must describe capabilities conditionally.
- The pasted implementation request ends mid-sentence in Phase 6 (“Evidence that the opportunity exists in the targeted”). No later requirements were present in the attachment; this audit and implementation cover the supplied text only.
- The project directory has no `.git` metadata, so repository status/diff cannot be used to distinguish pre-existing edits.

## Files to change and minimum implementation

- Keep the existing main skill, weighted score, run history and templates; extend the skill and provider-routing reference with question-specific Tavily/Exa/Brave/GitHub/public-source selection and country/market interpretation guidance. Make the first-customer market explicit in the hard-gate wording without changing weights or evidence thresholds.
- Add a local provider policy with configurable Quick/Deep operation limits (explicitly local guardrails, not provider quotas or prices) and an append-only run usage ledger for provider/operation/query counts, known actual usage, unknown/estimated spend, budget decisions and approvals.
- Add a standard-library Brave Search wrapper using `X-Subscription-Token`, environment-variable lookup, no secret logging, optional behavior when authentication is absent, and no retention of Search Results in line with provider terms.
- Add a compatible machine-readable source schema and update source/evidence template guidance without replacing the existing Markdown evidence ledger.
- Update package documentation and structural checks to expose the new interfaces and limitations.

## Work not performed during audit

- No existing run, account or secret was modified. Official Brave API documentation was consulted to verify its endpoint, authentication header, current list pricing, quota headers, privacy and result-retention terms. Upstream framework READMEs were inspected for architecture overlap; no market/opportunity sources were researched and no code was installed.
- No package, skill, MCP server or external framework was installed.
- Existing tests/evaluations were inspected, not run during audit.

## Repository cleanup follow-up — 2026-10-23

This follow-up records the state of the current repository and does not rewrite the findings above, which describe the earlier audit snapshot.

- At the earlier snapshot, the audit did not find a Brave wrapper/configuration and recorded that the local Brave environment variables were unset. The current repository contains `core/opportunity-radar/scripts/brave_search.py` and `config/provider-policy.json` entries for Brave. The public repository cannot establish whether any particular user's local API-key environment variable is set; the wrapper checks locally at runtime and makes no request when neither supported variable is present.
- Current Brave behavior: the wrapper sends the configured token in `X-Subscription-Token`, never prints it, enforces local operation/cost guardrails, records applicable estimates and returned quota headers, displays result links transiently, and does not persist Brave Search Results. It also avoids sending a query that matches its credential-redaction rules. No live Brave API request was made for this follow-up.
- Tavily usage remains separate from USD estimates. The local ledger distinguishes documented rates, estimates and unknown research reservations; CLI requests do not establish actual account charges unless provider-reported usage is available. Preflight checks CLI/auth state without using research credits. Local operation limits are not provider quotas.
- Exa remains conditional on search/retrieval tools being exposed and configured in the active host. GitHub research uses surfaced MCP tools or `gh` when available; otherwise use permitted public access or record a coverage gap. Authentication state is per environment and is not inferred from repository contents.
- The earlier statement that the project directory had no `.git` metadata described an earlier repository snapshot. The current working copy has Git metadata on `master` at `d37ee22c5aeb1284c314a58077cde3fd9d9df58a`; it was clean before this follow-up.
- A manual secret-pattern scan found token-shaped strings in the redaction test fixture `core/opportunity-radar/tests/test_research_ledger.py` and its tracked generated package copies. The context identifies them as test inputs, not credentials; this has not been confirmed against a provider. The strings appear in the current tree and commit `d37ee22c5aeb1284c314a58077cde3fd9d9df58a`. The same commit's tracked bytecode also contained a machine-specific path; those bytecode files are removed from the current tree, but Git history was not rewritten. No secret value is reproduced here. If any fixture value was ever a real credential, revoke it. No Gitleaks, TruffleHog or equivalent scanner was installed in this environment.
- Four tracked Python bytecode cache files were removed from source control; no source files or historical research runs were removed or edited. `.gitignore` now excludes Python caches/bytecode, common Python virtual environments and tool caches, while keeping `.env.example` eligible for tracking.
- This cleanup did not run a market scan or provider API request, install tools, or rewrite Git history.

## CI and full-history secret audit — 2026-10-23

- Added a cross-platform GitHub Actions validation matrix for Python 3.10 and 3.14 on Ubuntu, Windows, and macOS, plus a separate Gitleaks full-history scan. The jobs use read-only repository permissions, SHA-pinned actions, no personal credentials, and no provider calls. The validation job checks generated package freshness without rebuilding packages.
- A redacted pattern scan covered all 2 reachable commits and 84 unique Git blobs. It found a Tavily-shaped value only in the synthetic secret-redaction test assignment copied into seven canonical/generated test files in both commits, and in one historical tracked `.pyc` file. This pattern is treated as a test fixture, not a confirmed live credential; it was not tested against a provider. No common GitHub, AWS, Stripe, Slack or Google token pattern, or private-key header, was found by the local scan. The scan is not a substitute for Gitleaks' broader rules, which will run in CI.
- A separate current-tree scan checked 323 tracked files and found the same seven test-fixture copies; no additional token pattern or private-key header was identified.
- A full working-directory scan checked 517 files, including ignored local outputs (excluding `.git`, Python environments and caches). It found the seven tracked fixture copies plus four copies in ignored skill backups, and a home-directory path pattern in two ignored local report files. Those backups and historical reports were left unchanged and do not appear in reachable Git history.
- A separate local-data scan found machine-specific Windows profile strings in four generated `.pyc` cache files in the older commit; all four files are absent from the current tree. The local research-run path pattern appeared only as documentation text, not as committed run output; no `.env` path was tracked.
- `.gitleaks.toml` allows only the exact fixture assignment line in the seven named files and the two commits that contain it; a separate allowlist covers the one historical bytecode file in its original commit. No test directory is broadly excluded. Gitleaks will scan both the current tree and reachable history in its full-history run.
- Gitleaks, TruffleHog, and detect-secrets are not installed locally; Docker is present but its daemon is unavailable. The Gitleaks action could not be executed in this environment. Remote GitHub secret-scanning alerts were not queried. Therefore the workflow's Gitleaks run remains pending on GitHub, and this audit does not claim the repository is free of every credential.
- Existing local historical reports were not changed. `validate-reports.py` reports structural passes with warnings that `research-usage.md` is missing in both saved runs.
