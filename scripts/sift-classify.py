#!/usr/bin/env python3
"""Sift v0.2 — Offline email classification pipeline.

Reads a Maildir, classifies each email via Ollama (qwen2.5-coder:14b),
and outputs a structured email-digest.json.

v0.2 changes:
- Seen-files index to skip already-classified emails (--no-cache to bypass)
- os.scandir() for faster directory iteration (avoids Path overhead at 158k+ files)
- Performance timing and logging to data/sift-perf.log

Usage:
    python scripts/sift-classify.py
    python scripts/sift-classify.py --input data/sample-maildir --output data/email-digest.json
    python scripts/sift-classify.py --hours 48
    python scripts/sift-classify.py --no-cache   # ignore seen-files index
"""

import argparse
import email
import email.header
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
VALID_CATEGORIES = {"newsletter", "tech", "local", "deals", "event", "transactional", "health", "other", "personal"}
VALID_ACTIONS = {"queue", "skip"}
VALID_PROJECTS = {"spoons", "localshout", "pomodoro", None}

SEEN_INDEX_FILE = "data/.sift-seen.json"
PERF_LOG_FILE = "data/sift-perf.log"
SEEN_INDEX_MAX_AGE_DAYS = 14

CLASSIFICATION_PROMPT = """\
You are an email classifier. Your ONLY job is to throw away obvious junk so the user gets a manageable inbox. You are a coarse filter, not a taste judge.

Email:
From: {sender_name} <{sender_email}>
Subject: {subject}
Date: {date}
Body:
{body_snippet}

ALWAYS QUEUE these (do not skip):
- Personal replies: emails where someone is writing TO the user directly (Re: subjects, conversational tone, direct address). Most important.
- Events: gigs, meetups, comedy, cinema, festivals, hiking, debates, tickets, concerts — anything with a date and place.
- Travel deals: flight deals, holiday packages, error fares, campervan relocations.
- Booking updates: Airbnb requests, cancellations, reservation changes.
- Newsletters and digests: subscriber content, curated roundups, tech digests — queue ALL of these. The user's curator will decide what's interesting.

ALWAYS SKIP these — be aggressive, this is where you earn your keep:
- Order confirmations and receipts (Wetherspoons, Amazon, Uber Eats, Deliveroo, Just Eat, any "your order" email)
- Delivery tracking and shipping updates ("your package is on its way", "out for delivery")
- Brand marketing and retail promos from: Checkatrade, Sainsbury's, Starbucks, Costa, Tesco, Lidl, Aldi, Asda, M&S, Boots, Superdrug, Argos, Currys, John Lewis, IKEA, H&M, ASOS, Nike, Adidas, Sky, BT, EE, Three, Vodafone, O2, Virgin Media
- Loyalty scheme emails: points updates, rewards, tier status, "earn double points"
- Credit card and banking marketing: "pre-approved", "increase your limit", cashback promos
- "We miss you" / "come back" / win-back emails
- Account summary / monthly statement / usage report emails (unless it looks like a bill with an action needed)
- Password reset emails the user didn't request
- Survey and feedback requests: "how did we do?", "rate your experience", NPS surveys
- App update notifications: "what's new", "new features", changelog emails
- Social media notifications: LinkedIn, Facebook, Twitter/X, Instagram digest emails
- Spam in foreign languages (Chinese, Japanese, Russian, Arabic — the user reads English only)
- Unsubscribe confirmations
- Cookie policy / privacy policy / T&C update notices
- Charity and donation solicitations (unless from a known personal contact)
- Job alerts and recruiter spam (LinkedIn jobs, Indeed, Glassdoor)
- Webinar and event marketing that is clearly promotional (not a real event the user would attend)

If the sender domain matches any of these patterns, SKIP: noreply@, no-reply@, marketing@, promo@, offers@, news@, newsletter@ combined with a clearly commercial brand.

DECISION RULE: If the email is clearly automated junk from a brand or service, SKIP it. If it's from a person, or could be genuinely useful content, QUEUE it. When genuinely unsure, queue it.

The user's active projects: Spoons (pub check-in app), LocalShout (community platform), Pomodoro (timer)
The user's location: Watford / South Oxhey, UK

Categories (pick one): newsletter, tech, local, deals, event, transactional, health, other, personal

Suggested action: queue or skip

Return JSON only: {{"category": "...", "subcategory": "...", "keywords": ["...", "...", "..."], "summary": "...", "time_estimate_min": N, "project_relevance": null, "suggested_action": "queue or skip", "confidence": 0.0-1.0}}"""


