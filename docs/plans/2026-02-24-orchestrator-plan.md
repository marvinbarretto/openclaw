# Orchestrator-Conductor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build Jimbo's orchestrator foundation — experiment tracker, worker infrastructure, email triage + newsletter reader workers — so the morning briefing delegates bulk work to cheaper models and every run is tracked.

**Architecture:** Python stdlib-only scripts in `workspace/`. Workers call model APIs directly from the Docker sandbox using env vars already present (GOOGLE_AI_API_KEY, ANTHROPIC_API_KEY). Experiment tracker is SQLite-backed, same pattern as cost-tracker.py. Task configs are JSON files. Workers return structured JSON; Jimbo synthesises.

**Tech Stack:** Python 3.11 (stdlib only), SQLite, Google AI Generative Language API, Anthropic Messages API. Deployed to VPS sandbox via workspace-push.sh.

**Conventions:**
- All Python scripts: stdlib only, no pip
- All scripts live in `workspace/` (pushed to VPS sandbox at `/workspace/`)
- Same coding patterns as `workspace/cost-tracker.py` (argparse CLI, SQLite, JSON output)
- Tests use Python unittest (stdlib) in `workspace/tests/`
- Task configs in `workspace/tasks/`
- Worker scripts in `workspace/workers/`

**Reference files:**
- `workspace/cost-tracker.py` — pattern to follow for SQLite + CLI
- `workspace/activity-log.py` — pattern to follow for logging
- `workspace/gmail-helper.py` — reference for how email digest JSON is structured
- `skills/sift-digest/SKILL.md` — the skill that will be updated to use workers
- `docs/plans/2026-02-24-orchestrator-design.md` — full design doc
- `decisions/029-orchestrator-conductor-pattern.md` — ADR with context

---

### Task 1: Experiment Tracker — Schema and Log Command

The foundation everything else depends on. Start with just the SQLite schema and the `log` command.

**Files:**
- Create: `workspace/experiment-tracker.py`
- Create: `workspace/tests/test_experiment_tracker.py`

**Step 1: Write the failing test**

