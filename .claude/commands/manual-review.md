---
description: Interactively review needs-context vault notes — triage, classify, and move them
argument-hint: "[count] [oldest|newest|random]"
---

# Manual Review of Needs-Context Vault Notes

You are running an interactive review session for Marvin's personal notes vault. Notes in `data/vault/needs-context/` are items that the LLM classifier couldn't confidently categorise. Marvin will give you context so they can be properly classified and filed.

## Setup

1. Parse arguments from `$ARGUMENTS`:
   - First argument: batch size (default 10)
   - Second argument: sort order — `oldest` (default), `newest`, or `random`
   - Examples: `10 newest`, `5`, `20 random`, empty = `10 oldest`
2. Read `context/PATTERNS.md` — this tells you how Marvin's notes actually work
3. List files in `data/vault/needs-context/`, read up to N of them in the chosen sort order
4. If there are fewer files than requested, just use what's there

## Present the Batch

Show a numbered markdown table with all notes in the batch:

| # | Title | Source | Created | Preview |
|---|-------|--------|---------|---------|

- **Title**: from frontmatter `title` field
- **Source**: from frontmatter `source` field
- **Created**: from frontmatter `created` field
- **Preview**: first 60 chars of the body (after frontmatter), trimmed

Then say: "Let's go through these one at a time. For each note I'll show the full content and you tell me what to do."

## Note-by-Note Review

For each note, show:

```
### Note N: [title]

**Source:** [source] | **List:** [source_list] | **Created:** [created]
**Current tags:** [tags]

> [full body content]
```

Then ask what to do. Adapt to the user's response style:

- **If they give a complete answer** like "direct, type=media, tags=tv,drama" — just do it, no follow-up needed
- **If they say "direct" but don't specify details** — ask follow-up questions using AskUserQuestion with multiple choice for type, then tags
- **If they say "archive"** without a reason — ask for the stale reason
- **If they give context conversationally** like "this is a TV show I wanted to watch" — infer the action (that's a direct classify: type=media, tags from context) and confirm before processing
- **If they say "skip"** — move on, leave the file untouched
- **If they say "all — archive, stale"** or similar — apply the same action to all remaining notes in the batch

## Actions

### Direct (classify and move to notes/)

Update frontmatter: set `type`, `tags` (JSON array), `status` to `active`, `processed` to today (YYYY-MM-DD). Move file to `data/vault/notes/`.

### Context (add context, leave for reprocessing)

Prepend context text to note body (after frontmatter). Add `review_context` to frontmatter. Leave in `data/vault/needs-context/`.

### Archive (move to archive/)

Update frontmatter: set `status` to `archived`, `stale_reason`, `processed` to today (YYYY-MM-DD). Move file to `data/vault/archive/`.

### Skip

Do nothing.

## File Operations — Use Python, Not Edit

**CRITICAL: Do NOT use the Edit tool for frontmatter changes.** Edit shows diffs to the user which clutters the review session. Instead, use a single inline Python script via Bash to update frontmatter and move the file in one silent operation.

For each note that needs processing, run a single Bash command like:

```bash
python3 -c "
import re, json, shutil, os, datetime
path = 'DATA_VAULT_PATH/needs-context/FILENAME'
with open(path) as f: content = f.read()
m = re.match(r'^---\n(.*?)\n---\n?(.*)', content, re.DOTALL)
if not m: exit(1)
yaml_text, body = m.group(1), m.group(2)
# Update fields
lines = yaml_text.split('\n')
updates = {UPDATES_DICT}
new_lines = []
for line in lines:
    km = re.match(r'^(\w[\w-]*)\s*:', line)
    if km and km.group(1) in updates:
        key = km.group(1)
        val = updates.pop(key)
        new_lines.append(f'{key}: {json.dumps(val) if isinstance(val, list) else val}')
    else:
        new_lines.append(line)
for key, val in updates.items():
    new_lines.append(f'{key}: {json.dumps(val) if isinstance(val, list) else val}')
new_content = '---\n' + '\n'.join(new_lines) + '\n---\n' + body
PREPEND_CONTEXT
with open(path, 'w') as f: f.write(new_content)
MOVE_COMMAND
"
```

Adapt the template per action:
- **Direct:** updates = status, type, tags, processed. Move to notes/.
- **Archive:** updates = status, stale_reason, processed. Move to archive/.
- **Context:** updates = review_context. Prepend text to body. No move.

This keeps the entire operation silent — one "Done" from Bash, no diffs shown.

## Reference: Type Taxonomy

bookmark, recipe, media, travel, idea, reference, event, task, checklist, person, finance, health, quote, journal, political

## Reference: Stale Reasons

stale, dead-url, completed, duplicate, past-event, empty

## Reference: Project Tags

project:localshout (venues, events, artists), project:film-planner (film/TV/shows), project:spoons (pub data), project:openclaw (Jimbo improvements)

## Session Summary

After processing all notes, print:

```
## Session complete
- X notes → notes/ (direct)
- X notes → given context (ready for reprocess)
- X notes → archive/
- X skipped
```

If you notice recurring patterns across 2+ notes not already in PATTERNS.md, mention them. Do NOT edit PATTERNS.md automatically.
