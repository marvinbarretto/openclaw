#!/usr/bin/env python3
"""
Cost tracker for Jimbo's sandbox.

SQLite-backed logging of API costs per interaction. Tracks provider, model,
task type, token counts, and estimated USD cost. Supports budgets and alerts.

Python 3.11 stdlib only. No pip dependencies.

Usage:
    python3 cost-tracker.py log --provider google --model gemini-2.5-flash --task heartbeat --input-tokens 500 --output-tokens 200
    python3 cost-tracker.py summary --days 1
    python3 cost-tracker.py summary --days 7
    python3 cost-tracker.py export --days 30 --format json
    python3 cost-tracker.py budget --set 10
    python3 cost-tracker.py budget --check
"""

import argparse
import datetime
import json
import os
import sqlite3
import sys
import uuid

_script_dir = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_script_dir, "cost-tracker.db")

# Cost rates per 1M tokens (USD)
COST_RATES = {
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "claude-haiku-4.5": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4.6": {"input": 3.00, "output": 15.00},
    "claude-opus-4.6": {"input": 15.00, "output": 75.00},
}

VALID_TASK_TYPES = (
    "heartbeat", "briefing", "chat", "research", "blog",
    "email-check", "nudge", "own-project", "digest", "day-planner",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS costs (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    task_type TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    estimated_cost REAL NOT NULL,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_costs_timestamp ON costs(timestamp);
CREATE INDEX IF NOT EXISTS idx_costs_task_type ON costs(task_type);
CREATE INDEX IF NOT EXISTS idx_costs_model ON costs(model);

CREATE TABLE IF NOT EXISTS budgets (
    id TEXT PRIMARY KEY,
    monthly_limit REAL NOT NULL,
    alert_threshold REAL NOT NULL DEFAULT 0.8,
    updated TEXT NOT NULL
);
"""


def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def generate_id():
    return "cost_" + uuid.uuid4().hex[:8]


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def estimate_cost(model, input_tokens, output_tokens):
    """Calculate estimated cost in USD from token counts."""
    rates = COST_RATES.get(model)
    if not rates:
        return 0.0
    input_cost = (input_tokens / 1_000_000) * rates["input"]
    output_cost = (output_tokens / 1_000_000) * rates["output"]
    return round(input_cost + output_cost, 6)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_log(args):
    """Log a cost entry."""
    db = get_db()

    cost_id = generate_id()
    cost = args.cost if args.cost is not None else estimate_cost(
        args.model, args.input_tokens, args.output_tokens
    )

    db.execute(
        """INSERT INTO costs
           (id, timestamp, provider, model, task_type, input_tokens, output_tokens, estimated_cost, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            cost_id,
            now_iso(),
            args.provider,
            args.model,
            args.task,
            args.input_tokens,
            args.output_tokens,
            cost,
            args.notes,
        ),
    )
    db.commit()
    db.close()

    print(json.dumps({
        "status": "ok",
        "id": cost_id,
        "estimated_cost": cost,
    }))


def cmd_summary(args):
    """Show cost summary for the last N days."""
    db = get_db()
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=args.days)).isoformat()

    # Total
    total_row = db.execute(
        "SELECT COALESCE(SUM(estimated_cost), 0) as total, COUNT(*) as count FROM costs WHERE timestamp >= ?",
        (cutoff,),
    ).fetchone()

    # By model
    model_rows = db.execute(
        """SELECT model, SUM(estimated_cost) as total, SUM(input_tokens) as input_tokens,
                  SUM(output_tokens) as output_tokens, COUNT(*) as count
           FROM costs WHERE timestamp >= ? GROUP BY model ORDER BY total DESC""",
        (cutoff,),
    ).fetchall()

    # By task type
    task_rows = db.execute(
        """SELECT task_type, SUM(estimated_cost) as total, COUNT(*) as count
           FROM costs WHERE timestamp >= ? GROUP BY task_type ORDER BY total DESC""",
        (cutoff,),
    ).fetchall()

    # By day
    day_rows = db.execute(
        """SELECT DATE(timestamp) as day, SUM(estimated_cost) as total, COUNT(*) as count
           FROM costs WHERE timestamp >= ? GROUP BY DATE(timestamp) ORDER BY day DESC""",
        (cutoff,),
    ).fetchall()

    db.close()

    result = {
        "period_days": args.days,
        "total_cost": round(total_row["total"], 4),
        "total_interactions": total_row["count"],
        "by_model": [dict(r) for r in model_rows],
        "by_task_type": [dict(r) for r in task_rows],
        "by_day": [dict(r) for r in day_rows],
    }

    print(json.dumps(result, indent=2))


