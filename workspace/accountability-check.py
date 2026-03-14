#!/usr/bin/env python3
"""
Daily accountability checker for Jimbo.

Queries jimbo-api for today's activity, experiments, and costs,
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
import subprocess
import sys
import urllib.request
import urllib.error

_script_dir = os.path.dirname(os.path.abspath(__file__))
ALERT_SCRIPT = os.path.join(_script_dir, "alert.py")
CALL_SCRIPT = os.path.join(_script_dir, "alert-call.py")


def send_alert(message):
    subprocess.run([sys.executable, ALERT_SCRIPT, message])


def send_call(message):
    """Escalate to phone call for critical failures."""
    try:
        subprocess.run([sys.executable, CALL_SCRIPT, message], timeout=30)
    except Exception:
        pass


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def today_str():
    return now_utc().strftime("%Y-%m-%d")


def api_request(method, path, body=None):
    api_url = os.environ.get("JIMBO_API_URL", "http://localhost:3100")
    api_key = os.environ.get("JIMBO_API_KEY", os.environ.get("API_KEY", ""))
    url = f"{api_url}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-API-Key", api_key)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def check_briefing_ran():
    """Did morning + afternoon briefing-prep pipeline runs log today?"""
    try:
        result = api_request("GET", "/api/experiments?task=briefing-prep&last=50")
        rows = [r for r in result.get("runs", []) if r.get("timestamp", "").startswith(today_str())]
    except Exception as e:
        return False, f"experiments API unreachable: {e}"

    if not rows:
        return False, "briefing pipeline did not run"

    # Classify by session
    morning_rows = [r for r in rows if (r.get("session") or "morning") == "morning"]
    afternoon_rows = [r for r in rows if r.get("session") == "afternoon"]

    parts = []

    if morning_rows:
        summary = morning_rows[-1].get("output_summary") or ""
        if "failed" in summary:
            parts.append("morning pipeline PARTIAL")
        else:
            parts.append("morning pipeline ran")
    else:
        parts.append("morning pipeline missing")

    # Afternoon — only flag missing after 16:00 UTC
    current_hour = now_utc().hour
    if afternoon_rows:
        summary = afternoon_rows[-1].get("output_summary") or ""
        if "failed" in summary:
            parts.append("afternoon pipeline PARTIAL")
        else:
            parts.append("afternoon pipeline ran")
    elif current_hour >= 16:
        parts.append("afternoon pipeline missing")

    any_missing = any("missing" in p for p in parts)
    return not any_missing, ", ".join(parts)


def check_gems_produced():
    """Did the newsletter reader produce gems today?"""
    try:
        result = api_request("GET", "/api/experiments?task=newsletter-deep-read&last=50")
        rows = [r for r in result.get("runs", []) if r.get("timestamp", "").startswith(today_str())]
    except Exception:
        return False, "no gems produced (experiments API unreachable)"

    if not rows:
        return False, "no gems produced (newsletter reader didn't run)"
    return True, f"gems produced ({len(rows)} run(s))"


def check_surprise_game():
    """Did a surprise game round happen today?"""
    try:
        result = api_request("GET", "/api/experiments?task=surprise-game&last=50")
        rows = [r for r in result.get("runs", []) if r.get("timestamp", "").startswith(today_str())]
    except Exception:
        return None, "surprise game not played (nudge)"

    if not rows:
        return None, "surprise game not played (nudge)"
    return True, "surprise game played"


def check_vault_tasks_surfaced():
    """Were vault tasks surfaced in the briefing today?"""
    try:
        result = api_request("GET", f"/api/activity?date={today_str()}")
        rows = result.get("entries", [])
    except Exception:
        return False, "no briefing activity logged (activity API unreachable)"

    briefing_rows = [r for r in rows if r.get("task_type") == "briefing"]
    if not briefing_rows:
        return False, "no briefing activity logged"

    # Check if any briefing mention vault tasks
    for row in briefing_rows:
        desc = (row.get("description") or "").lower()
        if "vault" in desc or "task" in desc:
            return True, "vault tasks surfaced in briefing"

    return False, "briefing ran but vault tasks not mentioned"


def check_activity_count():
    """How many activities were logged today?"""
    try:
        result = api_request("GET", f"/api/activity?date={today_str()}")
        rows = result.get("entries", [])
    except Exception:
        return False, "no activities logged today (activity API unreachable)"

    if not rows:
        return False, "no activities logged today"

    # Group by task_type
    by_type = {}
    for r in rows:
        task_type = r.get("task_type", "unknown")
        by_type[task_type] = by_type.get(task_type, 0) + 1

    total = len(rows)
    breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(by_type.items()))
    return True, f"{total} activities ({breakdown})"


def check_cost_today():
    """What did today cost?"""
    try:
        result = api_request("GET", "/api/costs/summary?days=1")
        total = result.get("total_cost", 0)
    except Exception:
        return True, "no cost data today"

    if total == 0:
        return True, "no cost data today"

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

        if ok is None:
            icon = "\U0001f4ad"  # 💭 soft nudge
        elif ok:
            icon = "\u2705"
        else:
            icon = "\u274c"
        results.append((icon, summary, ok))
        if ok is False:
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

    # Escalate: if both briefing pipelines missed, phone call
    briefing_ok, briefing_summary = check_briefing_ran()
    if not briefing_ok and "morning pipeline missing" in briefing_summary and "afternoon pipeline missing" in briefing_summary:
        send_call("Jimbo alert: both morning and afternoon briefing pipelines failed today. Check the VPS.")


if __name__ == "__main__":
    main()
