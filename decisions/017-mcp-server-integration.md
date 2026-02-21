# ADR-017: MCP Server Integration

## Status

Rejected (2026-02-20)

## Context

Jimbo currently interacts with external services through a mix of approaches:
- **GitHub:** `gh` CLI installed on VPS, bind-mounted into Docker sandbox, authenticated via PAT in env vars
- **Email:** Offline Sift pipeline (laptop → Ollama → JSON → rsync to VPS)
- **Calendar:** No access
- **Other services:** No access

MCP (Model Context Protocol) is a standard for connecting AI agents to external tools and data sources. We investigated adding MCP servers to give Jimbo structured access to GitHub, Google Calendar, and other services.

## Investigation

### What we tried

Added a top-level `mcpServers` key to `openclaw.json` with a filesystem MCP server as a smoke test. OpenClaw rejected it immediately:

```
Config invalid
Problem: <root>: Unrecognized key: "mcpServers"
```

### What we found

- **OpenClaw v2026.2.12 does NOT have native MCP support.** The config schema rejects unknown top-level keys.
- GitHub issue #4834 (native MCP support) has an open PR (#21530) that has **not been merged**.
- GitHub issue #13248 confirms MCP capabilities return `false` in current builds.
- Community plugins exist (`openclaw-mcp-adapter`, `openclaw-mcp-plugin`) that bridge MCP into the plugin system, but these are third-party npm packages with executable code — violates ADR-008 (no community plugins, supply chain risk).

### Config formats that DON'T work (v2026.2.12)

```json
// REJECTED — top-level mcpServers
{ "mcpServers": { ... } }

// NOT YET AVAILABLE — per-agent MCP (PR #21530, unmerged)
{ "agents": { "list": [{ "mcp": { "servers": [...] } }] } }
```

## Decision

**Reject MCP integration for now.** The reasons:

1. **Native support doesn't exist yet** in our OpenClaw version
2. **Community plugins violate ADR-008** (supply chain risk policy)
3. **GitHub MCP adds little value** over the existing `gh` CLI in sandbox
4. **Calendar access** (the real goal) can be achieved via a simpler approach — a Sift-style pipeline that fetches calendar data locally and pushes a JSON digest to the VPS, or a Google Calendar API skill running in the sandbox

### When to revisit

- When OpenClaw merges PR #21530 and releases native MCP support
- At that point, Calendar MCP and other integrations become straightforward
- Monitor OpenClaw releases for `mcp` in changelogs

## Consequences

- No MCP servers on the VPS for now
- Calendar integration will use an alternative approach (see ADR-018)
- GitHub access stays as-is (`gh` CLI in sandbox)
- ADR-008 (no community plugins) remains intact
- Less complexity on the $12/mo VPS

## Lessons learned

- Always smoke-test config changes before building out tooling — we wrote a full setup script and docs before confirming the feature existed
- Research from AI-generated blog posts and community guides can be wrong or ahead of the actual release
- Back up `openclaw.json` before any changes (the script did this correctly, which saved us)
