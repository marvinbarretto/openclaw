#!/usr/bin/env python3
"""
Cost tracker for Jimbo's sandbox.

API-backed logging of API costs per interaction. Tracks provider, model,
task type, token counts, and estimated USD cost. Supports budgets and alerts.

Python 3.11 stdlib only. No pip dependencies.

Usage:
    python3 cost-tracker.py log --provider google --model gemini-2.5-flash --task heartbeat --input-tokens 500 --output-tokens 200
    python3 cost-tracker.py summary --days 1
    python3 cost-tracker.py summary --days 7
    python3 cost-tracker.py export --days 30 --format json
    python3 cost-tracker.py budget --check
"""

import argparse
import datetime
import json
import os
import sys
import urllib.request
import urllib.error


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


# Cost rates per 1M tokens (USD)
COST_RATES = {
    "gemini-2.5-flash": {
        "input": get_setting("cost_rate_gemini_flash_input", 0.15),
        "output": get_setting("cost_rate_gemini_flash_output", 0.60),
    },
    "claude-haiku-4.5": {
        "input": get_setting("cost_rate_haiku_input", 0.80),
        "output": get_setting("cost_rate_haiku_output", 4.00),
    },
    "claude-sonnet-4.6": {"input": 3.00, "output": 15.00},
    "claude-opus-4.6": {"input": 15.00, "output": 75.00},
}

VALID_TASK_TYPES = (
    "heartbeat", "briefing", "chat", "research", "blog",
    "email-check", "nudge", "own-project", "digest", "day-planner",
)


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
    cost = args.cost if args.cost is not None else estimate_cost(
        args.model, args.input_tokens, args.output_tokens
    )

    body = {
        "provider": args.provider,
        "model": args.model,
        "task_type": args.task,
        "input_tokens": args.input_tokens,
        "output_tokens": args.output_tokens,
        "estimated_cost": cost,
    }
    if args.notes:
        body["notes"] = args.notes

    try:
        result = api_request("POST", "/api/costs", body)
        print(json.dumps({
            "status": "ok",
            "id": result["id"],
            "estimated_cost": result.get("estimated_cost", cost),
        }))
    except urllib.error.HTTPError as e:
        error = json.loads(e.read().decode()) if e.readable() else {"error": str(e)}
        print(json.dumps({"status": "error", "message": error.get("error", str(e))}), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        sys.exit(1)


def cmd_summary(args):
    """Show cost summary for the last N days."""
    try:
        result = api_request("GET", f"/api/costs/summary?days={args.days}")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        sys.exit(1)


def cmd_export(args):
    """Export cost data as JSON for dashboard consumption."""
    try:
        result = api_request("GET", f"/api/costs?days={args.days}")
        summary = api_request("GET", f"/api/costs/summary?days={args.days}")

        export = {
            "period_days": args.days,
            "total_cost": summary.get("total_cost", 0),
            "monthly_cost": summary.get("monthly_cost", 0),
            "total_interactions": summary.get("total_interactions", 0),
            "by_model": summary.get("by_model", []),
            "by_task_type": summary.get("by_task_type", []),
            "by_day": summary.get("by_day", []),
            "entries": result.get("entries", []),
        }
        print(json.dumps(export, indent=2))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        sys.exit(1)


def cmd_budget(args):
    """Check monthly budget status."""
    try:
        summary = api_request("GET", "/api/costs/summary?days=30")
        monthly_budget = get_setting("monthly_budget_usd", 25.0)

        spent = summary.get("monthly_cost", 0)
        remaining = round(monthly_budget - spent, 4)
        pct = round((spent / monthly_budget) * 100, 1) if monthly_budget > 0 else 0
        alert_threshold = get_setting("budget_alert_threshold", 80)
        alert = pct >= alert_threshold

        days_remaining = (datetime.date.today().replace(day=1) + datetime.timedelta(days=32)).replace(day=1) - datetime.date.today()

        result = {
            "monthly_limit": monthly_budget,
            "spent": spent,
            "remaining": remaining,
            "percent_used": pct,
            "alert": alert,
            "days_remaining": days_remaining.days,
        }
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
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
    budget_p = subparsers.add_parser("budget", help="Check monthly budget")
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
