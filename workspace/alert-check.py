#!/usr/bin/env python3
"""
Pipeline health checker with positive heartbeat.

Checks that pipeline stages have run recently. Sends a Telegram alert
on failure, and a positive heartbeat message when all is well.

Python 3.11 stdlib only. No pip dependencies.

Usage:
    python3 alert-check.py digest     # check email-digest.json is fresh (<25h)
    python3 alert-check.py briefing   # check experiment-tracker.db has today's run
"""

import datetime
import json
import os
import sqlite3
import subprocess
import sys


_script_dir = os.path.dirname(os.path.abspath(__file__))
ALERT_SCRIPT = os.path.join(_script_dir, "alert.py")
DIGEST_PATH = os.path.join(_script_dir, "email-digest.json")
TRACKER_DB_PATH = os.environ.get(
    "EXPERIMENT_TRACKER_DB",
    os.path.join(_script_dir, "experiment-tracker.db"),
)

MAX_DIGEST_AGE_HOURS = 25


def send_alert(message):
    """Send alert via alert.py."""
    subprocess.run([sys.executable, ALERT_SCRIPT, message])


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def check_digest():
    """Check email-digest.json exists and is fresh. Returns (ok, summary)."""
    if not os.path.exists(DIGEST_PATH):
        return False, "email-digest.json not found"

    try:
        with open(DIGEST_PATH) as f:
            digest = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return False, f"email-digest.json unreadable: {e}"

    generated_at = digest.get("generated_at")
    if not generated_at:
        return False, "email-digest.json missing generated_at field"

    try:
        gen_time = datetime.datetime.fromisoformat(generated_at)
        if gen_time.tzinfo is None:
            gen_time = gen_time.replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return False, f"email-digest.json has invalid generated_at: {generated_at}"

    age = now_utc() - gen_time
    age_hours = age.total_seconds() / 3600

    if age_hours > MAX_DIGEST_AGE_HOURS:
        return False, f"email-digest.json is {age_hours:.1f}h old (threshold: {MAX_DIGEST_AGE_HOURS}h)"

    email_count = len(digest.get("items", []))
    gen_short = gen_time.strftime("%H:%M")
    return True, f"digest fresh ({gen_short} UTC, {email_count} emails, {age_hours:.1f}h ago)"


def check_briefing():
    """Check experiment-tracker.db has a run with today's date. Returns (ok, summary)."""
    if not os.path.exists(TRACKER_DB_PATH):
        return False, "experiment-tracker.db not found"

    try:
        db = sqlite3.connect(TRACKER_DB_PATH)
        db.row_factory = sqlite3.Row
    except sqlite3.Error as e:
        return False, f"experiment-tracker.db unreadable: {e}"

    today = now_utc().strftime("%Y-%m-%d")

    try:
        row = db.execute(
            "SELECT COUNT(*) as count FROM runs WHERE timestamp LIKE ?",
            (f"{today}%",),
        ).fetchone()

        if row["count"] == 0:
            db.close()
            return False, f"no experiment runs found for {today}"

        # Get summary of today's runs
        runs = db.execute(
            """SELECT task_id, COUNT(*) as count,
                      SUM(output_tokens) as total_output_tokens
               FROM runs WHERE timestamp LIKE ?
               GROUP BY task_id""",
            (f"{today}%",),
        ).fetchall()

        db.close()

        parts = []
        for r in runs:
            parts.append(f"{r['task_id']}: {r['count']} run(s)")

        summary = f"briefing pipeline ran today ({', '.join(parts)})"
        return True, summary

    except sqlite3.Error as e:
        db.close()
        return False, f"experiment-tracker.db query failed: {e}"


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("digest", "briefing"):
        sys.stderr.write("Usage: python3 alert-check.py {digest|briefing}\n")
        sys.exit(1)

    command = sys.argv[1]

    if command == "digest":
        ok, summary = check_digest()
    elif command == "briefing":
        ok, summary = check_briefing()

    timestamp = now_utc().strftime("%H:%M")

    if ok:
        send_alert(f"\u2705 {timestamp} {summary}")
    else:
        send_alert(f"\u274c {timestamp} ALERT: {summary}")
        sys.exit(1)


if __name__ == "__main__":
    main()
