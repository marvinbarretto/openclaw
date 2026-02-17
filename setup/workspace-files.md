# Workspace Files — Jimbo's Brain

These files live on the VPS at `/home/openclaw/.openclaw/workspace/` and shape how Jimbo behaves. They persist across sessions — when Jimbo "wakes up", it reads these files to remember who it is and who you are.

## The files

| File | Purpose | Who writes it |
|---|---|---|
| `SOUL.md` | Personality, behaviour rules, boundaries | Pre-written by OpenClaw, yours to edit |
| `IDENTITY.md` | Jimbo's name, vibe, emoji | Jimbo (during bootstrapping) |
| `USER.md` | About you — name, projects, preferences | Jimbo (from conversations) |
| `MEMORY.md` | Long-term curated memory | Jimbo (over time) |
| `AGENTS.md` | Operating manual — memory system, safety | Pre-written by OpenClaw |
| `HEARTBEAT.md` | Periodic check tasks | You or Jimbo |
| `TOOLS.md` | Environment-specific notes (SSH hosts etc) | Jimbo |
| `BOOTSTRAP.md` | First-run script — delete after setup | Pre-written, should be deleted |
| `memory/*.md` | Daily conversation logs | Jimbo |

## Quick commands

### Read a file
```bash
# From your laptop
ssh root@167.99.206.214 "cat /home/openclaw/.openclaw/workspace/USER.md"
ssh root@167.99.206.214 "cat /home/openclaw/.openclaw/workspace/SOUL.md"
ssh root@167.99.206.214 "cat /home/openclaw/.openclaw/workspace/IDENTITY.md"
ssh root@167.99.206.214 "cat /home/openclaw/.openclaw/workspace/MEMORY.md"

# Read all at once
ssh root@167.99.206.214 "for f in SOUL.md IDENTITY.md USER.md MEMORY.md; do echo '===== '\$f' ====='; cat /home/openclaw/.openclaw/workspace/\$f 2>/dev/null || echo '(not created yet)'; echo; done"

# Check daily memory logs
ssh root@167.99.206.214 "ls /home/openclaw/.openclaw/workspace/memory/ 2>/dev/null"
ssh root@167.99.206.214 "cat /home/openclaw/.openclaw/workspace/memory/2026-02-16.md 2>/dev/null"
```

### Edit a file interactively
```bash
# SSH in and edit with nano
ssh -t root@167.99.206.214 "nano /home/openclaw/.openclaw/workspace/USER.md"
ssh -t root@167.99.206.214 "nano /home/openclaw/.openclaw/workspace/SOUL.md"
```

### Overwrite a file from your laptop
```bash
# Write a local file then push it
scp ~/my-user.md root@167.99.206.214:/home/openclaw/.openclaw/workspace/USER.md
```

### Append to a file
```bash
ssh root@167.99.206.214 "echo '- Prefers direct, no-fluff communication' >> /home/openclaw/.openclaw/workspace/USER.md"
```

## You can also just tell Jimbo

In Telegram, you can say things like:
- "Update your USER.md to note that I'm building Spoons and LocalShout"
- "Add to your SOUL.md that you should never be sycophantic"
- "Show me what's in your MEMORY.md"
- "What do you know about me?" (it'll read USER.md)

Jimbo will update the files itself. But if you want to make sure it's right, check via SSH.

## When to edit manually vs let Jimbo write

**Let Jimbo write:**
- Day-to-day memory updates
- Learning about your preferences from conversation
- Daily logs

**Edit manually when:**
- Jimbo got something wrong about you
- You want to set hard boundaries (SOUL.md)
- You're switching models and want to seed quality content before the weaker model takes over
- You want to delete sensitive info from memory files

## No restart needed

Changes to workspace files take effect on Jimbo's next message — no restart required. It reads these files at the start of each session.
