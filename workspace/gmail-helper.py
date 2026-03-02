#!/usr/bin/env python3
"""
Gmail API client for Jimbo's sandbox.

Fetches emails via Gmail API, applies a rules-based blacklist to remove junk,
and writes a structured digest to /workspace/email-digest.json. No LLM
classification — Jimbo reads the raw emails and applies his own judgment.

Python 3.11 stdlib only. Reads credentials from environment variables
(same OAuth credentials as calendar-helper.py — just needs wider scopes).

Environment variables:
    GOOGLE_CALENDAR_CLIENT_ID      — OAuth client ID
    GOOGLE_CALENDAR_CLIENT_SECRET  — OAuth client secret
    GOOGLE_CALENDAR_REFRESH_TOKEN  — OAuth refresh token (with gmail.readonly scope)

Usage:
    python3 gmail-helper.py fetch --hours 24
    python3 gmail-helper.py fetch --hours 48 --no-filter
    python3 gmail-helper.py fetch --hours 24 --limit 50
"""

import argparse
import base64
import datetime
import hashlib
import html.parser
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

GMAIL_API = "https://gmail.googleapis.com/gmail/v1"
TOKEN_URL = "https://oauth2.googleapis.com/token"
# Write output next to this script (works in sandbox /workspace/ and on laptop)
_script_dir = os.path.dirname(os.path.abspath(__file__))
TOKEN_CACHE = os.path.join(_script_dir, ".gmail-access-token.json")
OUTPUT_PATH = os.path.join(_script_dir, "email-digest.json")
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


MAX_BODY_LENGTH = get_setting("email_body_max_length", 5000)
SNIPPET_LENGTH = 200  # keep hardcoded, not worth a setting
MAX_LINKS = get_setting("email_max_links", 20)

# ---------------------------------------------------------------------------
# Blacklist — rules-based, no LLM. Easy to grow over time.
# ---------------------------------------------------------------------------

SENDER_BLACKLIST = [
    # Receipts & orders
    "noreply@uber.com", "noreply@ubereats.com",
    "auto-confirm@amazon.co.uk", "order-update@amazon.co.uk",
    "noreply@deliveroo.co.uk", "noreply@justeat.com",
    "shipment-tracking@amazon.co.uk", "digital-no-reply@amazon.co.uk",
    # Retail spam
    "@marketing.sainsburys.co.uk", "@email.tesco.com",
    "@mail.boots.com", "@email.argos.co.uk",
    "@email.hm.com", "@email.asos.com",
    "@email.nike.com", "@email.adidas.co.uk",
    # Loyalty & points
    "@starbucks.co.uk", "@costa.co.uk",
    "@email.nectar.com", "@clubcard.tesco.com",
    # Social media notifications
    "@linkedin.com", "@facebookmail.com",
    "@info.nextdoor.com", "@twitter.com", "@x.com",
    # GitHub notifications
    "notifications@github.com",
    # Generic noreply / account stuff
    "no-reply@accounts.google.com",
    "noreply@notify.google.com",
    "noreply@medium.com",
]

SUBJECT_BLACKLIST = [
    "your order", "order confirmation", "delivery update",
    "out for delivery", "your receipt", "payment received",
    "unsubscribe confirmation", "privacy policy update",
    "rate your experience", "how did we do",
    "your password", "verify your email", "confirm your email",
    "security alert", "sign-in attempt",
]

# ---------------------------------------------------------------------------
# HTML stripping
# ---------------------------------------------------------------------------

class HTMLTextExtractor(html.parser.HTMLParser):
    """Strip HTML tags and extract plain text."""

    def __init__(self):
        super().__init__()
        self._text = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False
        if tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._text.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self._text.append(data)

    def get_text(self):
        return "".join(self._text)


def strip_html(html_text):
    """Convert HTML to plain text."""
    parser = HTMLTextExtractor()
    try:
        parser.feed(html_text)
        text = parser.get_text()
    except Exception:
        # Fallback: crude regex strip
        text = re.sub(r"<[^>]+>", " ", html_text)
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Link extraction
# ---------------------------------------------------------------------------

def extract_links(text):
    """Extract URLs from text."""
    url_pattern = re.compile(r'https?://[^\s<>"\')\]]+')
    links = url_pattern.findall(text)
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for link in links:
        # Clean trailing punctuation
        link = link.rstrip(".,;:!?")
        if link not in seen:
            seen.add(link)
            unique.append(link)
    return unique


# ---------------------------------------------------------------------------
# OAuth token management (same pattern as calendar-helper.py)
# ---------------------------------------------------------------------------

def get_env(name):
    val = os.environ.get(name)
    if not val:
        print(f"ERROR: {name} environment variable not set", file=sys.stderr)
        sys.exit(1)
    return val


