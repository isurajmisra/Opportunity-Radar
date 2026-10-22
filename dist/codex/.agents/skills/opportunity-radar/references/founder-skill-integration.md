# Integrating an existing founder skills workflow safely

## Objective

Use installed founder skills to challenge the research-backed candidate, not to generate another generic idea list or manufacture a second opinion.

## Discover real installed commands

1. Inspect the session's available skills/plugin descriptions or use the skill-listing method supported by the active host.
2. Confirm exact names and namespaces in the actual installation. Some versions use names such as `/founder:validate-idea`, `/founder:competitor-matrix`, `/founder:pricing-strategy`, `/founder:cfo`, `/founder:customer-interviews` or locally customised equivalents. Do not assume a specific command exists.
3. Open the relevant skill's instructions to learn which files it reads/writes and whether it expects an existing `founder/` directory.
4. Do not install a new plugin automatically; ask for approval if an install is actually needed.

## Candidate packet

Create `candidate-packet.md` in the run directory with:
- name and short thesis;
- country, segment and buyer/payer;
- strongest evidence and citations;
- counter-evidence and current alternatives;
- current business model and economics assumptions;
- user constraints;
- unknowns and proposed test;
- status label: desk research only unless real behavior exists.

The packet must distinguish facts from hypotheses and include links so the founder skill can inspect source material.

## Safe invocation rules

- Prefer the most relevant skills: validate idea, competitor analysis, pricing/CFO/unit economics and interviews/offer validation.
- Do not run every founder skill on every raw hypothesis. Use them only on finalists that passed the research gate.
- If a skill can accept the packet as input and can save within the run folder, invoke it.
- If it writes into `founder/` at the current working directory, inspect existing paths first. Never overwrite the user's existing `founder/` files.
- If output paths cannot be controlled, use an isolated temporary workspace with a copy of the candidate packet or provide commands for the user to run manually there.
- Record exact skills executed, date, output paths and limitations in `founder-review.md`.
- If not actually executed, label the work “internal structured review; founder skill not run.”

## How to reconcile a founder verdict

Founder skill scores are another perspective, not ground truth. Reconcile differences by asking:
- Did it identify sources we missed or misread?
- Did it distinguish existing spend from stated interest?
- Did it account for free substitutes and how buyers actually find alternatives?
- Are its price, conversion, market-size or unit-economics inputs sourced?
- Does it assume an app/product is required before a manual test?
- Does it claim customer demand from simulated interviews?

Do not average scores mechanically. Explain why the evidence changes the conclusion. Preserve dissent in the report.

## Portable founder-review fallback

Use this checklist only for candidates that already passed the research hard gates. Label the report “Opportunity Radar portable founder review; native founder skill not run.” Do not imply that a simulated review is a real founder-plugin run or customer validation.

1. **Competitor review:** compare the closest paid and free substitutes, buyer switching costs, positioning, distribution, pricing, and why a buyer would change.
2. **Offer design:** define one target buyer, one urgent job, a narrow outcome, delivery scope, a test price, and a credible first-customer route. Avoid building before testing the offer.
3. **Customer and pricing validation:** list the evidence that would show real recent behavior, budget ownership, paid substitutes, procurement, or willingness to run a paid pilot. Treat stated interest as weak until connected to behavior.
4. **CFO and unit economics:** calculate contribution margin and break-even from explicit sourced, calculated, and assumed inputs. Include acquisition, support, payment, returns, compliance, inventory/working capital, and founder time where relevant. Show sensitivity to the assumptions that can reverse viability.
5. **Red team:** write the strongest reason buyers will keep their current approach, the best evidence against the thesis, likely bundling/copying, execution and regulatory risks, and the condition that would invalidate the opportunity.
6. **Real-world test:** define a low-cost manual offer or pilot with target sample, cost/time ceiling, pre-set pass/fail/inconclusive thresholds, and a stop rule. The user executes outreach; the agent does not contact prospects.

Record unresolved assumptions and the strongest contrary view. If the evidence cannot support a feasible offer and test, lower the status or reject the candidate; do not use the checklist to rescue it.
