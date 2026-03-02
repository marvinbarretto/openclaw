#!/usr/bin/env python3
"""
Settings API client for Jimbo's sandbox.

Fetches settings from jimbo-api and returns values for use by other scripts.

Python 3.11 stdlib only. No pip dependencies.

Usage:
    python3 /workspace/settings-helper.py get email_fetch_interval_hours
    python3 /workspace/settings-helper.py get email_fetch_interval_hours --default 1
    python3 /workspace/settings-helper.py all
    python3 /workspace/settings-helper.py all --json
"""

import json
import os
import sys
import urllib.request
import urllib.error


API_URL = os.environ.get("JIMBO_API_URL", "http://localhost:3100")
API_KEY = os.environ.get("JIMBO_API_KEY", os.environ.get("API_KEY", ""))


def fetch_all():
    """Fetch all settings. Returns dict or None on failure."""
    url = f"{API_URL}/api/settings"
    req = urllib.request.Request(
        url,
        headers={"X-API-Key": API_KEY, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return None


def fetch_one(key):
    """Fetch a single setting. Returns value string or None on failure."""
    url = f"{API_URL}/api/settings/{key}"
    req = urllib.request.Request(
        url,
        headers={"X-API-Key": API_KEY, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("value")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return None


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("get", "all"):
        sys.stderr.write("Usage: settings-helper.py {get <key> [--default <val>] | all [--json]}\n")
        sys.exit(1)

    command = sys.argv[1]

    if command == "all":
        settings = fetch_all()
        if settings is None:
            sys.stderr.write("settings-helper.py: failed to fetch settings\n")
            sys.exit(1)
        if "--json" in sys.argv:
            print(json.dumps(settings, indent=2))
        else:
            for key, value in sorted(settings.items()):
                print(f"{key}={value}")

    elif command == "get":
        if len(sys.argv) < 3:
            sys.stderr.write("Usage: settings-helper.py get <key> [--default <val>]\n")
            sys.exit(1)
        key = sys.argv[2]
        default = None
        if "--default" in sys.argv:
            idx = sys.argv.index("--default")
            if idx + 1 < len(sys.argv):
                default = sys.argv[idx + 1]

        value = fetch_one(key)
        if value is None:
            if default is not None:
                print(default)
            else:
                sys.stderr.write(f"settings-helper.py: setting '{key}' not found\n")
                sys.exit(1)
        else:
            print(value)


if __name__ == "__main__":
    main()