def refresh_access_token(client_id, client_secret, refresh_token):
    """Get a fresh access token, using cache if still valid."""
    if os.path.exists(TOKEN_CACHE):
        try:
            with open(TOKEN_CACHE) as f:
                cached = json.load(f)
            expires_at = cached.get("expires_at", 0)
            if datetime.datetime.now(datetime.timezone.utc).timestamp() < expires_at - 60:
                return cached["access_token"]
        except (json.JSONDecodeError, KeyError):
            pass

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
        if e.code in (400, 401):
            print("The refresh token may be expired or missing gmail.readonly scope.", file=sys.stderr)
            print("Ask Marvin to re-run google-auth.py.", file=sys.stderr)
        sys.exit(1)

    expires_at = datetime.datetime.now(datetime.timezone.utc).timestamp() + tokens.get("expires_in", 3600)
    cache_data = {
        "access_token": tokens["access_token"],
        "expires_at": expires_at,
    }
    try:
        with open(TOKEN_CACHE, "w") as f:
            json.dump(cache_data, f)
    except OSError:
        pass

    return tokens["access_token"]


# ---------------------------------------------------------------------------
# Gmail API helpers
# ---------------------------------------------------------------------------

def gmail_request(access_token, path, method="GET"):
    """Make an authenticated request to the Gmail API."""
    url = f"{GMAIL_API}/{path}"
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {access_token}")

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"ERROR: Gmail API ({e.code}): {error_body}", file=sys.stderr)
        sys.exit(1)


def list_message_ids(access_token, hours, limit=None):
    """List message IDs from the last N hours."""
    query = f"newer_than:{hours}h"
    encoded_query = urllib.parse.quote(query)
    max_results = min(limit, 500) if limit else 500

    all_ids = []
    page_token = None

    while True:
        path = f"users/me/messages?q={encoded_query}&maxResults={max_results}"
        if page_token:
            path += f"&pageToken={page_token}"

        result = gmail_request(access_token, path)
        messages = result.get("messages", [])
        all_ids.extend(msg["id"] for msg in messages)

        if limit and len(all_ids) >= limit:
            all_ids = all_ids[:limit]
            break

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return all_ids


def get_message(access_token, msg_id):
    """Fetch a full message by ID."""
    path = f"users/me/messages/{msg_id}?format=full"
    return gmail_request(access_token, path)


def extract_header(headers, name):
    """Extract a header value by name (case-insensitive)."""
    name_lower = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name_lower:
            return h.get("value", "")
    return ""


def parse_sender(from_header):
    """Parse 'Name <email>' into {name, email}."""
    match = re.match(r'^"?([^"<]*)"?\s*<?([^>]+)>?$', from_header.strip())
    if match:
        name = match.group(1).strip().strip('"')
        email = match.group(2).strip()
        return {"name": name, "email": email}
    return {"name": "", "email": from_header.strip()}


def decode_body_part(part):
    """Decode a MIME part body from base64url."""
    body_data = part.get("body", {}).get("data", "")
    if not body_data:
        return ""
    try:
        # Gmail uses URL-safe base64
        decoded = base64.urlsafe_b64decode(body_data + "==")
        return decoded.decode("utf-8", errors="replace")
    except Exception:
        return ""


def extract_body(payload):
    """Extract plain text body from a Gmail message payload.

    Prefers text/plain. Falls back to text/html (stripped).
    Recurses into multipart messages.
    """
    mime_type = payload.get("mimeType", "")
    parts = payload.get("parts", [])

    # Simple single-part message
    if not parts:
        text = decode_body_part(payload)
        if "html" in mime_type:
            return strip_html(text)
        return text

    # Multipart: look for text/plain first, then text/html
    plain_text = ""
    html_text = ""

    for part in parts:
        part_mime = part.get("mimeType", "")
        if part_mime == "text/plain":
            plain_text = decode_body_part(part)
        elif part_mime == "text/html":
            html_text = decode_body_part(part)
        elif part_mime.startswith("multipart/"):
            # Recurse into nested multipart
            nested = extract_body(part)
            if nested and not plain_text:
                plain_text = nested

    if plain_text:
        return plain_text
    if html_text:
        return strip_html(html_text)
    return ""


def parse_message(raw_msg):
    """Parse a raw Gmail API message into our digest format."""
    headers = raw_msg.get("payload", {}).get("headers", [])
    labels = raw_msg.get("labelIds", [])

    from_header = extract_header(headers, "From")
    sender = parse_sender(from_header)
    subject = extract_header(headers, "Subject")
    date = extract_header(headers, "Date")

    body = extract_body(raw_msg.get("payload", {}))
    body_truncated = body[:MAX_BODY_LENGTH] if body else ""
    body_snippet = body[:SNIPPET_LENGTH] if body else ""

    # Extract links from full body (before truncation)
    links = extract_links(body) if body else []

    # Generate a stable short ID
    short_id = "msg_" + hashlib.md5(raw_msg["id"].encode()).hexdigest()[:12]

    return {
        "id": short_id,
        "gmail_id": raw_msg["id"],
        "date": date,
        "sender": sender,
        "subject": subject,
        "body": body_truncated,
        "body_snippet": body_snippet,
        "links": links[:MAX_LINKS],
        "labels": labels,
    }


