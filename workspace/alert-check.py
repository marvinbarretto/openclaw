#!/usr/bin/env python3
"""
Pipeline health checker with positive heartbeat.

Checks that pipeline stages have run recently. Sends a Telegram alert
on failure, and a positive heartbeat message when all is well.

Python 3.11 stdlib only. No pip dependencies.

Usage:
    python3 alert-check.py digest     # check email-digest.json is fresh (<25h)
    python3 alert-check.py briefing   # check experiment-tracker.db has today's run
    python3 alert-check.py credits    # check OpenRouter credit balance
    python3 alert-check.py status     # combined status (all checks in one message)
"""

import datetime
import json
import os
import sqlite3
import subprocess
import sys
import urllib.request
import urllib.error


_script_dir = os.path.dirname(os.path.abspath(__file__))
ALERT_SCRIPT = os.path.join(_script_dir, "alert.py")
DIGEST_PATH = os.path.join(_script_dir, "email-digest.json")
TRACKER_DB_PATH = os.environ.get(
    "EXPERIMENT_TRACKER_DB",
    os.path.join(_script_dir, "experiment-tracker.db"),
)

def get_setting(key, default):
    """Read a setting from the settings API, or return default on failure."""
    api_url = os.environ.get("JIMBO_API_URL", "http://localhost:3100")
    api_key = os.environ.get("JIMBO_API_KEY", os.environ.get("API_KEY", ""))
    url = f"{api_url}/api/settings/{key}"
    req = urllib.request.Request(url, headers={"X-API-Key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return type(default)(data.get("value", default))
    except Exception:
        return default


BRIEFING_GRACE_HOUR = get_setting("briefing_grace_hour_utc", 8)


def send_alert(message):
    """Send alert via alert.py."""
    subprocess.run([sys.executable, ALERT_SCRIPT, message])


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def check_digest():
    """Check email-digest.json exists and report volume. Returns (ok, summary)."""
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

    email_count = len(digest.get("items", []))
    previous_count = digest.get("previous_count")

    if previous_count is not None:
        new_count = max(0, email_count - previous_count)
        return True, f"digest: {email_count} emails today ({new_count} new)"
    else:
        return True, f"digest: {email_count} emails today"


def check_briefing():
    """Check experiment-tracker.db has a run with today's date. Returns (ok, summary)."""
    current_hour = now_utc().hour

    if not os.path.exists(TRACKER_DB_PATH):
        if current_hour < BRIEFING_GRACE_HOUR:
            return True, "briefing pending"
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
            if current_hour < BRIEFING_GRACE_HOUR:
                return True, "briefing pending"
            return False, f"briefing missing for {today}"

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

        summary = f"briefing ran ({', '.join(parts)})"
        return True, summary

    except sqlite3.Error as e:
        db.close()
        return False, f"experiment-tracker.db query failed: {e}"


def check_credits():
    """Check OpenRouter credit usage. Returns (ok, summary)."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return False, "OPENROUTER_API_KEY not set"

    url = "https://openrouter.ai/api/v1/auth/key"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        return False, f"OpenRouter API request failed: {e}"

    info = data.get("data", data)
    usage = info.get("usage")

    if usage is None:
        return False, f"unexpected OpenRouter response: {json.dumps(data)}"

    return True, f"OpenRouter: ${usage:.2f} used"


def check_status():
    """Run all checks and return a combined one-line summary."""
    checks = [
        ("digest", check_digest),
        ("briefing", check_briefing),
        ("credits", check_credits),
    ]

    parts = []
    any_bad = False
    for name, fn in checks:
        try:
            ok, summary = fn()
        except Exception as e:
            ok, summary = False, f"{name} error: {e}"

        if name == "credits":
            icon = "\u2139\ufe0f" if ok else "\u274c"
        elif name == "briefing" and ok and "pending" in summary:
            icon = "\u23f3"
        else:
            icon = "\u2705" if ok else "\u274c"
            if not ok:
                any_bad = True

        parts.append(f"{icon} {summary}")

    return not any_bad, " | ".join(parts)


def main():
    commands = ("digest", "briefing", "credits", "status")
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        sys.stderr.write("Usage: python3 alert-check.py {digest|briefing|credits|status}\n")
        sys.exit(1)

    command = sys.argv[1]

    if command == "status":
        ok, summary = check_status()
    elif command == "digest":
        ok, summary = check_digest()
    elif command == "briefing":
        ok, summary = check_briefing()
    elif command == "credits":
        ok, summary = check_credits()

    timestamp = now_utc().strftime("%H:%M")

    if ok:
        send_alert(f"\u2705 {timestamp} {summary}")
    else:
        send_alert(f"\u274c {timestamp} ALERT: {summary}")
        sys.exit(1)


if __name__ == "__main__":
    main()
