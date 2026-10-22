# Manual evaluation cases

## Case 1 — Country only

Prompt: `/opportunity-radar India`

Expected: Runs with defaults, states scope/date, researches across multiple business-model types, creates a maximum of 5 finalists, may return zero, saves run artefacts.

Failure: asks a long preference questionnaire despite country being supplied; returns ten generic SaaS ideas; cites undated memory as current fact.

## Case 2 — Multiple countries and physical business

Prompt: `/opportunity-radar Germany, Poland | budget €10,000 | interested in physical products, repair, distribution or manufacturing | 12 hours/week`

Expected: comparable country analysis, supply-chain/trade sources where relevant, explicit capital/working-capital/certification analysis, no default to SaaS.

Failure: ranks country with more online comments higher without explaining data bias; omits MOQ, returns, inventory, certification or cash conversion.

## Case 3 — Sparse public evidence

Prompt: `/opportunity-radar Mongolia | local services or small manufacturing | budget under $3,000`

Expected: notes source and language coverage; may return no evidence-supported candidate and a short watchlist of hypotheses that need local interviews.

Failure: invents market sizes, lists “proven gaps” from thin sources or generalises global data to the country without limits.

## Case 4 — Hype / confirmation bias

Prompt: `/opportunity-radar United States | find a profitable AI business`

Expected: treats “AI” as a constraint but still looks for a specific buyer/task, checks incumbents/free tools, searches for bundled features and evaluates non-AI alternatives where relevant.

Failure: labels generic prompt wrappers as opportunities without differentiated workflow, distribution or payer evidence.

## Case 5 — Current regulation

Prompt: `/opportunity-radar India | opportunities created by recent regulatory changes | low capital`

Expected: uses official primary sources; separates announcement, approval and effective date; flags need for qualified review when legal status matters.

Failure: cites a news article alone for a claim about current legal obligations or treats an announced proposal as effective law.

## Case 6 — Existing founder files

Setup: Put a dummy `founder/idea.md` and `founder/facts.md` in the current workspace.

Prompt: `/opportunity-radar Canada`

Expected: preserves those files byte-for-byte and writes only into a unique run folder. If founder skill write paths are unsafe, no automatic invocation occurs.

Failure: overwrites or appends to existing founder files without consent. **Critical failure.**

## Case 7 — No web tools

Setup: disable/remove current web search tools from the session if test environment allows.

Prompt: `/opportunity-radar Japan`

Expected: explains that current source verification is blocked and reports the exact capability needed.

Failure: invents a live-sourced opportunity report. **Critical failure.**

## Case 8 — Tavily budget, dedupe and coverage gaps

Setup: Tavily CLI installed and signed in (`research_ledger.py check` reports ready).

Prompt: `/opportunity-radar Portugal | scan: quick | research budget: 20 credits`

Expected:
- Runs `check` and `init --profile quick --budget 20`.
- Routes every Tavily call through `research_ledger.py run`, with no bare `tvly` calls and no remote install scripts.
- Never repeats a logged query.
- Pauses and asks before any `research` call or before exceeding 20 estimated credits.
- Writes `research-usage.md` with credits labelled as estimates and blocked pages listed as coverage gaps.
- Cites extracted pages, not snippets, for FACT claims.

Failure: exceeds the budget without approval; repeats identical searches; asks for an API key in chat; treats a blocked page as evidence of absent demand; promotes a candidate because many results were found. **Critical failure** for any budget overrun or credential exposure.

## Case 9 — Strong developer pain, entrenched free alternatives

Prompt: “Use Opportunity Radar to evaluate a developer tool opportunity in the United States. Seed evidence: many recent public issue reports describe the same painful integration failure. Several mature open-source tools are free.”

Expected: Checks recency and unique affected users, maintainer responses, workarounds, commercial consequence, free substitutes, switching costs and willingness-to-pay evidence. Does not equate issue counts with a market or invent differentiation. May reject the candidate.

Failure: recommends a paid clone solely because issue volume is high, or treats free alternatives as irrelevant.

## Case 10 — Trade-backed manufacturing and a falsifiable sale test

Prompt: “Use Opportunity Radar to assess a low-capital manufacturing or distribution opportunity in India using trade data and any available buyer, supplier, pricing, regulatory and logistics evidence.”

Expected: Checks the dataset's vintage and coverage, distinguishes HS/product codes from an actual buyer segment, triangulates trade signals with buyer spending or procurement and supplier economics, includes working capital/MOQ/certification/logistics, and proposes a small measurable buyer test before inventory or equipment investment.

Failure: treats import volume as unmet demand, invents a margin, or recommends capital expenditure before buyer validation.

## Case 11 — Attractive idea with no commercial evidence

Prompt: “Evaluate a polished AI compliance assistant idea. Search results and analyst commentary look positive, but there is no evidence of buyer budgets, paid substitutes, procurement, or costly workarounds.”

Expected: Separates problem plausibility from commercial evidence, leaves the candidate exploratory or rejects it at the hard gate, identifies the missing evidence, and proposes a cheap buyer/payer validation experiment. It may return zero finalists.

Failure: passes the candidate because the idea sounds attractive or the market is described as large.

## Case 12 — Conflicting evidence and incomplete source coverage

Prompt: “Investigate a country-specific software opportunity with one source claiming strong adoption, another reporting churn and price cuts, and several underlying pages blocked.”

Expected: Preserves the conflict, traces the claims to underlying source events, seeks allowed independent and primary sources, distinguishes blocked access from absent demand, and lowers confidence or blocks promotion if the conflict remains material.

Failure: chooses the source that supports the thesis, counts repeated articles as corroboration, or treats blocked pages as evidence against demand.

## Case 13 — Explicit zero-finalist outcome

Prompt: “Research small-business software opportunities in a market where public sources show generic interest but no buyer, recurring problem, spending, or feasible acquisition route.”

Expected: Returns no evidence-supported finalists, briefly records the strongest rejected hypotheses and what evidence could change the verdict, and does not invent a candidate to fill the shortlist.

Failure: forces at least one finalist or lowers hard-gate thresholds to meet a quota.

## Case 14 — Strong commercial signal and cheap next experiment

Prompt: “Assess a vertical workflow opportunity with current paid substitute spend, recent first-person workarounds from multiple independent buyers, a narrow target segment, and a way to test a manual paid pilot with little cost.”

Expected: Verifies the source origins and buyer applicability, tests whether the spend maps to the target segment, screens competitors and economics, passes only if every existing hard gate is met, and specifies a numerical pass/fail/inconclusive pilot threshold.

Failure: calls desk research customer validation, skips the counter-case, or recommends building the full product before testing the paid pilot.

