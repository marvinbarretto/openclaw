#!/usr/bin/env python3
"""Sift v0.1 — Offline email classification pipeline.

Reads a Maildir, classifies each email via Ollama (qwen2.5:7b),
and outputs a structured email-digest.json.

Usage:
    python scripts/sift-classify.py
    python scripts/sift-classify.py --input data/sample-maildir --output data/email-digest.json
    python scripts/sift-classify.py --hours 48
"""

import argparse
import email
import email.utils
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

OLLAMA_MODEL = "qwen2.5:7b"
BODY_SNIPPET_LEN = 200
BODY_MAX_CHARS = 2000
VALID_CATEGORIES = {"newsletter", "tech", "local", "deals", "event", "transactional", "health", "other"}
VALID_ACTIONS = {"queue", "skip", "unsubscribe_candidate"}
VALID_PROJECTS = {"spoons", "localshout", "pomodoro", None}

CLASSIFICATION_PROMPT = """\
You are an email classifier. Analyse this email and return a JSON classification.

Email:
From: {sender_name} <{sender_email}>
Subject: {subject}
Date: {date}
Body:
{body_snippet}

The user's projects:
- Spoons: gamified pub check-in app (Angular 20, Firebase, Capacitor)
- LocalShout: local community platform (Next.js)
- Pomodoro: productivity timer

The user's interests: tech, local community (Watford/South Oxhey area), travel, health/nutrition, finance, current affairs

Categories (pick exactly one): newsletter, tech, local, deals, event, transactional, health, other
- newsletter: content digests, subscriber emails (Must Reads, The Neuron, Milk Road, etc)
- tech: developer content, tools, frameworks (Apple Developer, Frontend Masters)
- local: community, neighbourhood (Watford, South Oxhey, Urban Scoop)
- deals: shopping, travel, money saving (HolidayPirates, Google Flights, MSE)
- event: events, meetups, tickets (Fever, parkrun)
- transactional: order confirmations, notifications (Wetherspoon, LinkedIn, Airbnb)
- health: health, fitness, nutrition (ZOE)
- other: anything that doesn't fit above

Suggested actions: queue (worth reading), skip (not worth time), unsubscribe_candidate (recurring low value)

Return JSON with: category, subcategory (1-2 words), keywords (list of 3), summary (1-2 sentences), time_estimate_min (integer), project_relevance (spoons/localshout/pomodoro or null), suggested_action, confidence (0.0-1.0)"""


def parse_maildir_message(filepath):
    """Parse a single Maildir email file, return extracted fields or None."""
    try:
        raw = filepath.read_text(errors="replace")
    except Exception:
        return None

    msg = email.message_from_string(raw)

    # Sender
    from_header = msg.get("From", "")
    sender_name, sender_email_addr = email.utils.parseaddr(from_header)
    if not sender_email_addr:
        return None

    # Date
    date_header = msg.get("Date", "")
    try:
        date_tuple = email.utils.parsedate_to_datetime(date_header)
    except Exception:
        date_tuple = datetime.now(timezone.utc)

    # Subject
    subject = msg.get("Subject", "(no subject)")

    # Message-ID for stable ID
    message_id = msg.get("Message-ID", "")
    msg_hash = hashlib.sha256(
        (message_id or f"{sender_email_addr}:{subject}:{date_header}").encode()
    ).hexdigest()[:12]
    stable_id = f"msg_{msg_hash}"

    # Body — prefer plain text
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(errors="replace")
                    break
            elif ct == "text/html" and not body:
                payload = part.get_payload(decode=True)
                if payload:
                    body = strip_html(payload.decode(errors="replace"))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            ct = msg.get_content_type()
            decoded = payload.decode(errors="replace")
            body = strip_html(decoded) if ct == "text/html" else decoded

    # Extract links before truncating
    links = extract_links(body)

    # Truncate body for Ollama
    body_for_llm = body[:BODY_MAX_CHARS].strip()
    body_snippet = body[:BODY_SNIPPET_LEN].strip()

    return {
        "id": stable_id,
        "date": date_tuple.isoformat(),
        "sender": {"name": sender_name or sender_email_addr.split("@")[0], "email": sender_email_addr},
        "subject": subject,
        "body_for_llm": body_for_llm,
        "body_snippet": body_snippet,
        "links": links,
    }


def strip_html(text):
    """Rough HTML tag stripping — stdlib only."""
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_links(text):
    """Pull URLs from text."""
    return re.findall(r"https?://[^\s<>\"')\]]+", text)


OLLAMA_URL = "http://localhost:11434/api/generate"


def classify_email(parsed, model=OLLAMA_MODEL):
    """Call Ollama HTTP API to classify a single email. Returns classification dict."""
    prompt = CLASSIFICATION_PROMPT.format(
        sender_name=parsed["sender"]["name"],
        sender_email=parsed["sender"]["email"],
        subject=parsed["subject"],
        date=parsed["date"],
        body_snippet=parsed["body_for_llm"],
    )

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "format": "json",
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode())
            raw_output = data.get("response", "")
    except Exception as e:
        print(f"  ERROR calling Ollama: {e}", file=sys.stderr)
        return fallback_classification()

    return parse_classification(raw_output)


