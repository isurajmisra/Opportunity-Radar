# Opportunity Radar evaluation suite

These are manual behavior tests for the skill, not actual market research. Run each prompt in a clean session for the host being evaluated and check the output against `expected-behavior.md`. Use the same date window, evidence pack, budget and user constraints when comparing hosts. Record unavailable host tools rather than silently substituting them.

A useful evaluation catches confident-looking failure modes before a live business search. Do not grade the skill simply on whether it finds candidates. Synthetic fixtures and packaging tests are in `cross-platform/` and `../tests/cross-platform/`; they make no live provider calls.
