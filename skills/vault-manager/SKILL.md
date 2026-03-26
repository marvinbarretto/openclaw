---
name: vault-manager
description: Surface priority vault tasks and track velocity in a persistent session
user-invokable: false
---

# Vault Manager

You are running as an isolated cron job in a **persistent session ("vault")**. You track what was surfaced previously. Your job: report vault status, suggest today's focus, notice changes.

## Steps

### 1. Gather data

Vault stats:
```bash
curl -s -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/vault/stats"
```

Priority tasks:
```bash
curl -s -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/vault/tasks?sort=priority&limit=10"
```

Recent activity:
```bash
curl -s -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/activity?days=1"
```

### 2. Check session memory

This session persists across runs. Check what you surfaced yesterday. Note:
- Did the suggested focus get actioned? (Check activity log for related entries)
- Are the same items appearing for 3+ days? (Stale — note briefly, don't nag)
- Any new inbox items since last check?

### 3. Compose status

Start with a label, then one short message:

**[Vault]**

- **Vault:** active count, inbox count (+N new if changed)
- **Velocity:** completed this week (be honest — if 0, say 0)
- **Focus today:** ONE actionable task from the top priorities. Pick items with `actionability: "clear"` over `"needs-breakdown"`. If the same item was suggested 3+ days, try the next one.

Example:
> Vault: 1,634 active, 84 inbox (+3 new). Velocity: 0 this week. Focus: "Plan the week" (priority 9, clear).

### 4. Output discipline

If nothing changed since yesterday (same counts, same top tasks, no activity): **produce ZERO output.** Complete silence.

### 5. Log

```bash
python3 /workspace/activity-log.py log --type vault-check --description "Active: N, inbox: N, velocity: N" --outcome "suggested: [task name]"
```
