#!/usr/bin/env python3
"""
Google Calendar API client for Jimbo's sandbox.

Python 3.11 stdlib only. Reads credentials from environment variables.
Outputs JSON to stdout, errors to stderr.

Environment variables:
    GOOGLE_CALENDAR_CLIENT_ID      — OAuth client ID
    GOOGLE_CALENDAR_CLIENT_SECRET  — OAuth client secret
    GOOGLE_CALENDAR_REFRESH_TOKEN  — OAuth refresh token

Usage:
    python3 calendar-helper.py list-calendars
    python3 calendar-helper.py list-events --days 7
    python3 calendar-helper.py list-events --days 1 --calendar-id someone@gmail.com
    python3 calendar-helper.py check-conflicts --start 2026-02-20T14:00:00 --end 2026-02-20T15:00:00
    python3 calendar-helper.py create-event --summary "Review PRs" --start 2026-02-21T15:00:00 --end 2026-02-21T15:30:00
    python3 calendar-helper.py create-event --summary "Lunch" --start 2026-02-21T12:00:00 --end 2026-02-21T13:00:00 --attendee marvin@example.com
    python3 calendar-helper.py create-calendar --summary "Jimbo Suggestions"
    python3 calendar-helper.py share-calendar --calendar-id CALENDAR_ID --email marvin@example.com
"""

import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

CALENDAR_API = "https://www.googleapis.com/calendar/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"
TOKEN_CACHE = "/workspace/.calendar-access-token.json"
DEFAULT_TZ = "Europe/London"


def get_env(name):
    val = os.environ.get(name)
    if not val:
        print(f"ERROR: {name} environment variable not set", file=sys.stderr)
        sys.exit(1)
    return val


def refresh_access_token(client_id, client_secret, refresh_token):
    """Get a fresh access token, using cache if still valid."""
    # Check cache
    if os.path.exists(TOKEN_CACHE):
        try:
            with open(TOKEN_CACHE) as f:
                cached = json.load(f)
            expires_at = cached.get("expires_at", 0)
            if datetime.datetime.now(datetime.timezone.utc).timestamp() < expires_at - 60:
                return cached["access_token"]
        except (json.JSONDecodeError, KeyError):
            pass

    # Refresh
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode()

    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req) as resp:
            tokens = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"ERROR: Token refresh failed ({e.code}): {body}", file=sys.stderr)
        if e.code == 400 or e.code == 401:
            print("The refresh token may be expired. Ask Marvin to re-run calendar-auth.py.", file=sys.stderr)
        sys.exit(1)

    # Cache with expiry
    expires_at = datetime.datetime.now(datetime.timezone.utc).timestamp() + tokens.get("expires_in", 3600)
    cache_data = {
        "access_token": tokens["access_token"],
        "expires_at": expires_at,
    }
    try:
        with open(TOKEN_CACHE, "w") as f:
            json.dump(cache_data, f)
    except OSError:
        pass  # non-fatal — token still works, just won't be cached

    return tokens["access_token"]


def api_request(access_token, path, method="GET", body=None):
    """Make an authenticated request to the Calendar API."""
    url = f"{CALENDAR_API}/{path}"
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {access_token}")

    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(body).encode()

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"ERROR: Calendar API ({e.code}): {error_body}", file=sys.stderr)
        sys.exit(1)


def cmd_list_calendars(access_token, _args):
    """List all visible calendars."""
    result = api_request(access_token, "users/me/calendarList")
    calendars = []
    for cal in result.get("items", []):
        calendars.append({
            "id": cal["id"],
            "summary": cal.get("summary", "(no name)"),
            "access_role": cal.get("accessRole", "unknown"),
            "primary": cal.get("primary", False),
        })
    print(json.dumps(calendars, indent=2))