def parse_maildir_message(filepath):
    """Parse a single Maildir email file, return extracted fields or None."""
    try:
        with open(filepath, "r", errors="replace") as f:
            raw = f.read()
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
    date_parsed = None
    try:
        date_parsed = email.utils.parsedate_to_datetime(date_header)
    except Exception:
        pass

    # Subject — decode MIME-encoded headers (=?UTF-8?B?...=)
    raw_subject = msg.get("Subject", "(no subject)")
    try:
        decoded_parts = email.header.decode_header(raw_subject)
        subject = " ".join(
            part.decode(charset or "utf-8", errors="replace") if isinstance(part, bytes) else part
            for part, charset in decoded_parts
        )
    except Exception:
        subject = raw_subject

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
        "date": date_parsed.isoformat() if date_parsed else None,
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


def load_seen_index(repo_root):
    """Load the seen-files index from disk. Returns dict of filename → date ISO string."""
    index_path = repo_root / SEEN_INDEX_FILE
    if not index_path.exists():
        return {}
    try:
        with open(index_path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        print("  WARNING: corrupt seen-files index, starting fresh", file=sys.stderr)
        return {}


def save_seen_index(repo_root, index):
    """Save the seen-files index to disk, pruning entries older than 14 days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=SEEN_INDEX_MAX_AGE_DAYS)).isoformat()
    pruned = {k: v for k, v in index.items() if v and v >= cutoff}
    index_path = repo_root / SEEN_INDEX_FILE
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "w") as f:
        json.dump(pruned, f)
    pruned_count = len(index) - len(pruned)
    if pruned_count > 0:
        print(f"  Pruned {pruned_count} old entries from seen-files index")


def collect_emails(maildir_path, hours=24, seen_index=None):
    """Read Maildir and return parsed emails from the last N hours.

    Optimization flow for each file:
      1. Index check — skip files already in seen_index (no stat, no parse needed).
         This is the primary speedup: mbsync sets filenames and mtimes to sync time,
         not email receive time, so 158k+ files would otherwise need stat calls.
      2. mtime check — quick pre-filter using file modification time with a 7-day
         buffer (because mbsync mtime ≠ email Date header).
      3. Parse + Date header check — parse the email and filter by actual Date header.

    os.scandir() is used instead of Path.iterdir() to avoid creating Path objects
    for every file. At 158k+ files, this avoids significant overhead.

    Args:
        hours: Look-back window. 0 means no date filter.
        seen_index: Dict of filename → date ISO string. Files in this dict are skipped.
    """
    no_filter = (hours == 0)
    cutoff = None if no_filter else datetime.now(timezone.utc) - timedelta(hours=hours)
    emails = []
    files_total = 0
    skipped_index = 0
    skipped_mtime = 0
    skipped_date = 0

    if seen_index is None:
        seen_index = {}

    for subdir in ("new", "cur"):
        dirpath = maildir_path / subdir
        if not dirpath.exists():
            continue

        # Use os.scandir() for faster iteration — avoids Path object overhead at scale.
        # Each DirEntry gives us the name and a fast stat() without extra syscalls.
        try:
            entries = list(os.scandir(str(dirpath)))
        except OSError:
            continue

        file_entries = [e for e in entries if e.is_file() and not e.name.startswith(".")]
        files_total += len(file_entries)
        print(f"  Scanning {len(file_entries)} files in {subdir}/...")

        for entry in file_entries:
            if (files_total - skipped_index) % 1000 == 0 and (files_total - skipped_index) > 0:
                print(f"  ...processed {files_total} files, found {len(emails)} so far", flush=True)

            # Step 1: Index check — skip already-seen files (no stat, no parse).
            # This is the key optimisation: avoids 158k stat calls on repeat runs.
            if entry.name in seen_index:
                skipped_index += 1
                continue

            if not no_filter:
                # Step 2: mtime pre-filter — skip files much older than cutoff.
                # Use a generous buffer (7 days) because mbsync sets mtime to
                # sync time, not email receive time.
                try:
                    mtime = datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc)
                    mtime_buffer = cutoff - timedelta(days=7)
                    if mtime < mtime_buffer:
                        skipped_mtime += 1
                        # Still record in index so we don't stat again next run
                        seen_index[entry.name] = mtime.isoformat()
                        continue
                except OSError:
                    continue

            # Step 3: Parse the email and check the Date header.
            parsed = parse_maildir_message(Path(entry.path))
            if parsed:
                # Record in seen index regardless of whether it passes the date filter
                seen_index[entry.name] = parsed["date"] or datetime.now(timezone.utc).isoformat()

                if not no_filter:
                    if parsed["date"] is None:
                        skipped_date += 1
                        continue
                    try:
                        msg_date = datetime.fromisoformat(parsed["date"])
                        if msg_date.tzinfo is None:
                            msg_date = msg_date.replace(tzinfo=timezone.utc)
                        if msg_date < cutoff:
                            skipped_date += 1
                            continue
                    except (ValueError, TypeError):
                        skipped_date += 1
                        continue
                emails.append(parsed)

    print(f"  Scanned {files_total} files: {skipped_index} skipped (index), "
          f"{skipped_mtime} skipped (mtime), {skipped_date} skipped (date), "
          f"{len(emails)} to classify")

    # Sort by date descending (dateless emails go to the end)
    emails.sort(key=lambda e: e["date"] or "", reverse=True)

    return emails, {
        "files_total": files_total,
        "files_skipped_index": skipped_index,
        "files_skipped_mtime": skipped_mtime,
        "files_skipped_date": skipped_date,
    }


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


def log_performance(repo_root, perf):
    """Append a JSON-lines entry to data/sift-perf.log."""
    perf_path = repo_root / PERF_LOG_FILE
    perf_path.parent.mkdir(parents=True, exist_ok=True)
    with open(perf_path, "a") as f:
        f.write(json.dumps(perf, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Sift v0.2 — email classification pipeline")
    parser.add_argument("--input", default="data/sample-maildir", help="Maildir path")
    parser.add_argument("--output", default="data/email-digest.json", help="Output JSON path")
    parser.add_argument("--hours", type=int, default=24, help="Look back N hours (default 24)")
    parser.add_argument("--all", action="store_true", help="Ignore date filters, process all emails")
    parser.add_argument("--limit", type=int, default=0, help="Max emails to classify (0 = unlimited)")
    parser.add_argument("--model", default=OLLAMA_MODEL, help=f"Ollama model (default {OLLAMA_MODEL})")
    parser.add_argument("--no-cache", action="store_true", help="Bypass seen-files index")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    maildir_path = repo_root / args.input
    output_path = repo_root / args.output

    if not maildir_path.exists():
        print(f"ERROR: Maildir not found at {maildir_path}", file=sys.stderr)
        print("Run sift-sample.py first to generate test data.", file=sys.stderr)
        sys.exit(1)

    t_total_start = time.monotonic()

    # Load seen-files index (unless --no-cache)
    if args.no_cache:
        print("Seen-files index bypassed (--no-cache)")
        seen_index = {}
    else:
        seen_index = load_seen_index(repo_root)
        print(f"Loaded seen-files index: {len(seen_index)} entries")

    # Collect emails
    print(f"Reading emails from {maildir_path}...")
    t_scan_start = time.monotonic()
    if args.all:
        emails, scan_stats = collect_emails(maildir_path, hours=0, seen_index=seen_index)
    else:
        emails, scan_stats = collect_emails(maildir_path, hours=args.hours, seen_index=seen_index)
    t_scan_end = time.monotonic()

    if args.limit and len(emails) > args.limit:
        print(f"Found {len(emails)} emails, limiting to {args.limit}")
        emails = emails[:args.limit]
    else:
        print(f"Found {len(emails)} emails")

    if not emails:
        print("No emails found. Nothing to classify.")
        # Still save the index — we learned about files even if none passed the filter
        if not args.no_cache:
            save_seen_index(repo_root, seen_index)
        sys.exit(0)

    # Classify each email
    t_classify_start = time.monotonic()
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
    t_classify_end = time.monotonic()

    # Save seen-files index
    if not args.no_cache:
        save_seen_index(repo_root, seen_index)

    # Build digest
    digest = build_digest(items)

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(digest, indent=2, ensure_ascii=False))
    print(f"\nDigest written to {output_path}")
    print(f"Total items: {digest['total_items']}")
    print(f"Stats: {json.dumps(digest['stats'], indent=2)}")

    # Performance summary
    t_total_end = time.monotonic()
    scan_seconds = round(t_scan_end - t_scan_start, 2)
    classify_seconds = round(t_classify_end - t_classify_start, 2)
    total_seconds = round(t_total_end - t_total_start, 2)
    files_classified = len(emails)
    avg_classify = round(classify_seconds / files_classified, 2) if files_classified else 0

    perf = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scan_seconds": scan_seconds,
        "classify_seconds": classify_seconds,
        "total_seconds": total_seconds,
        "files_total": scan_stats["files_total"],
        "files_skipped_index": scan_stats["files_skipped_index"],
        "files_skipped_mtime": scan_stats["files_skipped_mtime"],
        "files_skipped_date": scan_stats["files_skipped_date"],
        "files_classified": files_classified,
        "avg_classify_seconds": avg_classify,
    }

    print(f"\nPerformance: scan={scan_seconds}s, classify={classify_seconds}s, "
          f"total={total_seconds}s, avg_per_email={avg_classify}s")
    log_performance(repo_root, perf)
    print(f"Perf log appended to {PERF_LOG_FILE}")


if __name__ == "__main__":
    main()
