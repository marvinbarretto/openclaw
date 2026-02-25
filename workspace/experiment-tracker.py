#!/usr/bin/env python3
"""
Experiment tracker for Jimbo's orchestrator.

SQLite-backed logging of every worker run — task, model, tokens, cost,
quality scores, conductor ratings, user ratings. Supports comparison
queries across models and time periods.

Python 3.11 stdlib only. No pip dependencies.

Usage:
    python3 experiment-tracker.py log --task email-triage --model gemini-2.5-flash --input-tokens 5000 --output-tokens 500
    python3 experiment-tracker.py log --task newsletter-deep-read --model claude-haiku-4.5 --input-tokens 40000 --output-tokens 3000 --quality '{"cited_articles": true}'
    python3 experiment-tracker.py runs --task email-triage --last 10
    python3 experiment-tracker.py compare --task newsletter-deep-read --days 14
    python3 experiment-tracker.py rate <run_id> --user-rating 8 --notes "good briefing"
    python3 experiment-tracker.py export --days 30
    python3 experiment-tracker.py stats --days 7
"""

import argparse
import datetime
import hashlib
import json
import os
import sqlite3
import sys
import uuid

_script_dir = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get(
    "EXPERIMENT_TRACKER_DB",
    os.path.join(_script_dir, "experiment-tracker.db"),
)

# Cost rates per 1M tokens (USD)
COST_RATES = {
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.5-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-2.5-pro": {"input": 1.25, "output": 5.00},
    "claude-haiku-4.5": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4.6": {"input": 3.00, "output": 15.00},
    "claude-opus-4.6": {"input": 15.00, "output": 75.00},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    parent_run_id TEXT,
    timestamp TEXT NOT NULL,
    model TEXT NOT NULL,
    config_hash TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    duration_ms INTEGER,
    input_summary TEXT,
    output_summary TEXT,
    quality_scores TEXT,
    conductor_rating INTEGER,
    user_rating INTEGER,
    user_notes TEXT,
    conductor_reasoning TEXT,
    config_snapshot TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_timestamp ON runs(timestamp);
CREATE INDEX IF NOT EXISTS idx_runs_task_id ON runs(task_id);
CREATE INDEX IF NOT EXISTS idx_runs_model ON runs(model);
CREATE INDEX IF NOT EXISTS idx_runs_parent ON runs(parent_run_id);

CREATE TABLE IF NOT EXISTS games (
    game_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS game_rounds (
    round_id TEXT PRIMARY KEY,
    game_id TEXT NOT NULL,
    run_id TEXT,
    timestamp TEXT NOT NULL,
    jimbo_play TEXT,
    outcome TEXT,
    jimbo_score INTEGER,
    marvin_score INTEGER,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_rounds_game ON game_rounds(game_id);
CREATE INDEX IF NOT EXISTS idx_rounds_timestamp ON game_rounds(timestamp);
"""


def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def generate_run_id():
    return "run_" + uuid.uuid4().hex[:8]


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def estimate_cost(model, input_tokens, output_tokens):
    rates = COST_RATES.get(model)
    if not rates:
        return 0.0
    input_cost = (input_tokens / 1_000_000) * rates["input"]
    output_cost = (output_tokens / 1_000_000) * rates["output"]
    return round(input_cost + output_cost, 6)


def config_hash(task_id):
    config_path = os.path.join(_script_dir, "tasks", f"{task_id}.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            content = f.read()
        return hashlib.sha256(content.encode()).hexdigest()[:12]
    return None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_log(args):
    db = get_db()
    run_id = generate_run_id()
    cost = estimate_cost(args.model, args.input_tokens, args.output_tokens)
    c_hash = config_hash(args.task)

    db.execute(
        """INSERT INTO runs
           (run_id, task_id, parent_run_id, timestamp, model, config_hash,
            input_tokens, output_tokens, cost_usd, duration_ms,
            input_summary, output_summary, quality_scores,
            conductor_rating, conductor_reasoning, config_snapshot)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            run_id, args.task, getattr(args, "parent_run", None),
            now_iso(), args.model, c_hash,
            args.input_tokens, args.output_tokens, cost,
            getattr(args, "duration", None),
            getattr(args, "input_summary", None),
            getattr(args, "output_summary", None),
            getattr(args, "quality", None),
            getattr(args, "conductor_rating", None),
            getattr(args, "conductor_reasoning", None),
            None,
        ),
    )
    db.commit()
    db.close()

    print(json.dumps({"status": "ok", "run_id": run_id, "cost_usd": cost}))


def cmd_runs(args):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM runs WHERE task_id = ? ORDER BY timestamp DESC LIMIT ?",
        (args.task, args.last),
    ).fetchall()
    db.close()
    print(json.dumps([dict(r) for r in rows], indent=2))


def cmd_compare(args):
    db = get_db()
    cutoff = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=args.days)
    ).isoformat()

    query = """
        SELECT model,
               COUNT(*) as run_count,
               ROUND(AVG(conductor_rating), 1) as avg_conductor_rating,
               ROUND(AVG(user_rating), 1) as avg_user_rating,
               ROUND(SUM(cost_usd), 4) as total_cost,
               ROUND(AVG(cost_usd), 4) as avg_cost_per_run,
               ROUND(AVG(input_tokens), 0) as avg_input_tokens,
               ROUND(AVG(output_tokens), 0) as avg_output_tokens
        FROM runs
        WHERE task_id = ? AND timestamp >= ?
    """
    params = [args.task, cutoff]

    if args.models:
        model_list = [m.strip() for m in args.models.split(",")]
        placeholders = ",".join("?" * len(model_list))
        query += f" AND model IN ({placeholders})"
        params.extend(model_list)

    query += " GROUP BY model ORDER BY avg_conductor_rating DESC"
    rows = db.execute(query, params).fetchall()
    db.close()
    print(json.dumps({
        "task": args.task, "days": args.days,
        "models": [dict(r) for r in rows],
    }, indent=2))


