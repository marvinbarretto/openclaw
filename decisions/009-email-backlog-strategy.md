# ADR-009: Email Backlog Processing Strategy

## Status

Accepted

## Context

28,799 emails in Gmail, synced to local Maildir via mbsync. The daily pipeline (`sift-classify.py --hours 24`) handles new incoming mail, but the backlog needs a separate strategy. Processing all 28k through Ollama at ~15 seconds per email would take ~120 hours of continuous inference.

We need to:
1. Process the backlog in manageable batches
2. Give Jimbo access to backlog digests without overwhelming him
3. Eventually build a searchable email index Jimbo can query

## Decision

### Phase 1: Batch processing (newest-first)

Process the backlog in reverse chronological order, 200 emails at a time:

```bash
# Batch 1: Most recent 200 (beyond today's digest)
python3 scripts/sift-classify.py --input ~/Mail/gmail/INBOX --all --limit 200 \
    --output data/email-backlog-001.json

# Batch 2: Next 200
python3 scripts/sift-classify.py --input ~/Mail/gmail/INBOX --all --limit 400 \
    --output data/email-backlog-002.json
# (then diff/skip the first 200 — needs --offset flag, TODO)
```

**Why 200:** At ~15s/email, a batch of 200 takes ~50 minutes. Feasible to run overnight or while AFK. Small enough to review output quality between batches.

**Why newest-first:** Recent emails are most actionable. The oldest 20k are probably archive/bulk with little value. Per ADR-002: "the 90-day batch likely contains everything you're actually stressed about."

### Phase 2: Backlog digests for Jimbo

Backlog output files go to a separate location on the VPS:

```
/workspace/email-backlog/
  ├── batch-001.json    (most recent 200)
  ├── batch-002.json    (next 200)
  ├── ...
  └── summary.json      (aggregate stats across all batches)
```

A new skill (`sift-backlog`) will teach Jimbo to:
- Read `summary.json` for high-level stats ("28k emails, 12k classified so far, 340 queued")
- Search across batches by sender, category, or keyword
- Present backlog findings separately from the daily digest

### Phase 3: Merged searchable index (later)

Once enough batches are processed, merge all batch files into a single searchable index:
- SQLite FTS5 database (same tech as OpenClaw's memory-core plugin)
- Jimbo can query: "find emails from Wetherspoon" or "what newsletters am I subscribed to?"
- This is the long-term goal but not needed yet

### Processing schedule

| Timeframe | What | Emails | Time |
|-----------|------|--------|------|
| Week 1 | Last 90 days | ~600-800 | 3-4 overnight runs |
| Week 2-3 | Last 12 months | ~2000-3000 | 10-15 overnight runs |
| Month 2+ | Full archive | ~25000 remaining | Background, low priority |

Run batches overnight on the laptop. Ollama handles inference; laptop can sleep between batches if needed.

### Required script changes

1. **Add `--offset N`** to sift-classify.py — skip first N emails after sorting, to process batch windows
2. **Add backlog push script** — `scripts/sift-backlog-push.sh` to rsync backlog files to VPS
3. **Add sift-backlog skill** — teaches Jimbo to navigate backlog digests
4. **Add summary generator** — script to merge batch stats into summary.json

## Consequences

### Easier
- Newest-first gets value fast — actionable mail surfaces first
- Batch size is manageable — can spot-check quality between runs
- Jimbo can start using backlog data incrementally, doesn't need to wait for full processing
- Overnight runs don't block laptop usage

### Harder
- 120+ hours total inference time for full backlog — this is a weeks-long project
- Need to track which emails have been processed to avoid duplicates
- Backlog digests are large — Jimbo needs search, not sequential reading
- Older emails may classify poorly (stale context, dead links, outdated projects)

### Acceptable tradeoffs
- Full backlog coverage is a nice-to-have, not urgent. The 90-day window covers actionable mail.
- Duplicate processing wastes Ollama time but doesn't cause errors (stable IDs prevent data issues)
- Older email quality doesn't matter much — the main value is identifying unsubscribe candidates and forgotten subscriptions
