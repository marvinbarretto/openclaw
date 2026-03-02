#!/usr/bin/env python3
"""
Interval-aware email fetch wrapper for cron.

Reads email_fetch_interval_hours from jimbo-api settings, checks digest age,
and runs gmail-helper.py if the digest is stale.

Python 3.11 stdlib only. No pip dependencies.

Environment variables:
    JIMBO_API_URL  — jimbo-api base URL (default: http://localhost:3100)
    JIMBO_API_KEY  — API key for jimbo-api
"""

import datetime
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error

_script_dir = os.path.dirname(os.path.abspath(__file__))
DIGEST_PATH = os.path.join(_script_dir, "email-digest.json")
GMAIL_HELPER = os.path.join(_script_dir, "gmail-helper.py")
ALERT_SCRIPT = os.path.join(_script_dir, "alert.py")

DEFAULT_INTERVAL_HOURS = 1


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def get_interval_from_api():
    """Fetch email_fetch_interval_hours from settings API. Returns hours as int."""
    api_url = os.environ.get("JIMBO_API_URL", "http://localhost:3100")
    api_key = os.environ.get("JIMBO_API_KEY", os.environ.get("API_KEY", ""))

    url = f"{api_url}/api/settings/email_fetch_interval_hours"
    req = urllib.request.Request(
        url,
        headers={
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return int(data.get("value", DEFAULT_INTERVAL_HOURS))
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError, KeyError):
        return DEFAULT_INTERVAL_HOURS


def get_digest_age_hours():
    """Return age of email-digest.json in hours, or None if missing/unreadable."""
    if not os.path.exists(DIGEST_PATH):
        return None

    try:
        with open(DIGEST_PATH) as f:
            digest = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    generated_at = digest.get("generated_at")
    if not generated_at:
        return None

    try:
        gen_time = datetime.datetime.fromisoformat(generated_at)
        if gen_time.tzinfo is None:
            gen_time = gen_time.replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None

    age = now_utc() - gen_time
    return age.total_seconds() / 3600


def get_current_email_count():
    """Return number of items in current digest, or 0 if missing."""
    if not os.path.exists(DIGEST_PATH):
        return 0
    try:
        with open(DIGEST_PATH) as f:
            digest = json.load(f)
        return len(digest.get("items", []))
    except (json.JSONDecodeError, OSError):
        return 0


def inject_previous_count(count):
    """Read the digest file and add previous_count field."""
    if not os.path.exists(DIGEST_PATH):
        return
    try:
        with open(DIGEST_PATH) as f:
            digest = json.load(f)
        digest["previous_count"] = count
        with open(DIGEST_PATH, "w") as f:
            json.dump(digest, f, indent=2)
    except (json.JSONDecodeError, OSError):
        pass


def send_alert(message):
    """Send alert via alert.py."""
    subprocess.run([sys.executable, ALERT_SCRIPT, message])


def main():
    interval = get_interval_from_api()
    age = get_digest_age_hours()

    if age is not None and age < interval:
        # Digest is fresh enough, skip
        return

    # Record current count before fetch overwrites
    previous_count = get_current_email_count()

    # Run gmail-helper.py fetch
    result = subprocess.run(
        [sys.executable, GMAIL_HELPER, "fetch", "--hours", str(min(interval * 2, 48))],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        send_alert(f"email-fetch-cron FAILED: {result.stderr[:200]}")
        sys.exit(1)

    # Inject previous_count into the new digest
    inject_previous_count(previous_count)


if __name__ == "__main__":
    main()
