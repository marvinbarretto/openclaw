# CLAUDE.md

## What This Is

Tooling & config repo for Jimbo (personal OpenClaw AI instance on DigitalOcean VPS). Read ADRs in `decisions/` for architecture decisions, not this file.

## Critical Rules

**Deployment:**
- `jimbo-api`: `git push/pull` only (systemd runs from repo root)
- `workspace/` files (Python scripts, workers, prompts, workflows): `rsync` via `workspace-push.sh` only
- `workspace-push.sh` targets `/home/openclaw/.openclaw/workspace/` (OpenClaw's managed workspace, mounted as `/workspace/` in Docker)
- **Never use per-file `scp`** — VPS rate-limits SSH after ~5 connections

**Security (ADR-001, 003, 008, 022):**
- No ClawHub skills — custom SKILL.md only
- Email via Gmail API read-only, sandbox processing only
- Reader/Actor split — untrusted text → Reader model only

**Scripts:**
- Bash: `set -euo pipefail`, no `scp` loops
- Python: stdlib only, defaults to dry-run with `--live` flag

## Gotchas

- VPS workspace path: `/home/openclaw/.openclaw/workspace/`, not `/home/openclaw/workspace/`
- VPS jimbo-api path: `/home/openclaw/jimbo-api`, not `~/jimbo-api`
- Running `openclaw` CLI: needs env vars + correct HOME + `openclaw` user
- Blog deployed to Cloudflare Pages from `blog-src/` on `gh-pages` branch
