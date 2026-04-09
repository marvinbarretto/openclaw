#!/usr/bin/env python3
"""
Activity log for Jimbo's sandbox.

API-backed logging of everything Jimbo does — email checks, research,
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
import json
import os
import sys
import urllib.request
import urllib.error

VALID_TASK_TYPES = (
    "email-check", "research", "nudge", "blog", "briefing",
    "chat", "own-project", "heartbeat", "digest", "day-planner",
    "tasks-triage", "orchestration",
)


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


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_log(args):
    """Log an activity."""
    if args.task not in VALID_TASK_TYPES:
        print(json.dumps({"status": "error", "message": f"Invalid task type: {args.task}. Valid: {', '.join(VALID_TASK_TYPES)}"}))
        sys.exit(1)

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

    try:
        result = api_request("POST", "/api/activity", body)
        print(json.dumps({
            "status": "ok",
            "id": result["id"],
            "action": "logged",
        }))
    except urllib.error.HTTPError as e:
        error = json.loads(e.read().decode()) if e.readable() else {"error": str(e)}
        print(json.dumps({"status": "error", "message": error.get("error", str(e))}), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        sys.exit(1)


def cmd_rate(args):
    """Rate an activity (Marvin's satisfaction score)."""
    if args.satisfaction < 1 or args.satisfaction > 5:
        print(json.dumps({"status": "error", "message": "Satisfaction must be 1-5"}))
        sys.exit(1)

    body = {"satisfaction": args.satisfaction}
    if args.notes:
        body["notes"] = args.notes

    try:
        result = api_request("PUT", f"/api/activity/{args.id}/rate", body)
        print(json.dumps({
            "status": "ok",
            "id": result["id"],
            "action": "rated",
            "satisfaction": result.get("satisfaction"),
        }))
    except urllib.error.HTTPError as e:
        error = json.loads(e.read().decode()) if e.readable() else {"error": str(e)}
        print(json.dumps({"status": "error", "message": error.get("error", str(e))}), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        sys.exit(1)


def cmd_list(args):
    """List recent activities."""
    params = []
    if args.days:
        params.append(f"days={args.days}")
    if args.task:
        params.append(f"task={args.task}")

    query = "&".join(params)
    path = f"/api/activity?{query}" if query else "/api/activity"

    try:
        result = api_request("GET", path)
        entries = result.get("entries", [])
        if args.limit:
            entries = entries[:args.limit]
        print(json.dumps(entries, indent=2))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        sys.exit(1)


def cmd_export(args):
    """Export activity data as JSON for dashboard consumption."""
    try:
        result = api_request("GET", f"/api/activity?days={args.days}")
        stats = api_request("GET", f"/api/activity/stats?days={args.days}")

        entries = result.get("entries", [])
        export = {
            "period_days": args.days,
            "total_activities": stats.get("total", len(entries)),
            "avg_satisfaction": stats.get("avg_satisfaction"),
            "by_task_type": stats.get("by_task_type", {}),
            "by_day": stats.get("by_day", {}),
            "entries": entries,
        }
        print(json.dumps(export, indent=2))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        sys.exit(1)


def cmd_stats(args):
    """Summary statistics for the last N days."""
    try:
        result = api_request("GET", f"/api/activity/stats?days={args.days}")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        sys.exit(1)


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
    log_p.add_argument("--rationale", default=None, help="Why this decision was made")
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
