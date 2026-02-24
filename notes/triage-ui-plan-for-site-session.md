# Notes Triage UI — Plan for Site Session

## What This Is

A mobile-friendly triage UI for ~6,500 Obsidian vault notes. Marvin reviews LLM-suggested classifications on his phone (bus, couch, wherever) and confirms/overrides them.

## How It Fits Together

```
LAPTOP (openclaw repo)                    VPS                           SITE
──────────────────────                    ───                           ────
process-inbox.py --manifest               Hono API                     React island
  → triage-manifest.json                  reads manifest.json          at /app/notes-triage
  → rsync to VPS ──────────────────────→  serves /api/triage/*  ←────  fetches queue, posts decisions
                                          writes decisions.json
  ← rsync from VPS ←────────────────────
apply-decisions.py
  → moves files in vault
```

**The openclaw session builds:** `--manifest` flag, `apply-decisions.py`, rsync scripts
**You build:** Hono API on VPS + React island in the site

## VPS API (Hono)

### Location
Separate repo. Deploys to VPS independently. Caddy reverse proxy route.

### Data
Two JSON files on VPS filesystem:
- `triage/manifest.json` — pushed from laptop, read-only for API
- `triage/decisions.json` — written by API, pulled to laptop

### Auth
`X-API-Key` header. The site is already behind Cloudflare Access for `/app/*`, so API key is a second factor.

### Endpoints

#### `GET /api/triage/queue?offset=0&limit=50`
Returns manifest items, excluding items that already have decisions.

```json
{
  "items": [
    {
      "id": "note_85ded1a",
      "filename": "dopesic--note_85ded1a.md",
      "title": "Dopesic",
      "source": "google-keep",
      "source_list": "Today",
      "created": "2025-08-14",
      "age_days": 558,
      "preview": "Dopesic",
      "word_count": 1,
      "has_url": false,
      "url_content": null,
      "suggested": {
        "action": "direct",
        "type": "media",
        "tags": ["tv", "drama", "project:film-planner"],
        "confidence": 9,
        "title": "Dopesic (TV Series)"
      }
    }
  ],
  "total": 6511,
  "remaining": 6489,
  "decided": 22
}
```

#### `POST /api/triage/decisions`
Append decisions. Body:
```json
{
  "decisions": [
    {
      "id": "note_85ded1a",
      "filename": "dopesic--note_85ded1a.md",
      "action": "direct",
      "type": "media",
      "tags": ["tv", "drama", "project:film-planner"],
      "title": "Dopesic (TV Series)"
    }
  ]
}
```

Response: `{ "saved": 1, "total_decided": 23 }`

#### `GET /api/triage/stats`
```json
{
  "total": 6511,
  "decided": 25,
  "remaining": 6486,
  "by_action": { "direct": 15, "archive": 8, "context": 0, "skip": 2 }
}
```

#### `POST /api/triage/undo`
Body: `{ "id": "note_85ded1a" }`
Removes last decision for that ID. Returns it to the queue.

### VPS Deploy
- SSH alias: `ssh jimbo`
- Caddy reverse proxy (already running, add route for triage API)
- systemd service (same pattern as openclaw service)
- Path: `/home/openclaw/.openclaw/workspace/triage/` for data files

## React Island UI

### Mount Point
Astro island at `/app/notes-triage` (behind Cloudflare Access)

### Card View — One Card at a Time

The primary interaction. Shows one note, user acts on it, next card appears.

**Card layout:**
- Progress counter: `12 / 6,511`
- Title (large)
- Metadata line: `google-keep · 558d ago · 1 word`
- Preview (body text, first ~120 chars)
- URL content if available (fetched tweet text, page title)
- LLM suggestion box with confidence indicator
- Action buttons

**Confidence colouring:**
- Green (8-10): LLM is confident. Default UX is "confirm with one tap"
- Amber (5-7): Uncertain. Show suggestion but prompt user to review
- Red (1-4): LLM couldn't classify. No strong suggestion, user must decide

### Actions

**Quick actions (one tap/swipe):**
- **Accept** (swipe right / tap ✓) — confirm LLM suggestion as-is
- **Archive** (swipe left / tap ✗) — archive with LLM's stale_reason (or "stale" default)
- **Skip** (swipe up) — leave for later
- **Edit** (tap pencil icon) — open override form

**Keyboard shortcuts (desktop):**
- `D` — accept/direct
- `A` — archive
- `S` — skip
- `E` — edit
- `U` — undo last

### Override Form

Expands below the card when user taps Edit:

| Field | Type | When shown |
|-------|------|------------|
| Action | Radio: Direct / Archive / Context / Skip | Always |
| Type | Dropdown (15 options) | If Direct |
| Tags | Chip input with autocomplete | If Direct |
| Project | Shortcut dropdown (4 options) | If Direct |
| Stale reason | Dropdown (6 options) | If Archive |
| Context | Text field | If Context |
| Title | Text input (pre-filled) | If Direct |

### Type Taxonomy (dropdown options)
bookmark, recipe, media, travel, idea, reference, event, task, checklist, person, finance, health, quote, journal, political

### Stale Reasons (dropdown options)
stale, dead-url, completed, duplicate, past-event, empty

### Project Tags (shortcut dropdown)
- project:localshout — venues, events, artists
- project:film-planner — film/TV/shows
- project:spoons — pub data
- project:openclaw — AI assistant improvements

Selecting a project adds the tag to the tags list automatically.

### Tag Autocomplete
Build a frequency list from all tags in the manifest. Show top suggestions as user types. Support `person:` prefix (free text after it).

### Queue Filtering (nice to have for v1)
- By confidence: high/medium/low
- By source: google-keep / google-tasks
- By suggested action: direct / needs-context / archive
- By age: newer than / older than
- Has URL: yes/no

### Progress & Stats Bar
Persistent bar showing: decided count, remaining, breakdown by action. Updates after each decision.

### Undo
Tap undo button or press `U` to revert last decision. Calls `POST /api/triage/undo`.

## Decisions JSON Format

What the API writes to disk (and what the laptop pulls):

```json
{
  "decisions": [
    {
      "id": "note_85ded1a",
      "filename": "dopesic--note_85ded1a.md",
      "action": "direct",
      "type": "media",
      "tags": ["tv", "drama", "project:film-planner"],
      "title": "Dopesic (TV Series)",
      "decided_at": "2026-02-23T22:15:00Z"
    },
    {
      "id": "note_7222101",
      "filename": "1520--note_7222101.md",
      "action": "archive",
      "stale_reason": "stale",
      "decided_at": "2026-02-23T22:15:03Z"
    },
    {
      "id": "note_72fc7e9",
      "filename": "httpsxcom...--note_72fc7e9.md",
      "action": "context",
      "context": "This tweet is about housing policy",
      "decided_at": "2026-02-23T22:15:05Z"
    },
    {
      "id": "note_abc1234",
      "filename": "something--note_abc1234.md",
      "action": "skip",
      "decided_at": "2026-02-23T22:15:06Z"
    }
  ]
}
```

## Build Order Suggestion

1. **API first** — Hono server with the 4 endpoints, reading a test manifest.json
2. **Card component** — static card with mock data, action buttons wired to POST
3. **Swipe gestures** — touch support for mobile
4. **Override form** — type/tags/stale_reason pickers
5. **Queue management** — pagination, filtering, stats
6. **Polish** — undo, keyboard shortcuts, progress bar, confidence colouring
