#!/usr/bin/env python3
"""
Email triage worker.

Reads the full email digest, calls a cheap model (Flash) to classify and rank
emails by relevance to Marvin's context. Returns a shortlist of ~30 worth
reading deeply.

Usage:
    python3 workers/email_triage.py --digest /workspace/email-digest.json
    python3 workers/email_triage.py --digest /workspace/email-digest.json --output /tmp/shortlist.json
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from workers.base_worker import BaseWorker


def build_triage_prompt(emails, context, categories=None):
    """Build the prompt for the triage model."""
    if categories is None:
        categories = ["newsletter", "event", "personal", "deal", "job-alert", "football", "notification", "other"]
    categories_str = ", ".join(f'"{c}"' for c in categories)

    context_block = ""
    for filename, content in context.items():
        context_block += f"\n## {filename}\n{content}\n"

    emails_block = ""
    for i, email in enumerate(emails):
        sender = email.get("sender", {})
        emails_block += (
            f"\n--- Email {i+1} ---\n"
            f"Gmail ID: {email.get('gmail_id', 'unknown')}\n"
            f"From: {sender.get('name', '')} <{sender.get('email', '')}>\n"
            f"Subject: {email.get('subject', '')}\n"
            f"Snippet: {email.get('body_snippet', '')}\n"
            f"Date: {email.get('date', '')}\n"
            f"Labels: {', '.join(email.get('labels', []))}\n"
        )

    # Build calibration block if EMAIL_EXAMPLES.md is in context
    calibration_block = ""
    if "EMAIL_EXAMPLES.md" in context:
        calibration_block = f"""
# Calibration Examples

Use the EMAIL_EXAMPLES below to calibrate your scoring. These show how Marvin actually evaluates emails — what he considers high value, medium value, and skip-worthy. Match your triage decisions to these patterns.

{context.get("EMAIL_EXAMPLES.md", "")}
"""

    min_shortlist = max(3, len(emails) // 10)

    return f"""You are an email triage assistant. Your job is to classify and rank emails by relevance.

# Marvin's Context
{context_block}
{calibration_block}
# Emails to Triage ({len(emails)} total)
{emails_block}

# Instructions

Review each email. For each one, decide:
1. Is this worth reading deeply? (newsletters with real content, events, personal replies, deals)
2. Is it time-sensitive? (events, tickets, deadlines)
3. How relevant is it to Marvin's current interests and priorities?

Return a JSON object with:
- "shortlist": array of emails worth reading, ranked by relevance (most relevant first)
- "stats": object with total_reviewed, shortlisted, skipped counts

Each shortlist item must have:
- "gmail_id": the Gmail ID from the email
- "rank": integer (1 = most relevant)
- "category": one of {categories_str}
- "reason": one sentence explaining why this is worth reading
- "time_sensitive": boolean
- "deadline": ISO date string if time-sensitive, otherwise null

**Target shortlist rate: 10-20% of the batch.** For {len(emails)} emails, aim for {len(emails) // 10}-{len(emails) // 5} items. You must shortlist at least {min_shortlist} emails unless the batch is truly all junk (automated notifications, receipts, spam). Newsletters, personal emails, events, and deals almost always deserve a spot. Only skip genuine noise.

Respond with ONLY the JSON object, no markdown fences, no explanation."""


class EmailTriageWorker(BaseWorker):
    def __init__(self):
        super().__init__("email-triage")

    def run(self, digest):
        """Triage emails from digest. Returns shortlist JSON."""
        items = digest.get("items", [])
        if not items:
            return {"shortlist": [], "stats": {"total_reviewed": 0, "shortlisted": 0, "skipped": 0}}

        context = self.get_context()
        batch_size = self.config.get("batch_size", 50)
        categories = self.config.get("categories")

        all_shortlisted = []
        total_input_tokens = 0
        total_output_tokens = 0

        # Process in batches
        num_batches = (len(items) + batch_size - 1) // batch_size
        sys.stderr.write(f"[email-triage] processing {len(items)} emails in {num_batches} batch(es)\n")

        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            batch_num = i // batch_size + 1
            prompt = build_triage_prompt(batch, context, categories=categories)

            sys.stderr.write(f"[email-triage] batch {batch_num}/{num_batches}: {len(batch)} emails, prompt {len(prompt)} chars\n")

            result = self.call(prompt)
            total_input_tokens += result["input_tokens"]
            total_output_tokens += result["output_tokens"]

            try:
                parsed = json.loads(result["text"])
                batch_shortlist = parsed.get("shortlist", [])
                all_shortlisted.extend(batch_shortlist)
                sys.stderr.write(f"[email-triage] batch {batch_num}: {len(batch_shortlist)} shortlisted\n")
            except json.JSONDecodeError:
                sys.stderr.write(f"[email-triage] batch {batch_num}: failed to parse response as JSON\n")
                continue

        # Re-rank across all batches
        all_shortlisted.sort(key=lambda x: x.get("rank", 999))
        for idx, item in enumerate(all_shortlisted):
            item["rank"] = idx + 1

        sys.stderr.write(f"[email-triage] total: {len(all_shortlisted)} shortlisted, {len(items) - len(all_shortlisted)} skipped\n")

        output = {
            "shortlist": all_shortlisted,
            "stats": {
                "total_reviewed": len(items),
                "shortlisted": len(all_shortlisted),
                "skipped": len(items) - len(all_shortlisted),
            }
        }

        self.log_run(
            model=self.get_model(),
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            input_summary=f"{len(items)} emails in {(len(items) + batch_size - 1) // batch_size} batches",
            output_summary=f"{len(all_shortlisted)} shortlisted, {len(items) - len(all_shortlisted)} skipped",
        )

        return output


def main():
    parser = argparse.ArgumentParser(description="Email triage worker")
    parser.add_argument("--digest", required=True, help="Path to email-digest.json")
    parser.add_argument("--output", default=None, help="Output path (default: stdout)")
    args = parser.parse_args()

    try:
        with open(args.digest) as f:
            digest = json.load(f)

        worker = EmailTriageWorker()
        result = worker.run(digest)

        output_json = json.dumps(result, indent=2)
        if args.output:
            with open(args.output, "w") as f:
                f.write(output_json)
            sys.stderr.write(f"Wrote shortlist to {args.output}\n")
        else:
            print(output_json)
    except Exception as e:
        subprocess.run([sys.executable, "/workspace/alert.py",
                        f"email_triage worker failed: {e}"])
        raise


if __name__ == "__main__":
    main()
