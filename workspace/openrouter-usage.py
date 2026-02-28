#!/usr/bin/env python3
"""
OpenRouter usage and balance checker.

Queries OpenRouter's API to show current credit balance and usage breakdown.
Gives Jimbo programmatic access to cost data.

Python 3.11 stdlib only. No pip dependencies.

Usage:
    python3 openrouter-usage.py balance              # credit balance + daily burn estimate
    python3 openrouter-usage.py usage --days 7        # usage breakdown by model
"""

import datetime
import json
import os
import sys
import urllib.request
import urllib.error


API_BASE = "https://openrouter.ai/api/v1"


def get_api_key():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.stderr.write("openrouter-usage.py: OPENROUTER_API_KEY not set\n")
        sys.exit(1)
    return key


def api_get(path):
    """GET request to OpenRouter API. Returns parsed JSON."""
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {get_api_key()}",
            "Content-Type": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        sys.stderr.write(f"openrouter-usage.py: HTTP {e.code}: {body}\n")
        sys.exit(1)
    except (urllib.error.URLError, OSError) as e:
        sys.stderr.write(f"openrouter-usage.py: request failed: {e}\n")
        sys.exit(1)


def cmd_balance():
    """Show current credit balance and estimated daily burn."""
    data = api_get("/auth/key")
    info = data.get("data", data)

    balance = info.get("limit")
    usage = info.get("usage")

    if balance is None or usage is None:
        print(json.dumps({"error": "unexpected response format", "raw": data}))
        sys.exit(1)

    remaining = balance - usage

    # Output structured data
    result = {
        "credit_limit": balance,
        "usage_total": round(usage, 4),
        "remaining": round(remaining, 4),
    }

    print(f"OpenRouter balance: ${remaining:.2f} remaining (${usage:.2f} used of ${balance:.2f} limit)")

    if remaining < 1.0:
        print(f"WARNING: Balance below $1.00")
    elif remaining < 2.0:
        print(f"Note: Balance below $2.00")

    return result


def cmd_usage(days):
    """Show usage breakdown. Note: OpenRouter /auth/key gives totals only.
    For detailed breakdown, we'd need the /generation endpoint which requires
    partner access. This shows what's available."""
    data = api_get("/auth/key")
    info = data.get("data", data)

    balance = info.get("limit")
    usage = info.get("usage")

    if balance is None or usage is None:
        print(json.dumps({"error": "unexpected response format", "raw": data}))
        sys.exit(1)

    remaining = balance - usage

    print(f"OpenRouter Usage Summary (last {days} days requested)")
    print(f"  Credit limit:  ${balance:.2f}")
    print(f"  Total used:    ${usage:.2f}")
    print(f"  Remaining:     ${remaining:.2f}")
    print()
    print("Note: Per-model breakdown requires the OpenRouter activity page.")
    print("      Visit https://openrouter.ai/activity for detailed model-level costs.")


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: python3 openrouter-usage.py {balance|usage [--days N]}\n")
        sys.exit(1)

    command = sys.argv[1]

    if command == "balance":
        cmd_balance()
    elif command == "usage":
        days = 7
        if "--days" in sys.argv:
            idx = sys.argv.index("--days")
            if idx + 1 < len(sys.argv):
                try:
                    days = int(sys.argv[idx + 1])
                except ValueError:
                    sys.stderr.write("--days must be a number\n")
                    sys.exit(1)
        cmd_usage(days)
    else:
        sys.stderr.write(f"Unknown command: {command}\n")
        sys.stderr.write("Usage: python3 openrouter-usage.py {balance|usage [--days N]}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