def cmd_rate(args):
    db = get_db()
    row = db.execute("SELECT run_id FROM runs WHERE run_id = ?", (args.run_id,)).fetchone()
    if not row:
        print(json.dumps({"status": "error", "message": f"Run {args.run_id} not found"}))
        db.close()
        sys.exit(1)

    db.execute(
        "UPDATE runs SET user_rating = ?, user_notes = ? WHERE run_id = ?",
        (args.user_rating, args.notes, args.run_id),
    )
    db.commit()
    db.close()
    print(json.dumps({"status": "ok", "run_id": args.run_id, "user_rating": args.user_rating}))


def cmd_stats(args):
    db = get_db()
    cutoff = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=args.days)
    ).isoformat()

    total = db.execute(
        """SELECT COUNT(*) as runs, ROUND(SUM(cost_usd), 4) as total_cost,
                  ROUND(AVG(conductor_rating), 1) as avg_conductor,
                  ROUND(AVG(user_rating), 1) as avg_user
           FROM runs WHERE timestamp >= ?""",
        (cutoff,),
    ).fetchone()

    by_task = db.execute(
        """SELECT task_id, COUNT(*) as runs, ROUND(SUM(cost_usd), 4) as cost,
                  ROUND(AVG(conductor_rating), 1) as avg_quality
           FROM runs WHERE timestamp >= ?
           GROUP BY task_id ORDER BY runs DESC""",
        (cutoff,),
    ).fetchall()

    by_model = db.execute(
        """SELECT model, COUNT(*) as runs, ROUND(SUM(cost_usd), 4) as cost,
                  ROUND(AVG(conductor_rating), 1) as avg_quality
           FROM runs WHERE timestamp >= ?
           GROUP BY model ORDER BY cost DESC""",
        (cutoff,),
    ).fetchall()

    db.close()
    print(json.dumps({
        "period_days": args.days,
        "totals": dict(total),
        "by_task": [dict(r) for r in by_task],
        "by_model": [dict(r) for r in by_model],
    }, indent=2))


def cmd_export(args):
    db = get_db()
    cutoff = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=args.days)
    ).isoformat()

    rows = db.execute(
        "SELECT * FROM runs WHERE timestamp >= ? ORDER BY timestamp DESC",
        (cutoff,),
    ).fetchall()

    stats = db.execute(
        """SELECT task_id, model,
                  COUNT(*) as runs, ROUND(SUM(cost_usd), 4) as cost,
                  ROUND(AVG(conductor_rating), 1) as avg_conductor,
                  ROUND(AVG(user_rating), 1) as avg_user
           FROM runs WHERE timestamp >= ?
           GROUP BY task_id, model""",
        (cutoff,),
    ).fetchall()

    db.close()
    print(json.dumps({
        "generated_at": now_iso(),
        "period_days": args.days,
        "summary": [dict(s) for s in stats],
        "runs": [dict(r) for r in rows],
    }, indent=2))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Experiment tracker for Jimbo's orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # log
    log_p = subparsers.add_parser("log", help="Log a worker run")
    log_p.add_argument("--task", required=True, help="Task ID (e.g. email-triage)")
    log_p.add_argument("--model", required=True, help="Model used")
    log_p.add_argument("--input-tokens", type=int, required=True)
    log_p.add_argument("--output-tokens", type=int, required=True)
    log_p.add_argument("--parent-run", default=None, help="Parent run ID")
    log_p.add_argument("--duration", type=int, default=None, help="Duration in ms")
    log_p.add_argument("--input-summary", default=None)
    log_p.add_argument("--output-summary", default=None)
    log_p.add_argument("--quality", default=None, help="JSON quality scores")
    log_p.add_argument("--conductor-rating", type=int, default=None, help="1-10")
    log_p.add_argument("--conductor-reasoning", default=None, help="JSON reasoning")

    # runs
    runs_p = subparsers.add_parser("runs", help="List recent runs for a task")
    runs_p.add_argument("--task", required=True)
    runs_p.add_argument("--last", type=int, default=10)

    # compare
    cmp_p = subparsers.add_parser("compare", help="Compare models for a task")
    cmp_p.add_argument("--task", required=True)
    cmp_p.add_argument("--days", type=int, default=14)
    cmp_p.add_argument("--models", default=None, help="Comma-separated model names")

    # rate
    rate_p = subparsers.add_parser("rate", help="Rate a run")
    rate_p.add_argument("run_id", help="Run ID to rate")
    rate_p.add_argument("--user-rating", type=int, required=True, help="1-10")
    rate_p.add_argument("--notes", default=None)

    # stats
    stats_p = subparsers.add_parser("stats", help="Summary stats")
    stats_p.add_argument("--days", type=int, default=7)

    # export
    export_p = subparsers.add_parser("export", help="Export for dashboard")
    export_p.add_argument("--days", type=int, default=30)

    args = parser.parse_args()
    commands = {
        "log": cmd_log, "runs": cmd_runs, "compare": cmd_compare,
        "rate": cmd_rate, "stats": cmd_stats, "export": cmd_export,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
