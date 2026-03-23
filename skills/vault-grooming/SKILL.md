---
name: vault-grooming
description: Interactive backlog grooming session via Telegram
user-invokable: true
---

# Vault Grooming

When Marvin says "let's groom", "backlog review", "triage", or you have 10+ inbox items and suggest a session.

## Step 1: Prepare the summary

```bash
curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/vault/tasks/summary"
```

Report the numbers, then load the items:

```bash
# Inbox items
curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/vault/notes?status=inbox&sort=created_at&order=desc&limit=50"

# Blocked items
curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/vault/notes?status=blocked&limit=20"

# Need breakdown
curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/vault/notes?status=active&actionability=needs-breakdown&limit=20"
```

Present: "Ready to groom. 8 inbox, 2 blocked, 3 need breakdown. Start with inbox?"

## Step 2: Walk through each category

### Inbox items

Present each with title, source, and when it arrived. Move quickly — Marvin knows his own backlog. For each, Marvin says one of:

| Marvin says | You do |
|---|---|
| "Active" / "Keep" | `curl -sf -X PATCH -H "X-API-Key: $JIMBO_API_KEY" -H "Content-Type: application/json" -d '{"status":"active"}' "$JIMBO_API_URL/api/vault/notes/<ID>"` |
| "I'll take it" | `PATCH {"status":"in_progress","owner":"marvin"}` |
| "You do it" / "Jimbo" | `PATCH {"status":"in_progress","owner":"jimbo"}` |
| "Not now" / "Later" | Ask when to revisit. `PATCH {"status":"deferred","due_date":"<date>"}` |
| "Archive" / "Kill it" | `PATCH {"status":"archived"}` |
| "Break it down" | Ask for subtasks. For each: `curl -sf -X POST -H "X-API-Key: $JIMBO_API_KEY" -H "Content-Type: application/json" -d '{"title":"<subtask>","status":"active"}' "$JIMBO_API_URL/api/vault/notes/<PARENT_ID>/subtasks"` |
| "Skip" | Move to next |

If Marvin says "archive the rest" or "skip the rest", use batch:

```bash
curl -sf -X PATCH -H "X-API-Key: $JIMBO_API_KEY" -H "Content-Type: application/json" \
  -d '{"ids":["id1","id2","id3"],"patch":{"status":"archived"}}' \
  "$JIMBO_API_URL/api/vault/notes/batch"
```

### Blocked items

For each, show title and `blocked_by` text. Ask: "Still blocked on {blocked_by}?"

If resolved: `PATCH {"status":"in_progress","blocked_by":null}`
If still blocked: move on.

### Needs breakdown

Present the task. Ask Marvin to list subtasks. Create each via the subtasks endpoint with `parent_id`.

## Step 3: Wrap up

```bash
curl -sf -H "X-API-Key: $JIMBO_API_KEY" "$JIMBO_API_URL/api/vault/tasks/summary"
```

Report the new numbers: "Groomed: 5 activated, 2 archived, 1 broken down into 3 subtasks. Inbox down from 8 to 1."

Log to activity log:

```bash
curl -sf -X POST -H "X-API-Key: $JIMBO_API_KEY" -H "Content-Type: application/json" \
  -d '{"task_type":"grooming","description":"Backlog grooming session","outcome":"success"}' \
  "$JIMBO_API_URL/api/activity"
```

## Notes

- If the session is interrupted, just re-invoke this skill. It reads state from the API — partially groomed items keep their updates.
- Don't explain each task. Marvin knows what they are. Just present title + source + age.
- Move fast. A grooming session should take 5-15 minutes, not an hour.
