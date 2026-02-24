#!/usr/bin/env python3
"""
Activity log for Jimbo's sandbox.

SQLite-backed logging of everything Jimbo does — email checks, research,
nudges, blog posts, chats. Supports satisfaction scoring by Marvin and
export for dashboard consumption.

Python 3.11 stdlib only. No pip dependencies.

Usage:
    python3 activity-log.py log --task email-check --description "Fetched 12 emails, flagged 2 interesting" --model gemini-2.5-flash
    python3 activity-log.py log --task research --description "Looked up Watford fixtures" --outcome "Next match: Feb 25 vs QPR"
    python3 activity-log.py rate act_abc123 --satisfaction 4 --notes "useful find"
    python3 activity-log.py list --days 1
    python3 activity-log.py export --days 30 --format json
    python3 activity-log.py stats --days 7
"""

import argparse
import datetime
import json
import os
import sqlite3
import sys
import uuid

_script_dir = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_script_dir, "activity-log.db")

VALID_TASK_TYPES = (
    "email-check", "research", "nudge", "blog", "briefing",
    "chat", "own-project", "heartbeat", "digest", "day-planner",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    task_type TEXT NOT NULL,
    description TEXT NOT NULL,
    outcome TEXT,
    model_used TEXT,
    cost_id TEXT,
    satisfaction INTEGER,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_activities_timestamp ON activities(timestamp);
CREATE INDEX IF NOT EXISTS idx_activities_task_type ON activities(task_type);
"""


def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def generate_id():
    return "act_" + uuid.uuid4().hex[:8]


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_log(args):
    """Log an activity."""
    db = get_db()

    act_id = generate_id()

    db.execute(
        """INSERT INTO activities
           (id, timestamp, task_type, description, outcome, model_used, cost_id, satisfaction, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            act_id,
            now_iso(),
            args.task,
            args.description,
            args.outcome,
            args.model,
            args.cost_id,
            None,
            args.notes,
        ),
    )
    db.commit()
    db.close()

    print(json.dumps({
        "status": "ok",
        "id": act_id,
        "action": "logged",
    }))


def cmd_rate(args):
    """Rate an activity (Marvin's satisfaction score)."""
    db = get_db()

    row = db.execute(
        "SELECT id FROM activities WHERE id = ?", (args.id,)
    ).fetchone()
    if not row:
        print(json.dumps({"status": "error", "message": f"Not found: {args.id}"}))
        db.close()
        sys.exit(1)

    if args.satisfaction < 1 or args.satisfaction > 5:
        print(json.dumps({"status": "error", "message": "Satisfaction must be 1-5"}))
        db.close()
        sys.exit(1)

    updates = ["satisfaction = ?"]
    params = [args.satisfaction]

    if args.notes:
        updates.append("notes = ?")
        params.append(args.notes)

    params.append(args.id)
    db.execute(
        f"UPDATE activities SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    db.commit()
    db.close()

    print(json.dumps({
        "status": "ok",
        "id": args.id,
        "action": "rated",
        "satisfaction": args.satisfaction,
    }))


def cmd_list(args):
    """List recent activities."""
    db = get_db()

    conditions = []
    params = []

    if args.task:
        conditions.append("task_type = ?")
        params.append(args.task)

    if args.days:
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=args.days)).isoformat()
        conditions.append("timestamp >= ?")
        params.append(cutoff)

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    limit = args.limit or 50
    params.append(limit)

    rows = db.execute(
        f"SELECT * FROM activities {where} ORDER BY timestamp DESC LIMIT ?",
        params,
    ).fetchall()
    db.close()

    results = [dict(r) for r in rows]
    print(json.dumps(results, indent=2))


