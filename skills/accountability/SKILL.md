---
name: accountability
description: End-of-day accountability report — what ran, what broke, honest assessment
user-invokable: false
---

# Accountability Report

You are running as an isolated cron job at 20:00 UTC. Honest daily accountability. No sugar-coating.

## Steps

### 1. Gather data

Health:
```bash
curl -s -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/health"
```

Activity:
```bash
curl -s -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/activity?days=1"
```

Costs:
```bash
curl -s -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/costs/summary?days=1"
```

### 2. Report

Start with **[Accountability]**, then cover these areas:

- **Pipeline:** Did morning + afternoon pipelines run? Gem count, insight count.
- **Activity:** Total activities today, breakdown by type (briefing, email-scan, vault-check, heartbeat, etc.)
- **Vault:** Velocity this week. Any tasks completed today? Any new inbox items?
- **Cost:** Today's spend, month-to-date, budget %.
- **Issues:** Broken tools (check `health.tools`), recurring failures, stale data.

### 3. Assessment

If everything ran fine: keep it to 3-4 lines. "Both pipelines ran. 14 gems, 8 activities. Vault velocity: 0 (day 7). $0.05 today. No new issues."

If things broke: explain what, how long it's been broken, and suggest a fix if obvious. "vault_reader 401 for 5th day — likely needs token refresh. vault_roulette still returning no candidates."

### 4. Patterns

If you notice something recurring (same failure 3+ days, cost trending up, activity dropping), call it out. "This is the 4th consecutive day with 0 vault velocity. The task system isn't being used."

### 5. Log

```bash
python3 /workspace/activity-log.py log --type accountability --description "Daily report" --outcome "[brief assessment]"
```
