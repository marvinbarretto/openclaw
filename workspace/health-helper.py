#!/usr/bin/env python3
"""
Health API client for Jimbo's sandbox.

Fetches comprehensive system health from jimbo-api and formats it
as readable text. Gives Jimbo self-awareness: what's working, what's
broken, what he's done today, what's in the dispatch queue.

Python 3.11 stdlib only. No pip dependencies.

Usage:
    python3 /workspace/health-helper.py status       # full formatted status
    python3 /workspace/health-helper.py pipeline      # pipeline section only
    python3 /workspace/health-helper.py dispatch      # dispatch queue only
    python3 /workspace/health-helper.py activity      # today's activity summary
    python3 /workspace/health-helper.py costs         # cost summary
    python3 /workspace/health-helper.py json          # raw JSON (for scripts)
"""

import json
import os
import sys
import urllib.request
import urllib.error


API_URL = os.environ.get("JIMBO_API_URL", "http://localhost:3100")
API_KEY = os.environ.get("JIMBO_API_KEY", os.environ.get("API_KEY", ""))


def fetch_health():
    """Fetch /api/health. Returns parsed JSON or None."""
    url = f"{API_URL}/api/health"
    req = urllib.request.Request(
        url,
        headers={
            "X-API-Key": API_KEY,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        sys.stderr.write(f"health-helper.py: failed to fetch health: {e}\n")
        return None


def fmt_pipeline(data):
    """Format pipeline section."""
    lines = ["# Pipeline"]
    for session in ("morning", "afternoon"):
        p = data.get("pipeline", {}).get(session, {})
        if not p.get("ran"):
            lines.append(f"\n## {session.title()}: not run")
            continue
        stats = p.get("stats", {})
        delivered = "yes" if p.get("delivered") else "no"
        lines.append(f"\n## {session.title()} (ran {p.get('ran_at', '?')})")
        lines.append(f"- Emails: {stats.get('emails', 0)}, Gems: {stats.get('gems', 0)}, Insights: {stats.get('insights', 0)}")
        lines.append(f"- Calendar events: {stats.get('calendar_events', 0)}, Vault tasks: {stats.get('vault_tasks', 0)}")
        lines.append(f"- Delivered: {delivered}")

    latest = data.get("pipeline", {}).get("latest_input", {})
    dispatch = latest.get("dispatch", {})
    if dispatch:
        lines.append(f"\n## Dispatch Queue")
        lines.append(f"- Awaiting dispatch: {dispatch.get('awaiting_dispatch', 0)}")
        lines.append(f"- PRs for review: {dispatch.get('prs_for_review', 0)}")
        lines.append(f"- In progress: {dispatch.get('in_progress', 0)}")
        lines.append(f"- Needs grooming: {dispatch.get('needs_grooming', 0)}")
    return "\n".join(lines)


def fmt_dispatch(data):
    """Format dispatch section only."""
    latest = data.get("pipeline", {}).get("latest_input", {})
    dispatch = latest.get("dispatch", {})
    if not dispatch:
        return "No dispatch data available."
    lines = [
        "# Dispatch Queue",
        f"- Awaiting dispatch: {dispatch.get('awaiting_dispatch', 0)}",
        f"- PRs for review: {dispatch.get('prs_for_review', 0)}",
        f"- In progress: {dispatch.get('in_progress', 0)}",
        f"- Recon completed: {dispatch.get('recon_completed', 0)}",
        f"- Needs grooming: {dispatch.get('needs_grooming', 0)}",
    ]
    return "\n".join(lines)


def fmt_activity(data):
    """Format today's activity summary."""
    act = data.get("activity", {})
    lines = [
        "# Today's Activity",
        f"- Total: {act.get('today', 0)} (yesterday: {act.get('yesterday', 0)})",
        f"- Last: {act.get('last_activity', 'none')}",
    ]
    by_type = act.get("by_type_today", {})
    if by_type:
        lines.append("- By type: " + ", ".join(f"{k}={v}" for k, v in by_type.items()))
    nudges = act.get("nudges_today", [])
    if nudges:
        lines.append(f"- Nudges sent: {len(nudges)}")
    else:
        lines.append("- Nudges sent: 0")
    heartbeat = act.get("heartbeat_today", [])
    if heartbeat:
        lines.append(f"- Heartbeat entries: {len(heartbeat)}")
    return "\n".join(lines)


def fmt_costs(data):
    """Format cost summary."""
    costs = data.get("costs", {})
    lines = [
        "# Costs",
        f"- Today: ${costs.get('today', 0):.3f} ({costs.get('today_calls', 0)} calls)",
        f"- This month: ${costs.get('month', 0):.2f} / ${costs.get('budget', 25)} ({costs.get('budget_pct', 0)}%)",
    ]
    by_model = costs.get("by_model_today", [])
    if by_model:
        for m in by_model:
            lines.append(f"  - {m['model']}: ${m['total']:.3f} ({m['count']} calls)")
    return "\n".join(lines)


def fmt_status(data):
    """Format full status report."""
    lines = [f"# System Status: {data.get('overall', 'unknown').upper()}"]

    issues = data.get("issues", [])
    if issues:
        lines.append("\n## Issues")
        for issue in issues:
            lines.append(f"- {issue}")

    lines.append("")
    lines.append(fmt_pipeline(data))
    lines.append("")
    lines.append(fmt_activity(data))
    lines.append("")
    lines.append(fmt_costs(data))

    # Vault
    vault = data.get("vault", {})
    by_status = vault.get("by_status", {})
    if by_status:
        lines.append(f"\n# Vault")
        lines.append(f"- Active: {by_status.get('active', 0)}, Inbox: {by_status.get('inbox', 0)}, Done: {by_status.get('done', 0)}")
        lines.append(f"- 7-day velocity: {vault.get('velocity_7d', 0)}, Completed 7d: {vault.get('completed_7d', 0)}")
        pri = vault.get("by_priority", {})
        if pri:
            lines.append(f"- Priority: {pri.get('critical',0)} critical, {pri.get('high',0)} high, {pri.get('medium',0)} med, {pri.get('low',0)} low")

    # Model
    model = data.get("model", {})
    if model:
        lines.append(f"\n# Model")
        lines.append(f"- Current: {model.get('current_model', '?')} via {model.get('provider', '?')}")

    # Token warnings
    tokens = data.get("tokens", {})
    warnings = tokens.get("warnings", [])
    if warnings:
        lines.append(f"\n# Token Warnings")
        for w in warnings:
            lines.append(f"- {w}")

    # Email quality
    email = data.get("email", {})
    if email:
        lines.append(f"\n# Email")
        lines.append(f"- Reports today: {email.get('reports_today', 0)}, Decided: {email.get('decided_today', 0)}")
        iq = email.get("insight_quality", {})
        if iq:
            lines.append(f"- Insight quality: {iq.get('with_insight_content', 0)}/{iq.get('total_recent', 0)} complete")

    # Duplicates
    dupes = data.get("duplicates", [])
    if dupes:
        lines.append(f"\n# Duplicate Messages: {len(dupes)}")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: python3 health-helper.py <status|pipeline|dispatch|activity|costs|json>\n")
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if not API_KEY:
        sys.stderr.write("health-helper.py: JIMBO_API_KEY or API_KEY not set\n")
        sys.exit(1)

    data = fetch_health()
    if not data:
        sys.exit(1)

    if cmd == "json":
        print(json.dumps(data, indent=2))
    elif cmd == "status":
        print(fmt_status(data))
    elif cmd == "pipeline":
        print(fmt_pipeline(data))
    elif cmd == "dispatch":
        print(fmt_dispatch(data))
    elif cmd == "activity":
        print(fmt_activity(data))
    elif cmd == "costs":
        print(fmt_costs(data))
    else:
        sys.stderr.write(f"Unknown command: {cmd}\n")
        sys.stderr.write("Commands: status, pipeline, dispatch, activity, costs, json\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
