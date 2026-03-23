# Vault Quick Capture Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a global `/vault` Claude Code skill that captures thoughts into the Jimbo vault via the jimbo-api REST endpoint.

**Architecture:** Single markdown command file at `~/.claude/commands/vault.md` (source in openclaw repo, symlinked globally). Uses `curl` to POST to jimbo-api. No dependencies beyond shell env vars.

**Tech Stack:** Markdown skill file, bash/curl, jimbo-api REST endpoint

**Spec:** `docs/superpowers/specs/2026-03-23-vault-capture-design.md`

---

### Task 1: Write the skill file

**Files:**
- Create: `.claude/commands/vault.md`

- [ ] **Step 1: Create the vault.md command file**

Write the skill file with frontmatter and full instructions:

```markdown
---
description: Quick-capture a thought, task, or idea into the Jimbo vault
argument-hint: "[type] [description]"
---

# Vault Capture

Capture a thought into the Jimbo vault via jimbo-api. Parse `$ARGUMENTS`, compose a note with conversation context, and POST it.

## Step 1: Check Environment

Before doing anything, verify the required env vars exist. Run:

` ` `bash
echo "JIMBO_API_URL=${JIMBO_API_URL:-MISSING}" && echo "JIMBO_API_KEY=${JIMBO_API_KEY:-MISSING}"
` ` `

If either is `MISSING`, stop and tell the user:
> Missing environment variable(s). Set `JIMBO_API_URL` and `JIMBO_API_KEY` in your shell profile or Claude Code settings.
> Example: `export JIMBO_API_URL=https://167.99.206.214` and `export JIMBO_API_KEY=your-key`

## Step 2: Parse Arguments

Look at `$ARGUMENTS`.

**Known types:** task, idea, bookmark, reference, recipe, travel, media, checklist, person, finance, health, quote, journal, political, event

- If the first word matches a known type, use it as the type and the rest as the description.
  - Example: `task look into Hono auth` → type=task, description="look into Hono auth"
- If the first word does NOT match a known type, treat the entire string as the description and ask:
  > What type is this? **task**, **idea**, **bookmark**, or **reference**?
  > (Type "other" for the full list: recipe, travel, media, checklist, person, finance, health, quote, journal, political, event)
- If `$ARGUMENTS` is empty, ask for the type first, then the description.

## Step 3: Harvest Context

Gather context from the current environment and conversation. Run in parallel where possible:

**Environment context** (use Bash tool):
- Current working directory (pwd)
- Git repo name and branch (if in a git repo — skip if not): `git rev-parse --abbrev-ref HEAD 2>/dev/null` and `basename $(git rev-parse --show-toplevel 2>/dev/null) 2>/dev/null`
- Recently modified files (if in a git repo): `git status --short 2>/dev/null | head -5`

**Conversation context** (from your memory of this conversation):
- What was the user working on before invoking /vault?
- What problem were they solving, what decisions were made?
- Any relevant file paths, error messages, or code references?
- What do they want to think about or follow up on?

If this is a fresh conversation with no prior context, skip the conversation context — don't generate filler.

## Step 4: Compose Draft

Build the note from the gathered information:

**Title:** Derive from the description — first sentence or a concise summary (~10 words max). Sentence case.

**Body:** Markdown format, structured as:

```
## What

[User's description, expanded into a clear paragraph with enough context to be useful when revisited days later]

## Context

- **Repo:** [repo name] ([path])
- **Branch:** [branch name]
- **Working on:** [brief description of what was happening]
- **Related files:** [any relevant file paths]

## Notes

[Conversation-derived context — decisions made, problems encountered, things to follow up on. Only include if there's meaningful context to capture.]
```

Keep the body under ~500 words. This is a capture note, not a document.

**Show the draft to the user:**

```
Title:  [derived title]
Type:   [type]
Status: inbox

Body:
[the composed body]
```

Then ask: "Send this to the vault? (or tell me what to change)"

If the user requests changes, apply them, show the updated draft again, and ask for confirmation. Repeat until they confirm.

## Step 5: Send to API

