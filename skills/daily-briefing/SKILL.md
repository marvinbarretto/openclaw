---
name: daily-briefing
description: Give a concise morning briefing combining email, tasks, and context
user-invokable: true
---

# Daily Briefing

When the user says good morning, asks for a briefing, or it's a scheduled morning session, give a concise daily overview.

## Before you start

1. Run `python3 /workspace/recommendations-helper.py expire` to clean up expired time-sensitive items.

Read Marvin's context to understand what matters today:
1. `/workspace/context/PRIORITIES.md` — what's active this week
2. `/workspace/context/GOALS.md` — longer-term ambitions
3. `/workspace/context/TASTE.md` — how he likes information presented (concise, scannable, timely)

## What to include

### 1. Date and greeting
- Today's date and day of the week
- Brief, friendly greeting (match the tone in SOUL.md)

### 2. Today's schedule + day plan proposal
- Run `python3 /workspace/calendar-helper.py list-events --days 1` in the sandbox
- If it works: show today's **fixed** events (non-suggestion calendar items) in chronological order. Flag anything in the next 2 hours. Suppress routine recurring meetings — just mention the count.
- If it fails or the script doesn't exist: skip this section silently (calendar may not be set up yet)
- **Then propose a day plan.** Read the day-planner skill (`skills/day-planner/SKILL.md`) for the full logic. In short:
  - Identify free gaps (30+ minutes) between fixed events
  - Cross-reference with email digest, PRIORITIES, GOALS, INTERESTS, **and vault tasks**
  - Search `/workspace/vault/notes/` for tasks matching today's active project(s) from PRIORITIES.md
  - Suggest 3-5 activities for those gaps with emoji prefixes — include 📋 vault tasks where specific saved items are more actionable than generic project work
  - End with "Anything you'd swap or skip?" to invite negotiation
- This turns the briefing into a conversation. Don't create any events yet — wait for Marvin's response. See the day-planner skill for the negotiation flow and event creation rules.

### 3. Vault snapshot
- Count vault notes: `ls /workspace/vault/notes/ | wc -l`
- Search for tasks matching today's focus from PRIORITIES.md: `grep -rli 'type: task' /workspace/vault/notes/ | head -20` then check tags/project
- If there are actionable vault tasks for today's project, weave 2-3 into the day plan (already covered above)
- If the vault directory doesn't exist or is empty, skip silently

### 4. Anything time-sensitive from email
- Read `/workspace/email-digest.json`
- If fresh (< 24h): scan for events, tickets, deadlines, personal replies needing action. Call these out first — even before the stats.
- If stale: "Your email digest is from [date] — might be outdated"
- If missing: "No email digest today"

### 5. Recommendation follow-ups
- Run `python3 /workspace/recommendations-helper.py list --urgency time-sensitive --status surfaced --days 7`
- If any results: "Reminder: [title] expires [date] — still unread"
- Run `python3 /workspace/recommendations-helper.py stats`
- If unread count > 10: briefly mention "You have N unread recommendations piling up"
- Keep to 1-2 lines, don't overwhelm the briefing

### 6. Email quick stats
- Total emails, reading time, how many queued vs skipped
- Mention any standout emails: "There's a good Product Hunt issue and an Anjuna event worth looking at"
- Keep to 2-3 lines. Say "ask me about email for the full rundown" for details.

### 7. Priority reminders
- Check PRIORITIES.md for anything due or active
- "You mentioned chasing Daniel about the DisplayLink fix" or "YNAB setup is on your list"
- Only mention 1-2 things, not the whole list

### 8. Context freshness
- Check modification dates of `/workspace/context/PRIORITIES.md` and `/workspace/context/GOALS.md`
- If PRIORITIES is more than 10 days old, nudge: "Your priorities file is [N] days old — worth a quick review?"
- If GOALS is more than 45 days old, nudge: "Your goals file hasn't been updated in [N] days"
- If INTERESTS is more than 90 days old, mention it too
- Only mention stale files, skip this section if everything is fresh
- Keep it to one line per stale file — this is a nudge, not a nag

### 9. Heartbeat tasks
- Read `/workspace/HEARTBEAT.md`
- If there are pending checks, mention briefly
- If nothing due, skip this section

## Presentation format

Keep the briefing concise — the day plan proposal adds a few lines but the total should still be scannable in under a minute. Example:

```
Morning, Marvin. It's Thursday 20 Feb.

Fixed: Dentist at 10:30, Spoons standup at 16:00.

I'd suggest:
  🔨 09:00-10:00 — Spoons PR review (4 days overdue)
  📧 11:30-12:00 — Chase Daniel about DisplayLink
  📋 14:00-15:30 — LocalShout: review auth flow notes (from your vault)
  💰 15:30-16:00 — YNAB setup (keeps slipping)

Anything you'd swap or skip?

Heads up: Anjuna fabric event — tickets might go fast.

Email: 145 messages overnight, ~25 min queued. Standouts: strong UnHerd piece, Watford FC ticket alert.

Heartbeat: All clear — digest is fresh, tokens valid.
```

### 10. Cost snapshot
- Run `python3 /workspace/cost-tracker.py budget --check`
- If a budget is set: show a one-liner like "Costs: $0.42 of $10 this month (4.2%)"
- If over alert threshold: flag it clearly
- If no budget set, skip this section

### 11. OpenRouter balance
- Run `python3 /workspace/openrouter-usage.py balance`
- If balance is below $5 or daily burn rate exceeds $1: include in the briefing (e.g. "OpenRouter: $3.20 remaining")
- If balance is below $1: flag prominently and suggest `./scripts/model-swap.sh daily` or `free`
- If the script fails or env var is missing, skip silently

## After the briefing

Log the briefing to both trackers:

```bash
python3 /workspace/cost-tracker.py log --provider <provider> --model <model> --task briefing --input-tokens <est> --output-tokens <est>
python3 /workspace/activity-log.py log --task briefing --description "Morning briefing: <brief summary of key points>" --model <model>
```

## Rules

- Be concise — this is a glance, not a deep dive
- Lead with anything time-sensitive or actionable
- Don't list every queued email — pick the 2-3 best based on his context
- If all sources are empty/missing, just greet and say "Nothing pressing today"
- Match Jimbo's personality from SOUL.md
