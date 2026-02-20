# ADR-014: Sift pipeline performance and resilience

## Status

Accepted

## Context

Two problems surfaced on 2026-02-20:

1. **mbsync failed silently** — the Mac woke from sleep at 04:00 but the network wasn't ready. mbsync got "Connection reset by peer" from Gmail IMAP. The script continued and classified a near-empty Maildir, pushing a 4-item digest to Jimbo instead of ~150.

2. **Scanning is slow** — `collect_emails()` iterates all 158k Maildir files, stat-ing each one. Since mbsync sets both filenames and mtimes to sync time (not email receive time), the mtime pre-filter is useless for bulk-synced mailboxes — nearly all files pass. The scan takes several minutes even though only ~150 emails are relevant.

## Decision

### Network-ready retry loop (sift-cron.sh)

Before running mbsync, wait up to 60 seconds for network connectivity by pinging `imap.gmail.com` every 5 seconds. If the network isn't ready after 60s, abort the run entirely rather than classifying stale data.

### Seen-files index (sift-classify.py)

Track which filenames have been processed in `data/.sift-seen.json` (a dict mapping filename → email Date header ISO string). On each run:

- Skip any file already in the index (no stat, no parse)
- After classifying new files, save the updated index
- Prune entries older than 14 days to prevent unbounded growth
- `--no-cache` flag bypasses the index when needed

### os.scandir() for directory iteration

Replace `Path.iterdir()` with `os.scandir()` in `collect_emails()`. Avoids creating Path objects for 158k files and gives us DirEntry objects with cheaper stat calls.

### Performance instrumentation

Each run measures scan time, classify time, and total time via `time.monotonic()`, then appends one JSON line to `data/sift-perf.log` with full metrics (files_total, files_skipped_index, files_skipped_mtime, files_skipped_date, files_classified, avg_classify_seconds).

## Consequences

- **Repeat runs are near-instant** — the index skips ~158k files without any stat calls.
- **First run after a fresh sync only processes truly new files** — mbsync adds new filenames, which won't be in the index.
- **Network failures are caught early** — no more 4-item digests from stale Maildirs.
- **Performance is measurable** — `sift-perf.log` gives before/after proof and ongoing monitoring.
- **Index adds a new file** (`data/.sift-seen.json`) that must be gitignored and will grow up to ~14 days of filenames (~150/day × 14 = ~2100 entries, negligible).
- **`--no-cache` is the escape hatch** if the index ever gets corrupt or needs rebuilding.
- **`collect_emails()` return signature changed** — now returns `(emails, scan_stats)` tuple instead of just `emails`.