# ---------------------------------------------------------------------------
# Blacklist filtering
# ---------------------------------------------------------------------------

def is_blacklisted(item):
    """Check if an email matches the blacklist rules."""
    email = item["sender"]["email"].lower()
    subject = item["subject"].lower()

    # Check sender blacklist
    for pattern in SENDER_BLACKLIST:
        pattern_lower = pattern.lower()
        if pattern_lower.startswith("@"):
            # Domain match
            if email.endswith(pattern_lower):
                return True
        else:
            # Exact email match
            if email == pattern_lower:
                return True

    # Check subject blacklist
    for phrase in SUBJECT_BLACKLIST:
        if phrase.lower() in subject:
            return True

    return False


# ---------------------------------------------------------------------------
# Main fetch command
# ---------------------------------------------------------------------------

def cmd_fetch(access_token, args):
    """Fetch emails, apply blacklist, write digest."""
    print(f"Fetching emails from last {args.hours} hours...", file=sys.stderr)

    # Step 1: List message IDs
    msg_ids = list_message_ids(access_token, args.hours, limit=args.limit)
    print(f"Found {len(msg_ids)} messages", file=sys.stderr)

    if not msg_ids:
        digest = {
            "date": datetime.date.today().isoformat(),
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "total_items": 0,
            "filtered_count": 0,
            "items": [],
            "stats": {
                "total_fetched": 0,
                "blacklist_filtered": 0,
                "items_kept": 0,
            },
        }
        with open(OUTPUT_PATH, "w") as f:
            json.dump(digest, f, indent=2)
        print(f"No emails found. Empty digest written to {OUTPUT_PATH}", file=sys.stderr)
        print(json.dumps({"status": "ok", "total": 0, "kept": 0, "filtered": 0}))
        return

    # Step 2: Fetch each message
    items = []
    for i, msg_id in enumerate(msg_ids):
        if (i + 1) % 25 == 0:
            print(f"  Fetching {i + 1}/{len(msg_ids)}...", file=sys.stderr)
        try:
            raw_msg = get_message(access_token, msg_id)
            item = parse_message(raw_msg)
            items.append(item)
        except Exception as e:
            print(f"  WARNING: Failed to fetch message {msg_id}: {e}", file=sys.stderr)
            continue

    print(f"Fetched {len(items)} messages", file=sys.stderr)

    # Step 3: Apply blacklist (unless --no-filter)
    if args.no_filter:
        filtered_count = 0
        kept_items = items
        print("Blacklist bypassed (--no-filter)", file=sys.stderr)
    else:
        kept_items = []
        filtered_count = 0
        for item in items:
            if is_blacklisted(item):
                filtered_count += 1
            else:
                kept_items.append(item)
        print(f"Blacklist filtered: {filtered_count}, kept: {len(kept_items)}", file=sys.stderr)

    # Step 4: Write digest
    digest = {
        "date": datetime.date.today().isoformat(),
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_items": len(kept_items),
        "filtered_count": filtered_count,
        "items": kept_items,
        "stats": {
            "total_fetched": len(items),
            "blacklist_filtered": filtered_count,
            "items_kept": len(kept_items),
        },
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(digest, f, indent=2, ensure_ascii=False)

    print(f"Digest written to {OUTPUT_PATH}", file=sys.stderr)

    # JSON summary to stdout (for Jimbo to read)
    print(json.dumps({
        "status": "ok",
        "total": len(items),
        "kept": len(kept_items),
        "filtered": filtered_count,
        "output": OUTPUT_PATH,
    }))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Gmail helper for Jimbo")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # fetch
    fetch_parser = subparsers.add_parser("fetch", help="Fetch emails and write digest")
    fetch_parser.add_argument("--hours", type=int, default=24, help="Look back N hours (default: 24)")
    fetch_parser.add_argument("--limit", type=int, default=None, help="Max emails to fetch")
    fetch_parser.add_argument("--no-filter", action="store_true", help="Bypass blacklist filter")

    args = parser.parse_args()

    # Get credentials from env (same env vars as calendar-helper.py)
    client_id = get_env("GOOGLE_CALENDAR_CLIENT_ID")
    client_secret = get_env("GOOGLE_CALENDAR_CLIENT_SECRET")
    refresh_token = get_env("GOOGLE_CALENDAR_REFRESH_TOKEN")

    access_token = refresh_access_token(client_id, client_secret, refresh_token)

    commands = {
        "fetch": cmd_fetch,
    }
    commands[args.command](access_token, args)


if __name__ == "__main__":
    main()