On user confirmation, POST to jimbo-api using the Bash tool:

` ` `bash
curl -s -X POST "${JIMBO_API_URL}/api/vault/notes" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${JIMBO_API_KEY}" \
  -d '{
    "title": "<TITLE>",
    "type": "<TYPE>",
    "status": "inbox",
    "source": "claude-code",
    "route": "claude_code",
    "owner": "marvin",
    "body": "<BODY — escape newlines and quotes for JSON>"
  }'
` ` `

**Mandatory fields** (API defaults differ — these MUST be sent explicitly):
- `status`: `"inbox"` (API defaults to `"active"`, which would skip triage)
- `source`: `"claude-code"`
- `route`: `"claude_code"` (API defaults to `"unrouted"`)
- `owner`: `"marvin"` (API defaults to `"unassigned"`)

Do NOT send `actionability`, `ai_priority`, or `tags` — the downstream Gemini Flash scoring pipeline handles those.

## Step 6: Confirm

If the API returns 201, parse the response JSON and print:
> Captured: **[title]** (id: [note_id], type: [type])

If the API returns an error, print the status code and response body, then show the drafted note content so the user can copy it or retry.

If the API is unreachable, print the error and suggest checking VPS status (`ssh jimbo` then `systemctl status jimbo-api`). Show the draft content.
```

**Important:** The skill file content above contains ` ` ` (spaced backticks) as a workaround for nested fencing in this plan document. When writing the actual file, replace ALL instances of ` ` ` with real triple backticks (no spaces).

- [ ] **Step 2: Verify the file exists and reads correctly**

Run: `cat .claude/commands/vault.md | head -5`
Expected: The frontmatter with description and argument-hint.

- [ ] **Step 3: Commit**

```bash
git add .claude/commands/vault.md
git commit -m "feat: add /vault quick-capture skill for Jimbo vault"
```

---

### Task 2: Create global symlink

**Files:**
- Create: `~/.claude/commands/vault.md` (symlink)

- [ ] **Step 1: Create the symlink**

```bash
ln -s /Users/marvinbarretto/development/openclaw/.claude/commands/vault.md ~/.claude/commands/vault.md
```

This follows the existing pattern — assess.md, manual-review.md, etc. are all symlinked the same way.

- [ ] **Step 2: Verify the symlink**

```bash
ls -la ~/.claude/commands/vault.md
```

Expected: Symlink pointing to the openclaw repo file.

---

### Task 3: Test the skill end-to-end

- [ ] **Step 1: Verify env vars are set**

```bash
echo "JIMBO_API_URL=${JIMBO_API_URL:-MISSING}" && echo "JIMBO_API_KEY=${JIMBO_API_KEY:-MISSING}"
```

If missing, set them before testing.

- [ ] **Step 2: Test API connectivity**

```bash
curl -s -H "X-API-Key: ${JIMBO_API_KEY}" "${JIMBO_API_URL}/api/vault/notes?limit=1"
```

Expected: JSON response with a note object (confirms API is reachable and auth works).

- [ ] **Step 3: Test creating a note via curl directly**

```bash
curl -s -X POST "${JIMBO_API_URL}/api/vault/notes" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${JIMBO_API_KEY}" \
  -d '{
    "title": "Test note from vault skill development",
    "type": "task",
    "status": "inbox",
    "source": "claude-code",
    "route": "claude_code",
    "owner": "marvin",
    "body": "## What\n\nTest note created during /vault skill development.\n\n## Context\n\n- **Repo:** openclaw\n- **Branch:** master\n- **Working on:** building the /vault quick-capture skill"
  }'
```

Expected: 201 response with full VaultNote object including generated `note_XXXXXXXX` id.

- [ ] **Step 4: Invoke `/vault` from Claude Code**

Run `/vault task test the vault skill works end to end` in a conversation. Verify:
1. It shows a draft with title, type, body
2. On confirmation, it POSTs to the API
3. It prints confirmation with the note ID

- [ ] **Step 5: Clean up test note**

Use the vault web UI or API to delete the test note if desired.
