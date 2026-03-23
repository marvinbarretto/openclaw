# Vault Quick Capture Skill — Design Spec

**Date:** 2026-03-23
**Status:** Draft
**Author:** Marvin + Claude

## Problem

When working in any repo or context, Marvin often has ideas, tasks, bookmarks, or research threads he wants to capture without losing his train of thought. Currently there's no way to quickly file something into the Jimbo vault from Claude Code — he'd need to switch to the web UI or mentally hold onto it until later.

## Solution

A global Claude Code skill (`/vault`) that captures thoughts into the Jimbo vault via the jimbo-api REST endpoint. Notes go straight to the SQLite database — no markdown files, no filesystem. It harvests conversation context automatically so the note is rich enough to be useful later, not just a one-liner.

## Invocation

```
/vault [type] [title/description]
```

### Examples

```
/vault task look into Hono middleware patterns for auth
/vault idea what if Spoons had a pub crawl mode with leaderboard
/vault bookmark that Astro content collections article from the docs
/vault reference the OpenClaw skill format spec
/vault                  # no args — prompts for type, then description
```

## Flow

1. **Parse args** — extract type (first word, if it matches a known type) and description (everything after)
2. **If no type provided**, ask: `task, idea, bookmark, or reference? (type "other" for full list)`
   - Full list: task, bookmark, recipe, idea, reference, travel, media, checklist, person, finance, health, quote, journal, political, event
3. **If no description provided**, ask for one
4. **Harvest context** — gather environment and conversation context automatically
5. **Compose draft** — build title + structured body, show to user
6. **User confirms or edits** — any affirmative response sends it. If the user requests changes, apply them and show the updated draft
7. **POST to API** — `POST /api/vault/notes` with the composed note
8. **Confirm** — print note title and confirmation, return to previous work

## Context Harvesting

The skill builds the note body from three layers:

### Layer 1: User's Words
The description they typed becomes the opening paragraph under `## What`.

### Layer 2: Environment (automatic)
- Current working directory / repo name
- Current git branch (if in a git repo — omit if not)
- Recently touched files (from git status or conversation context)

If not in a git repo, omit branch and git status. Use working directory path only.

### Layer 3: Conversation Context (automatic)
A brief summary of what was being discussed/worked on, relevant to the capture:
- What problem was being solved
- Key decisions or findings
- Relevant file paths, error messages, or code references
- What the user might want to think about or do next

If invoked in a fresh conversation with no prior context, omit the Notes section entirely rather than generating filler. Keep the body under ~500 words — this is a capture note, not a document.

### Draft Preview

The skill shows the user a preview of the JSON payload before sending:

```
Title:  Look into Hono middleware patterns for auth
Type:   task
Status: inbox

Body:
  ## What
  Look into Hono middleware patterns for auth — the current
  jimbo-api routes have no auth middleware, each handler checks
  the API key individually.

  ## Context
  - **Repo:** jimbo-api (~/development/jimbo/jimbo-api)
  - **Branch:** main
  - **Working on:** vault CRUD routes
  - **Related files:** src/routes/vault.ts, src/middleware/

  ## Notes
  Was discussing vault API contract, noticed auth pattern
  is copy-pasted across every handler. Worth extracting to
  middleware before adding more routes.
```

The body is markdown — the `body` field in the DB is `string | null` and existing vault notes already contain markdown from the ingestion pipeline. Using markdown headers and formatting makes notes readable when revisited in the web UI.

The user sees this preview and confirms before it's sent.

## API Integration

### Request

```bash
curl -s -X POST "${JIMBO_API_URL}/api/vault/notes" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${JIMBO_API_KEY}" \
  -d '{
    "title": "Look into Hono middleware patterns for auth",
    "type": "task",
    "status": "inbox",
    "source": "claude-code",
    "route": "claude_code",
    "owner": "marvin",
    "body": "## What\n\nLook into Hono middleware patterns for auth...\n\n## Context\n\n- **Repo:** jimbo-api, branch main\n- **Related:** src/routes/vault.ts"
  }'
```

### Environment Variables

- `JIMBO_API_URL` — base URL for jimbo-api (e.g., `https://167.99.206.214`)
- `JIMBO_API_KEY` — API authentication key

These must be set in the user's shell environment or Claude Code settings. The skill checks for them on invocation and gives a clear error if missing.

### Mandatory Fields

The API defaults differ from what we want. These fields MUST be sent explicitly — omitting them will bypass triage or lose routing context:

| Field | Value | API default if omitted | Why it must be explicit |
|-------|-------|----------------------|----------------------|
| `status` | `"inbox"` | `"active"` | Would skip triage pipeline |
| `source` | `"claude-code"` | `null` | Filterable origin |
| `route` | `"claude_code"` | `"unrouted"` | Needed for downstream filtering |
| `owner` | `"marvin"` | `"unassigned"` | Single user system |

### Optional Fields (left for downstream pipeline)

| Field | Value | Rationale |
|-------|-------|-----------|
| `actionability` | omit | Let Gemini Flash scoring pipeline decide |
| `ai_priority` | omit | Let scoring pipeline decide |
| `tags` | omit | Add during triage later (API stores as JSON string, not array) |

### Title Derivation

The title is derived from the user's description — take the first sentence or a concise summary (~10 words max). The full description goes into the body.

## Skill Location

**Global:** `~/.claude/commands/vault.md`

This makes it available from any repo and any conversation. The skill is a prompt-only markdown file — no executable code, just instructions for Claude Code.

### Frontmatter

```yaml
---
description: Quick-capture a thought, task, or idea into the Jimbo vault
argument-hint: "[type] [description]"
---
```

## Data Flow

```
/vault task "idea description"
  → Claude Code composes JSON payload (title, type, body, status, source, route, owner)
  → curl POST to jimbo-api /api/vault/notes
  → jimbo-api generates ID (note_XXXXXXXX), inserts into SQLite vault_notes table
  → Returns full VaultNote object with ID and timestamps
  → Skill prints confirmation with note ID
```

No markdown files. No filesystem writes. No ingestion pipeline. The note lands directly in the database and is immediately queryable via the vault API and visible in the web UI.

## Scope — What This Doesn't Do

- **No read/search/update/delete** — this is capture only. The web UI, Jimbo, and `/triage-tasks` handle the rest.
- **No LLM classification** — notes go in as `inbox`, the existing Gemini Flash scoring pipeline handles triage and priority.
- **No blocking workflows** — fire and forget. Confirm, send, back to work.

## Error Handling

- **Missing env vars:** Print which var is missing and how to set it
- **API unreachable:** Print error, suggest checking VPS status. Don't retry — the user can re-run `/vault` when the API is back.
- **API returns error:** Print the status code and response body. Show the drafted note content so the user can copy it or retry.

## Success Criteria

- Can invoke `/vault task [description]` from any repo and have a note appear in the vault within seconds
- Context harvesting produces a body that's useful when revisited days later
- The review step is fast — glance, confirm, done
- No dependencies beyond `curl` and two env vars
