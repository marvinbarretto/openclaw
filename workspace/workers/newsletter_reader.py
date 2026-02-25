#!/usr/bin/env python3
"""
Newsletter deep-reader worker.

Takes a shortlist of emails (from email_triage) plus their full bodies,
calls a capable model (Haiku) to extract specific articles, links, events,
prices, and gems that match Marvin's context.

Usage:
    python3 workers/newsletter_reader.py --shortlist /tmp/shortlist.json --digest /workspace/email-digest.json
    python3 workers/newsletter_reader.py --shortlist /tmp/shortlist.json --digest /workspace/email-digest.json --output /tmp/gems.json
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from workers.base_worker import BaseWorker


def build_reader_prompt(emails, context):
    """Build the deep-reading prompt."""
    context_block = ""
    for filename, content in context.items():
        context_block += f"\n## {filename}\n{content}\n"

    emails_block = ""
    for email in emails:
        sender = email.get("sender", {})
        links = email.get("links", [])
        links_str = "\n".join(f"  - {url}" for url in links) if links else "  (none)"
        emails_block += (
            f"\n--- {sender.get('name', 'Unknown')} ---\n"
            f"Gmail ID: {email.get('gmail_id', 'unknown')}\n"
            f"Subject: {email.get('subject', '')}\n"
            f"Full body:\n{email.get('body', email.get('body_snippet', ''))}\n\n"
            f"Links found:\n{links_str}\n"
        )

    return f"""You are a deep-reading assistant. Read each email carefully — every paragraph, every link — and extract what matters.

# Marvin's Context
{context_block}

# Emails to Read Deeply ({len(emails)} total)
{emails_block}

# Instructions

For each email, read the FULL BODY carefully. Don't just read the subject line. Look for:
- Specific articles, blog posts, or resources mentioned in the body
- Events with dates, venues, and prices
- Deals or offers with concrete details (price, expiry)
- Surprising or non-obvious connections to Marvin's interests or projects
- Links worth clicking

For each gem you find, note whether it could be a "surprise" — something non-obvious that connects two unrelated things, or a buried find Marvin wouldn't expect.

Return a JSON object with:
- "gems": array of extracted items
- "stats": object with newsletters_read, gems_extracted, links_found

Each gem must have:
- "gmail_id": which email it came from
- "source": sender/newsletter name
- "title": the specific article/event/deal title
- "why": one sentence connecting it to Marvin's context (reference specific interests/priorities)
- "links": array of relevant URLs
- "time_sensitive": boolean
- "deadline": ISO date if time-sensitive, null otherwise
- "price": price string if relevant, null otherwise
- "surprise_candidate": boolean — true if this is a non-obvious find

Be specific. "Interesting AI article" is bad. "OpenAI released Codex 2 — connects to your agent-building work on Spoons" is good.

Respond with ONLY the JSON object, no markdown fences, no explanation."""


class NewsletterReaderWorker(BaseWorker):
    def __init__(self):
        super().__init__("newsletter-deep-read")

    def run(self, shortlist_data):
        """Deep read shortlisted emails. Returns gems JSON."""
        shortlist = shortlist_data.get("shortlist", [])
        email_lookup = shortlist_data.get("emails", {})

        if not shortlist:
            return {"gems": [], "stats": {"newsletters_read": 0, "gems_extracted": 0, "links_found": 0}}

        # Get full email bodies for shortlisted items
        emails_to_read = []
        for item in shortlist:
            gmail_id = item.get("gmail_id")
            if gmail_id in email_lookup:
                emails_to_read.append(email_lookup[gmail_id])

        if not emails_to_read:
            return {"gems": [], "stats": {"newsletters_read": 0, "gems_extracted": 0, "links_found": 0}}

        context = self.get_context()
        batch_size = self.config.get("batch_size", 15)

        all_gems = []
        total_input_tokens = 0
        total_output_tokens = 0

        for i in range(0, len(emails_to_read), batch_size):
            batch = emails_to_read[i:i + batch_size]
            prompt = build_reader_prompt(batch, context)

            result = self.call(prompt)
            total_input_tokens += result["input_tokens"]
            total_output_tokens += result["output_tokens"]

            try:
                parsed = json.loads(result["text"])
                all_gems.extend(parsed.get("gems", []))
            except json.JSONDecodeError:
                sys.stderr.write(f"Failed to parse batch {i // batch_size + 1} response as JSON\n")
                continue

        output = {
            "gems": all_gems,
            "stats": {
                "newsletters_read": len(emails_to_read),
                "gems_extracted": len(all_gems),
                "links_found": sum(len(g.get("links", [])) for g in all_gems),
            }
        }

        self.log_run(
            model=self.get_model(),
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            input_summary=f"{len(emails_to_read)} emails deep-read in {(len(emails_to_read) + batch_size - 1) // batch_size} batches",
            output_summary=f"{len(all_gems)} gems extracted, {output['stats']['links_found']} links",
        )

        return output


def main():
    parser = argparse.ArgumentParser(description="Newsletter deep-reader worker")
    parser.add_argument("--shortlist", required=True, help="Path to shortlist JSON (from email_triage)")
    parser.add_argument("--digest", required=True, help="Path to email-digest.json (for full bodies)")
    parser.add_argument("--output", default=None, help="Output path (default: stdout)")
    args = parser.parse_args()

    with open(args.shortlist) as f:
        shortlist_raw = json.load(f)

    with open(args.digest) as f:
        digest = json.load(f)

    # Build email lookup from digest
    email_lookup = {item["gmail_id"]: item for item in digest.get("items", []) if "gmail_id" in item}

    shortlist_data = {
        "shortlist": shortlist_raw.get("shortlist", shortlist_raw),
        "emails": email_lookup,
    }

    worker = NewsletterReaderWorker()
    result = worker.run(shortlist_data)

    output_json = json.dumps(result, indent=2)
    if args.output:
        with open(args.output, "w") as f:
            f.write(output_json)
        sys.stderr.write(f"Wrote gems to {args.output}\n")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
