# Opportunity Radar platform capability matrix

The matrix separates package support from runtime access. “Supported with an adapter” means the distribution and documented route exist; the relevant host must still expose the listed filesystem, shell, MCP or CLI capability. No provider service is made mandatory.

| Capability | Claude Code | OpenAI Codex | GitHub Copilot |
|---|---|---|---|
| Skill discovery and invocation | Supported with an adapter | Supported with an adapter | Supported with an adapter |
| References and bundled scripts | Supported with an adapter | Supported with an adapter | Supported with an adapter |
| Shell and CLI execution | Supported with an adapter | Supported with an adapter | Manual fallback |
| Tavily search and extraction | Supported with an adapter when the installed CLI/skills are authenticated | Supported with an adapter when `tvly` is installed and signed in | Manual fallback unless the selected surface exposes an authenticated CLI or MCP |
| Exa search and retrieval | Manual fallback until Exa tools are visible in the active Claude session | Manual fallback until Exa is separately configured in the Codex environment | Manual fallback until Exa is separately configured in the selected Copilot surface |
| Brave Search API | Supported with an adapter; requires a configured environment key | Supported with an adapter; requires a configured environment key | Supported with an adapter only where Python/network access and the key are available |
| GitHub technical research | Supported with an adapter through surfaced MCP tools or `gh` | Supported with an adapter through surfaced MCP tools or `gh` | Supported with an adapter through surfaced MCP tools or `gh` |
| Parallel specialist agents | Supported with an adapter through the six Claude subagent definitions when delegation is enabled | Manual fallback; use bounded work packets unless the current runtime exposes delegation | Manual fallback; use bounded work packets unless the selected surface exposes delegation |
| Founder-validation integration | Supported with an adapter; native founder skills are conditional | Manual fallback using the portable founder review playbook | Manual fallback using the portable founder review playbook |
| Budget tracking | Supported with an adapter; Python and writable run folder required | Supported with an adapter; Python and writable run folder required | Supported with an adapter when Python and writable workspace are available; otherwise manual usage log |
| Report creation and persistence | Supported with an adapter in a writable workspace | Supported with an adapter in a writable workspace | Manual fallback in review/cloud surfaces without a writable project workspace |

## Runtime verification notes

- The portable skill format and host paths were checked against current official Claude Code, OpenAI Developers, and GitHub Copilot documentation (links below). This workspace does not contain running Claude Code, Codex CLI, or Copilot clients, so those host sessions were not end-to-end tested; no capability is marked fully supported on a documented format alone.
- Codex package format is documented and generated, but package discovery in a separately installed Codex product has not been exercised from this workspace. Project install path is `.agents/skills/opportunity-radar`; personal installation uses `$CODEX_HOME/skills/opportunity-radar` (default `~/.codex/skills/opportunity-radar`).
- This task's active tool registry exposes GitHub MCP tools and `gh` is authenticated. It does not expose Exa or Tavily MCP tools. The installed `tvly` CLI is available on this Windows machine; provider authentication should be checked by the packaged preflight in the user's host before a scan.
- A previous audit found no Brave key in the current environment. The adapter is optional and reports missing credentials without revealing any value.
- Copilot officially documents Agent Skills for cloud agent, code review, CLI, app, and VS Code agent mode, but tool and file-write capabilities vary by surface. The package does not promise those capabilities uniformly.
- A matrix state describes package support and its documented prerequisites. It does not claim that an integration was tested in every product, account, or session.

## Official format references

- [Claude Code skills](https://code.claude.com/docs/en/skills) and [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)
- [OpenAI Developers: Skills](https://developers.openai.com/api/docs/guides/tools-skills) and [Codex repo skills example](https://developers.openai.com/blog/skills-agents-sdk)
- [GitHub Copilot: adding agent skills](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills)
