#!/usr/bin/env python3
"""
Telegram alert sender for Jimbo's pipeline.

Sends a message via the Telegram Bot API. Exits silently if env vars
are missing (avoids cascading failures when alerting itself breaks).

Python 3.11 stdlib only. No pip dependencies.

Usage:
    python3 alert.py "06:00 email fetch FAILED"
    python3 alert.py "briefing ran successfully — 3 gems extracted"
"""

import json
import os
import sys
import urllib.request
import urllib.error


def send_telegram(message):
    """Send a message via Telegram Bot API. Returns True on success."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        sys.stderr.write("alert.py: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set, skipping\n")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": message}).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        sys.stderr.write(f"alert.py: failed to send Telegram message: {e}\n")
        return False


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: python3 alert.py \"message text\"\n")
        sys.exit(1)

    message = " ".join(sys.argv[1:])
    ok = send_telegram(message)
    if ok:
        print(json.dumps({"status": "sent", "message": message}))
    else:
        print(json.dumps({"status": "skipped", "message": message}))


if __name__ == "__main__":
    main()
