# ADR-025: Recommendations Store — Persistent Memory for Jimbo's Finds

## Status

Proposed

## Context

Jimbo reads 50-150 emails daily, surfaces 3-10 articles worth reading, presents them in the morning briefing, and then... forgets everything. Next day he starts fresh. There's no record of what he recommended, whether Marvin read it, how strong the signal was, or whether a time-sensitive event has passed.

Over a month, that's potentially 100+ curated recommendations — lost. The email digest itself is overwritten daily. Telegram chat history is not structured or searchable. Nothing accumulates.

The problem gets worse with the notes vault (ADR-023). As Jimbo starts processing bookmarks and media notes from the vault, he'll surface even more recommendations from multiple sources. Without a store, none of this compounds.

What we need:
- **Persistence** — recommendations survive across sessions and days
- **Scoring** — not all recommendations are equal; some are strong signals, others are maybes
- **Urgency** — a festival next Saturday is different from an evergreen blog post
- **Status tracking** — surfaced → read → saved/dismissed
- **Queryability** — "show me unread recommendations from last 2 weeks" needs to be fast

## Decision

### SQLite over JSON or markdown

This is cumulative, queryable data. It doesn't fit the existing patterns:

- **JSON files** (like email-digest.json) work for ephemeral daily snapshots. A recommendations log that grows to 1000+ entries and needs date-range/score/status queries is painful in flat JSON.
- **Markdown files** (like vault notes) work for documents you browse. One file per recommendation = explosion. Aggregation queries require parsing hundreds of files.
- **SQLite** is in Python stdlib (`sqlite3`). Single file. Handles scores, dates, status natively. Range queries are trivial. Still just a file in `data/` — easy to backup, rsync, gitignore.

New pattern for this repo, but the right tool for the job.

### Schema

```sql
CREATE TABLE recommendations (
    id TEXT PRIMARY KEY,           -- rec_<8hex>
    url TEXT,                      -- nullable (not all recs have URLs)
    title TEXT NOT NULL,
    source TEXT NOT NULL,          -- newsletter name, sender, or "vault"
    source_id TEXT,                -- gmail_id or vault note id for dedup
    snippet TEXT,                  -- 200 char preview / Jimbo's summary

    score REAL NOT NULL DEFAULT 0.5,  -- 0.0 to 1.0 signal strength
    urgency TEXT NOT NULL DEFAULT 'evergreen',
        -- evergreen: read whenever
        -- this-week: relevant soon but not critical
        -- time-sensitive: has a hard deadline (check expires)
    expires TEXT,                  -- ISO date, nullable. For events, deals, deadlines.

    status TEXT NOT NULL DEFAULT 'surfaced',
        -- surfaced: Jimbo recommended it
        -- read: Marvin opened/acknowledged it
        -- saved: Marvin wants to keep it
        -- dismissed: not interested
        -- expired: time-sensitive item past its date

    tags TEXT,                     -- JSON array as text: ["ai", "music", "localshout"]
    reasoning TEXT,                -- why Jimbo thinks this matters (1 sentence)

    surfaced_date TEXT NOT NULL,   -- ISO datetime when first recommended
    read_date TEXT,                -- when Marvin marked it read
    updated_date TEXT,             -- last status change

    source_type TEXT NOT NULL DEFAULT 'email'
        -- email: from daily digest
        -- vault: from notes vault
        -- manual: Marvin added directly
);

CREATE INDEX idx_status ON recommendations(status);
CREATE INDEX idx_surfaced ON recommendations(surfaced_date);
CREATE INDEX idx_urgency ON recommendations(urgency);
CREATE INDEX idx_expires ON recommendations(expires);
```

### Where it lives

**On the VPS, in the sandbox workspace.** Jimbo writes to it during briefing prep. This is the same location as email-digest.json — Jimbo already has read/write access.

Path: `/workspace/recommendations.db` (VPS sandbox)
Backup: rsynced to laptop `data/recommendations.db` periodically

On the laptop, a copy in `data/recommendations.db` (gitignored) for local queries and backup.

### How Jimbo writes to it

A small Python helper: `workspace/recommendations-helper.py`. Jimbo calls it from the sandbox during briefing prep, after reading the email digest.