```python
# workspace/tests/test_experiment_tracker.py
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "experiment-tracker.py")


class TestLogCommand(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "experiment-tracker.db")
        self.env = {**os.environ, "EXPERIMENT_TRACKER_DB": self.db_path}

    def test_log_creates_run_and_returns_json(self):
        result = subprocess.run(
            [
                sys.executable, SCRIPT, "log",
                "--task", "email-triage",
                "--model", "gemini-2.5-flash",
                "--input-tokens", "5000",
                "--output-tokens", "500",
                "--quality", '{"cited_articles": true}',
            ],
            capture_output=True, text=True, env=self.env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["status"], "ok")
        self.assertIn("run_id", data)
        self.assertIn("cost_usd", data)
        self.assertGreater(data["cost_usd"], 0)

    def test_log_writes_to_database(self):
        subprocess.run(
            [
                sys.executable, SCRIPT, "log",
                "--task", "newsletter-deep-read",
                "--model", "claude-haiku-4.5",
                "--input-tokens", "40000",
                "--output-tokens", "3000",
            ],
            capture_output=True, text=True, env=self.env,
        )
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM runs").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["task_id"], "newsletter-deep-read")
        self.assertEqual(row["model"], "claude-haiku-4.5")
        self.assertEqual(row["input_tokens"], 40000)
        db.close()


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/marvinbarretto/development/openclaw && python3 -m pytest workspace/tests/test_experiment_tracker.py -v`
Expected: FAIL (script doesn't exist)

**Step 3: Write minimal implementation**

```python
# workspace/experiment-tracker.py
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
    python3 experiment-tracker.py export --days 30 --format json
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

# Cost rates per 1M tokens (USD) — same as cost-tracker.py
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
    """Hash the task config file for change tracking."""
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
    query = "SELECT * FROM runs WHERE task_id = ? ORDER BY timestamp DESC LIMIT ?"
    rows = db.execute(query, (args.task, args.last)).fetchall()
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
    print(json.dumps({"task": args.task, "days": args.days, "models": [dict(r) for r in rows]}, indent=2))


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
    log_p.add_argument("--parent-run", default=None, help="Parent run ID (for conductor linking)")
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
    cmp_p.add_argument("--models", default=None, help="Comma-separated model names to compare")

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
    export_p.add_argument("--format", default="json")

    args = parser.parse_args()
    commands = {
        "log": cmd_log, "runs": cmd_runs, "compare": cmd_compare,
        "rate": cmd_rate, "stats": cmd_stats, "export": cmd_export,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/marvinbarretto/development/openclaw && python3 -m pytest workspace/tests/test_experiment_tracker.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add workspace/experiment-tracker.py workspace/tests/test_experiment_tracker.py
git commit -m "feat: add experiment tracker — SQLite-backed run logging with CLI"
```

---

### Task 2: Experiment Tracker — Compare, Rate, Stats, Export Commands

Add the remaining CLI commands and their tests.

**Files:**
- Modify: `workspace/tests/test_experiment_tracker.py`
- (experiment-tracker.py already has all commands from Task 1)

**Step 1: Write the failing tests**

Add to `workspace/tests/test_experiment_tracker.py`:

```python
class TestCompareCommand(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "experiment-tracker.db")
        self.env = {**os.environ, "EXPERIMENT_TRACKER_DB": self.db_path}
        # Seed two runs with different models
        for model in ["gemini-2.5-flash", "claude-haiku-4.5"]:
            subprocess.run(
                [sys.executable, SCRIPT, "log",
                 "--task", "email-triage", "--model", model,
                 "--input-tokens", "5000", "--output-tokens", "500",
                 "--conductor-rating", "7"],
                capture_output=True, text=True, env=self.env,
            )

    def test_compare_returns_both_models(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "compare",
             "--task", "email-triage", "--days", "1"],
            capture_output=True, text=True, env=self.env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(len(data["models"]), 2)


class TestRateCommand(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "experiment-tracker.db")
        self.env = {**os.environ, "EXPERIMENT_TRACKER_DB": self.db_path}
        result = subprocess.run(
            [sys.executable, SCRIPT, "log",
             "--task", "email-triage", "--model", "gemini-2.5-flash",
             "--input-tokens", "5000", "--output-tokens", "500"],
            capture_output=True, text=True, env=self.env,
        )
        self.run_id = json.loads(result.stdout)["run_id"]

    def test_rate_updates_run(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "rate", self.run_id,
             "--user-rating", "8", "--notes", "good stuff"],
            capture_output=True, text=True, env=self.env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["user_rating"], 8)

        # Verify in DB
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT user_rating, user_notes FROM runs WHERE run_id = ?", (self.run_id,)).fetchone()
        self.assertEqual(row["user_rating"], 8)
        self.assertEqual(row["user_notes"], "good stuff")
        db.close()

    def test_rate_nonexistent_run_fails(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "rate", "run_nonexistent",
             "--user-rating", "5"],
            capture_output=True, text=True, env=self.env,
        )
        self.assertNotEqual(result.returncode, 0)


class TestStatsCommand(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "experiment-tracker.db")
        self.env = {**os.environ, "EXPERIMENT_TRACKER_DB": self.db_path}
        subprocess.run(
            [sys.executable, SCRIPT, "log",
             "--task", "email-triage", "--model", "gemini-2.5-flash",
             "--input-tokens", "5000", "--output-tokens", "500"],
            capture_output=True, text=True, env=self.env,
        )

    def test_stats_returns_summary(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "stats", "--days", "1"],
            capture_output=True, text=True, env=self.env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["totals"]["runs"], 1)
        self.assertGreater(data["totals"]["total_cost"], 0)
```

**Step 2: Run tests to verify they pass** (they should — implementation already exists from Task 1)

Run: `python3 -m pytest workspace/tests/test_experiment_tracker.py -v`
Expected: PASS (all tests)

**Step 3: Commit**

```bash
git add workspace/tests/test_experiment_tracker.py
git commit -m "test: add compare, rate, stats tests for experiment tracker"
```

---

### Task 3: Task Registry

Create the JSON config files that define each task.

**Files:**
- Create: `workspace/tasks/email-triage.json`
- Create: `workspace/tasks/newsletter-deep-read.json`
- Create: `workspace/tasks/briefing-synthesis.json`
- Create: `workspace/tasks/heartbeat.json`

**Step 1: Create task config files**

```json
// workspace/tasks/email-triage.json
{
  "task_id": "email-triage",
  "description": "Bulk classify emails from digest, rank by relevance, return shortlist",
  "default_model": "gemini-2.5-flash",
  "fallback_model": "gemini-2.5-flash-lite",
  "provider": "google",
  "evaluation": {
    "method": "conductor-review",
    "criteria": [
      "shortlist_contains_newsletters",
      "shortlist_excludes_obvious_junk",
      "reasons_reference_context_files",
      "time_sensitive_items_flagged"
    ]
  },
  "budget_ceiling_per_run": 0.02,
  "batch_size": 50,
  "context_files": ["INTERESTS.md", "TASTE.md"],
  "output_schema": {
    "shortlist": [
      {
        "gmail_id": "string",
        "rank": "integer",
        "category": "newsletter|event|personal|deal|notification|other",
        "reason": "string",
        "time_sensitive": "boolean",
        "deadline": "ISO date or null"
      }
    ],
    "stats": {
      "total_reviewed": "integer",
      "shortlisted": "integer",
      "skipped": "integer"
    }
  }
}
```

```json
// workspace/tasks/newsletter-deep-read.json
{
  "task_id": "newsletter-deep-read",
  "description": "Deep read shortlisted newsletters, extract specific articles, links, events, prices, and gems matching Marvin's context",
  "default_model": "claude-haiku-4.5",
  "fallback_model": "gemini-2.5-flash",
  "provider": "anthropic",
  "evaluation": {
    "method": "conductor-review",
    "criteria": [
      "cited_specific_articles",
      "extracted_links",
      "linked_to_context_files",
      "surfaced_surprises",
      "prices_and_dates_included"
    ]
  },
  "budget_ceiling_per_run": 0.08,
  "batch_size": 15,
  "context_files": ["INTERESTS.md", "TASTE.md", "PRIORITIES.md", "GOALS.md"],
  "output_schema": {
    "gems": [
      {
        "gmail_id": "string",
        "source": "string",
        "title": "string",
        "why": "string — connection to context",
        "links": ["url"],
        "time_sensitive": "boolean",
        "deadline": "ISO date or null",
        "price": "string or null",
        "surprise_candidate": "boolean"
      }
    ],
    "stats": {
      "newsletters_read": "integer",
      "gems_extracted": "integer",
      "links_found": "integer"
    }
  }
}
```

```json
// workspace/tasks/briefing-synthesis.json
{
  "task_id": "briefing-synthesis",
  "description": "Conductor task — Jimbo synthesises worker outputs into the morning briefing",
  "default_model": "claude-haiku-4.5",
  "fallback_model": null,
  "provider": "openclaw",
  "evaluation": {
    "method": "user-rating",
    "criteria": [
      "followed_presentation_format",
      "time_sensitive_items_first",
      "surprise_attempt_included",
      "concise_and_scannable"
    ]
  },
  "budget_ceiling_per_run": 0.10,
  "notes": "This task is performed by Jimbo himself (conductor), not a worker script. Logged for tracking."
}
```

```json
// workspace/tasks/heartbeat.json
{
  "task_id": "heartbeat",
  "description": "Run periodic system checks — digest freshness, token validity, cost budget",
  "default_model": "gemini-2.5-flash",
  "fallback_model": null,
  "provider": "openclaw",
  "evaluation": {
    "method": "automated",
    "criteria": [
      "all_checks_completed",
      "issues_reported_accurately"
    ]
  },
  "budget_ceiling_per_run": 0.005,
  "notes": "Low-complexity, high-frequency task. Flash is fine."
}
```

**Step 2: Verify config_hash works with the registry**

Run: `cd /Users/marvinbarretto/development/openclaw && python3 -c "
import hashlib, json
with open('workspace/tasks/email-triage.json') as f:
    content = f.read()
    json.loads(content)  # validate JSON
    print('Hash:', hashlib.sha256(content.encode()).hexdigest()[:12])
    print('Valid JSON: OK')
"`
Expected: Hash and "Valid JSON: OK"

**Step 3: Commit**

```bash
git add workspace/tasks/
git commit -m "feat: add task registry — config files for email-triage, newsletter-read, briefing, heartbeat"
```

---

### Task 4: Base Worker — API Client Infrastructure

The shared base that all workers inherit. Handles API calls to Google AI and Anthropic, token counting, experiment logging.

**Files:**
- Create: `workspace/workers/__init__.py` (empty)
- Create: `workspace/workers/base_worker.py`
- Create: `workspace/tests/test_base_worker.py`

**Step 1: Write the failing test**

```python
# workspace/tests/test_base_worker.py
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Add workspace to path so we can import workers
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from workers.base_worker import BaseWorker, load_task_config, call_google_ai, call_anthropic


class TestLoadTaskConfig(unittest.TestCase):
    def test_loads_email_triage_config(self):
        config = load_task_config("email-triage")
        self.assertEqual(config["task_id"], "email-triage")
        self.assertEqual(config["default_model"], "gemini-2.5-flash")

    def test_missing_config_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_task_config("nonexistent-task")


class TestBaseWorker(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "experiment-tracker.db")
        os.environ["EXPERIMENT_TRACKER_DB"] = self.db_path

    def tearDown(self):
        os.environ.pop("EXPERIMENT_TRACKER_DB", None)

    def test_worker_init_loads_config(self):
        worker = BaseWorker("email-triage")
        self.assertEqual(worker.task_id, "email-triage")
        self.assertEqual(worker.config["default_model"], "gemini-2.5-flash")
        self.assertIsNotNone(worker.run_id)

    def test_worker_log_run_writes_to_tracker(self):
        import sqlite3
        worker = BaseWorker("email-triage")
        worker.log_run(
            model="gemini-2.5-flash",
            input_tokens=5000,
            output_tokens=500,
            input_summary="200 emails",
            output_summary="30 shortlisted",
        )
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM runs WHERE run_id = ?", (worker.run_id,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["task_id"], "email-triage")
        db.close()


class TestApiClients(unittest.TestCase):
    @patch("workers.base_worker.urllib.request.urlopen")
    def test_call_google_ai_sends_request(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "hello"}]}}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = call_google_ai("test prompt", model="gemini-2.5-flash", api_key="fake-key")
        self.assertEqual(result["text"], "hello")
        self.assertEqual(result["input_tokens"], 10)
        self.assertEqual(result["output_tokens"], 5)

    @patch("workers.base_worker.urllib.request.urlopen")
    def test_call_anthropic_sends_request(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "content": [{"text": "hello"}],
            "usage": {"input_tokens": 10, "output_tokens": 5}
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = call_anthropic("test prompt", model="claude-haiku-4.5", api_key="fake-key")
        self.assertEqual(result["text"], "hello")
        self.assertEqual(result["input_tokens"], 10)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest workspace/tests/test_base_worker.py -v`
Expected: FAIL (module doesn't exist)

**Step 3: Write minimal implementation**

```python
# workspace/workers/__init__.py
# Workers package
```

```python
# workspace/workers/base_worker.py
"""
Base worker for Jimbo's orchestrator.

Provides shared infrastructure: API clients for Google AI and Anthropic,
experiment tracker logging, task config loading, retry with fallback.

Python 3.11 stdlib only. No pip dependencies.
"""

import json
import os
import ssl
import subprocess
import sys
import time
import urllib.request
import urllib.error
import uuid

_workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_tasks_dir = os.path.join(_workspace_dir, "tasks")
_tracker_script = os.path.join(_workspace_dir, "experiment-tracker.py")


def load_task_config(task_id):
    """Load a task definition from the registry."""
    path = os.path.join(_tasks_dir, f"{task_id}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"No task config: {path}")
    with open(path) as f:
        return json.load(f)


def load_context_file(filename):
    """Load a context file from /workspace/context/ (sandbox) or workspace/context/ (local)."""
    for base in ["/workspace/context", os.path.join(_workspace_dir, "context")]:
        path = os.path.join(base, filename)
        if os.path.exists(path):
            with open(path) as f:
                return f.read()
    return None


def _ssl_context():
    """Create SSL context — permissive for sandbox (certs may be limited)."""
    ctx = ssl.create_default_context()
    # In sandbox, certs are mounted at /etc/ssl/certs
    # If that fails, fall back to unverified (sandbox is already isolated)
    try:
        ctx.load_default_certs()
    except Exception:
        pass
    return ctx


def call_google_ai(prompt, model="gemini-2.5-flash", api_key=None, system=None):
    """Call Google AI Generative Language API. Returns {text, input_tokens, output_tokens}."""
    api_key = api_key or os.environ.get("GOOGLE_AI_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_AI_API_KEY not set")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    contents = [{"role": "user", "parts": [{"text": prompt}]}]
    body = {"contents": contents}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    with urllib.request.urlopen(req, context=_ssl_context()) as resp:
        result = json.loads(resp.read())

    text = result["candidates"][0]["content"]["parts"][0]["text"]
    usage = result.get("usageMetadata", {})

    return {
        "text": text,
        "input_tokens": usage.get("promptTokenCount", 0),
        "output_tokens": usage.get("candidatesTokenCount", 0),
    }


def call_anthropic(prompt, model="claude-haiku-4.5", api_key=None, system=None, max_tokens=4096):
    """Call Anthropic Messages API. Returns {text, input_tokens, output_tokens}."""
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    body = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system

    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers)

    with urllib.request.urlopen(req, context=_ssl_context()) as resp:
        result = json.loads(resp.read())

    text = result["content"][0]["text"]
    usage = result.get("usage", {})

    return {
        "text": text,
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
    }


def call_model(prompt, model, provider=None, api_key=None, system=None):
    """Route to the correct API based on model name or provider."""
    if provider == "google" or model.startswith("gemini"):
        return call_google_ai(prompt, model=model, api_key=api_key, system=system)
    elif provider == "anthropic" or model.startswith("claude"):
        return call_anthropic(prompt, model=model, api_key=api_key, system=system)
    else:
        raise ValueError(f"Unknown model/provider: {model}/{provider}")


class BaseWorker:
    """Base class for all orchestrator workers."""

    def __init__(self, task_id):
        self.task_id = task_id
        self.config = load_task_config(task_id)
        self.run_id = "run_" + uuid.uuid4().hex[:8]
        self.start_time = time.time()

    def get_model(self):
        return self.config["default_model"]

    def get_fallback_model(self):
        return self.config.get("fallback_model")

    def get_context(self):
        """Load all context files specified in the task config."""
        context = {}
        for filename in self.config.get("context_files", []):
            content = load_context_file(filename)
            if content:
                context[filename] = content
        return context

    def call(self, prompt, system=None, model=None):
        """Call the model API with automatic fallback."""
        model = model or self.get_model()
        try:
            return call_model(prompt, model=model, system=system)
        except Exception as e:
            fallback = self.get_fallback_model()
            if fallback and fallback != model:
                sys.stderr.write(f"Primary model {model} failed ({e}), trying fallback {fallback}\n")
                return call_model(prompt, model=fallback, system=system)
            raise

    def log_run(self, model=None, input_tokens=0, output_tokens=0,
                input_summary=None, output_summary=None, quality_scores=None,
                conductor_rating=None, conductor_reasoning=None):
        """Log this run to the experiment tracker."""
        duration = int((time.time() - self.start_time) * 1000)
        model = model or self.get_model()

        cmd = [
            sys.executable, _tracker_script, "log",
            "--task", self.task_id,
            "--model", model,
            "--input-tokens", str(input_tokens),
            "--output-tokens", str(output_tokens),
        ]
        if duration:
            cmd.extend(["--duration", str(duration)])
        if input_summary:
            cmd.extend(["--input-summary", input_summary])
        if output_summary:
            cmd.extend(["--output-summary", output_summary])
        if quality_scores:
            cmd.extend(["--quality", json.dumps(quality_scores) if isinstance(quality_scores, dict) else quality_scores])
        if conductor_rating is not None:
            cmd.extend(["--conductor-rating", str(conductor_rating)])
        if conductor_reasoning:
            cmd.extend(["--conductor-reasoning", json.dumps(conductor_reasoning) if isinstance(conductor_reasoning, dict) else conductor_reasoning])

        # Use the same run_id — override via env
        env = {**os.environ}
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if result.returncode != 0:
            sys.stderr.write(f"Tracker log failed: {result.stderr}\n")
            return None

        return json.loads(result.stdout)

    def run(self, input_data):
        """Override in each worker. Returns structured output dict."""
        raise NotImplementedError("Subclasses must implement run()")
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest workspace/tests/test_base_worker.py -v`
Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add workspace/workers/__init__.py workspace/workers/base_worker.py workspace/tests/test_base_worker.py
git commit -m "feat: add base worker — API clients for Google AI + Anthropic, experiment logging"
```

---

### Task 5: Email Triage Worker

The first real worker. Takes the full email digest, calls Flash to classify and rank, returns a shortlist.

**Files:**
- Create: `workspace/workers/email_triage.py`
- Create: `workspace/tests/test_email_triage.py`

**Step 1: Write the failing test**

```python
# workspace/tests/test_email_triage.py
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from workers.email_triage import EmailTriageWorker, build_triage_prompt


class TestBuildTriagePrompt(unittest.TestCase):
    def test_prompt_includes_emails_and_context(self):
        emails = [
            {"gmail_id": "abc", "sender": {"name": "Test", "email": "test@example.com"},
             "subject": "Newsletter", "body_snippet": "Great article about AI", "body": "Full body here"},
        ]
        context = {"INTERESTS.md": "AI and agents", "TASTE.md": "Surprising, niche"}
        prompt = build_triage_prompt(emails, context)
        self.assertIn("Newsletter", prompt)
        self.assertIn("AI and agents", prompt)
        self.assertIn("Surprising, niche", prompt)

    def test_prompt_batches_correctly(self):
        emails = [{"gmail_id": f"id_{i}", "sender": {"name": "S", "email": "s@e.com"},
                    "subject": f"Email {i}", "body_snippet": "snip", "body": "body"}
                   for i in range(100)]
        context = {}
        prompt = build_triage_prompt(emails[:50], context)
        self.assertIn("Email 0", prompt)
        self.assertIn("Email 49", prompt)


class TestEmailTriageWorker(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ["EXPERIMENT_TRACKER_DB"] = os.path.join(self.tmpdir, "tracker.db")

    def tearDown(self):
        os.environ.pop("EXPERIMENT_TRACKER_DB", None)

    @patch("workers.base_worker.call_model")
    def test_run_returns_shortlist(self, mock_call):
        mock_call.return_value = {
            "text": json.dumps({
                "shortlist": [
                    {"gmail_id": "abc", "rank": 1, "category": "newsletter",
                     "reason": "AI content", "time_sensitive": False, "deadline": None}
                ],
                "stats": {"total_reviewed": 5, "shortlisted": 1, "skipped": 4}
            }),
            "input_tokens": 5000,
            "output_tokens": 500,
        }

        worker = EmailTriageWorker()
        digest = {
            "items": [
                {"gmail_id": "abc", "sender": {"name": "T", "email": "t@e.com"},
                 "subject": "AI News", "body_snippet": "snip", "body": "full body",
                 "date": "2026-02-24T06:00:00Z", "links": [], "labels": ["INBOX"]}
            ] * 5
        }
        result = worker.run(digest)
        self.assertIn("shortlist", result)
        self.assertEqual(len(result["shortlist"]), 1)
        self.assertEqual(result["shortlist"][0]["gmail_id"], "abc")


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest workspace/tests/test_email_triage.py -v`
Expected: FAIL (module doesn't exist)

**Step 3: Write implementation**

```python
# workspace/workers/email_triage.py
#!/usr/bin/env python3
"""
Email triage worker.

Reads the full email digest, calls a cheap model (Flash) to classify and rank
emails by relevance to Marvin's context. Returns a shortlist of ~30 worth
reading deeply.

Usage:
    python3 workers/email_triage.py --digest /workspace/email-digest.json
    python3 workers/email_triage.py --digest /workspace/email-digest.json --output /tmp/shortlist.json
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from workers.base_worker import BaseWorker


def build_triage_prompt(emails, context):
    """Build the prompt for the triage model."""
    context_block = ""
    for filename, content in context.items():
        context_block += f"\n## {filename}\n{content}\n"

    emails_block = ""
    for i, email in enumerate(emails):
        sender = email.get("sender", {})
        emails_block += f"""
--- Email {i+1} ---
Gmail ID: {email.get('gmail_id', 'unknown')}
From: {sender.get('name', '')} <{sender.get('email', '')}>
Subject: {email.get('subject', '')}
Snippet: {email.get('body_snippet', '')}
Date: {email.get('date', '')}
Labels: {', '.join(email.get('labels', []))}
"""

    return f"""You are an email triage assistant. Your job is to classify and rank emails by relevance.

# Marvin's Context
{context_block}

# Emails to Triage ({len(emails)} total)
{emails_block}

# Instructions

Review each email. For each one, decide:
1. Is this worth reading deeply? (newsletters with real content, events, personal replies, deals)
2. Is it time-sensitive? (events, tickets, deadlines)
3. How relevant is it to Marvin's current interests and priorities?

Return a JSON object with:
- "shortlist": array of emails worth reading, ranked by relevance (most relevant first)
- "stats": object with total_reviewed, shortlisted, skipped counts

Each shortlist item must have:
- "gmail_id": the Gmail ID from the email
- "rank": integer (1 = most relevant)
- "category": one of "newsletter", "event", "personal", "deal", "notification", "other"
- "reason": one sentence explaining why this is worth reading
- "time_sensitive": boolean
- "deadline": ISO date string if time-sensitive, otherwise null

Be selective. Aim for 20-30 items from a batch of 50. Skip obvious marketing, generic notifications, and anything that fails the "would Marvin regret missing this?" test.

Respond with ONLY the JSON object, no markdown fences, no explanation."""


class EmailTriageWorker(BaseWorker):
    def __init__(self):
        super().__init__("email-triage")

    def run(self, digest):
        """Triage emails from digest. Returns shortlist JSON."""
        items = digest.get("items", [])
        if not items:
            return {"shortlist": [], "stats": {"total_reviewed": 0, "shortlisted": 0, "skipped": 0}}

        context = self.get_context()
        batch_size = self.config.get("batch_size", 50)

        all_shortlisted = []
        total_input_tokens = 0
        total_output_tokens = 0

        # Process in batches
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            prompt = build_triage_prompt(batch, context)

            result = self.call(prompt)
            total_input_tokens += result["input_tokens"]
            total_output_tokens += result["output_tokens"]

            try:
                parsed = json.loads(result["text"])
                batch_shortlist = parsed.get("shortlist", [])
                all_shortlisted.extend(batch_shortlist)
            except json.JSONDecodeError:
                sys.stderr.write(f"Failed to parse batch {i//batch_size + 1} response as JSON\n")
                continue

        # Re-rank across all batches
        all_shortlisted.sort(key=lambda x: x.get("rank", 999))
        for i, item in enumerate(all_shortlisted):
            item["rank"] = i + 1

        output = {
            "shortlist": all_shortlisted,
            "stats": {
                "total_reviewed": len(items),
                "shortlisted": len(all_shortlisted),
                "skipped": len(items) - len(all_shortlisted),
            }
        }

        # Log the run
        self.log_run(
            model=self.get_model(),
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            input_summary=f"{len(items)} emails in {(len(items) + batch_size - 1) // batch_size} batches",
            output_summary=f"{len(all_shortlisted)} shortlisted, {len(items) - len(all_shortlisted)} skipped",
        )

        return output


def main():
    parser = argparse.ArgumentParser(description="Email triage worker")
    parser.add_argument("--digest", required=True, help="Path to email-digest.json")
    parser.add_argument("--output", default=None, help="Output path (default: stdout)")
    args = parser.parse_args()

    with open(args.digest) as f:
        digest = json.load(f)

    worker = EmailTriageWorker()
    result = worker.run(digest)

    output_json = json.dumps(result, indent=2)
    if args.output:
        with open(args.output, "w") as f:
            f.write(output_json)
        sys.stderr.write(f"Wrote shortlist to {args.output}\n")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest workspace/tests/test_email_triage.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add workspace/workers/email_triage.py workspace/tests/test_email_triage.py
git commit -m "feat: add email triage worker — Flash-powered bulk classification"
```

---

### Task 6: Newsletter Reader Worker

The deep-reading worker. Takes the shortlist from email triage, reads full bodies through Haiku, extracts specific gems.

**Files:**
- Create: `workspace/workers/newsletter_reader.py`
- Create: `workspace/tests/test_newsletter_reader.py`

**Step 1: Write the failing test**

```python
# workspace/tests/test_newsletter_reader.py
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from workers.newsletter_reader import NewsletterReaderWorker, build_reader_prompt


class TestBuildReaderPrompt(unittest.TestCase):
    def test_prompt_includes_full_body(self):
        emails = [
            {"gmail_id": "abc", "sender": {"name": "Dense Discovery", "email": "dd@example.com"},
             "subject": "Issue 287", "body": "This week: amazing article about local-first software...",
             "links": ["https://example.com/article"]},
        ]
        context = {"INTERESTS.md": "AI, frontend dev", "PRIORITIES.md": "LocalShout this week"}
        prompt = build_reader_prompt(emails, context)
        self.assertIn("local-first software", prompt)
        self.assertIn("LocalShout this week", prompt)
        self.assertIn("https://example.com/article", prompt)


class TestNewsletterReaderWorker(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ["EXPERIMENT_TRACKER_DB"] = os.path.join(self.tmpdir, "tracker.db")

    def tearDown(self):
        os.environ.pop("EXPERIMENT_TRACKER_DB", None)

    @patch("workers.base_worker.call_model")
    def test_run_returns_gems(self, mock_call):
        mock_call.return_value = {
            "text": json.dumps({
                "gems": [
                    {"gmail_id": "abc", "source": "Dense Discovery", "title": "Local-first article",
                     "why": "Connects to LocalShout architecture", "links": ["https://example.com"],
                     "time_sensitive": False, "deadline": None, "price": None, "surprise_candidate": True}
                ],
                "stats": {"newsletters_read": 1, "gems_extracted": 1, "links_found": 1}
            }),
            "input_tokens": 40000,
            "output_tokens": 2000,
        }

        worker = NewsletterReaderWorker()
        shortlist_data = {
            "shortlist": [
                {"gmail_id": "abc", "rank": 1, "category": "newsletter", "reason": "AI content"}
            ],
            "emails": {
                "abc": {"gmail_id": "abc", "sender": {"name": "DD", "email": "dd@e.com"},
                        "subject": "Issue 287", "body": "Full newsletter body here...",
                        "links": ["https://example.com"], "labels": []}
            }
        }
        result = worker.run(shortlist_data)
        self.assertIn("gems", result)
        self.assertEqual(len(result["gems"]), 1)
        self.assertTrue(result["gems"][0]["surprise_candidate"])


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest workspace/tests/test_newsletter_reader.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# workspace/workers/newsletter_reader.py
#!/usr/bin/env python3
"""
Newsletter deep-reader worker.

Takes a shortlist of emails (from email_triage) plus their full bodies,
calls a capable model (Haiku) to extract specific articles, links, events,
prices, and gems that match Marvin's context.

Usage:
    python3 workers/newsletter_reader.py --shortlist /tmp/shortlist.json --digest /workspace/email-digest.json
    python3 workers/newsletter_reader.py --shortlist /tmp/shortlist.json --digest /workspace/email-digest.json --output /tmp/gems.json
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from workers.base_worker import BaseWorker


def build_reader_prompt(emails, context):
    """Build the deep-reading prompt."""
    context_block = ""
    for filename, content in context.items():
        context_block += f"\n## {filename}\n{content}\n"

    emails_block = ""
    for email in emails:
        sender = email.get("sender", {})
        links = email.get("links", [])
        links_str = "\n".join(f"  - {url}" for url in links) if links else "  (none)"
        emails_block += f"""
--- {sender.get('name', 'Unknown')} ---
Gmail ID: {email.get('gmail_id', 'unknown')}
Subject: {email.get('subject', '')}
Full body:
{email.get('body', email.get('body_snippet', ''))}

Links found:
{links_str}
"""

    return f"""You are a deep-reading assistant. Read each email carefully — every paragraph, every link — and extract what matters.

# Marvin's Context
{context_block}

# Emails to Read Deeply ({len(emails)} total)
{emails_block}

# Instructions

For each email, read the FULL BODY carefully. Don't just read the subject line. Look for:
- Specific articles, blog posts, or resources mentioned in the body
- Events with dates, venues, and prices
- Deals or offers with concrete details (price, expiry)
- Surprising or non-obvious connections to Marvin's interests or projects
- Links worth clicking

For each gem you find, note whether it could be a "surprise" — something non-obvious that connects two unrelated things, or a buried find Marvin wouldn't expect.

Return a JSON object with:
- "gems": array of extracted items (see schema below)
- "stats": object with newsletters_read, gems_extracted, links_found

Each gem must have:
- "gmail_id": which email it came from
- "source": sender/newsletter name
- "title": the specific article/event/deal title
- "why": one sentence connecting it to Marvin's context (reference specific interests/priorities)
- "links": array of relevant URLs
- "time_sensitive": boolean
- "deadline": ISO date if time-sensitive, null otherwise
- "price": price string if relevant, null otherwise
- "surprise_candidate": boolean — true if this is a non-obvious find

Be specific. "Interesting AI article" is bad. "OpenAI released Codex 2 — connects to your agent-building work on Spoons" is good.

Respond with ONLY the JSON object, no markdown fences, no explanation."""


class NewsletterReaderWorker(BaseWorker):
    def __init__(self):
        super().__init__("newsletter-deep-read")

    def run(self, shortlist_data):
        """Deep read shortlisted emails. Returns gems JSON."""
        shortlist = shortlist_data.get("shortlist", [])
        email_lookup = shortlist_data.get("emails", {})

        if not shortlist:
            return {"gems": [], "stats": {"newsletters_read": 0, "gems_extracted": 0, "links_found": 0}}

        # Get full email bodies for shortlisted items
        emails_to_read = []
        for item in shortlist:
            gmail_id = item.get("gmail_id")
            if gmail_id in email_lookup:
                emails_to_read.append(email_lookup[gmail_id])

        if not emails_to_read:
            return {"gems": [], "stats": {"newsletters_read": 0, "gems_extracted": 0, "links_found": 0}}

        context = self.get_context()
        batch_size = self.config.get("batch_size", 15)

        all_gems = []
        total_input_tokens = 0
        total_output_tokens = 0

        for i in range(0, len(emails_to_read), batch_size):
            batch = emails_to_read[i:i + batch_size]
            prompt = build_reader_prompt(batch, context)

            result = self.call(prompt)
            total_input_tokens += result["input_tokens"]
            total_output_tokens += result["output_tokens"]

            try:
                parsed = json.loads(result["text"])
                all_gems.extend(parsed.get("gems", []))
            except json.JSONDecodeError:
                sys.stderr.write(f"Failed to parse batch {i//batch_size + 1} response as JSON\n")
                continue

        output = {
            "gems": all_gems,
            "stats": {
                "newsletters_read": len(emails_to_read),
                "gems_extracted": len(all_gems),
                "links_found": sum(len(g.get("links", [])) for g in all_gems),
            }
        }

        self.log_run(
            model=self.get_model(),
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            input_summary=f"{len(emails_to_read)} emails deep-read in {(len(emails_to_read) + batch_size - 1) // batch_size} batches",
            output_summary=f"{len(all_gems)} gems extracted, {output['stats']['links_found']} links",
        )

        return output


def main():
    parser = argparse.ArgumentParser(description="Newsletter deep-reader worker")
    parser.add_argument("--shortlist", required=True, help="Path to shortlist JSON (from email_triage)")
    parser.add_argument("--digest", required=True, help="Path to email-digest.json (for full bodies)")
    parser.add_argument("--output", default=None, help="Output path (default: stdout)")
    args = parser.parse_args()

    with open(args.shortlist) as f:
        shortlist_raw = json.load(f)

    with open(args.digest) as f:
        digest = json.load(f)

    # Build email lookup from digest
    email_lookup = {item["gmail_id"]: item for item in digest.get("items", []) if "gmail_id" in item}

    shortlist_data = {
        "shortlist": shortlist_raw.get("shortlist", shortlist_raw),
        "emails": email_lookup,
    }

    worker = NewsletterReaderWorker()
    result = worker.run(shortlist_data)

    output_json = json.dumps(result, indent=2)
    if args.output:
        with open(args.output, "w") as f:
            f.write(output_json)
        sys.stderr.write(f"Wrote gems to {args.output}\n")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest workspace/tests/test_newsletter_reader.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add workspace/workers/newsletter_reader.py workspace/tests/test_newsletter_reader.py
git commit -m "feat: add newsletter reader worker — Haiku-powered deep reading with gem extraction"
```

---

### Task 7: Update Sift-Digest Skill to Use Workers

Rewrite the skill instructions so Jimbo delegates to workers instead of reading all emails himself.

**Files:**
- Modify: `skills/sift-digest/SKILL.md`

**Step 1: Read current skill** (already read — it's at `skills/sift-digest/SKILL.md`)

**Step 2: Update the skill**

Replace the "Your job: read deeply, curate ruthlessly" section and add the worker delegation flow. Keep the presentation format sections unchanged.

Key changes:
- Add a "Worker pipeline" section between "Loading the digest" and "Presentation format"
- Replace "read each email's full body" with "call workers, then synthesise"
- Add conductor's log instructions
- Add surprise game instructions
- Keep all the presentation format rules

The updated skill should instruct Jimbo to:
1. Call `python3 /workspace/workers/email_triage.py --digest /workspace/email-digest.json --output /tmp/shortlist.json`
2. Read the shortlist output
3. Call `python3 /workspace/workers/newsletter_reader.py --shortlist /tmp/shortlist.json --digest /workspace/email-digest.json --output /tmp/gems.json`
4. Read the gems output
5. Synthesise into the briefing using the existing presentation format
6. Log conductor reasoning (what he promoted/dropped/why, self-critique of worker quality)
7. Play the surprise game (pick best surprise_candidate, present it)
8. Log the overall briefing run to experiment tracker
9. Log recommendations as before

**Step 3: Commit**

```bash
git add skills/sift-digest/SKILL.md
git commit -m "feat: update sift-digest skill to delegate to workers"
```

---

### Task 8: Deploy and End-to-End Test

Push everything to the VPS and verify it works with real data.

**Files:**
- Modify: `scripts/workspace-push.sh` (add workers/ and tasks/ to rsync)

**Step 1: Check workspace-push.sh includes new directories**

Read `scripts/workspace-push.sh` and ensure `workers/` and `tasks/` and `tests/` are included in the rsync. Add them if not.

**Step 2: Deploy to VPS**

Run: `./scripts/workspace-push.sh && ./scripts/skills-push.sh`

**Step 3: SSH in and verify files are present**

Run: `ssh jimbo "ls /home/openclaw/.openclaw/workspace/workers/ && ls /home/openclaw/.openclaw/workspace/tasks/"`
Expected: All worker scripts and task configs listed

**Step 4: Test experiment tracker on VPS**

Run: `ssh jimbo 'docker exec $(docker ps -q --filter name=openclaw-sbx) python3 /workspace/experiment-tracker.py log --task email-triage --model gemini-2.5-flash --input-tokens 5000 --output-tokens 500'`
Expected: `{"status": "ok", "run_id": "run_...", "cost_usd": ...}`

**Step 5: Test email triage worker with real digest** (if digest exists)

Run: `ssh jimbo 'docker exec $(docker ps -q --filter name=openclaw-sbx) python3 /workspace/workers/email_triage.py --digest /workspace/email-digest.json --output /tmp/shortlist.json 2>&1 | head -5'`
Expected: JSON output with shortlist

**Step 6: Test newsletter reader with real shortlist**

Run: `ssh jimbo 'docker exec $(docker ps -q --filter name=openclaw-sbx) python3 /workspace/workers/newsletter_reader.py --shortlist /tmp/shortlist.json --digest /workspace/email-digest.json --output /tmp/gems.json 2>&1 | head -5'`
Expected: JSON output with gems

**Step 7: Verify experiment tracker logged both runs**

Run: `ssh jimbo 'docker exec $(docker ps -q --filter name=openclaw-sbx) python3 /workspace/experiment-tracker.py stats --days 1'`
Expected: Shows 2+ runs with costs

**Step 8: Commit any deployment script changes**

```bash
git add scripts/workspace-push.sh
git commit -m "chore: add workers/ and tasks/ to workspace-push.sh"
```

---

### Task 9: Switch Jimbo's Model to Haiku (Conductor Upgrade)

The conductor needs to be on a capable model to synthesise worker outputs well.

**Step 1: Switch model**

Run: `./scripts/model-swap.sh haiku`

**Step 2: Verify**

Run: `ssh jimbo "journalctl -u openclaw -n 5 --no-pager"`
Expected: Log shows `claude-haiku-4.5` as active model

**Step 3: Test via Telegram**

Send Jimbo a message on Telegram and verify he responds coherently.

**Step 4: No commit needed** (VPS-only config change)

---

## Summary

| Task | What it builds | Dependencies |
|------|---------------|--------------|
| 1 | Experiment tracker (schema + log) | None |
| 2 | Experiment tracker (compare, rate, stats) | Task 1 |
| 3 | Task registry (JSON configs) | None |
| 4 | Base worker (API clients, logging) | Tasks 1, 3 |
| 5 | Email triage worker | Task 4 |
| 6 | Newsletter reader worker | Task 4 |
| 7 | Update sift-digest skill | Tasks 5, 6 |
| 8 | Deploy + E2E test | Tasks 1-7 |
| 9 | Switch to Haiku | Task 8 |

Tasks 1+3 can run in parallel. Tasks 5+6 can run in parallel. Task 7 depends on both workers existing. Task 8 is the integration test. Task 9 is the final flip.
