# ADR-024: Notes Review Queue — Mobile-First Triage for Needs-Context Items

## Status

Proposed

## Context

`process-inbox.py` (ADR-023) classifies vault notes via LLM. Items the LLM can't confidently classify land in `data/vault/needs-context/`. Currently ~hundreds of items accumulate there with no structured way to review them.

Marvin needs to triage these on mobile — on the bus, in a queue, anywhere with a phone. Add a sentence of context, fix tags, assign a type, or dismiss. His responses feed back into the system: notes get reclassified and PATTERNS.md improves over time.

A personal website (Vercel or Cloudflare, TBD) is planned. The review queue would be one route on that site — a lightweight page hitting the VPS API.

## Decision

### Architecture

```
Laptop (export script)
  → reads data/vault/needs-context/
  → generates review-queue.json (batch of 20 notes)
  → pushes JSON to VPS via rsync

VPS (tiny Python API behind Caddy)
  → GET  /api/review-queue    — serves the queue JSON
  → POST /api/review-response — receives Marvin's responses, appends to file

Personal website (Vercel/Cloudflare, future)
  → /review route — static HTML+JS
  → fetches queue from VPS API, renders cards
  → posts responses back to VPS
  → mobile-first, card-based, one note at a time

Laptop (import script)
  → pulls responses from VPS
  → re-processes notes with added context
  → PATTERNS.md updated manually after review sessions
```

### VPS as data API, personal site as frontend

Data stays on existing infrastructure. The VPS already runs Caddy with auto TLS — adding two JSON endpoints is trivial. The frontend goes wherever the personal site lands (Vercel, Cloudflare, whatever). Clean separation: API is stable, UI can be rebuilt or moved without touching the VPS.

### JSON file exchange, no database

Export script writes `review-queue.json`. API serves it. Responses append to `review-responses.json`. Import script reads that file. No SQLite, no Redis, no state to manage. Debuggable with `cat`. Fits every existing pattern in this repo.

### Queue format

```json
{
  "exported": "2026-02-22T09:00:00Z",
  "batch": 1,
  "notes": [
    {
      "id": "note_a1b2c3d4",
      "title": "Baba ganoush recipe",
      "body": "Baba ganoush - 4 small-to-medium aubergines...",
      "source": "google-keep",
      "current_type": null,
      "current_tags": [],
      "created": "2025-03-14"
    }
  ]
}
```

### Response format

```json
{
  "id": "note_a1b2c3d4",
  "action": "context | edit | dismiss",
  "context": "This is the recipe from that Turkish place in Watford",
  "type": "recipe",
  "tags": ["food", "turkish", "aubergine"],
  "responded": "2026-02-22T10:15:00Z"
}
```

### Three response types per note

1. **Add context** — free text sentence explaining what the note means. Gets prepended to the note body before reclassification.
2. **Edit tags/type** — directly assign type and tags. Note moves straight to `notes/` with no reclassification needed.
3. **Dismiss** — archive the note. Moves to `archive/` with status `archived`.

### Batch model

Queue of 20 notes at a time. Not a live stream. Matches the "do this on the bus" workflow — swipe through a batch, done. New batch exported next time the script runs.

### No auth initially

Unlisted URL, personal use only. The API serves read-only vault metadata (titles, short bodies) — no credentials, no tokens, no secrets. Auth added when/if the personal site goes public or gets a custom domain.

### Feedback loop

```
Marvin reviews batch on phone
  → responses pulled to laptop
  → notes with added context re-run through process-inbox.py
  → notes with direct edits moved to notes/
  → dismissed notes archived
  → PATTERNS.md updated manually with new classification insights
```

Over time, PATTERNS.md improvements mean fewer items land in `needs-context/` at all.

## Implementation

### Scripts (laptop, stdlib Python)

- `scripts/export-review-queue.py` — reads `data/vault/needs-context/`, generates `data/review-queue.json` (batch of 20), rsyncs to VPS
- `scripts/import-review-responses.py` — pulls `review-responses.json` from VPS, applies responses to vault (reclassify, move, archive)

### VPS API (stdlib Python, behind Caddy)

- `workspace/review-api.py` — minimal HTTP server (http.server), two endpoints. Runs as systemd service or supervised by OpenClaw.
- Caddy reverse proxy: `/api/review-*` → `localhost:<port>`

### Frontend (personal website, future)

- `/review` route — static HTML+JS, no framework needed
- Card UI: shows note title, body preview, source, date
- Swipe or tap: add context, edit, dismiss
- Mobile-first, works offline (queue cached in localStorage, responses synced when online)

### What this defers

- **Personal website build** — separate project, hosting TBD
- **Authentication** — added later, not needed for unlisted personal use
- **Automated PATTERNS.md updates** — manual for now, automated when patterns stabilise
- **Live sync** — batch export is fine; real-time not needed for bus triage

## Consequences

**What becomes easier:**
- Needs-context items actually get reviewed instead of accumulating forever
- Triage happens in dead time (commute, queues) instead of competing for desk time
- Classification improves over time as PATTERNS.md grows from real feedback
- Clean separation means API and UI can evolve independently

**What becomes harder:**
- One more service on the VPS (review-api.py)
- Caddy config gets another route
- Export/import adds two more scripts to maintain

**What this enables (future):**
- Same API pattern reusable for other vault operations (browse, search)
- Personal website has a real use case from day one
- Foundation for more interactive Jimbo workflows beyond Telegram
