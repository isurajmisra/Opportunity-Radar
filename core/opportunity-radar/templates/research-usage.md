# Research usage

Complete this file for every run, including when no external providers were called. Run `provider_usage.py summary` at close. Distinguish measured provider-reported use, published-price estimates, configured local operation caps and unknown values. Never convert request counts to provider spend without a verified pricing basis.

## Summary

- Scan profile, Tavily credit use and remaining balance: generated from the run's Tavily ledger when used; otherwise state that Tavily was not used.
- Non-Tavily call count, local limits, verified prices, USD estimates and plan quota snapshots: generated below.
- Actual cost/credits and estimated charges must remain separate. Record unavailable providers and resulting research gaps in the coverage section.

## Operations

| Operation ID | Provider | Operation | Query / URL reference | Status | Actual usage | Estimate and basis | Retrieved at |
|---|---|---|---|---|---|---|---|

For source-level extraction, report successful extraction, confirmed source access failure, command/configuration failure (retry eligible), provider/network failure with unknown source status, and not attempted separately. Include attempt IDs and a concise reason. Local preflight/argument failures are logged but are not provider operations; attempted provider failures count. Keep this table and the executive summary consistent with the underlying ledger. Tavily CLI credits are estimates unless provider-reported usage is available.

## Coverage gaps

| Provider/source | Access issue | Alternatives tried | Effect on conclusions |
|---|---|---|---|
