# ADR-006: GitHub Skill Lifecycle — Enable for Bootstrap, Disable Before Free Model

## Status

Accepted

## Context

Jimbo needs to read our repos (Spoons, LocalShout, Pomodoro) to build a solid understanding during the bootstrapping phase. The GitHub skill uses `gh` CLI inside the Docker sandbox to access the GitHub API with a fine-grained read-only token.

However, the OpenClaw FAQ warns: "Smaller tiers are more susceptible to instruction hijacking, so avoid them for tool-enabled agents or when reading untrusted content." Repo content (issues, PRs, code comments) is untrusted input — it could contain prompt injection payloads.

## Decision

**Enable the GitHub skill during bootstrapping (Claude Sonnet), disable it before switching to a free/cheap model.**

### Why

- Claude Sonnet is more resistant to prompt injection — safer to read untrusted repo content
- Bootstrapping is a one-time phase — Jimbo only needs to read the repos once to build USER.md/MEMORY.md
- Once the knowledge is in Jimbo's workspace files, the skill isn't needed for daily use
- If we need GitHub access later on a cheap model, we can re-enable it temporarily on Claude, then switch back

### How to disable

```bash
# Option 1: Remove GH_TOKEN from sandbox env
ssh root@167.99.206.214 "python3 -c \"
import json
with open('/home/openclaw/.openclaw/openclaw.json') as f:
    cfg = json.load(f)
cfg['agents']['defaults']['sandbox']['docker']['env'] = {}
with open('/home/openclaw/.openclaw/openclaw.json', 'w') as f:
    json.dump(cfg, f, indent=2)
\""

# Option 2: Also remove the gh binary mount if you want belt-and-suspenders
# Edit binds list to remove /home/openclaw/homebrew mount

# Then kill container + restart
docker rm -f $(docker ps -q --filter name=openclaw-sbx)
systemctl restart openclaw
```

## Consequences

- **Good:** Reduces attack surface when running cheap models. Follows principle of least privilege.
- **Good:** Jimbo still retains knowledge from repos in its workspace files after skill is disabled.
- **Trade-off:** If Jimbo needs to check repo state after bootstrapping, we'd need to temporarily re-enable or paste content manually.
- **Trade-off:** We're using Marvin's personal GitHub token, not a dedicated bot account (FAQ recommends separate accounts). Acceptable for now given the token is read-only, scoped to 3 repos, and expires in 60 days.