def cmd_list_events(access_token, args):
    """List upcoming events, optionally from a specific calendar."""
    now = datetime.datetime.now(datetime.timezone.utc)
    end = now + datetime.timedelta(days=args.days)

    time_min = now.isoformat()
    time_max = end.isoformat()

    calendar_ids = [args.calendar_id] if args.calendar_id else None

    # If no calendar specified, get calendars (optionally filtered)
    if calendar_ids is None:
        cal_list = api_request(access_token, "users/me/calendarList")
        if args.primary_only:
            calendar_ids = [
                c["id"] for c in cal_list.get("items", [])
                if c.get("primary") or c.get("accessRole") == "owner"
            ]
        else:
            calendar_ids = [c["id"] for c in cal_list.get("items", [])]

    all_events = []
    for cal_id in calendar_ids:
        encoded_id = urllib.parse.quote(cal_id, safe="")
        params = urllib.parse.urlencode({
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 100,
            "timeZone": DEFAULT_TZ,
        })
        result = api_request(access_token, f"calendars/{encoded_id}/events?{params}")
        for event in result.get("items", []):
            summary = event.get("summary", "(no title)")

            # Skip cancelled events
            if event.get("status") == "cancelled":
                continue
            if "CANCELED" in summary.upper():
                continue

            start_raw = event.get("start", {})
            end_raw = event.get("end", {})
            start_val = start_raw.get("dateTime", start_raw.get("date", ""))
            end_val = end_raw.get("dateTime", end_raw.get("date", ""))

            # Skip multi-day all-day events (exhibitions, festivals)
            is_all_day = "date" in start_raw and "dateTime" not in start_raw
            if is_all_day and start_val and end_val:
                try:
                    s = datetime.date.fromisoformat(start_val)
                    e = datetime.date.fromisoformat(end_val)
                    if (e - s).days > 1:
                        continue
                except ValueError:
                    pass

            all_events.append({
                "calendar": cal_id,
                "summary": summary,
                "start": start_val,
                "end": end_val,
                "location": event.get("location", ""),
                "status": event.get("status", ""),
                "html_link": event.get("htmlLink", ""),
            })

    # Sort by start time
    all_events.sort(key=lambda e: e["start"])
    print(json.dumps(all_events, indent=2))


def cmd_check_conflicts(access_token, args):
    """Check for conflicts in a proposed time window across all calendars."""
    cal_list = api_request(access_token, "users/me/calendarList")
    calendar_ids = [c["id"] for c in cal_list.get("items", [])]

    # Ensure ISO format with timezone
    start = args.start
    end = args.end
    if "T" in start and "+" not in start and "Z" not in start:
        start += "+00:00"
    if "T" in end and "+" not in end and "Z" not in end:
        end += "+00:00"

    # Use freebusy API
    body = {
        "timeMin": start,
        "timeMax": end,
        "timeZone": DEFAULT_TZ,
        "items": [{"id": cid} for cid in calendar_ids],
    }
    result = api_request(access_token, "freeBusy", method="POST", body=body)

    conflicts = []
    for cal_id, data in result.get("calendars", {}).items():
        for busy in data.get("busy", []):
            conflicts.append({
                "calendar": cal_id,
                "start": busy["start"],
                "end": busy["end"],
            })

    conflicts.sort(key=lambda c: c["start"])
    output = {
        "requested_start": args.start,
        "requested_end": args.end,
        "has_conflicts": len(conflicts) > 0,
        "conflicts": conflicts,
    }
    print(json.dumps(output, indent=2))


def cmd_create_event(access_token, args):
    """Create an event on a specified calendar (defaults to primary)."""
    event = {
        "summary": args.summary,
        "start": {
            "dateTime": args.start if "T" in args.start else None,
            "date": args.start if "T" not in args.start else None,
            "timeZone": DEFAULT_TZ,
        },
        "end": {
            "dateTime": args.end if "T" in args.end else None,
            "date": args.end if "T" not in args.end else None,
            "timeZone": DEFAULT_TZ,
        },
    }

    # Clean up null fields
    event["start"] = {k: v for k, v in event["start"].items() if v is not None}
    event["end"] = {k: v for k, v in event["end"].items() if v is not None}

    if args.description:
        event["description"] = args.description

    if args.attendee:
        event["attendees"] = [{"email": args.attendee}]

    # Create on specified calendar, or primary by default
    cal_id = args.calendar_id if args.calendar_id else "primary"
    encoded_cal = urllib.parse.quote(cal_id, safe="")
    result = api_request(access_token, f"calendars/{encoded_cal}/events", method="POST", body=event)

    output = {
        "created": True,
        "id": result.get("id", ""),
        "summary": result.get("summary", ""),
        "start": result.get("start", {}),
        "end": result.get("end", {}),
        "html_link": result.get("htmlLink", ""),
    }
    print(json.dumps(output, indent=2))