def cmd_export(args):
    """Export cost data as JSON for dashboard consumption."""
    db = get_db()
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=args.days)).isoformat()

    rows = db.execute(
        "SELECT * FROM costs WHERE timestamp >= ? ORDER BY timestamp DESC",
        (cutoff,),
    ).fetchall()

    # Also include summary stats
    total_row = db.execute(
        "SELECT COALESCE(SUM(estimated_cost), 0) as total FROM costs WHERE timestamp >= ?",
        (cutoff,),
    ).fetchone()

    # Monthly total (current calendar month)
    month_start = datetime.date.today().replace(day=1).isoformat()
    month_row = db.execute(
        "SELECT COALESCE(SUM(estimated_cost), 0) as total FROM costs WHERE timestamp >= ?",
        (month_start,),
    ).fetchone()

    # Budget
    budget_row = db.execute(
        "SELECT monthly_limit, alert_threshold FROM budgets ORDER BY updated DESC LIMIT 1"
    ).fetchone()

    # By day (last 30 days)
    day_rows = db.execute(
        """SELECT DATE(timestamp) as day, SUM(estimated_cost) as total, COUNT(*) as count,
                  SUM(input_tokens) as input_tokens, SUM(output_tokens) as output_tokens
           FROM costs WHERE timestamp >= ? GROUP BY DATE(timestamp) ORDER BY day""",
        (cutoff,),
    ).fetchall()

    # By model
    model_rows = db.execute(
        """SELECT model, SUM(estimated_cost) as total, COUNT(*) as count
           FROM costs WHERE timestamp >= ? GROUP BY model ORDER BY total DESC""",
        (cutoff,),
    ).fetchall()

    # By task type
    task_rows = db.execute(
        """SELECT task_type, SUM(estimated_cost) as total, COUNT(*) as count
           FROM costs WHERE timestamp >= ? GROUP BY task_type ORDER BY total DESC""",
        (cutoff,),
    ).fetchall()

    db.close()

    export = {
        "generated_at": now_iso(),
        "period_days": args.days,
        "total_cost": round(total_row["total"], 4),
        "monthly_cost": round(month_row["total"], 4),
        "budget": {
            "monthly_limit": budget_row["monthly_limit"] if budget_row else None,
            "alert_threshold": budget_row["alert_threshold"] if budget_row else None,
        },
        "by_day": [dict(r) for r in day_rows],
        "by_model": [dict(r) for r in model_rows],
        "by_task_type": [dict(r) for r in task_rows],
        "entries": [dict(r) for r in rows],
    }

    print(json.dumps(export, indent=2))


def cmd_budget(args):
    """Set or check monthly budget."""
    db = get_db()

    if args.set is not None:
        budget_id = "budget_" + uuid.uuid4().hex[:8]
        threshold = args.threshold if args.threshold is not None else 0.8
        db.execute(
            "INSERT INTO budgets (id, monthly_limit, alert_threshold, updated) VALUES (?, ?, ?, ?)",
            (budget_id, args.set, threshold, now_iso()),
        )
        db.commit()
        db.close()
        print(json.dumps({
            "status": "ok",
            "monthly_limit": args.set,
            "alert_threshold": threshold,
        }))
        return

    if args.check:
        budget_row = db.execute(
            "SELECT monthly_limit, alert_threshold FROM budgets ORDER BY updated DESC LIMIT 1"
        ).fetchone()

        if not budget_row:
            print(json.dumps({"status": "error", "message": "No budget set. Use --set to create one."}))
            db.close()
            sys.exit(1)

        month_start = datetime.date.today().replace(day=1).isoformat()
        month_row = db.execute(
            "SELECT COALESCE(SUM(estimated_cost), 0) as total FROM costs WHERE timestamp >= ?",
            (month_start,),
        ).fetchone()

        limit = budget_row["monthly_limit"]
        spent = round(month_row["total"], 4)
        remaining = round(limit - spent, 4)
        pct = round((spent / limit) * 100, 1) if limit > 0 else 0
        alert = pct >= (budget_row["alert_threshold"] * 100)

        db.close()

        result = {
            "monthly_limit": limit,
            "spent": spent,
            "remaining": remaining,
            "percent_used": pct,
            "alert": alert,
            "days_remaining": (datetime.date.today().replace(day=1) + datetime.timedelta(days=32)).replace(day=1) - datetime.date.today(),
        }
        # days_remaining is a timedelta, convert
        result["days_remaining"] = result["days_remaining"].days

        print(json.dumps(result, indent=2))
        return

    print(json.dumps({"status": "error", "message": "Use --set <amount> or --check"}))
    sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Cost tracker for Jimbo")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # log
    log_p = subparsers.add_parser("log", help="Log an API interaction cost")
    log_p.add_argument("--provider", required=True, help="API provider (google, anthropic, openrouter)")
    log_p.add_argument("--model", required=True, help="Model name (gemini-2.5-flash, claude-haiku-4.5)")
    log_p.add_argument("--task", required=True, help=f"Task type: {', '.join(VALID_TASK_TYPES)}")
    log_p.add_argument("--input-tokens", type=int, required=True, help="Input token count")
    log_p.add_argument("--output-tokens", type=int, required=True, help="Output token count")
    log_p.add_argument("--cost", type=float, default=None, help="Override estimated cost (USD)")
    log_p.add_argument("--notes", default=None, help="Optional notes about this interaction")

    # summary
    summary_p = subparsers.add_parser("summary", help="Cost summary for last N days")
    summary_p.add_argument("--days", type=int, required=True, help="Number of days to summarise")

    # export
    export_p = subparsers.add_parser("export", help="Export cost data as JSON")
    export_p.add_argument("--days", type=int, default=30, help="Number of days to export (default: 30)")
    export_p.add_argument("--format", default="json", help="Output format (only json supported)")

    # budget
    budget_p = subparsers.add_parser("budget", help="Set or check monthly budget")
    budget_p.add_argument("--set", type=float, default=None, help="Set monthly budget in USD")
    budget_p.add_argument("--threshold", type=float, default=None, help="Alert threshold 0-1 (default: 0.8)")
    budget_p.add_argument("--check", action="store_true", help="Check current spending vs budget")

    args = parser.parse_args()

    commands = {
        "log": cmd_log,
        "summary": cmd_summary,
        "export": cmd_export,
        "budget": cmd_budget,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