def cmd_export(args):
    """Export activity data as JSON for dashboard consumption."""
    db = get_db()
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=args.days)).isoformat()

    rows = db.execute(
        "SELECT * FROM activities WHERE timestamp >= ? ORDER BY timestamp DESC",
        (cutoff,),
    ).fetchall()

    # By task type
    task_rows = db.execute(
        """SELECT task_type, COUNT(*) as count
           FROM activities WHERE timestamp >= ? GROUP BY task_type ORDER BY count DESC""",
        (cutoff,),
    ).fetchall()

    # By day
    day_rows = db.execute(
        """SELECT DATE(timestamp) as day, COUNT(*) as count
           FROM activities WHERE timestamp >= ? GROUP BY DATE(timestamp) ORDER BY day""",
        (cutoff,),
    ).fetchall()

    # Satisfaction stats
    sat_row = db.execute(
        """SELECT AVG(satisfaction) as avg_satisfaction, COUNT(satisfaction) as rated_count
           FROM activities WHERE timestamp >= ? AND satisfaction IS NOT NULL""",
        (cutoff,),
    ).fetchone()

    db.close()

    export = {
        "generated_at": now_iso(),
        "period_days": args.days,
        "total_activities": len(rows),
        "avg_satisfaction": round(sat_row["avg_satisfaction"], 2) if sat_row["avg_satisfaction"] else None,
        "rated_count": sat_row["rated_count"],
        "by_task_type": [dict(r) for r in task_rows],
        "by_day": [dict(r) for r in day_rows],
        "entries": [dict(r) for r in rows],
    }

    print(json.dumps(export, indent=2))


def cmd_stats(args):
    """Summary statistics for the last N days."""
    db = get_db()
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=args.days)).isoformat()

    total = db.execute(
        "SELECT COUNT(*) as count FROM activities WHERE timestamp >= ?",
        (cutoff,),
    ).fetchone()["count"]

    # By task type
    task_rows = db.execute(
        """SELECT task_type, COUNT(*) as count
           FROM activities WHERE timestamp >= ? GROUP BY task_type ORDER BY count DESC""",
        (cutoff,),
    ).fetchall()

    # Satisfaction
    sat_row = db.execute(
        """SELECT AVG(satisfaction) as avg, COUNT(satisfaction) as rated,
                  MIN(satisfaction) as min, MAX(satisfaction) as max
           FROM activities WHERE timestamp >= ? AND satisfaction IS NOT NULL""",
        (cutoff,),
    ).fetchone()

    # Most active day
    busiest = db.execute(
        """SELECT DATE(timestamp) as day, COUNT(*) as count
           FROM activities WHERE timestamp >= ?
           GROUP BY DATE(timestamp) ORDER BY count DESC LIMIT 1""",
        (cutoff,),
    ).fetchone()

    db.close()

    result = {
        "period_days": args.days,
        "total_activities": total,
        "by_task_type": {r["task_type"]: r["count"] for r in task_rows},
        "satisfaction": {
            "average": round(sat_row["avg"], 2) if sat_row["avg"] else None,
            "rated_count": sat_row["rated"],
            "min": sat_row["min"],
            "max": sat_row["max"],
        },
        "busiest_day": dict(busiest) if busiest else None,
    }

    print(json.dumps(result, indent=2))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Activity log for Jimbo")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # log
    log_p = subparsers.add_parser("log", help="Log an activity")
    log_p.add_argument("--task", required=True, help=f"Task type: {', '.join(VALID_TASK_TYPES)}")
    log_p.add_argument("--description", required=True, help="What happened")
    log_p.add_argument("--outcome", default=None, help="Result or outcome")
    log_p.add_argument("--model", default=None, help="Model used (if applicable)")
    log_p.add_argument("--cost-id", default=None, help="Link to cost entry (cost_xxxxxxxx)")
    log_p.add_argument("--notes", default=None, help="Additional notes")

    # rate
    rate_p = subparsers.add_parser("rate", help="Rate an activity")
    rate_p.add_argument("id", help="Activity ID (act_xxxxxxxx)")
    rate_p.add_argument("--satisfaction", type=int, required=True, help="Satisfaction score 1-5")
    rate_p.add_argument("--notes", default=None, help="Rating notes")

    # list
    list_p = subparsers.add_parser("list", help="List activities")
    list_p.add_argument("--task", default=None, help="Filter by task type")
    list_p.add_argument("--days", type=int, default=None, help="Only last N days")
    list_p.add_argument("--limit", type=int, default=50, help="Max results (default: 50)")

    # export
    export_p = subparsers.add_parser("export", help="Export activity data as JSON")
    export_p.add_argument("--days", type=int, default=30, help="Number of days to export (default: 30)")
    export_p.add_argument("--format", default="json", help="Output format (only json supported)")

    # stats
    stats_p = subparsers.add_parser("stats", help="Summary statistics")
    stats_p.add_argument("--days", type=int, required=True, help="Number of days to summarise")

    args = parser.parse_args()

    commands = {
        "log": cmd_log,
        "rate": cmd_rate,
        "list": cmd_list,
        "export": cmd_export,
        "stats": cmd_stats,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