```bash
# Log recommendations from today's digest
python3 /workspace/recommendations-helper.py log \
    --title "Anjuna fabric event" \
    --url "https://example.com/event" \
    --source "Resident Advisor" \
    --source-id "18dfa3b2c1e" \
    --score 0.9 \
    --urgency time-sensitive \
    --expires 2026-03-01 \
    --tags '["music", "events", "london"]' \
    --reasoning "Matches your electronic music interest, next Saturday in London"

# Mark as read
python3 /workspace/recommendations-helper.py update rec_a1b2c3d4 --status read

# Query
python3 /workspace/recommendations-helper.py list --status surfaced --days 7
python3 /workspace/recommendations-helper.py list --urgency time-sensitive --status surfaced
python3 /workspace/recommendations-helper.py list --expired  # show items past their date
python3 /workspace/recommendations-helper.py stats  # counts by status, avg score, urgency breakdown
```

### How Jimbo integrates it

The sift-digest and daily-briefing skills get updated to:

1. **During briefing prep:** After reading the email digest and identifying highlights, Jimbo logs each recommendation to the store with a score and urgency.
2. **During briefing presentation:** Jimbo checks the store for unread time-sensitive items approaching their expiry. "Reminder: that Anjuna event is in 2 days and you haven't looked at it."
3. **During conversation:** When Marvin says "I read that" or "not interested", Jimbo updates the status.
4. **Weekly:** Jimbo can surface stats — "You saved 12 articles this week, read 8. 3 time-sensitive items expired unread."

### Scoring model

Jimbo assigns scores during briefing prep based on context files:

| Score | Meaning | Example |
|---|---|---|
| 0.9-1.0 | Strong match to active priorities + personally relevant | LocalShout competitor launch, Spoons-related pub news |
| 0.7-0.8 | Good match to interests, timely | New AI tool matching his stack, good music event in London |
| 0.5-0.6 | Interesting but not urgent | Thoughtful essay on a topic he follows |
| 0.3-0.4 | Tangential, might be worth a glance | Broadly relevant but not a strong signal |
| 0.1-0.2 | Included for completeness | Borderline item Jimbo isn't sure about |

Scores are Jimbo's judgment call, informed by PRIORITIES, INTERESTS, TASTE, and GOALS. They're not algorithmic — they're editorial.

### Deduplication

`source_id` prevents the same email or vault note being logged twice. If Jimbo processes the same digest again (e.g. user asks for email twice in a day), existing entries are skipped, not duplicated.

### Expiry handling

A nightly or briefing-time check marks `time-sensitive` items past their `expires` date as `expired`. Jimbo mentions these during briefing: "2 recommendations expired unread this week — want to see what you missed?"

### No auth, no API (yet)

The store lives on the VPS filesystem. Jimbo reads/writes via the helper script. No HTTP API needed until the personal website review queue (ADR-024) wants to display recommendations alongside needs-context notes. At that point, the review API gains a `/api/recommendations` endpoint.

## Implementation

### Phase 1: Store + helper (build now)

- `workspace/recommendations-helper.py` — SQLite CRUD, CLI interface. Stdlib Python only.
- Deploy to VPS via `workspace-push.sh`

### Phase 2: Skill integration (build now)

- Update `skills/sift-digest/SKILL.md` — instruct Jimbo to log recommendations after reading digest
- Update `skills/daily-briefing/SKILL.md` — check store for expiring/unread items, include in briefing
- Add a "recommendations" conversational command — Jimbo responds to "what should I read?" from the store

### Phase 3: Review queue integration (after personal website)

- ADR-024 review API gains `/api/recommendations` endpoint
- Mobile UI shows recommendations alongside needs-context vault items
- Swipe to mark read/save/dismiss

## Consequences

**What becomes easier:**
- Jimbo's finds accumulate over time instead of vanishing daily
- Time-sensitive recommendations get follow-up nudges
- "What should I read this weekend?" has a real answer
- Weekly retros can surface patterns: "You keep saving AI articles but never reading them"
- Scoring creates signal — the best stuff floats to the top

**What becomes harder:**
- Jimbo needs to log recommendations during briefing (extra sandbox calls)
- New helper script to maintain on VPS
- SQLite is a new pattern — not human-readable like JSON/markdown
- Score calibration will take a few weeks to feel right

**What this enables (future):**
- Recommendation quality tracking over time (does Marvin read high-score items more?)
- Cross-referencing with vault notes ("you bookmarked this 6 months ago AND it was in today's email")
- Personal website dashboard showing reading stats and patterns
- Eventually: score model improves from feedback (read rate by score band)
