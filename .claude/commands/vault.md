---
description: Quick-capture a thought, task, or idea into the Jimbo vault
argument-hint: "[type] [description]"
---

# Vault Quick-Capture

Capture whatever is in `$ARGUMENTS` into the Jimbo vault via the REST API. Parse it, draft a note, confirm with Marvin, and send it.

## Step 1: Check Environment

Run a quick check that the API credentials are available:

```bash
echo "JIMBO_API_URL=${JIMBO_API_URL:-MISSING}" && echo "JIMBO_API_KEY=${JIMBO_API_KEY:-MISSING}"
```

If either shows `MISSING`, stop and tell Marvin:

> Set `JIMBO_API_URL` and `JIMBO_API_KEY` in your environment. These are the same values used by jimbo-api (check `/opt/openclaw.env` on the VPS or ask Marvin for the local values).

Do not proceed until both are set.

## Step 2: Parse Arguments

Look at `$ARGUMENTS`. The known note types are: task, idea, bookmark, reference, recipe, travel, media, checklist, person, finance, health, quote, journal, political, event.

- **If the first word matches a known type:** use it as the type, treat the rest as the description.
- **If the first word doesn't match:** treat the entire string as the description. Ask Marvin to pick a type — offer these common ones as quick picks: task, idea, bookmark, reference. Mention "other" if none fit (show the full list on request).
- **If `$ARGUMENTS` is empty:** ask Marvin for a type first, then a description. Don't guess.

## Step 3: Harvest Context

Gather useful context to enrich the note. Run these in parallel where possible:

**Environment context:**
```bash
echo "cwd: $(pwd)" && git rev-parse --abbrev-ref HEAD 2>/dev/null && git status --short 2>/dev/null | head -10
```

**Conversation context:** Look at what Marvin has been working on in this conversation — what problems were discussed, what decisions were made, what files were touched. If this is a fresh conversation with no prior context, skip this part entirely. Don't fabricate context.

## Step 4: Compose Draft

Build a draft note:

- **Title:** ~10 words max, sentence case, descriptive. Not a filename — a human-readable title.
- **Body:** Markdown with these sections:
  - `## What` — what the note is about, in 2-3 sentences
  - `## Context` — where it came from (conversation topic, repo, branch, problem being solved). Omit if no meaningful context exists.
  - `## Notes` — any additional detail, links, or next steps. Omit if empty.

Keep the total body under ~500 words. This is a quick capture, not a document.

Show the draft to Marvin like this:

> **Title:** [title]
> **Type:** [type]
> **Status:** inbox
>
> [body]
>
> Send this to the vault? (yes / edit / cancel)

If Marvin requests changes, apply them and show the updated draft. Loop until confirmed or cancelled.

## Step 5: Send to API

On confirmation, POST the note to the vault API:

```bash
curl -s -w "\n%{http_code}" \
  -X POST "${JIMBO_API_URL}/api/vault/notes" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${JIMBO_API_KEY}" \
  -d '{
    "title": "THE TITLE",
    "type": "THE TYPE",
    "body": "THE BODY WITH ESCAPED NEWLINES AND QUOTES",
    "status": "inbox",
    "source": "claude-code",
    "route": "claude_code",
    "owner": "marvin"
  }'
```

Important details:
- `status` MUST be `"inbox"` — the API defaults to "active" which skips triage.
- `route` MUST be `"claude_code"` — the API defaults to "unrouted".
- `owner` MUST be `"marvin"` — the API defaults to "unassigned".
- Do NOT send `actionability`, `ai_priority`, or `tags` — those are set by the scoring pipeline later.
- Properly escape newlines (`\n`) and double quotes in the body for valid JSON.

## Step 6: Confirm Result

Parse the response (the last line is the HTTP status code, everything before it is the response body).

- **On 201:** Extract the note ID from the response JSON. Print:
  > Captured: **[title]** (id: [note_id], type: [type])

- **On any other status code:** Print the status code and response body. Then show the draft content so Marvin can copy it or retry manually.

- **On network error (connection refused, timeout):** Print the error. Suggest checking the API:
  > API unreachable. Try: `ssh jimbo` then `systemctl status jimbo-api`

  Show the full draft content so nothing is lost.
