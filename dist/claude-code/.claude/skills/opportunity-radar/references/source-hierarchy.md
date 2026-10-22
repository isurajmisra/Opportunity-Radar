# Source hierarchy, recency and independence

## 1. Source classes

### Tier A — primary / official evidence

Prefer these for numerical, legal, policy and product-specific claims:
- national statistics offices, central banks, finance ministries and regulators;
- government budgets, legal gazettes, public procurement/tender portals and court/administrative decisions where relevant;
- World Bank, IMF, OECD, UN agencies, ILO, WTO, UN Comtrade and national statistical APIs;
- company filings, audited reports, official product/pricing documentation, terms, status pages and documentation;
- original research whose methodology, population, sample size, field dates and sponsor are disclosed;
- procurement award records, actual posted tenders, regulatory registers and public price lists.

### Tier B — strong secondary evidence

- reputable news outlets with named reporters and clear dates;
- trade/industry associations with disclosed methodology;
- analyst reports with transparent definitions and sourcing;
- credible business publications reporting real customer or market activity;
- university/independent research institutes.

### Tier C — direct but non-representative behavioral evidence

- first-person forum posts and public discussion threads;
- product reviews and app-store reviews;
- GitHub issues, public feature requests and bug reports;
- public job postings, support forums, seller listings and professional communities;
- company case studies, with their marketing bias clearly noted.

These may establish that a particular user reports a problem or workaround, but they do not establish market prevalence by themselves.

### Tier D — discovery only / weak evidence

- search snippets without opened source;
- AI-generated summaries without primary links;
- anonymous social posts with unclear context;
- SEO listicles with no method or sources;
- unsourced market-size infographics;
- vendor claims that do not disclose their evidence.

Use these to discover sources, not as sole support for major conclusions.

## 2. Independence

A source is not independent merely because it is on a different domain. If five news pages repeat one company's press release, one underlying signal was found. Record the shared origin in the evidence ledger.

For surveys, preserve sponsor, population, field dates, sample size, geography, question wording and relevant limitations. Do not generalise a US survey to another country without explaining the gap.

For reviews, report the platform, approximate review count/time window when visible and selection bias. Do not treat a few negative reviews as representative market-wide evidence.

## 3. Recency rules (defaults, not substitutes for judgment)

| Claim type | Default recency | Notes |
|---|---|---|
| Current competitor pricing/features | Verify on official page during run; ideally updated/checked within 90 days | Prices, availability, policy and feature access change quickly. |
| Laws, taxes, eligibility, subsidies | Use current official text and latest effective date | Distinguish announcement date, passage date and effective date. |
| Breaking market/event change | Prefer last 0–90 days | Include event date and latest update date. |
| Public buyer complaints/reviews | Prefer last 12–24 months | Older reports may still expose structural problems; say so. |
| Consumer/industry behavior trends | Prefer recent data with trend baseline over 12–36 months | Compare same definitions, populations and seasonal windows. |
| Demographics and national accounts | Latest available official data; often 1–3 years old | Explicitly state observation year, release date and lag. |
| Trade and manufacturing trends | Use latest available periods and a multi-year baseline | Confirm product codes, units, reporting country and revisions. |
| Long-lived technology/industry constraint | Current primary sources; older sources may be acceptable | Explain why the source remains relevant. |

Never describe publication recency as event recency. Example: a report published yesterday might analyse behavior from three years ago.

## 4. Citation requirements

Every substantial factual claim in the report must have an inline URL/citation near the sentence. The Sources file records:
- source ID (`S001`, `S002`, ...);
- title and publisher;
- URL;
- publication/update date (or “not stated”);
- relevant event/observation date;
- access date;
- country/geography covered;
- source tier/type;
- claims supported;
- known limitations and independence cluster.

Do not cite a homepage if a relevant article, dataset, terms page or pricing page exists. Do not assert a number from a search snippet if the page itself was never inspected.

## 5. Search breadth

For each major candidate, search different formulations and local-language equivalents where material. Search at least:
- problem phrasing and synonyms;
- existing product/service category;
- negative reviews / alternatives / cancellation / “too expensive”;
- price / quote / tender / contract / purchase;
- country-specific regulation and official data;
- competitor name plus reviews / pricing / limits.

Search queries should be recorded at least at a summary level in `run-log.md` for important findings and failed searches.
