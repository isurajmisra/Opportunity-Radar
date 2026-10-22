# Installation and operation

For current cross-platform installation and update instructions, see [CROSS-PLATFORM.md](CROSS-PLATFORM.md). This file documents the original Claude Code personal installation path; use `install.ps1` or `install.sh` with a selected platform for new installations.

## Option A — install as a personal Claude Code skill (recommended)

This makes `/opportunity-radar` available across your projects and installs the specialist subagents as personal agents.

### Windows PowerShell

1. Extract the ZIP.
2. Open PowerShell in the extracted folder.
3. Read `install.ps1` before running it.
4. Run:

```powershell
.\install.ps1
```

To permit replacement of existing files:

```powershell
.\install.ps1 -Force
```

The script creates a timestamped backup of existing destination folders when `-Force` is used. Confirm the source folder is the expected extracted package.

### macOS / Linux

```bash
chmod +x install.sh
./install.sh
```

To overwrite existing copies after review:

```bash
./install.sh --force
```

After installation, start Claude Code in a dedicated research folder and run `/opportunity-radar India`. The skill writes to `opportunity-radar-runs/` under the current working directory, not into its installation folder.

## Option B — project-local

Copy these into your chosen research repository:

- `.claude/skills/opportunity-radar/`
- `.claude/agents/`

Project-local installs are easier to version-control and share, but are only discovered when Claude Code runs in that project context.

## Check availability

In a Claude Code session, inspect the available slash commands/skills or invoke `/opportunity-radar India`. If it is not found:

1. Check that the skill path is exactly `.claude/skills/opportunity-radar/SKILL.md` or `~/.claude/skills/opportunity-radar/SKILL.md`.
2. Check the YAML frontmatter at the start of `SKILL.md`.
3. Restart Claude Code if your version does not reload newly installed personal skills automatically.
4. Check whether project/global settings restrict skills or subagents.

## Web research tools

Opportunity Radar adapts to research tools available in the current Claude Code session. Use built-in WebSearch/WebFetch if available, or a trusted search/browser MCP configured by the user. Do not install an MCP server automatically.

If no credible current web research capability exists, stop and state that the live scan is blocked. Offer a setup checklist; do not fabricate a current report.

## Founder plugin (optional)

If your existing founder plugin is already installed, keep it. Do not reinstall it just for Opportunity Radar.

Otherwise, review the plugin's current README and licence first: https://github.com/emotixco/claude-skills-founder

The repository currently documents marketplace installation in Claude Code. Verify the current command and actual skill names in your installation before running them. Do not allow its output to overwrite or contaminate your existing founder files.

## Optional integrations

The first version uses no API keys. Official open datasets and browsable pages can be accessed via normal research tools. Add data-source MCP servers only if a repeated research bottleneck justifies them and after reviewing their permissions, terms, cost and maintenance status.
