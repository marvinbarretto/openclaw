#!/usr/bin/env python3
"""
Recommendations store for Jimbo's sandbox.

SQLite-backed CRUD for persisting recommendations across sessions. Jimbo logs
findings from email digests, vault notes, and manual entries. Recommendations
carry scores, urgency levels, and expiry dates.

Python 3.11 stdlib only. No OAuth needed — local SQLite file.

Usage:
    python3 recommendations-helper.py log --title "Great article" --source "Dense Discovery" --score 0.8
    python3 recommendations-helper.py update rec_a1b2c3d4 --status read
    python3 recommendations-helper.py list --status surfaced --days 7
    python3 recommendations-helper.py expire
    python3 recommendations-helper.py stats
"""

import argparse
import datetime
import json
import os
import sqlite3
import sys
import uuid

# DB lives next to this script (works in sandbox /workspace/ and on laptop)
_script_dir = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_script_dir, "recommendations.db")

VALID_STATUSES = ("surfaced", "read", "saved", "dismissed", "expired")
VALID_URGENCIES = ("evergreen", "this-week", "time-sensitive")
VALID_SOURCE_TYPES = ("email", "vault", "manual")

SCHEMA = """
CREATE TABLE IF NOT EXISTS recommendations (
    id TEXT PRIMARY KEY,
    url TEXT,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    source_id TEXT,
    snippet TEXT,
    score REAL NOT NULL DEFAULT 0.5,
    urgency TEXT NOT NULL DEFAULT 'evergreen',
    expires TEXT,
    status TEXT NOT NULL DEFAULT 'surfaced',
    tags TEXT,
    reasoning TEXT,
    surfaced_date TEXT NOT NULL,
    read_date TEXT,
    updated_date TEXT,
    source_type TEXT NOT NULL DEFAULT 'email'
);
CREATE INDEX IF NOT EXISTS idx_status ON recommendations(status);
CREATE INDEX IF NOT EXISTS idx_surfaced ON recommendations(surfaced_date);
CREATE INDEX IF NOT EXISTS idx_urgency ON recommendations(urgency);
CREATE INDEX IF NOT EXISTS idx_expires ON recommendations(expires);
"""


def get_db():
    """Open (and create if needed) the recommendations database."""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def generate_id():
    """Generate a rec_<8hex> ID."""
    return "rec_" + uuid.uuid4().hex[:8]


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def today_iso():
    return datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_log(args):
    """Insert a recommendation (dedup on source_id)."""
    db = get_db()

    # Dedup check
    if args.source_id:
        row = db.execute(
            "SELECT id FROM recommendations WHERE source_id = ?",
            (args.source_id,),
        ).fetchone()
        if row:
            print(json.dumps({
                "status": "ok",
                "id": row["id"],
                "action": "skipped_duplicate",
            }))
            db.close()
            return

    rec_id = generate_id()
    now = now_iso()

    db.execute(
        """INSERT INTO recommendations
           (id, url, title, source, source_id, snippet, score, urgency,
            expires, status, tags, reasoning, surfaced_date, source_type)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'surfaced', ?, ?, ?, ?)""",
        (
            rec_id,
            args.url,
            args.title,
            args.source,
            args.source_id,
            args.snippet,
            args.score,
            args.urgency,
            args.expires,
            args.tags,
            args.reasoning,
            now,
            args.source_type,
        ),
    )
    db.commit()
    db.close()

    print(json.dumps({
        "status": "ok",
        "id": rec_id,
        "action": "created",
    }))


def cmd_update(args):
    """Update status or fields on an existing recommendation."""
    db = get_db()

    row = db.execute(
        "SELECT id, status FROM recommendations WHERE id = ?",
        (args.id,),
    ).fetchone()
    if not row:
        print(json.dumps({"status": "error", "message": f"Not found: {args.id}"}))
        db.close()
        sys.exit(1)

    updates = []
    params = []

    if args.status:
        if args.status not in VALID_STATUSES:
            print(json.dumps({"status": "error", "message": f"Invalid status: {args.status}. Valid: {', '.join(VALID_STATUSES)}"}))
            db.close()
            sys.exit(1)
        updates.append("status = ?")
        params.append(args.status)
        # Auto-set read_date when marking as read
        if args.status == "read" and row["status"] != "read":
            updates.append("read_date = ?")
            params.append(now_iso())

    if args.score is not None:
        updates.append("score = ?")
        params.append(args.score)

    if args.tags is not None:
        updates.append("tags = ?")
        params.append(args.tags)

    if args.reasoning is not None:
        updates.append("reasoning = ?")
        params.append(args.reasoning)

    if not updates:
        print(json.dumps({"status": "ok", "id": args.id, "action": "no_changes"}))
        db.close()
        return

    updates.append("updated_date = ?")
    params.append(now_iso())
    params.append(args.id)

    db.execute(
        f"UPDATE recommendations SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    db.commit()
    db.close()

    print(json.dumps({
        "status": "ok",
        "id": args.id,
        "action": "updated",
    }))


def cmd_list(args):
    """Query recommendations with filters."""
    db = get_db()

    conditions = []
    params = []

    if args.status:
        conditions.append("status = ?")
        params.append(args.status)

    if args.urgency:
        conditions.append("urgency = ?")
        params.append(args.urgency)

    if args.source_type:
        conditions.append("source_type = ?")
        params.append(args.source_type)

    if args.days:
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=args.days)).isoformat()
        conditions.append("surfaced_date >= ?")
        params.append(cutoff)

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    limit = args.limit or 20
    params.append(limit)

    rows = db.execute(
        f"SELECT * FROM recommendations {where} ORDER BY surfaced_date DESC LIMIT ?",
        params,
    ).fetchall()
    db.close()

    results = [dict(r) for r in rows]
    print(json.dumps(results, indent=2))


