# ADR-023: Notes Vault — Processing 13,000 Scattered Notes

## Status

Accepted

## Context

Marvin has ~13,000 scattered notes across Google Tasks (4,755) and Google Keep (8,432). Mostly quick-capture shorthand: bare URLs, 2-3 word phrases, recipes, travel plans. The pattern: capture fast, never process.

Google Tasks has 2,268 open items (1,768 short text, 284 bare URLs, almost no metadata). Google Keep has 4,450 active notes (1,117 bare URLs, 1,582 short, 1,336 medium, 187 checklists, only 84 labelled). Total active: ~6,700 items to process. Most are cryptic one-liners.

The goal: ingest everything into a structured, searchable vault. Jimbo processes daily going forward. Marvin keeps his capture habit (dump into Google Tasks), Jimbo does the organising.

## Decision

### The Vault

A local directory of markdown files with YAML frontmatter, Obsidian-compatible:

```
data/vault/
  ├── notes/          — processed notes (markdown + frontmatter)
  ├── inbox/          — raw unprocessed items awaiting triage
  ├── needs-context/  — items the LLM couldn't classify
  └── archive/        — stale, done, or discarded items
```

Point Obsidian at `data/vault/` and it just works. But primary interface is Jimbo via Telegram.

### Note format

```markdown
---
id: note_a1b2c3d4
source: google-tasks | google-keep | manual
source_id: <original API ID>
source_list: "My Tasks"
type: bookmark | recipe | idea | task | reference | travel | media | checklist
status: inbox | active | needs-context | done | archived
tags: [food, italian, pasta]
created: 2025-03-14
processed: 2026-02-22
title: Baba ganoush recipe
---

Baba ganoush - 4 small-to-medium aubergines...
```

### Type taxonomy

Starting set — new types can be added anytime, removing means retagging:

| Type | What it is |
|---|---|
| `bookmark` | URL to read/watch/use later |
| `recipe` | Food/drink recipe or note |
| `idea` | Something to think about or explore |
| `task` | Something actionable to do |
| `reference` | Info to keep for later |
| `travel` | Trip planning, places, itineraries |
| `media` | Film/TV/music/podcast/book to consume |
| `checklist` | Multi-item list |

### Where things should live

- **Google Tasks** = capture inbox. Dump anything here. Jimbo processes daily, marks complete.
- **Google Keep** = reference material fine to browse visually (recipes, shopping lists). Not for actionable items.
- **Vault** = the processed, structured, searchable system. Everything ends up here.
- **Calendar** = time-sensitive tasks extracted from vault notes.
- **Context files** = updated weekly, informed by vault patterns.

### The "don't guess" principle

If the LLM can't confidently classify a note, it goes to `needs-context/` with status `needs-context`. During conversational triage sessions, Jimbo asks Marvin rapid-fire what things mean. Feels like a chat, not admin.

### Daily processing loop

1. Fetch email (gmail-helper.py), calendar (calendar-helper.py), new tasks (tasks-helper.py)
2. Ingest new tasks → vault inbox/
3. Classify inbox items → type, tags, connections
4. Present in morning briefing alongside email and calendar
5. Marvin confirms → Jimbo marks tasks completed in Google Tasks
6. If tasks sit >24 hours: Jimbo nudges

### Weekly retro (Jimbo-driven)

Vault health, pattern detection, stale sweep, context file update suggestions, deferred item processing. Jimbo keeps a log of patterns and observations.

### Backlog strategy

Most of the 13,000 items are stale. LLM aggressively archives completed tasks, past events, dead URLs, duplicates. Marvin gets a summary and can rescue anything.

Processing waves:
1. Items with existing labels/structure (~700)
2. Short text from active lists (Today, Immediate) (~650)
3. Bare URLs — fetch titles, classify (~1,400)
4. Everything else (My Tasks backlog, older Keep) (~3,500)

### Cost

~6,500 items × ~500 tokens each via Haiku: ~$1-3 total for entire backlog. Ongoing: negligible.

## Implementation

### Phase A: Ingest scripts (laptop, one-time backlog)

- `scripts/ingest-tasks.py` — converts tasks-dump.json → `data/vault/inbox/` markdown
- `scripts/ingest-keep.py` — converts Keep JSON export → `data/vault/inbox/` markdown

### Phase B: LLM processing (laptop)

- `scripts/process-inbox.py` — batch classify, tag, archive stale, move to notes/

### Phase C: Daily system (VPS)

- `workspace/tasks-helper.py` — Tasks API client: poll new, mark completed
- `skills/vault/SKILL.md` — Jimbo skill for vault queries + triage mode
- Upgrade `scripts/google-auth.py` scope: `tasks.readonly` → `tasks`
- Update `skills/daily-briefing/SKILL.md` with notes section

### Security

- Tasks API scope upgrade: from `tasks.readonly` to `tasks` (read-write) so Jimbo can mark tasks as completed after ingesting
- Same OAuth infrastructure as Calendar and Gmail
- Vault lives in `data/` (gitignored) — no note content in repo
- If VPS compromised: attacker could mark tasks complete (nuisance, not data loss). Tasks are trivially recoverable.

## Consequences

**What becomes easier:**
- Every quick thought is captured AND processed
- Notes are searchable, typed, tagged, connected
- Context files evolve from actual data, not guesswork
- Google Tasks stays clean — true inbox, never a graveyard
- Obsidian gives visual browsing for free

**What becomes harder:**
- One more OAuth scope to manage
- Vault directory needs backing up (or pushing to VPS)
- LLM classification quality needs monitoring during backlog processing

**What this enables (future):**
- Context files served as API from personal website
- Weekly retros that surface real patterns
- Cross-referencing notes with email highlights
- Light web UI for browsing vault
