---
name: daily-briefing
description: Give a concise morning briefing combining email, tasks, and context
user-invokable: true
---

# Daily Briefing

When the user says good morning, asks for a briefing, or it's a scheduled morning session, give a concise daily overview.

**IMPORTANT: This skill has REQUIRED sections. Do not skip sections 1-4. A briefing without a day plan is not a briefing — it's a notification. Read SOUL.md's "Morning Briefing Minimum Bar" section.**

## Before you start

**Memory check (if available):** Before running any commands, use `memory_search` to look up:
- Yesterday's briefing — what was highlighted, what Marvin reacted to
- Recent surprise game results — what worked, what didn't
- Any feedback patterns (e.g. "stop mentioning X", "I liked when you Y")

This makes today's briefing build on yesterday's instead of starting from scratch.

Run these commands in the SANDBOX, before composing any output. Use the sandbox/execute tool (NOT the read tool — files are inside the Docker container, not on the host filesystem).

1. `python3 /workspace/recommendations-helper.py expire`
2. `python3 /workspace/calendar-helper.py list-events --days 1`
3. `cat /workspace/email-digest.json | python3 -c "import sys,json; d=json.load(sys.stdin); items=list(d['items']); print(f'Date: {d[\"date\"]}'); print(f'Total: {len(items)}'); [print(f'  {i[\"sender\"][\"name\"] if isinstance(i[\"sender\"],dict) else i[\"sender\"]}: {i[\"subject\"]}') for i in items[:15]]"`
4. `python3 /workspace/context-helper.py priorities`
5. `python3 /workspace/context-helper.py goals`
6. `python3 /workspace/context-helper.py interests`
7. `cat /workspace/context/TASTE.md`
8. `grep -rl 'priority: [789]' /workspace/vault/notes/ | head -20 | xargs -I{} head -25 {}`
9. `cat /workspace/tasks-triage-pending.json 2>/dev/null || echo '{"needs_triage": 0}'`

IMPORTANT: All file access must go through sandbox commands (cat, grep, python3). Do NOT use the read/file tool — those paths don't exist on the host.

Note: Context files (Priorities, Interests, Goals) are served from the context API via context-helper.py. TASTE.md is still a local file. If context-helper.py fails, fall back to `cat /workspace/context/PRIORITIES.md` etc.

Do ALL of these before writing a single word of output. If a command fails, note it and move on — don't skip the rest.

## What to include (REQUIRED sections marked with *)

### *1. Date and greeting
- Today's date and day of the week
- Brief, friendly greeting (match the tone in SOUL.md)

### *2. Today's schedule + day plan proposal
- Show today's **fixed** events from the calendar command in chronological order
- Flag anything in the next 2 hours
- If the calendar command failed: say "Calendar unavailable" and move on (do NOT skip the day plan)
- **Then propose a day plan:**
  - Identify free gaps (30+ minutes) between fixed events
  - Cross-reference with email digest, PRIORITIES, GOALS, INTERESTS, **and vault tasks**
  - Suggest 3-5 activities for those gaps with emoji prefixes (see day-planner skill)
  - Include at least 1 vault task (📋) from the priority-scored results
  - End with **"Anything you'd swap or skip?"** to invite negotiation
- This turns the briefing into a conversation. Don't create any events yet — wait for Marvin's response.

### *3. Vault tasks
- From the vault search in step 7 above, read the frontmatter of matched files
- Filter for `type: task`, `status: active`, sort by `priority` descending
- Surface the top 2-3 tasks with `priority >= 7` and `actionability: clear` — weave them into the day plan with 📋 emoji
- If any tasks have `suggested_status: stale`, flag them: "This task might be stale — want to dismiss it?"
- Fallback if no priority field: `grep -rli 'type: task' /workspace/vault/notes/ | head -20` then check tags
- If vault is empty, say so briefly

### 3.5 Tasks triage announcement

Run in the sandbox:
```bash
cat /workspace/tasks-triage-pending.json 2>/dev/null || echo '{"needs_triage": 0}'
```

- If the file exists and `needs_triage > 0`:
  - Announce: "I picked up **{total_classified} tasks** overnight. **{needs_triage} need your input** — cryptic notes I couldn't confidently classify."
  - Ask: "When's good for a 15-min triage session? I'll send a calendar invite."
  - Wait for Marvin's reply with a time
  - Create the invite:
    ```bash
    python3 /workspace/calendar-helper.py create-event --summary "Jimbo: Tasks Triage" --start <ISO_TIME> --end <ISO_TIME+15min> --description "Triage ambiguous vault tasks from today's sweep"
    ```
  - Confirm: "Booked — I'll walk you through them at [time]."
- If the file is missing or `needs_triage` is 0: skip this section silently

### *4. Email highlights (NOT just subject lines)
- Read `/workspace/email-digest.json` (key: `items`, each has `sender`, `subject`, `body_snippet`)
- If fresh (< 24h): scan for time-sensitive items FIRST (overdue payments, expiring deals, event deadlines, personal replies)
- Then pick 2-3 genuinely interesting items based on PRIORITIES.md, GOALS.md, and INTERESTS.md
- **Explain WHY each matters** — "Buenos Aires flight dropped to £632 — you were tracking this" is good. Just listing a subject line is lazy.
- **You know Marvin.** You have his interests, priorities, goals, and taste. Don't hedge with "if that's your thing" or "if you're interested" — you already know what he's interested in. Be confident. Say "you'll want to read this" not "if politics is your thing".
- Filter out promotional junk that survived the blacklist — if it's a loyalty scheme, promo, or newsletter with no real content, skip it
- If stale: "Your email digest is from [date] — might be outdated"
- If missing: "No email digest today"

### 5. Recommendation follow-ups
- Run `python3 /workspace/recommendations-helper.py list --urgency time-sensitive --status surfaced --days 7`
- If any results: "Reminder: [title] expires [date] — still unread"
- Keep to 1-2 lines

### 6. Email quick stats
- Total emails, brief summary
- Say "ask me about email for the full rundown" for details

### 7. Priority reminders
- Check PRIORITIES.md for anything due or active
- Only mention 1-2 things that haven't already been covered in the day plan

### 8. Context freshness
- The context-helper.py output from steps 4-6 includes a `Last updated:` line at the bottom with the date
- Use THAT date (from the API), NOT the file modification time of the backup markdown files
- If PRIORITIES hasn't been updated in more than 10 days, nudge: "Your priorities are [N] days old — worth a quick review via the site?"
- If GOALS hasn't been updated in more than 45 days, nudge similarly
- Only mention stale files, skip if fresh

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

Log the briefing to both trackers. This is MANDATORY — the daily accountability check at 20:00 UTC reads these logs to verify the briefing ran and what it covered.

```bash
python3 /workspace/cost-tracker.py log --provider <provider> --model <model> --task briefing --input-tokens <est> --output-tokens <est>
python3 /workspace/activity-log.py log --task briefing \
    --description "Morning briefing: <brief summary of key points>" \
    --outcome "<success|partial|fallback>" \
    --rationale "Components: calendar=<ok|failed>, email=<ok|stale|missing>, vault=<N tasks surfaced|empty>, surprise=<played|skipped>" \
    --model <model>
```

The `--rationale` field is what the accountability checker uses to verify each component ran. Be specific — "vault=3 tasks surfaced" is better than "vault=ok".

## Rules

- Be concise — this is a glance, not a deep dive
- Lead with anything time-sensitive or actionable
- Don't list every queued email — pick the 2-3 best based on his context
- If all sources are empty/missing, just greet and say "Nothing pressing today"
- Match Jimbo's personality from SOUL.md
