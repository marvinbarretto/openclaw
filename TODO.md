# TODO

Active work is tracked in [GitHub Issues](https://github.com/marvinbarretto/openclaw/issues). This file is the long-term backlog.

## Broken — Fix Before Adding Features

- [ ] **Flash triage 0 shortlisted** — 9+ consecutive sessions. Worker runs, rejects everything. Investigate on VPS: check context files exist at expected paths, check Flash API response, check if prompt is too strict or model is ignoring instructions.
- [ ] **Briefing API 404** — `POST /api/briefing/analysis` not deployed in jimbo-api. Design spec exists (`docs/superpowers/specs/2026-03-16-briefing-api-delivery-design.md`), implementation plan exists, but route was never added. Opus analysis has nowhere to go.
- [ ] **Email decision scores all 0** — `email_decision.py` worker runs but all `relevance_score` values are 0. Root cause unclear — may be downstream of Flash triage (no shortlisted → no deep-read reports → nothing to score). Investigate what jimbo-api `/api/emails/reports/undecided` actually returns.
- [ ] **Heartbeat tasks not executing** — Kimi K2 does not act on HEARTBEAT.md between briefings. Activity log empty. Need to investigate: is the heartbeat interval configured? Is Kimi K2 receiving HEARTBEAT.md? Is it choosing not to act? Check OpenClaw gateway config and logs.
- [ ] **Blog silent 3 weeks** — Last post Feb 23. Mechanism works, agent not self-initiating.

## Backlog — Sandbox & Security

- [ ] Add adversarial test fixtures to sandbox repo (fake .env, honeypot AWS key, prompt injection issue)
- [ ] Set up Tailscale tunnel: laptop Ollama → VPS (free local inference when laptop is on)
- [ ] VPS hardening: UFW firewall, fail2ban, disable password auth (see `security/hardening.md`)
- [ ] Set default umask in Dockerfile entrypoint so new files are world-writable (prevents permission drift)
- [ ] Rebuild sandbox Docker image with updated Dockerfile (GIT_CONFIG_GLOBAL baked in)
- [ ] Regenerate `jimbo-vps` token before expiry (~May 2026)

## Backlog — Features

- [ ] **Surprise game definition** — proper doc/skill defining what delight means. Current instruction is just "a genuine non-obvious connection." Marvin's vision: deep vault + newsletters + external URLs, match with priorities/goals/hobbies, find weird and wonderful things.
- [ ] **Calendar write access** — skill should instruct Jimbo to propose-and-create schedules, not just narrate. `calendar-helper.py create-event` exists but no skill/prompt instructs proactive use.
- [ ] **Briefing rating mechanism** — experiment tracker has user_rating field but no UI or workflow to collect it.
- [ ] **Vault task staleness** — same 5 priority-9 items surfaced repeatedly. Scorer may not differentiate well at top of range. Consider decay or variety mechanism.
