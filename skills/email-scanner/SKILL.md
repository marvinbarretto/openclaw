---
name: email-scanner
description: Check pre-scored email insights for urgent/time-sensitive items and surface them immediately
user-invokable: false
---

# Email Scanner

You are running as an isolated cron job in a **persistent session ("email")**. You remember what you flagged in previous runs. Your job: check pre-scored email insights for urgent items, surface only what's worth interrupting for, stay silent otherwise.

**IMPORTANT: Do NOT fetch or read the raw email digest.** The email_triage and email_decision workers have already scored everything. You only read the small, pre-processed insights from jimbo-api.

## Steps

### 1. Read pre-scored insights

```bash
curl -s -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/emails/reports?limit=30"
```

This returns scored email insights with: subject, from, relevance_score, category, suggested_action, reason, time_sensitive, deadline.

### 2. Check what you already flagged

```bash
curl -s -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/activity?days=1"
```

Look for recent `email-scan` activities. Do NOT re-flag items you already surfaced today. Also check your session memory for items from previous runs.

### 3. Filter for urgency

From the scored insights, surface ONLY items that are:
- **Security alerts** (relevance 9+, security-related subjects)
- **Expiring deals/deadlines** within 48 hours (`time_sensitive: true` with near deadline)
- **Direct personal messages** requiring a response
- **High-relevance items** (score 9+) that are genuinely actionable TODAY

Do NOT surface: newsletters, marketing, routine notifications, anything that can wait.

**Maximum 2-3 items per scan.** If in doubt, leave it out.

### 4. Output

Start with a label so Marvin knows which job this is:

**[Email]**

Then for each item:
- Bold source/subject
- 1-2 line WHY this is urgent
- Inline link if available from the insight data

Example:
> **[Email]**
> **GitHub security alert** — new PAT 'jimbo-vps' added to your account. Verify: https://github.com/settings/security-log

### 5. Output discipline

**If nothing urgent: produce ZERO output.** No "all clear", no summary. Complete silence.

### 6. Log

```bash
python3 /workspace/activity-log.py log --type email-scan --description "Checked N insights" --outcome "flagged N items"
```

Use "silent" as outcome if nothing was flagged.
