#!/usr/bin/env python3
"""
Twilio phone call alert for critical Jimbo failures.

Makes an actual phone call via Twilio REST API with TTS message.
Use for escalation-tier alerts only (both briefings failed, gateway down,
budget blown). Exits silently if env vars are missing.

60-minute cooldown prevents repeated calls if checker runs in a loop.

Python 3.11 stdlib only. No pip dependencies.

Usage:
    python3 alert-call.py "Both briefing pipelines failed today"
"""

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


COOLDOWN_FILE = "/tmp/.alert-call-last"
COOLDOWN_SECONDS = 3600  # 60 minutes


def _check_cooldown():
    """Return True if cooldown has elapsed (ok to call)."""
    try:
        with open(COOLDOWN_FILE) as f:
            last_call = float(f.read().strip())
        return (time.time() - last_call) >= COOLDOWN_SECONDS
    except (FileNotFoundError, ValueError):
        return True


def _set_cooldown():
    """Record current time as last call."""
    try:
        with open(COOLDOWN_FILE, "w") as f:
            f.write(str(time.time()))
    except OSError:
        pass


def make_call(message):
    """Make a phone call via Twilio REST API. Returns (status, detail)."""
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_FROM_NUMBER")
    to_number = os.environ.get("TWILIO_TO_NUMBER")

    if not all([account_sid, auth_token, from_number, to_number]):
        sys.stderr.write("alert-call.py: TWILIO env vars not set, skipping\n")
        return "skipped", "missing env vars"

    if not _check_cooldown():
        sys.stderr.write("alert-call.py: cooldown active, skipping\n")
        return "skipped", "cooldown active"

    # Build TwiML for text-to-speech
    twiml = f'<Response><Say voice="alice">{message}</Say></Response>'

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"

    # Basic auth header
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()

    data = urllib.parse.urlencode({
        "To": to_number,
        "From": from_number,
        "Twiml": twiml,
    }).encode()

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
            _set_cooldown()
            return "called", body.get("sid", "ok")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        sys.stderr.write(f"alert-call.py: Twilio API error {e.code}: {error_body}\n")
        return "error", f"HTTP {e.code}"
    except (urllib.error.URLError, OSError) as e:
        sys.stderr.write(f"alert-call.py: failed to make call: {e}\n")
        return "error", str(e)


def main():
    if len(sys.argv) < 2:
        sys.stderr.write('Usage: python3 alert-call.py "message text"\n')
        sys.exit(1)

    message = " ".join(sys.argv[1:])
    status, detail = make_call(message)
    print(json.dumps({"status": status, "detail": detail, "message": message}))


if __name__ == "__main__":
    main()
