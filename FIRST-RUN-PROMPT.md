# First-run compatibility and safety check

For cross-platform architecture and current host limits, see `CROSS-PLATFORM.md` and `PLATFORM-CAPABILITIES.md`.

Paste this into Claude Code from the extracted package root **before running a country scan**.

> Read `README.md`, `CLAUDE.md`, `INSTALL.md`, the entire Opportunity Radar skill, its references, templates, scripts, all subagents, and the evaluation cases.
>
> Do a read-only setup review first. Check:
> 1. The skill is discoverable from its expected path and the YAML frontmatter has the required fields.
> 2. Each subagent uses valid Claude Code frontmatter and has a clear research scope.
> 3. All linked relative files exist.
> 4. The skill references the actual tool capabilities available in this session; do not assume a tool or MCP server exists when it does not.
> 5. Run the package validator if Python is available. Do not install packages.
> 6. Confirm that a run can produce a report without writing into an existing `founder/` directory.
> 7. Check for contradictory instructions, missing gates, stale paths, or promises that the research cannot support.
>
> Do not browse for business ideas yet. Do not install third-party skills, plugins, packages or MCP servers. Do not overwrite existing files. You may fix a concrete bug only after describing it and confirming the intended change is limited to this starter package. Report the compatibility result and any blocker.

After review, start with:

```text
/opportunity-radar India
```

Allow it to create the research plan and source plan first. Check source access and scope before continuing with the full scan.
