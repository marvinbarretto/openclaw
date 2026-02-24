# TODO

Active work is tracked in [GitHub Issues](https://github.com/marvinbarretto/openclaw/issues). This file is the long-term backlog.

## Backlog — Sandbox & Security

- [ ] Add adversarial test fixtures to sandbox repo (fake .env, honeypot AWS key, prompt injection issue)
- [ ] Set up Tailscale tunnel: laptop Ollama → VPS (free local inference when laptop is on)
- [ ] VPS hardening: UFW firewall, fail2ban, disable password auth (see `security/hardening.md`)
- [ ] Run `openclaw security audit --deep` on VPS
- [ ] Review OpenClaw skills before enabling — vet source code (see ADR-001 skill vetting)

## Backlog — Sandbox & Permissions

- [ ] Set default umask in Dockerfile entrypoint so new files are world-writable (prevents permission drift)
- [ ] Move PAT from git remote URL to credential helper using `JIMBO_GH_TOKEN` env var
- [ ] Regenerate `jimbo-vps` token before expiry (~May 2026)
- [ ] Rebuild sandbox Docker image with updated Dockerfile (GIT_CONFIG_GLOBAL baked in)

## Backlog — Email Triage

### Pipeline fixes
- [x] Fix Date header fallback — use None instead of now() for broken headers (2026-02-18)
- [x] Decode MIME-encoded subjects (=?UTF-8?B?...=) before classification (2026-02-18)
- [x] Tune classification prompt — 18/20 queue → 3/20 queue, much stricter filtering (2026-02-18)

### Automation (see ADR-010, updated ADR-022)
- [x] Set up sift-cron.sh with launchd for 6am laptop-side pipeline (2026-02-18) — RETIRED 2026-02-24, replaced by VPS cron
- [x] Set up VPS root crontab: gmail-helper.py fetch at 06:00 UTC, no laptop dependency (2026-02-24)
- [x] Unload laptop launchd job (com.openclaw.sift-cron) (2026-02-24)
- [x] Configure OpenClaw cron job for 7am morning briefing (isolated session, Telegram) (2026-02-18)
- [x] Add email digest freshness check + token expiry check to HEARTBEAT.md (2026-02-18)
- [x] Configure heartbeat timing: every 30m, active 07:00–01:00 London (2026-02-18)
- [ ] Process 28k email backlog in batches (see ADR-009)

### Gmail sync (RETIRED — replaced by Gmail API on VPS)
- ~~mbsync pulling ~100k emails from Gmail archive~~ — no longer needed, Gmail API fetches directly
- `--hours 24` works daily via VPS cron at 06:00 UTC

### Briefing quality
- [ ] Fix Gemini thinking leak — reasoning tokens appear in Telegram (see ADR-015). Try Claude Haiku or wait for OpenClaw update.
- [ ] Try other models that don't leak thinking: Claude Haiku 4.5 (~$2.49/mo), Qwen3 235B free tier, or Gemini with reasoning off + better prompting
- [ ] Redesign briefing as conversational — short headlines first, then Marvin asks to drill into what interests him, instead of one huge report message
- [ ] Run classifier on full batch to measure new queue/skip ratio (target ~50%, down from ~97%)

### Future
- [ ] Design digest-feedback.json schema for learning loop
- [ ] Implement time-budget tracking (content-queue.json)

## Backlog — Calendar & Planning

- [ ] Create `GOALS.md` workflow — agent reads goals, proposes weekly plans
- [ ] Set up dedicated "Focus Blocks" calendar (write-only, no deletion)

## Done

- [x] Upgrade VPS model to Gemini 2.5 Flash via direct Google AI — working, ~$0.78/mo (ADR-015) (2026-02-20)
- [x] Tighten classifier prompt + bump default to qwen2.5-coder:14b (ADR-015) (2026-02-20)
- [x] Track workspace brain files in repo + workspace-push.sh deploy script (2026-02-20)
- [x] Add provider setup cheatsheet to setup/configuration.md (2026-02-20)
- [x] Fix compaction config — reserveTokensFloor 5000→20000, enable memoryFlush (ADR-013) (2026-02-19)

- [x] Set up mbsync, sync 28,799 emails from Gmail to local Maildir (2026-02-18)
- [x] Run Sift pipeline end-to-end on real email data (2026-02-18)
- [x] Fix sift-classify.py: add date filtering, mtime pre-filter, progress output, --all/--limit flags (2026-02-18)
- [x] Create custom skills: sift-digest + daily-briefing (2026-02-18)
- [x] Deploy skills to VPS via skills-push.sh (2026-02-18)
- [x] Test Jimbo reading real email digest via Telegram — WORKING (2026-02-18)
- [x] Write ADR-008: Plugin & skill adoption policy (2026-02-18)
- [x] Create CLAUDE.md for repo context (2026-02-18)
- [x] Install Ollama on laptop (2026-02-16)
- [x] Pull qwen2.5:7b (Reader) and qwen2.5-coder:14b (Actor) — tested (2026-02-16)
- [x] Create test monorepo and push to GitHub (2026-02-16)
- [x] Provision DigitalOcean droplet — 1-Click OpenClaw (2026-02-16)
- [x] Configure Anthropic API key on VPS (2026-02-16)
- [x] Set up Telegram bot ("Jimbo" / @fourfold_openclaw_bot) (2026-02-16)
- [x] Pair Telegram with OpenClaw (2026-02-16)
- [x] Set up OpenRouter API key on VPS (2026-02-16)
- [x] Switch to free model: stepfun/step-3.5-flash:free (2026-02-16)
- [x] Write ADRs 001–005 (2026-02-16)
- [x] Document installation steps, config, and troubleshooting (2026-02-16)
- [x] Create fine-grained GitHub token — read-only for LocalShout, Spoons, Pomodoro (2026-02-16, 60-day expiry)
- [x] Write model-swap helper script: `openclaw/scripts/model-swap.sh` (2026-02-16)
- [x] Install `gh` CLI on VPS and enable GitHub skill (2026-02-16)
- [x] Verify read-only repo access from VPS (2026-02-16)
- [x] Switch to Claude Sonnet for bootstrapping phase (2026-02-16)
- [x] Fix sandbox GitHub access — GH_TOKEN in docker env + CA certs mount (2026-02-17)
- [x] Write ADR-006: GitHub skill lifecycle (enable for bootstrap, disable for free model) (2026-02-17)
- [x] Document sandbox architecture, layered config gotchas, and troubleshooting (2026-02-17)
- [x] Install Python 3.11 + Node 18 in sandbox via custom Docker image (2026-02-17)
- [x] Fix systemd PATH order — homebrew Node was overriding system Node, crashing Telegram (2026-02-17)
- [x] Clone jimbo-workspace into sandbox and verify push access (2026-02-17)
- [x] Jimbo's first autonomous commit and push to own repo (2026-02-17)
- [x] Remove GH_TOKEN from sandbox (personal repo access revoked per ADR-006) (2026-02-17)
- [x] Switch back to free model after bootstrapping complete (2026-02-17)
- [x] Create Jimbo's GitHub account: `marvinbarretto-labs` (2026-02-17)
- [x] Create `jimbo-workspace` repo under Jimbo's account (2026-02-17)
- [x] Generate fine-grained token (`jimbo-vps`) — read+write on jimbo-workspace, 90-day expiry (2026-02-17)
- [x] Add `JIMBO_GH_TOKEN` to sandbox docker env config (2026-02-17)
- [x] Set up SSH config alias: `ssh jimbo` → VPS (2026-02-17)
- [x] Write ADR-007: Jimbo's autonomous workspace (2026-02-17)
- [x] Bootstrap Jimbo's identity on Claude Sonnet — SOUL.md, IDENTITY.md, USER.md written (2026-02-17)
- [x] Jimbo read Spoons, LocalShout, Pomodoro repos via GitHub skill (2026-02-17)
- [x] Build custom Docker sandbox image with Python 3.11, Node 18, git (2026-02-17)
- [x] Jimbo wrote initial BDD specs for Sift email digest project (2026-02-17)
- [x] Share email inbox samples with Jimbo for category analysis (2026-02-17)
- [x] Document architecture mental model (setup/architecture.md) (2026-02-17)
- [x] Fix sandbox git permissions — chmod + GIT_CONFIG_GLOBAL env var (2026-02-18)
- [x] Jimbo's blog live on GitHub Pages — static HTML, self-deployed (2026-02-18)
- [x] Write ADR-011: Sandbox git & blog deployment fix (2026-02-18)
- [x] Create CAPABILITIES.md — Jimbo capability matrix with token expiry tracking (2026-02-18)
