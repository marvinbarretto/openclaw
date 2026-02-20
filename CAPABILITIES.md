# Jimbo Capability Matrix

Quick reference for what Jimbo can and can't do. Updated as capabilities change.

## Communication

| Capability | Status | Notes |
|---|---|---|
| Telegram chat | WORKING | Via `@fourfold_openclaw_bot` |
| Morning briefing | READY | Needs OpenClaw cron config (ADR-010) |
| Email digest summary | WORKING | Via `sift-digest` skill |

## Code & Files

| Capability | Status | Notes |
|---|---|---|
| Read/write workspace files | WORKING | `/workspace` in sandbox |
| Git commit & push (jimbo-workspace) | WORKING | Fixed 2026-02-18 (ADR-011) |
| GitHub Pages blog | WORKING | Static HTML at `gh-pages` branch |
| Read Marvin's repos (GitHub) | DISABLED | Token exists but skill disabled for free model (ADR-006) |
| npm / Node build tools | WORKING | Fixed 2026-02-20 (ADR-016). Astro, webpack, npm install all work. Node 18. |
| Python scripts | WORKING | Python 3.11 in sandbox, stdlib only |

## Email

| Capability | Status | Notes |
|---|---|---|
| Read email digest | WORKING | JSON pushed from laptop daily |
| Classify emails | N/A | Runs on laptop via Ollama (qwen2.5-coder:14b), not in sandbox |
| Send/delete/modify email | BLOCKED | By design (ADR-002) |
| Email backlog processing | NOT STARTED | ADR-009 planned |

## Autonomy

| Capability | Status | Notes |
|---|---|---|
| Self-publish blog posts | WORKING | Commit + push to gh-pages |
| Update own diary | WORKING | JIMBO_DIARY.md in workspace |
| Automated daily pipeline | NOT STARTED | Laptop launchd + VPS cron (ADR-010) |
| Heartbeat / self-monitoring | NOT STARTED | HEARTBEAT.md planned |
| Install packages (npm/pip) | WORKING | Fixed 2026-02-20 (ADR-016). npm install works; pip needs venv in /workspace |

## VPS Model

| Model | Status | Notes |
|---|---|---|
| `stepfun/step-3.5-flash:free` | RETIRED | Can't follow curation instructions (ADR-005) |
| `google/gemini-2.5-flash` | WORKING | Daily driver (~$0.78/month). Direct Google AI API. See ADR-015 for setup. |
| `anthropic/claude-haiku-4.5` | AVAILABLE | Fallback if Gemini quality disappoints (~$2.49/month) |

## Security Boundaries

| Boundary | Status | Notes |
|---|---|---|
| Zone 1: own workspace | ENFORCED | Full read/write |
| Zone 2: Marvin's repos | DISABLED | Re-enable only with capable model |
| Zone 3: production/cloud/DNS | BLOCKED | No credentials on VPS |
| Prompt injection mitigation | ENFORCED | Reader/Actor split (ADR-003) |

## Token Expiry

| Token | Expires | Purpose |
|---|---|---|
| `jimbo-vps` (fine-grained PAT) | 2026-05-18 | Read+write jimbo-workspace |
| `openclaw-readonly` (fine-grained PAT) | ~2026-04-17 | Read-only Marvin's repos (currently disabled) |

---

*Last updated: 2026-02-20*
