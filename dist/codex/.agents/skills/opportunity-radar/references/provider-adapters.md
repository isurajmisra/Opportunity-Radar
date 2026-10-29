# Provider adapters and common source records

Provider transport is selected at runtime. Claude Code, Codex, and Copilot do not share MCP connections, credentials, CLI installations, or network permissions. A provider is usable only when its client/tool is actually exposed and permitted by the current budget policy.

## Available transports

| Provider | Transport | Runtime requirement | Mapping guidance |
|---|---|---|---|
| Tavily | Installed CLI through `scripts/research_ledger.py` | `tvly` installed and authenticated | Host/MCP Tavily tools are not interchangeable with the CLI schema and must not be used directly. Record operation, sources, and estimate basis in the ledger. |
| Exa | Host-specific MCP search/fetch tools | Exa MCP configured separately in that host and visible in its tool list | Normalize the opened original page into the common record. Under a hard run cap, do not use unless a guarded adapter reserves and records the operation in the shared run ledger. |
| Brave | `scripts/brave_search.py` guarded HTTPS API wrapper | Python, network access, and `BRAVE_API_KEY` or `BRAVE_SEARCH_API_KEY` | Checks and serializes against the shared run-operation ledger before making the request. Search results are transient discovery leads; do not persist result payloads. |
| GitHub | Host GitHub MCP or `gh api` | Search/read tools or authenticated/public CLI access | Record repository/issue/PR/release URLs and dates. Under a hard run cap, do not use unless a guarded adapter reserves and records the operation in the shared run ledger. |
| Hacker News | Public Firebase API or host web tools | Network/API access in the active runtime | Discussion is qualitative, self-selected evidence; retain item URL/time and do not estimate prevalence from votes/comments. |
| PyPI | PyPI Stats endpoint or project metadata pages | Network access; third-party statistics may have their own limits/retention | Record package, interval, returned metric and dataset caveat; downloads are not unique users or paying customers. |
| World Bank | Public API | Network access | Preserve indicator code, country, period, unit, source and revision; use only as market context. |
| Eurostat | Official API/database | Network access | Preserve dataset code, filters, unit, reference period, and revision. Compare equivalent measures. |
| UN Comtrade | Official API or public portal | Network access; authentication/plan requirement may apply to requested endpoints | Record reporter/partner, commodity code, flow, year, value/quantity and source vintage. Trade is a lead, not proof of unmet demand. |
| OpenAlex | Public API | Network access and any current service limits | Record query and result date; research volume indicates research activity, not commercial readiness. |
| Adzuna | Intelligence API | Account credentials, permitted use, and target-country coverage | Optional; record country/query, returned period and access status. Job listings do not equal hires or total vacancies. |

The catalog in `source-catalog.md` contains authoritative starting points and interpretation limits. Consult current provider documentation for endpoint, authentication, terms, pricing, rate limits and retention before adding or changing a transport. Do not invent a provider allowance or store credentials in package files.

## Common normalized record

All transports feed `templates/source-record.schema.json` and the existing Markdown `sources.md` and `evidence-ledger.md`. Stable source IDs are assigned by the run coordinator after deduplication. The transport layer must not assign opportunity scores, evidence maturity labels, or gate outcomes.

1. Save the provider and retrieval method, canonical URL, title/publisher, publication/event/retrieval timestamps, market, industry, evidence type, claim and source limitations when available.
2. Store concise claim support and a source pointer; retain full page text only when the provider terms and research need permit it.
3. Deduplicate canonical URLs and underlying source events. Independent search engines repeating the same announcement are one evidence event.
4. Preserve contradicters and corroborators through source IDs. Do not drop a conflicting result when it weakens the hypothesis.
5. If retrieval is blocked or a host lacks the provider, log the gap and evidence impact. Do not treat blocked access as absence of demand.
6. Assign evidence class and reliability only after inspecting the underlying material. Search snippets and summary payloads are leads, not verified evidence.
