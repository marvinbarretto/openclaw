#!/usr/bin/env python3
"""
Activity API client for Jimbo's sandbox.

Logs activities to jimbo-api (instead of local SQLite) so the dashboard
can display them in real time. Supports rationale — Jimbo's reasoning
for decisions, not just what happened.

Python 3.11 stdlib only. No pip dependencies.

Environment variables:
    JIMBO_API_URL  — jimbo-api base URL (default: http://localhost:3100)
    JIMBO_API_KEY  — API key for jimbo-api

Usage:
    python3 activity-helper.py log --task briefing --description "Morning briefing delivered" --rationale "Highlighted Anjuna event because INTERESTS lists fabric/music"
    python3 activity-helper.py log --task email-check --description "Fetched 38 emails" --outcome "12 shortlisted" --model gemini-2.5-flash
    python3 activity-helper.py today
    python3 activity-helper.py day 2026-03-02
    python3 activity-helper.py stats --days 7
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


API_URL = os.environ.get("JIMBO_API_URL", "http://localhost:3100")
API_KEY = os.environ.get("JIMBO_API_KEY", os.environ.get("API_KEY", ""))


def _request(method, path, body=None):
    """Make an authenticated request to jimbo-api. Returns parsed JSON or None."""
    url = f"{API_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-API-Key", API_KEY)
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        print(f"ERROR: API {e.code}: {body_text}", file=sys.stderr)
        return None
    except (urllib.error.URLError, OSError) as e:
        print(f"ERROR: API unreachable: {e}", file=sys.stderr)
        return None


def cmd_log(args):
    """Log an activity via the API."""
    body = {
        "task_type": args.task,
        "description": args.description,
    }
    if args.outcome:
        body["outcome"] = args.outcome
    if args.rationale:
        body["rationale"] = args.rationale
    if args.model:
        body["model_used"] = args.model
    if args.cost_id:
        body["cost_id"] = args.cost_id

    result = _request("POST", "/api/activity", body)
    if result:
        print(json.dumps({"status": "ok", "id": result.get("id"), "action": "logged"}))
    else:
        sys.exit(1)


def cmd_today(args):
    """Show today's activities."""
    import datetime
    today = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
    result = _request("GET", f"/api/activity?date={today}")
    if result:
        entries = result.get("entries", [])
        if not entries:
            print("No activities logged today.")
            return
        for entry in entries:
            time = entry.get("timestamp", "")
            if "T" in time:
                time = time.split("T")[1][:5]
            task = entry.get("task_type", "")
            desc = entry.get("description", "")
            rationale = entry.get("rationale", "")
            line = f"  {time}  {task:16s} {desc}"
            if rationale:
                line += f"\n        {'':16s} Why: {rationale}"
            print(line)
    else:
        sys.exit(1)


def cmd_day(args):
    """Show activities for a specific date."""
    result = _request("GET", f"/api/activity?date={args.date}")
    if result:
        entries = result.get("entries", [])
        if not entries:
            print(f"No activities for {args.date}.")
            return
        for entry in entries:
            time = entry.get("timestamp", "")
            if "T" in time:
                time = time.split("T")[1][:5]
            task = entry.get("task_type", "")
            desc = entry.get("description", "")
            rationale = entry.get("rationale", "")
            line = f"  {time}  {task:16s} {desc}"
            if rationale:
                line += f"\n        {'':16s} Why: {rationale}"
            print(line)
        print(json.dumps(result))
    else:
        sys.exit(1)


def cmd_stats(args):
    """Show activity statistics."""
    result = _request("GET", f"/api/activity/stats?days={args.days}")
    if result:
        print(json.dumps(result, indent=2))
    else:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Activity API client for Jimbo")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # log
    log_p = subparsers.add_parser("log", help="Log an activity")
    log_p.add_argument("--task", required=True, help="Task type")
    log_p.add_argument("--description", required=True, help="What happened")
    log_p.add_argument("--outcome", default=None, help="Result or outcome")
    log_p.add_argument("--rationale", default=None, help="Why this decision was made")
    log_p.add_argument("--model", default=None, help="Model used")
    log_p.add_argument("--cost-id", default=None, help="Link to cost entry")

    # today
    subparsers.add_parser("today", help="Show today's activities")

    # day
    day_p = subparsers.add_parser("day", help="Show activities for a date")
    day_p.add_argument("date", help="Date (YYYY-MM-DD)")

    # stats
    stats_p = subparsers.add_parser("stats", help="Activity statistics")
    stats_p.add_argument("--days", type=int, default=30, help="Number of days (default: 30)")

    args = parser.parse_args()

    commands = {
        "log": cmd_log,
        "today": cmd_today,
        "day": cmd_day,
        "stats": cmd_stats,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
