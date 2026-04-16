# ADR-048: Sunset OpenClaw, Migrate to Hermes Agent

## Status

Accepted

## Context

Over 18 sessions (Feb–Apr 2026), OpenClaw has been Jimbo's runtime on a DigitalOcean VPS. Despite significant investment, the system never reached a state where it reliably helped Marvin day-to-day:

1. **Over-engineered security model.** ADR-001's reader/actor split (untrusted text → reader-only model) was appropriate for adversarial environments but disproportionate for processing personal email and RSS. Every feature became an architecture problem.

2. **Accumulated complexity.** 60+ Python workspace scripts, many replicating or working around platform features. Session 15 identified this: "working against the platform instead of using it." Custom orchestration engine (13 jimbo_runtime_* files), custom dispatch system (7 files), custom briefing pipeline — all solving problems the platform should handle.

3. **Daily briefing never worked reliably.** The flagship feature oscillated between "use OpenClaw for everything" and "bypass with Python scripts" four times (ADR-046). Each approach created new problems.

4. **Hermes Agent emerged as OpenClaw's MIT-licensed successor.** Built by Nous Research (same team), v0.9.0 released April 2026. Includes `hermes claw migrate` for direct migration. 47 built-in tools, native subagent spawning, self-improving skills, 18+ messaging platforms, better memory system (SQLite FTS5), prompt caching.

## Decision

- **Sunset OpenClaw.** Stop the gateway, archive the repo. No active development.
- **Install Hermes Agent** on the same VPS, running as a new `jimbo` user.
- **Keep jimbo-api** as the data layer (95 endpoints, mature, working).
- **Use hub repo** as version-controlled source of truth for Hermes config (skills, SOUL.md, config.yaml).
- **Simplify security** to container isolation + propose-and-approve pattern. No reader/actor model split. jimbo-api preprocesses untrusted input as a natural boundary.
- **Kill the daily briefing.** Replace with 30-minute status pulse via Hermes cron.
- **Start with zero workspace scripts.** Only add scripts when Hermes can't do something natively.

## Consequences

### Positive
- Fresh start informed by 18 sessions of lessons learned
- Hermes native features replace ~20 custom orchestration files
- MIT license — full control, self-hosted, no vendor lock-in
- Skills format identical (SKILL.md) — portable domain logic
- Simpler mental model: Hermes does orchestration, jimbo-api does data

### Negative
- Some workspace scripts contain real domain logic (email triage, vault connectors) that needs porting as Hermes skills
- Hermes is v0.9.0 — may have its own rough edges
- New system to learn and debug
- OpenClaw-specific knowledge (18 sessions) partially obsoleted

### Neutral
- VPS stays (always-on requirement for Telegram gateway)
- Blog pipeline unchanged (Astro + Cloudflare Pages)
- Admin dashboard unchanged (site repo, already deployed)

## Migration Completed (2026-04-16)

- VPS hostname renamed `vps-lon1`
- New `jimbo` user created, SSH keys configured
- jimbo-api migrated to `jimbo` user (systemd service updated)
- Hermes v0.9.0 installed (79 bundled skills, Playwright, all deps)
- Configured: OpenRouter, Telegram, GitHub token, Google AI key, jimbo-api access
- SOUL.md written for Hermes (adapted from OpenClaw version)
- Gateway running as system service, responding on Telegram
- OpenClaw gateway stopped and disabled

## References

- Migration brief: `docs/plans/2026-04-16-hermes-migration-brief.md`
- Hermes docs: https://hermes-agent.nousresearch.com/docs
- Hermes repo: https://github.com/NousResearch/hermes-agent
