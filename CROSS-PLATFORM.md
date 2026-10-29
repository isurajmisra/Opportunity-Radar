# Cross-platform Opportunity Radar

## Source of truth

`core/opportunity-radar/` is the canonical, host-independent skill package. It owns the scoring rubric, evidence gates, provider policies, schema, templates, report scripts and portable founder-validation fallback. Claude Code agent definitions live in `adapters/claude-code/agents/` because those files use Claude's native subagent format. The distributions are generated; edit canonical files and rebuild instead of hand-editing `dist/`.

The six specialist agents and the existing research methodology were retained. The two dated historical runs under `opportunity-radar-runs/` are not included in package generation and are not modified by the build.

## Build, check and validate

Requires Python 3.10 or later; the runtime package and scripts use the Python standard library.

```text
python scripts/build-distributions.py
python scripts/build-distributions.py --check
python scripts/validate-skill.py
python scripts/validate-reports.py
python -m unittest discover -s core/opportunity-radar/tests -v
```

`dist/claude-code/`, `dist/codex/`, and `dist/github-copilot/` are self-contained packages. `--check` computes the expected package trees from canonical inputs and compares them with the generated copies without writing files. It does not access network providers.

GitHub Actions runs the tests, package checks, report validation, installer dry runs, and installer syntax checks on Ubuntu, Windows, and macOS with Python 3.10 and 3.14. A separate Gitleaks job scans full Git history. CI does not call providers, require personal credentials, or rebuild generated packages. To reproduce the remaining checks locally:

```text
python -m unittest discover -s tests/cross-platform -v
python core/opportunity-radar/scripts/validate_package.py
python dist/claude-code/.claude/skills/opportunity-radar/scripts/validate_package.py
python dist/codex/.agents/skills/opportunity-radar/scripts/validate_package.py
python dist/github-copilot/.github/skills/opportunity-radar/scripts/validate_package.py
python scripts/install.py --platform claude-code --project --target-root .test-tmp/install-claude --dry-run
python scripts/install.py --platform codex --project --target-root .test-tmp/install-codex --dry-run
python scripts/install.py --platform github-copilot --project --target-root .test-tmp/install-copilot --dry-run
```

Run `bash -n install.sh` on macOS/Linux. On Windows, parse `install.ps1` using PowerShell's `Parser.ParseFile`. To run the local history scan, install Gitleaks and run `gitleaks git --config .gitleaks.toml --redact --verbose` with the full repository history available.

The checked-out project also carries project-local `.claude`, `.agents`, and `.github` adapters for discovery when this folder is opened directly in each host. After editing canonical files, rebuild packages, then update each project adapter with `python scripts/install.py --platform <host> --project --target-root . --force`. The updater creates a timestamped backup under `.opportunity-radar-backups/`; `validate-skill.py` detects stale project copies.

## Install and update

Installers are never run automatically. Default behavior is a dry-safe conflict check: an existing destination stops the install without changing files. To inspect:

```powershell
.\install.ps1 -Platform codex -DryRun
.\install.ps1 -Platform github-copilot -DryRun
.\install.ps1 -Platform claude-code -DryRun
```

macOS/Linux:

```bash
./install.sh --platform codex --dry-run
./install.sh --platform github-copilot --dry-run
./install.sh --platform claude-code --dry-run
```

Remove `-DryRun` or `--dry-run` to install after reviewing the destinations. For an intentional update, add `-Force` or `--force`; the installer backs up each existing destination under `.opportunity-radar-backups/<timestamp>/` in the selected target root before replacement, so backup skills do not appear as active discovered skills. Use `--project` to install into an explicit project root instead of a personal host directory. Use `--target-root PATH` to choose the base directory. The installer validates the copied skill after a successful install.

Show an installed package version:

```text
python scripts/install.py --platform codex --show-version
```

Updating means rebuilding from this canonical source and rerunning the installer with the explicit force option. Backups are timestamped.

## Invocation

| Host | Personal skill location | Project location | Invocation |
|---|---|---|---|
| Claude Code | `~/.claude/skills/opportunity-radar` | `.claude/skills/opportunity-radar` | `/opportunity-radar India` |
| Codex | `$CODEX_HOME/skills/opportunity-radar` (default `~/.codex/skills`) | `.agents/skills/opportunity-radar` | “Use the opportunity-radar skill to research India for viable business opportunities.” |
| GitHub Copilot | `~/.copilot/skills/opportunity-radar` | `.github/skills/opportunity-radar` | “Use the opportunity-radar skill to research India for viable business opportunities.” |

Example constraints: `India, UAE | IT and software | budget under ₹1 lakh | solo founder | 10 hours/week | first revenue within 60 days`. The user provides the market scope; providers, agents, and host adapters must not change the scoring methodology.

## Providers and credentials

- **Tavily:** use existing Tavily CLI/skills when they are actually available. Every paid/credit-consuming operation goes through the run ledger and configured budget. Do not install Tavily or run remote installers. Other hosts need their own CLI/tool configuration; Claude Code MCP/skills are not inherited by Codex or Copilot.
- **Exa:** use only if the current host exposes Exa search/fetch tools. Configure it separately for every host that needs it. Record absence as a coverage gap and use another permitted provider.
- **Brave:** optional wrapper uses `BRAVE_API_KEY` or `BRAVE_SEARCH_API_KEY` and the documented `X-Subscription-Token` header. It never prints the key and does not persist Search Results. Configure the environment in the host that runs Python; do not put a key in this repository.
- **GitHub:** use host-provided GitHub MCP or authenticated `gh` CLI if available. The current `gh` login does not automatically propagate to other machines or cloud hosts. Public unauthenticated reads are acceptable when sufficient.
- **Hacker News, PyPI, World Bank, Eurostat, UN Comtrade, OpenAlex, Adzuna:** optional and question-specific. Missing keys or country coverage do not block the remaining workflow.

Credentials remain in each host's existing secret store or environment. Never place them in generated packages, reports, commands, or chat.

## Evaluation

Manual cases are in `evals/cases.md`; ten or more scenarios exercise coverage gaps, competing evidence, hard-gate failures, real commercial evidence, and low-cost validation. `evals/cross-platform/` contains synthetic fixtures for offline structural and schema checks. Automated tests use mocked provider responses. Live API tests are separate and are not run by the default test suite.

For a host comparison, run the same scenario, date window, budget, country, and fixed source pack in each host. Save each output in a separate new run folder. Compare source diversity/correctness, claim support, unsupported-claim rate, gate decisions, resource use, and experiment quality. Record unavailable host tools and model differences. Do not infer equal results from shared skill text alone.

## Support status

See [PLATFORM-CAPABILITIES.md](PLATFORM-CAPABILITIES.md) for the capability matrix and exact verification limits. In particular, provider access and persistence depend on the selected runtime surface; where an integration is absent, the skill requires an explicit coverage limitation or a manual fallback.
