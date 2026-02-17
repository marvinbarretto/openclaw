# ADR-001: Sandbox Architecture for Autonomous Coding

## Status

Accepted

## Context

We want OpenClaw to autonomously work on code — read issues, write code, open PRs — but with controlled blast radius. The agent must be able to experiment freely without risking real repos, credentials, or infrastructure.

Key tension: useful enough to be exciting, locked down enough to sleep at night.

## Decision

### Three-zone model

```
┌─────────────────────────────────────────────────┐
│ ZONE 1: SANDBOX (full autonomy)                 │
│                                                 │
│  - Dedicated test monorepo (GitHub)             │
│  - Dedicated GitHub bot account (not yours)     │
│  - Agent has full read/write/PR/issue access    │
│  - Can run CI, push branches, merge             │
│  - This is where you experiment freely          │
│                                                 │
├─────────────────────────────────────────────────┤
│ ZONE 2: READ-ONLY (supervised)                  │
│                                                 │
│  - Your real repos                              │
│  - Read-only GitHub token (repo:read scope)     │
│  - Agent outputs .patch files or draft PRs      │
│    via restricted GitHub App (no workflow        │
│    permissions, no secret access)               │
│  - YOU apply patches manually or approve PRs    │
│  - Graduate repos to Zone 1 after trust builds  │
│                                                 │
├─────────────────────────────────────────────────┤
│ ZONE 3: BLOCKED (no access whatsoever)          │
│                                                 │
│  - Your primary GitHub account token            │
│  - Production infrastructure                    │
│  - Cloud provider credentials (Vercel, CF)      │
│  - Domain registrar                             │
│  - Financial/billing accounts                   │
│  - DNS management                               │
│  - SSH keys to any real VPS/server              │
│  - Shared Docker socket                         │
│  - Shared artifact/package cache                │
│  - No tokens, no API keys, nothing              │
│                                                 │
└─────────────────────────────────────────────────┘
```

### Zone 2: Patch-based flow (not proposals/ directory)

Instead of writing into a repo working tree, the agent outputs changes as `.patch` files:

```
Agent analyzes real repo (read-only clone)
  → generates .patch file
  → writes to /data/patches/<repo>/<timestamp>.patch
  → OR opens a draft PR via restricted GitHub App

You review:
  git apply --stat patches/my-repo/2026-02-16-fix-auth.patch  # preview
  git apply patches/my-repo/2026-02-16-fix-auth.patch         # apply
```

**Why patches over proposals/ directory:**
- No process needed around cloning and staging into your real repo
- Patch files are inert — they're just text, harder to escalate
- Draft PRs via a restricted GitHub App have no workflow permissions and no secret access
- Clean separation: agent never writes into any real repo's working tree

### CI hardening (even in sandbox)

Even in the test monorepo, CI must be hardened:

- [ ] **No secrets in bot PRs** — GitHub Actions workflows triggered by bot PRs must not have access to repo secrets
- [ ] **Use `pull_request` not `pull_request_target`** — `pull_request_target` runs in the context of the base branch and has secret access
- [ ] **No `workflow_dispatch` from bot account** — bot cannot trigger arbitrary workflows
- [ ] **CI runs tests only** — no deploy steps, no publishing, no artifact uploads with credentials
- [ ] **Pin action versions** — use SHA pinning (`uses: actions/checkout@abc123`), not tags

Example safe workflow:
```yaml
on:
  pull_request:  # NOT pull_request_target
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    # No secrets available, no env vars with credentials
    steps:
      - uses: actions/checkout@v4  # pin to SHA in practice
      - run: npm ci
      - run: npm test
```

### VPS isolation

- **Dedicated VPS** (DigitalOcean 1-Click) — not your dev machine
- **Containerized agents** — OpenClaw runs agents in isolated Docker containers (built into DO 1-Click)
- **Network allowlist** — agent containers can reach: GitHub API, Telegram API, LLM API. Nothing else.
- **No SSH keys to real infrastructure** on the VPS at all
- **No shared Docker socket** — agent containers cannot access the host Docker daemon
- **Disposable** — nuke and rebuild from scratch anytime

### Test monorepo design

```
test-monorepo/
├── apps/
│   ├── web-app/          # Toy Next.js app for frontend experiments
│   └── api/              # Toy Express/Fastify API for backend experiments
├── packages/
│   └── shared/           # Shared utilities
├── .github/
│   └── workflows/        # CI — tests only, no secrets, no deploy
├── docs/
│   └── EXPERIMENTS.md    # Log of what the agent tried
└── GOALS.md              # What you want the agent to work on
```

- Use GitHub Issues as the task queue
- Agent opens PRs, you review on your phone whenever
- CI runs tests only — no secret access, no deploys

### Credential management

| Credential | Where it lives | Scope |
|---|---|---|
| GitHub bot token (sandbox) | VPS `.env` | Full access to test-monorepo only |
| GitHub App (Zone 2 PRs) | VPS `.env` | Draft PR + read on specific repos, no workflow/secret perms |
| Telegram bot token | VPS `.env` | Your bot only |
| LLM API key | VPS `.env` | Usage-capped at £25/mo |
| Gmail | NOT on VPS | See ADR-002 |
| Primary GitHub token | NOWHERE on VPS | Zone 3 — blocked |
| Cloud provider creds | NOWHERE on VPS | Zone 3 — blocked |
| Domain registrar | NOWHERE on VPS | Zone 3 — blocked |

## Consequences

**Easier:**
- Experiment freely in the sandbox without fear
- Clear mental model of what the agent can/can't touch
- Patch-based flow for real repos is clean and auditable
- CI can't leak secrets even if bot PRs contain malicious code
- Easy to graduate repos from Zone 3 → 2 → 1 as trust builds

**Harder:**
- Need a dedicated GitHub account + GitHub App (one-time setup)
- Real repos are read-only with patches — means you apply changes manually
- Network restrictions mean you can't easily add new integrations without updating the allowlist
- CI hardening requires discipline (easy to accidentally add secrets later)
