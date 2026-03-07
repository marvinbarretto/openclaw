#!/usr/bin/env python3
"""
Experiment tracker for Jimbo's orchestrator.

API-backed logging of every worker run — task, model, tokens, cost,
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
import hashlib
import json
import os
import sys
import urllib.request
import urllib.error

_script_dir = os.path.dirname(os.path.abspath(__file__))


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
    "gemini-2.5-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-2.5-pro": {"input": 1.25, "output": 5.00},
    "claude-haiku-4.5": {
        "input": get_setting("cost_rate_haiku_input", 0.80),
        "output": get_setting("cost_rate_haiku_output", 4.00),
    },
    "claude-sonnet-4.6": {"input": 3.00, "output": 15.00},
    "claude-opus-4.6": {"input": 15.00, "output": 75.00},
}


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
    cost = estimate_cost(args.model, args.input_tokens, args.output_tokens)
    c_hash = config_hash(args.task)

    body = {
        "task_id": args.task,
        "model": args.model,
        "input_tokens": args.input_tokens,
        "output_tokens": args.output_tokens,
        "cost_usd": cost,
    }
    if c_hash:
        body["config_hash"] = c_hash
    if args.parent_run:
        body["parent_run_id"] = args.parent_run
    if args.duration is not None:
        body["duration_ms"] = args.duration
    if args.input_summary:
        body["input_summary"] = args.input_summary
    if args.output_summary:
        body["output_summary"] = args.output_summary
    if args.quality:
        body["quality_scores"] = args.quality
    if args.conductor_rating is not None:
        body["conductor_rating"] = args.conductor_rating
    if args.conductor_reasoning:
        body["conductor_reasoning"] = args.conductor_reasoning
    if args.session:
        body["session"] = args.session

    try:
        result = api_request("POST", "/api/experiments", body)
        print(json.dumps({"status": "ok", "run_id": result["run_id"], "cost_usd": cost}))
    except urllib.error.HTTPError as e:
        error = json.loads(e.read().decode()) if e.readable() else {"error": str(e)}
        print(json.dumps({"status": "error", "message": error.get("error", str(e))}), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        sys.exit(1)


def cmd_runs(args):
    try:
        result = api_request("GET", f"/api/experiments?task={args.task}&last={args.last}")
        print(json.dumps(result.get("runs", []), indent=2))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        sys.exit(1)


def cmd_compare(args):
    try:
        result = api_request("GET", f"/api/experiments/stats?days={args.days}")
        # Filter by task if the API returns all tasks
        by_model = result.get("by_model", [])
        print(json.dumps({
            "task": args.task,
            "days": args.days,
            "models": by_model,
        }, indent=2))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        sys.exit(1)


def cmd_rate(args):
    body = {"user_rating": args.user_rating}
    if args.notes:
        body["user_notes"] = args.notes

    try:
        result = api_request("PUT", f"/api/experiments/{args.run_id}/rate", body)
        print(json.dumps({"status": "ok", "run_id": result["run_id"], "user_rating": result.get("user_rating")}))
    except urllib.error.HTTPError as e:
        error = json.loads(e.read().decode()) if e.readable() else {"error": str(e)}
        print(json.dumps({"status": "error", "message": error.get("error", str(e))}), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        sys.exit(1)


def cmd_stats(args):
    try:
        result = api_request("GET", f"/api/experiments/stats?days={args.days}")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        sys.exit(1)


def cmd_export(args):
    try:
        runs = api_request("GET", f"/api/experiments?last=1000")
        stats = api_request("GET", f"/api/experiments/stats?days={args.days}")
        print(json.dumps({
            "period_days": args.days,
            "summary": {
                "by_task": stats.get("by_task", []),
                "by_model": stats.get("by_model", []),
            },
            "runs": runs.get("runs", []),
        }, indent=2))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        sys.exit(1)


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
    log_p.add_argument("--session", default=None, choices=["morning", "afternoon"])

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
