---
name: morning-summary
description: Short morning status report — what's done, what's pending, today's shape
user-invokable: false
---

# Morning Summary

You are running as an isolated cron job at 07:30. Other jobs have already handled the detail work (email scanning, calendar check). Your job is a **5-7 line status report** — not a briefing, not analysis. Think daily standup.

## Steps

### 1. Pull system state

```bash
curl -s -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/health"
```

### 2. Compose status

Read the health response and write exactly this:

**Label:** Start with **[Morning]**

**Line 1 — Day shape:** Day of week. Overall feel based on calendar events count and gaps. "Tuesday. Wide open until 18:30 gym." or "Thursday. Packed — 4 events, protect the morning."

**Line 2 — Email:** How many processed, how many flagged by email-scanner. "52 emails processed, 3 flagged earlier."

**Line 3 — Vault:** Active count, today's suggested focus from vault-manager. "Vault focus: 'Plan the week' (priority 9)."

**Line 4 — System:** Any issues from `health.issues[]`. Pipeline status. "All systems green." or "vault_roulette still broken. Opus stale (8 days)."

**Line 5 — Cost:** Only if notable. "$0.05 today, $0.59 month (2% budget)." Skip if unremarkable.

**Line 6 — Editorial closer:** One sentence. Set the tone. Be opinionated. "Good day for deep work — protect it." or "Lots of options tonight, pick one and commit."

### 3. Rules

- This is a REPORT. No deep dives. No repeating what other jobs already delivered.
- Keep it scannable — someone glancing at their phone should get the picture in 5 seconds.
- Never exceed 7 lines.

### 4. Log

```bash
python3 /workspace/activity-log.py log --type briefing --description "Morning summary" --outcome "delivered"
```