def cmd_expire(args):
    """Mark time-sensitive items past their expiry date as expired."""
    db = get_db()
    today = today_iso()

    cursor = db.execute(
        """UPDATE recommendations
           SET status = 'expired', updated_date = ?
           WHERE urgency IN ('time-sensitive', 'this-week')
             AND expires IS NOT NULL
             AND expires < ?
             AND status = 'surfaced'""",
        (now_iso(), today),
    )
    count = cursor.rowcount
    db.commit()
    db.close()

    print(json.dumps({
        "status": "ok",
        "expired_count": count,
    }))
    if count > 0:
        print(f"Expired {count} item(s)", file=sys.stderr)


def cmd_stats(args):
    """Summary counts for the recommendations store."""
    db = get_db()

    # By status
    status_rows = db.execute(
        "SELECT status, COUNT(*) as count FROM recommendations GROUP BY status"
    ).fetchall()
    by_status = {r["status"]: r["count"] for r in status_rows}

    # By urgency
    urgency_rows = db.execute(
        "SELECT urgency, COUNT(*) as count FROM recommendations GROUP BY urgency"
    ).fetchall()
    by_urgency = {r["urgency"]: r["count"] for r in urgency_rows}

    # By source_type
    source_rows = db.execute(
        "SELECT source_type, COUNT(*) as count FROM recommendations GROUP BY source_type"
    ).fetchall()
    by_source_type = {r["source_type"]: r["count"] for r in source_rows}

    # Unread count (surfaced)
    unread = by_status.get("surfaced", 0)

    # Expiring soon (next 3 days, still surfaced)
    three_days = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
    today = today_iso()
    expiring_soon = db.execute(
        """SELECT COUNT(*) as count FROM recommendations
           WHERE expires IS NOT NULL
             AND expires >= ? AND expires <= ?
             AND status = 'surfaced'""",
        (today, three_days),
    ).fetchone()["count"]

    # Total
    total = db.execute("SELECT COUNT(*) as count FROM recommendations").fetchone()["count"]

    db.close()

    print(json.dumps({
        "total": total,
        "unread": unread,
        "expiring_soon": expiring_soon,
        "by_status": by_status,
        "by_urgency": by_urgency,
        "by_source_type": by_source_type,
    }, indent=2))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Recommendations store for Jimbo")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # log
    log_p = subparsers.add_parser("log", help="Log a new recommendation")
    log_p.add_argument("--title", required=True, help="Recommendation title")
    log_p.add_argument("--source", required=True, help="Source name (newsletter, sender, 'vault')")
    log_p.add_argument("--url", default=None, help="URL if available")
    log_p.add_argument("--source-id", default=None, help="Gmail ID or vault note ID for dedup")
    log_p.add_argument("--snippet", default=None, help="200 char preview or summary")
    log_p.add_argument("--score", type=float, default=0.5, help="Signal strength 0.0-1.0 (default: 0.5)")
    log_p.add_argument("--urgency", default="evergreen", choices=VALID_URGENCIES, help="Urgency level (default: evergreen)")
    log_p.add_argument("--expires", default=None, help="Expiry date ISO format (for time-sensitive items)")
    log_p.add_argument("--tags", default=None, help='JSON array as string: \'["ai", "music"]\'')
    log_p.add_argument("--reasoning", default=None, help="Why this matters (1 sentence)")
    log_p.add_argument("--source-type", default="email", choices=VALID_SOURCE_TYPES, help="Source type (default: email)")

    # update
    update_p = subparsers.add_parser("update", help="Update a recommendation")
    update_p.add_argument("id", help="Recommendation ID (rec_xxxxxxxx)")
    update_p.add_argument("--status", default=None, help=f"New status: {', '.join(VALID_STATUSES)}")
    update_p.add_argument("--score", type=float, default=None, help="Updated score")
    update_p.add_argument("--tags", default=None, help="Updated tags (JSON array string)")
    update_p.add_argument("--reasoning", default=None, help="Updated reasoning")

    # list
    list_p = subparsers.add_parser("list", help="Query recommendations")
    list_p.add_argument("--status", default=None, help="Filter by status")
    list_p.add_argument("--urgency", default=None, help="Filter by urgency")
    list_p.add_argument("--days", type=int, default=None, help="Only last N days")
    list_p.add_argument("--limit", type=int, default=20, help="Max results (default: 20)")
    list_p.add_argument("--source-type", default=None, help="Filter by source type")

    # expire
    subparsers.add_parser("expire", help="Mark past-due time-sensitive items as expired")

    # stats
    subparsers.add_parser("stats", help="Summary counts")

    args = parser.parse_args()

    commands = {
        "log": cmd_log,
        "update": cmd_update,
        "list": cmd_list,
        "expire": cmd_expire,
        "stats": cmd_stats,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