def cmd_subscribe(access_token, args):
    """Subscribe to a calendar by ID (adds it to Jimbo's calendar list)."""
    body = {"id": args.calendar_id}
    result = api_request(access_token, "users/me/calendarList", method="POST", body=body)
    output = {
        "subscribed": True,
        "id": result.get("id", ""),
        "summary": result.get("summary", "(no name)"),
        "access_role": result.get("accessRole", "unknown"),
    }
    print(json.dumps(output, indent=2))


def cmd_create_calendar(access_token, args):
    """Create a new secondary calendar."""
    body = {
        "summary": args.summary,
        "timeZone": DEFAULT_TZ,
    }
    if args.description:
        body["description"] = args.description

    result = api_request(access_token, "calendars", method="POST", body=body)
    output = {
        "created": True,
        "id": result.get("id", ""),
        "summary": result.get("summary", ""),
    }
    print(json.dumps(output, indent=2))


def cmd_share_calendar(access_token, args):
    """Share a calendar with another user (reader access)."""
    encoded_id = urllib.parse.quote(args.calendar_id, safe="")
    body = {
        "role": args.role,
        "scope": {
            "type": "user",
            "value": args.email,
        },
    }
    result = api_request(access_token, f"calendars/{encoded_id}/acl", method="POST", body=body)
    output = {
        "shared": True,
        "calendar_id": args.calendar_id,
        "email": args.email,
        "role": result.get("role", ""),
    }
    print(json.dumps(output, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Google Calendar helper for Jimbo")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list-calendars
    subparsers.add_parser("list-calendars", help="List all visible calendars")

    # list-events
    le = subparsers.add_parser("list-events", help="List upcoming events")
    le.add_argument("--days", type=int, default=1, help="Number of days ahead (default: 1)")
    le.add_argument("--calendar-id", default=None, help="Specific calendar ID (default: all)")
    le.add_argument("--primary-only", action="store_true", help="Only owner/primary calendars (skip subscribed feeds)")

    # check-conflicts
    cc = subparsers.add_parser("check-conflicts", help="Check for scheduling conflicts")
    cc.add_argument("--start", required=True, help="Start time (ISO 8601)")
    cc.add_argument("--end", required=True, help="End time (ISO 8601)")

    # create-event
    ce = subparsers.add_parser("create-event", help="Create event on Jimbo's calendar")
    ce.add_argument("--summary", required=True, help="Event title")
    ce.add_argument("--start", required=True, help="Start time (ISO 8601)")
    ce.add_argument("--end", required=True, help="End time (ISO 8601)")
    ce.add_argument("--description", default=None, help="Event description")
    ce.add_argument("--attendee", default=None, help="Email address to invite")
    ce.add_argument("--calendar-id", default=None, help="Target calendar ID (default: primary)")

    # subscribe
    sub = subparsers.add_parser("subscribe", help="Subscribe to a shared calendar")
    sub.add_argument("--calendar-id", required=True, help="Calendar ID (usually an email address)")

    # create-calendar
    ccal = subparsers.add_parser("create-calendar", help="Create a new secondary calendar")
    ccal.add_argument("--summary", required=True, help="Calendar name")
    ccal.add_argument("--description", default=None, help="Calendar description")

    # share-calendar
    sc = subparsers.add_parser("share-calendar", help="Share a calendar with another user")
    sc.add_argument("--calendar-id", required=True, help="Calendar ID to share")
    sc.add_argument("--email", required=True, help="Email address to share with")
    sc.add_argument("--role", default="reader", help="Access role: reader (default) or writer")

    args = parser.parse_args()

    # Get credentials from env
    client_id = get_env("GOOGLE_CALENDAR_CLIENT_ID")
    client_secret = get_env("GOOGLE_CALENDAR_CLIENT_SECRET")
    refresh_token = get_env("GOOGLE_CALENDAR_REFRESH_TOKEN")

    access_token = refresh_access_token(client_id, client_secret, refresh_token)

    commands = {
        "list-calendars": cmd_list_calendars,
        "list-events": cmd_list_events,
        "check-conflicts": cmd_check_conflicts,
        "create-event": cmd_create_event,
        "subscribe": cmd_subscribe,
        "create-calendar": cmd_create_calendar,
        "share-calendar": cmd_share_calendar,
    }
    commands[args.command](access_token, args)


if __name__ == "__main__":
    main()
