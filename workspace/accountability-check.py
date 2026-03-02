#!/usr/bin/env python3
"""
Daily accountability checker for Jimbo.

Queries activity-log.db + experiment-tracker.db for today's activity,
checks whether key pipeline stages ran, and sends a summary via Telegram.

Designed to run at 20:00 UTC via cron.

Python 3.11 stdlib only. No pip dependencies.

Usage:
    python3 accountability-check.py          # full accountability report
    python3 accountability-check.py --quiet  # only alert on failures
"""

import datetime
import json
import os
import sqlite3
import subprocess
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
ALERT_SCRIPT = os.path.join(_script_dir, "alert.py")
ACTIVITY_DB = os.path.join(_script_dir, "activity-log.db")
TRACKER_DB = os.environ.get(
    "EXPERIMENT_TRACKER_DB",
    os.path.join(_script_dir, "experiment-tracker.db"),
)
COST_DB = os.path.join(_script_dir, "cost-tracker.db")


def send_alert(message):
    subprocess.run([sys.executable, ALERT_SCRIPT, message])


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def today_str():
    return now_utc().strftime("%Y-%m-%d")


def query_db(db_path, sql, params=()):
    """Run a query against a SQLite db, return rows as dicts. Returns [] if db missing."""
    if not os.path.exists(db_path):
        return []
    try:
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        rows = db.execute(sql, params).fetchall()
        db.close()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []


def check_briefing_ran():
    """Did a briefing-synthesis run log today?"""
    rows = query_db(
        TRACKER_DB,
        "SELECT * FROM runs WHERE task_id = 'briefing-synthesis' AND timestamp LIKE ?",
        (f"{today_str()}%",),
    )
    if not rows:
        return False, "briefing did not run"

    # Check if it was fallback
    for row in rows:
        reasoning = row.get("conductor_reasoning", "") or ""
        if "fallback" in reasoning.lower():
            return True, f"briefing ran in FALLBACK mode ({len(rows)} run(s))"

    rating = rows[-1].get("conductor_rating")
    return True, f"briefing ran ({len(rows)} run(s), rating: {rating})"


def check_gems_produced():
    """Did the newsletter reader produce gems today?"""
    rows = query_db(
        TRACKER_DB,
        "SELECT * FROM runs WHERE task_id = 'newsletter-deep-read' AND timestamp LIKE ?",
        (f"{today_str()}%",),
    )
    if not rows:
        return False, "no gems produced (newsletter reader didn't run)"
    return True, f"gems produced ({len(rows)} run(s))"


def check_surprise_game():
    """Did a surprise game round happen today?"""
    rows = query_db(
        TRACKER_DB,
        "SELECT * FROM runs WHERE task_id = 'surprise-game' AND timestamp LIKE ?",
        (f"{today_str()}%",),
    )
    if not rows:
        return False, "surprise game not played"
    return True, "surprise game played"


def check_vault_tasks_surfaced():
    """Were vault tasks surfaced in the briefing today?"""
    rows = query_db(
        ACTIVITY_DB,
        "SELECT * FROM activities WHERE task_type = 'briefing' AND timestamp LIKE ?",
        (f"{today_str()}%",),
    )
    if not rows:
        return False, "no briefing activity logged"

    # Check if any briefing mention vault tasks
    for row in rows:
        desc = (row.get("description") or "").lower()
        if "vault" in desc or "task" in desc:
            return True, "vault tasks surfaced in briefing"

    return False, "briefing ran but vault tasks not mentioned"


def check_activity_count():
    """How many activities were logged today?"""
    rows = query_db(
        ACTIVITY_DB,
        "SELECT task_type, COUNT(*) as count FROM activities WHERE timestamp LIKE ? GROUP BY task_type",
        (f"{today_str()}%",),
    )
    if not rows:
        return False, "no activities logged today"

    total = sum(r["count"] for r in rows)
    breakdown = ", ".join(f"{r['task_type']}: {r['count']}" for r in rows)
    return True, f"{total} activities ({breakdown})"


def check_cost_today():
    """What did today cost?"""
    rows = query_db(
        COST_DB,
        "SELECT SUM(estimated_cost_usd) as total FROM costs WHERE timestamp LIKE ?",
        (f"{today_str()}%",),
    )
    if not rows or rows[0]["total"] is None:
        return True, "no cost data today"

    total = rows[0]["total"]
    return True, f"${total:.3f} spent today"


def main():
    quiet = "--quiet" in sys.argv

    checks = [
        ("briefing", check_briefing_ran),
        ("gems", check_gems_produced),
        ("surprise", check_surprise_game),
        ("vault", check_vault_tasks_surfaced),
        ("activity", check_activity_count),
        ("cost", check_cost_today),
    ]

    results = []
    failures = 0
    for name, fn in checks:
        try:
            ok, summary = fn()
        except Exception as e:
            ok, summary = False, f"{name}: error — {e}"

        icon = "\u2705" if ok else "\u274c"
        results.append((icon, summary, ok))
        if not ok:
            failures += 1

    if quiet and failures == 0:
        return

    lines = [f"\U0001f4cb Daily Accountability ({today_str()})"]
    lines.append("")
    for icon, summary, _ in results:
        lines.append(f"{icon} {summary}")

    if failures == 0:
        lines.append("")
        lines.append("All systems ran today.")
    else:
        lines.append("")
        lines.append(f"{failures} item(s) need attention.")

    send_alert("\n".join(lines))


if __name__ == "__main__":
    main()
