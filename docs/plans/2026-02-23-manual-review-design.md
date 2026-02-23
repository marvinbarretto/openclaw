# Manual Review Command — Design

## What

A Claude Code custom command (`/manual-review`) that lets Marvin review `needs-context` vault notes interactively. One file: `.claude/commands/manual-review.md`.

## Invocation

```
/manual-review 10    → review 10 items
/manual-review       → defaults to 10
```

`$ARGUMENTS` captures the number.

## Flow

1. Read up to N files from `data/vault/needs-context/` (oldest first)
2. Read `context/PATTERNS.md` for classification context
3. Present a numbered table: title, source, created date, body preview
4. Go through each note — show it, ask what to do
5. If the user gives a full answer (e.g. "direct, type=media, tags=tv,drama"), just do it
6. If the user is vague or unsure, ask follow-up questions — type, tags, project — using multiple choice where helpful
7. Move files and update frontmatter
8. Print session summary
9. Mention any new patterns worth adding to PATTERNS.md

## Actions per note

- **Direct** — user provides type + tags. Frontmatter updated (type, tags, status=active, processed=today). File moved to `notes/`.
- **Context** — user provides free text explanation. Text prepended to note body, `review_context` added to frontmatter. File stays in `needs-context/` for reprocessing via `process-inbox.py --reprocess`.
- **Archive** — user gives a reason (stale, completed, past-event, etc). Frontmatter updated (status=archived, stale_reason). File moved to `archive/`.
- **Skip** — untouched, still there next time.

## Presentation format

```
## Review Batch — 10 items from needs-context

| #  | Title              | Source       | Created    | Preview                   |
|----|--------------------|--------------|------------|---------------------------|
| 1  | Dopesic            | google-tasks | 2026-01-14 | Dopesic                   |
| 2  | 45 yen beer china  | google-tasks | 2026-01-16 | 45 yen beer china 10:1    |
| ...                                                                            |
```

Then note by note, Claude Code shows the full content and asks for a decision. Adaptive — uses interactive prompts when the user needs help, stays out of the way when they know what they want.

## Processing details

- **Frontmatter updates** follow the same schema as `process-inbox.py` — same field names, same values
- **Type taxonomy** sourced from `process-inbox.py` (bookmark, recipe, media, travel, idea, reference, event, task, checklist, person, finance, health, quote, journal, political)
- **Tag suggestions** drawn from existing tags in the vault + project tags from PATTERNS.md
- **File moves** use the same directory structure: `data/vault/notes/`, `data/vault/archive/`

## Session summary

After all notes processed:

```
## Session complete
- 3 notes → notes/ (direct)
- 2 notes → given context (ready for reprocess)
- 4 notes → archive/
- 1 skipped
```

Plus any pattern observations ("I noticed 3 notes were travel prices — consider adding a pattern for bare number + currency notes").

## What this doesn't do

- No mobile UI (that's ADR-024)
- No automatic PATTERNS.md editing (Claude mentions observations, you decide)
- No new scripts (Claude Code does the file operations directly)
- No `--reprocess` flag on process-inbox.py yet (separate task if needed)