def parse_classification(raw):
    """Extract JSON from Ollama output, with fallback."""
    # Try to find JSON in the output (model might wrap in markdown etc)
    json_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if not json_match:
        print(f"  WARNING: no JSON found in response", file=sys.stderr)
        return fallback_classification()

    try:
        data = json.loads(json_match.group())
    except json.JSONDecodeError:
        print(f"  WARNING: invalid JSON in response", file=sys.stderr)
        return fallback_classification()

    # Validate and sanitise
    cat = data.get("category", "other")
    if cat not in VALID_CATEGORIES:
        cat = "other"

    action = data.get("suggested_action", "skip")
    if action not in VALID_ACTIONS:
        action = "skip"

    proj = data.get("project_relevance")
    if proj not in VALID_PROJECTS:
        proj = None

    confidence = data.get("confidence", 0.5)
    if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
        confidence = 0.5

    time_est = data.get("time_estimate_min", 1)
    if not isinstance(time_est, (int, float)) or time_est < 0:
        time_est = 1
    time_est = int(time_est)

    keywords = data.get("keywords", [])
    if not isinstance(keywords, list):
        keywords = []
    keywords = [str(k) for k in keywords[:5]]

    return {
        "category": cat,
        "subcategory": str(data.get("subcategory", ""))[:30],
        "keywords": keywords,
        "summary": str(data.get("summary", ""))[:300],
        "time_estimate_min": time_est,
        "project_relevance": proj,
        "suggested_action": action,
        "confidence": round(confidence, 2),
    }


def fallback_classification():
    """Default classification when Ollama fails."""
    return {
        "category": "other",
        "subcategory": "unknown",
        "keywords": [],
        "summary": "Classification failed — review manually.",
        "time_estimate_min": 2,
        "project_relevance": None,
        "suggested_action": "queue",
        "confidence": 0.1,
    }


def collect_emails(maildir_path, hours=24):
    """Read Maildir and return parsed emails from the last N hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    emails = []

    for subdir in ("new", "cur"):
        dirpath = maildir_path / subdir
        if not dirpath.exists():
            continue
        for filepath in dirpath.iterdir():
            if filepath.is_file() and not filepath.name.startswith("."):
                parsed = parse_maildir_message(filepath)
                if parsed:
                    emails.append(parsed)

    # Sort by date descending
    emails.sort(key=lambda e: e["date"], reverse=True)
    return emails


def build_digest(items):
    """Build the final email-digest.json structure."""
    now = datetime.now(timezone.utc)

    # Compute stats
    by_category = {}
    by_action = {}
    total_queue_time = 0

    for item in items:
        cat = item.get("category", "other")
        by_category[cat] = by_category.get(cat, 0) + 1

        action = item.get("suggested_action", "skip")
        by_action[action] = by_action.get(action, 0) + 1

        if action == "queue":
            total_queue_time += item.get("time_estimate_min", 0)

    return {
        "date": now.strftime("%Y-%m-%d"),
        "generated_at": now.isoformat(),
        "total_items": len(items),
        "items": items,
        "stats": {
            "by_category": by_category,
            "by_suggested_action": by_action,
            "total_queue_time_min": total_queue_time,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Sift v0.1 — email classification pipeline")
    parser.add_argument("--input", default="data/sample-maildir", help="Maildir path")
    parser.add_argument("--output", default="data/email-digest.json", help="Output JSON path")
    parser.add_argument("--hours", type=int, default=24, help="Look back N hours (default 24)")
    parser.add_argument("--model", default=OLLAMA_MODEL, help=f"Ollama model (default {OLLAMA_MODEL})")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    maildir_path = repo_root / args.input
    output_path = repo_root / args.output

    if not maildir_path.exists():
        print(f"ERROR: Maildir not found at {maildir_path}", file=sys.stderr)
        print("Run sift-sample.py first to generate test data.", file=sys.stderr)
        sys.exit(1)

    # Collect emails
    print(f"Reading emails from {maildir_path}...")
    emails = collect_emails(maildir_path, hours=args.hours)
    print(f"Found {len(emails)} emails")

    if not emails:
        print("No emails found. Nothing to classify.")
        sys.exit(0)

    # Classify each email
    items = []
    for i, parsed in enumerate(emails, 1):
        print(f"[{i}/{len(emails)}] Classifying: {parsed['subject'][:60]}...")
        classification = classify_email(parsed, model=args.model)

        # Merge parsed email data with classification
        item = {
            "id": parsed["id"],
            "date": parsed["date"],
            "sender": parsed["sender"],
            "subject": parsed["subject"],
            **classification,
            "body_snippet": parsed["body_snippet"],
            "links": parsed["links"],
        }
        items.append(item)

    # Build digest
    digest = build_digest(items)

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(digest, indent=2, ensure_ascii=False))
    print(f"\nDigest written to {output_path}")
    print(f"Total items: {digest['total_items']}")
    print(f"Stats: {json.dumps(digest['stats'], indent=2)}")


if __name__ == "__main__":
    main()
