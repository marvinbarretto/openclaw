#!/usr/bin/env python3
"""
Pipeline health checker with positive heartbeat.

Checks that pipeline stages have run recently. Sends a Telegram alert
on failure, and a positive heartbeat message when all is well.

Python 3.11 stdlib only. No pip dependencies.

Usage:
    python3 alert-check.py openclaw   # check gateway is responding
    python3 alert-check.py digest     # check email-digest.json is fresh (<25h)
    python3 alert-check.py briefing   # check experiments API has today's run
    python3 alert-check.py credits    # check OpenRouter credit balance
    python3 alert-check.py model      # check current VPS model from openclaw.json
    python3 alert-check.py status     # combined status (all checks in one message)
"""

import datetime
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error


_script_dir = os.path.dirname(os.path.abspath(__file__))
ALERT_SCRIPT = os.path.join(_script_dir, "alert.py")
CALL_SCRIPT = os.path.join(_script_dir, "alert-call.py")
DIGEST_PATH = os.path.join(_script_dir, "email-digest.json")


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


BRIEFING_GRACE_HOUR = get_setting("briefing_grace_hour_utc", 8)
AFTERNOON_GRACE_HOUR = get_setting("afternoon_briefing_grace_hour_utc", 16)
AFTERNOON_ENABLED = get_setting("afternoon_briefing_enabled", "true").lower() == "true"


def send_alert(message):
    """Send alert via alert.py."""
    subprocess.run([sys.executable, ALERT_SCRIPT, message])


def send_call(message):
    """Escalate to phone call for critical failures."""
    try:
        subprocess.run([sys.executable, CALL_SCRIPT, message], timeout=30)
    except Exception:
        pass


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def check_digest():
    """Check email-digest.json exists and report volume. Returns (ok, summary)."""
    if not os.path.exists(DIGEST_PATH):
        return False, "email-digest.json not found"

    try:
        with open(DIGEST_PATH) as f:
            digest = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return False, f"email-digest.json unreadable: {e}"

    generated_at = digest.get("generated_at")
    if not generated_at:
        return False, "email-digest.json missing generated_at field"

    try:
        gen_time = datetime.datetime.fromisoformat(generated_at)
        if gen_time.tzinfo is None:
            gen_time = gen_time.replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return False, f"email-digest.json has invalid generated_at: {generated_at}"

    email_count = len(digest.get("items", []))
    previous_count = digest.get("previous_count")

    # Enhance with worker output counts if available
    shortlisted = 0
    gems = 0
    try:
        shortlist_path = os.path.join(_script_dir, ".worker-shortlist.json")
        if os.path.exists(shortlist_path):
            with open(shortlist_path) as sf:
                shortlisted = len(json.load(sf).get("shortlist", []))
    except (json.JSONDecodeError, OSError):
        pass
    try:
        gems_path = os.path.join(_script_dir, ".worker-gems.json")
        if os.path.exists(gems_path):
            with open(gems_path) as gf:
                gems = len(json.load(gf).get("gems", []))
    except (json.JSONDecodeError, OSError):
        pass

    if shortlisted > 0 or gems > 0:
        detail = f"{email_count} emails, {shortlisted} shortlisted, {gems} gems"
    elif previous_count is not None:
        new_count = max(0, email_count - previous_count)
        detail = f"{email_count} emails ({new_count} new)"
    else:
        detail = f"{email_count} emails"

    return True, f"digest: {detail}"


def check_briefing():
    """Check experiments API for morning + afternoon briefing-prep pipeline runs. Returns (ok, summary)."""
    current_hour = now_utc().hour
    today = now_utc().strftime("%Y-%m-%d")

    try:
        result = api_request("GET", "/api/experiments?task=briefing-prep&last=50")
        all_runs = result.get("runs", [])
    except Exception as e:
        if current_hour < BRIEFING_GRACE_HOUR:
            return True, "morning: pending"
        return False, f"experiments API unreachable: {e}"

    # Filter to today's runs
    rows = [r for r in all_runs if r.get("timestamp", "").startswith(today)]

    # Classify rows by session — rows without session value count as morning
    morning_rows = [r for r in rows if (r.get("session") or "morning") == "morning"]
    afternoon_rows = [r for r in rows if r.get("session") == "afternoon"]

    parts = []

    # Morning status
    if morning_rows:
        summary_text = morning_rows[-1].get("output_summary") or ""
        if "failed" in summary_text:
            parts.append("morning: partial")
        else:
            parts.append("morning: ran")
    elif current_hour < BRIEFING_GRACE_HOUR:
        parts.append("morning: pending")
    else:
        parts.append("morning: missing")

    # Afternoon status (only if enabled)
    if AFTERNOON_ENABLED:
        if afternoon_rows:
            summary_text = afternoon_rows[-1].get("output_summary") or ""
            if "failed" in summary_text:
                parts.append("afternoon: partial")
            else:
                parts.append("afternoon: ran")
        elif current_hour < AFTERNOON_GRACE_HOUR:
            parts.append("afternoon: pending")
        else:
            parts.append("afternoon: missing")

    any_missing = "missing" in " ".join(parts)
    summary = f"briefing: {' | '.join(parts)}"
    return not any_missing, summary


