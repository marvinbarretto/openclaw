# Workspace Files — Jimbo's Brain

These files live on the VPS at `/home/openclaw/.openclaw/workspace/` and shape how Jimbo behaves. They persist across sessions — when Jimbo "wakes up", it reads these files to remember who it is and who you are.

## The files

| File | Purpose | Who maintains it | Tracked in repo? |
|---|---|---|---|
| `SOUL.md` | Personality, behaviour rules, output rules | Us | Yes (`workspace/SOUL.md`) |
| `HEARTBEAT.md` | Periodic check tasks | Us | Yes (`workspace/HEARTBEAT.md`) |
| `context/*.md` | Interests, priorities, taste, goals | Us | Yes (`context/`) |
| `IDENTITY.md` | Jimbo's name, vibe, emoji | Jimbo | No |
| `USER.md` | About you — name, projects, preferences | Jimbo | No |
| `MEMORY.md` | Long-term curated memory | Jimbo | No |
| `JIMBO_DIARY.md` | Jimbo's daily journal | Jimbo | No |
| `AGENTS.md` | Operating manual — memory system, safety | Pre-written by OpenClaw | No |
| `TOOLS.md` | Environment-specific notes (SSH hosts etc) | Jimbo | No |
| `memory/*.md` | Daily conversation logs | Jimbo | No |

## Editing workflow

**The rule: edit locally, commit, push.** Don't edit files on the VPS directly — changes get lost and aren't tracked.

### Files we maintain

Edit in the repo, commit, then deploy:

```bash
# Edit locally
vim workspace/SOUL.md
vim context/PRIORITIES.md

# Commit
git add -A && git commit -m "Update SOUL.md output rules"

# Push to VPS (brain files + context files in one command)
./scripts/workspace-push.sh
```

### Files Jimbo maintains

These live only on the VPS. Read them via SSH but don't overwrite:

```bash
# Read Jimbo's files
ssh jimbo "cat /home/openclaw/.openclaw/workspace/USER.md"
ssh jimbo "cat /home/openclaw/.openclaw/workspace/MEMORY.md"
ssh jimbo "cat /home/openclaw/.openclaw/workspace/JIMBO_DIARY.md"

# Read all at once
ssh jimbo "for f in SOUL.md IDENTITY.md USER.md MEMORY.md; do echo '===== '\$f' ====='; cat /home/openclaw/.openclaw/workspace/\$f 2>/dev/null || echo '(not created yet)'; echo; done"
```

### Emergency edits on VPS

Only for quick fixes that can't wait for a commit (e.g. Jimbo wrote something wrong in USER.md, or you need to delete sensitive info from memory):

```bash
ssh -t jimbo "nano /home/openclaw/.openclaw/workspace/USER.md"
```

## You can also just tell Jimbo

In Telegram, you can say things like:
- "Update your USER.md to note that I'm building Spoons and LocalShout"
- "Show me what's in your MEMORY.md"
- "What do you know about me?" (it'll read USER.md)

Jimbo will update its own files. But for files we maintain (SOUL.md, HEARTBEAT.md, context/), always edit locally and push.

## No restart needed

Changes to workspace files take effect on Jimbo's next session — no restart required.
