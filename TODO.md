# TODO

Active work is tracked in [GitHub Issues](https://github.com/marvinbarretto/openclaw/issues). This file is the long-term backlog.

## Broken — Fix Before Adding Features

- [ ] **vault_reader.py 401** — Every call fails with Unauthorized. 4+ consecutive days (since Mar 19). Most-called tool, 0% success. Investigate auth config in openclaw.json.
- [ ] **vault_roulette no_candidates** — Returns "no_candidates" on every call. Either the 30-day dormancy threshold is wrong or the vault data lacks age diversity.
- [ ] **Opus `claude -p` error** — Mac-side analysis broken since Mar 16. File on VPS stale (147h). `opus-briefing.sh` needs investigation.
- [ ] **Email insight fields null** — `email_decision.py` produces scores (7-10) but category, suggested_action, reason, insight fields are all null. Scoring runs, content doesn't.
- [ ] **False success on rate limit** — Model hit rate limit (Mar 22), no briefing composed, but activity log recorded "briefing delivered: success." No alert. Need verification before logging success.
- [ ] **Duplicate messages** — Airbnb, HowTheLightGetsIn, petition all double-sent at same timestamp (Mar 21). Tool double-fire bug.
- [ ] **Blog silent 4 weeks** — Last post Feb 23. Mechanism works, git push broken ("no repository initialized at host workspace"), agent not self-initiating.

## Resolved (since last update)

- [x] **Flash triage 0 shortlisted** — Fixed Mar 19 (session 9). Drought broken: 13-18 shortlisted per session.
- [x] **Briefing API 404** — Routes deployed in session 9 (POST /analysis, GET /latest, GET /history).
- [x] **Heartbeat tasks not executing** — Fixed Mar 18 (session 9). 36+ activities per day. Autonomous mind Phase 1 deployed.

## Backlog — Infrastructure

- [ ] **Health endpoint in site UI** — `/api/health` is live. Replace the static GitHub JSON exports in status.astro and costs.astro with live API calls.
- [ ] **Vault task system** — Design in progress. Vault as shared task system between Marvin and Jimbo (session 10-11 vision).
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
- [ ] **Inline links in briefing** — Gem data has URLs but briefing says "link in the email" instead of including them. Skill fix needed.
- [ ] **Message format (wall of text)** — Briefing sent as one long message. Should split by section for Telegram UX. Skill says "send each as a separate message."
- [ ] **No nudge rate-limiting** — 10 Airbnb reminders in one day (session 10). No awareness of whether item was actioned.