def check_credits():
    """Check OpenRouter credit usage. Returns (ok, summary)."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return False, "OPENROUTER_API_KEY not set"

    url = "https://openrouter.ai/api/v1/auth/key"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        return False, f"OpenRouter API request failed: {e}"

    info = data.get("data", data)
    usage = info.get("usage")

    if usage is None:
        return False, f"unexpected OpenRouter response: {json.dumps(data)}"

    summary = f"OpenRouter: ${usage:.2f} total"

    # Add today's spend from costs API
    try:
        costs_summary = api_request("GET", "/api/costs/summary?days=1")
        today_cost = costs_summary.get("total_cost", 0)
        if today_cost > 0:
            summary += f", ${today_cost:.2f} today"
    except Exception:
        pass

    return True, summary


def _in_sandbox():
    """Detect if running inside Docker sandbox."""
    return os.path.exists("/.dockerenv") or os.environ.get("container") == "docker"


def check_openclaw():
    """Check OpenClaw gateway is responding. Returns (ok, summary)."""
    if _in_sandbox():
        return True, "gateway: skipped (sandbox)"

    import socket

    host = os.environ.get("OPENCLAW_GATEWAY_HOST", "127.0.0.1")
    port = int(os.environ.get("OPENCLAW_GATEWAY_PORT", "18789"))

    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
        return True, "gateway: up"
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False, "gateway: DOWN (port not responding)"


def check_model():
    """Check the current OpenClaw model from openclaw.json. Returns (ok, summary)."""
    config_path = os.environ.get(
        "OPENCLAW_CONFIG",
        "/home/openclaw/.openclaw/openclaw.json",
    )

    if not os.path.exists(config_path):
        if _in_sandbox():
            return True, "model: skipped (sandbox)"
        return False, "openclaw.json not found"

    try:
        with open(config_path) as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return False, f"openclaw.json unreadable: {e}"

    model = None
    # Try common config paths for the primary model
    for path in [
        lambda c: c.get("model", {}).get("primary"),
        lambda c: c.get("models", {}).get("primary"),
        lambda c: c.get("llm", {}).get("primary"),
    ]:
        try:
            model = path(config)
            if model:
                break
        except (KeyError, TypeError, AttributeError):
            continue

    if not model:
        # Fallback: grep for "primary" key at any depth
        config_str = json.dumps(config)
        match = re.search(r'"primary"\s*:\s*"([^"]+)"', config_str)
        if match:
            model = match.group(1)

    if not model:
        return False, "could not determine current model"

    # Extract short name (last segment after /)
    short_name = model.split("/")[-1] if "/" in model else model

    return True, f"model: {short_name}"


def check_status():
    """Run all checks and return a combined one-line summary."""
    checks = [
        ("openclaw", check_openclaw),
        ("digest", check_digest),
        ("briefing", check_briefing),
        ("credits", check_credits),
        ("model", check_model),
    ]

    parts = []
    any_bad = False
    is_sandbox = _in_sandbox()

    for name, fn in checks:
        # Suppress gateway and model checks entirely in sandbox — they can't
        # read openclaw.json or test the gateway from inside Docker.
        if is_sandbox and name in ("openclaw", "model"):
            continue

        try:
            ok, summary = fn()
        except Exception as e:
            ok, summary = False, f"{name} error: {e}"

        if name in ("credits", "model"):
            icon = "\u2139\ufe0f" if ok else "\u274c"
        elif name == "openclaw":
            icon = "\U0001f99e" if ok else "\u274c"  # 🦞 for gateway
            if not ok:
                any_bad = True
        elif name == "briefing" and ok and "pending" in summary:
            icon = "\u23f3"
        else:
            icon = "\u2705" if ok else "\u274c"
            if not ok:
                any_bad = True

        parts.append(f"{icon} {summary}")

    return not any_bad, " | ".join(parts)


def main():
    commands = ("openclaw", "digest", "briefing", "credits", "model", "status")
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        sys.stderr.write("Usage: python3 alert-check.py {openclaw|digest|briefing|credits|model|status}\n")
        sys.exit(1)

    command = sys.argv[1]

    if command == "status":
        ok, summary = check_status()
    elif command == "digest":
        ok, summary = check_digest()
    elif command == "briefing":
        ok, summary = check_briefing()
    elif command == "credits":
        ok, summary = check_credits()
    elif command == "model":
        ok, summary = check_model()
    elif command == "openclaw":
        ok, summary = check_openclaw()

    timestamp = now_utc().strftime("%H:%M")

    if ok:
        send_alert(f"\u2705 {timestamp} {summary}")
    else:
        send_alert(f"\u274c {timestamp} ALERT: {summary}")

        # Escalate critical failures to phone call
        if command == "openclaw":
            send_call("Jimbo alert: OpenClaw gateway is down. Service may need a restart.")
        elif command == "credits":
            send_call(f"Jimbo alert: budget threshold exceeded. {summary}")

        sys.exit(1)


if __name__ == "__main__":
    main()
