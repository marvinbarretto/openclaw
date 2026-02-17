# TODO

Single source of truth for all open tasks. Check items off as they're done.

## In Progress

- [ ] Jimbo building "Sift" email digest prototype (BDD specs written, implementing in jimbo-workspace)

## Up Next

- [ ] Review what Jimbo has written to USER.md / IDENTITY.md / MEMORY.md — edit if needed
- [ ] Build offline email classifier on laptop (IMAP → Ollama → email-digest.json)
- [ ] Add OpenRouter credits when ready to upgrade from free tier

## Backlog — Sandbox & Security

- [ ] Add adversarial test fixtures to sandbox repo (fake .env, honeypot AWS key, prompt injection issue)
- [ ] Connect OpenClaw to test monorepo (GitHub integration for Zone 1)
- [ ] Set up Tailscale tunnel: laptop Ollama → VPS (free local inference when laptop is on)
- [ ] VPS hardening: UFW firewall, fail2ban, disable password auth (see `security/hardening.md`)
- [ ] Run `openclaw security audit --deep` on VPS
- [ ] Review OpenClaw skills before enabling — vet source code (see ADR-001 skill vetting)

## Backlog — Email Triage

- [ ] Install `mbsync` (isync) on laptop
- [ ] Configure Gmail IMAP sync → Maildir
- [ ] Sync last 90 days as first batch
- [ ] Build email classification pipeline with local Ollama (offline, no network)
- [ ] Design digest-feedback.json schema for learning loop
- [ ] Implement time-budget tracking (content-queue.json)

## Backlog — Calendar & Planning

- [ ] Create `GOALS.md` workflow — agent reads goals, proposes weekly plans
- [ ] Set up dedicated "Focus Blocks" calendar (write-only, no deletion)

## Done

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
