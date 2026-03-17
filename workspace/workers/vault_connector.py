#!/usr/bin/env python3
"""
Vault connector worker.

Finds vault notes related to input text via keyword extraction + grep + tag matching.

Usage:
    python3 workers/vault_connector.py match --query "Fed rate outlook and mortgage impact"
    python3 workers/vault_connector.py match-email --gmail-id 19cf919de37e57bc
    python3 workers/vault_connector.py match-event --summary "Watford vs Wrexham"
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from workers.base_worker import BaseWorker
from workers.vault_utils import parse_frontmatter

_workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

KEYWORD_SYSTEM_PROMPT = """Extract 5-10 keywords and named entities from this text.
Return JSON only — no markdown fences, no explanation.
Schema: {"keywords": ["keyword1", "keyword2", ...]}"""


class VaultConnector(BaseWorker):
    def __init__(self, vault_dir=None):
        super().__init__("vault-connector")
        self.vault_dir = vault_dir or self.config.get("vault_dir", "/workspace/vault/notes")
        self.max_results = self.config.get("max_results", 5)
        self.min_hits = self.config.get("min_keyword_hits", 1)

    def _extract_keywords(self, text):
        """Call Flash to extract keywords from text."""
        result = self.call(text, system=KEYWORD_SYSTEM_PROMPT)
        response = result["text"].strip()
        if response.startswith("```"):
            response = response.split("\n", 1)[1] if "\n" in response else response[3:]
        if response.endswith("```"):
            response = response[:-3].strip()
        try:
            parsed = json.loads(response)
            return parsed.get("keywords", []), result
        except json.JSONDecodeError:
            return [], result

    def _scan_notes(self):
        """Scan vault and return list of (filepath, meta, body) tuples."""
        notes = []
        if not os.path.exists(self.vault_dir):
            return notes
        for filename in os.listdir(self.vault_dir):
            if not filename.endswith(".md"):
                continue
            filepath = os.path.join(self.vault_dir, filename)
            try:
                with open(filepath) as f:
                    content = f.read()
                meta, body = parse_frontmatter(content)
                if meta.get("status") != "active":
                    continue
                notes.append((filepath, meta, body))
            except OSError:
                continue
        return notes

    def _score_note(self, keywords, meta, body):
        """Score a note against keywords. Returns (score, reasons)."""
        score = 0
        reasons = []

        filename_lower = meta.get("title", "").lower()
        body_lower = body.lower()
        tags_str = meta.get("tags", "[]").lower()

        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in filename_lower:
                score += 3
                reasons.append(f"title: {kw}")
            if kw_lower in body_lower:
                score += 1
                reasons.append(f"keyword: {kw}")
            if kw_lower in tags_str:
                score += 2
                reasons.append(f"tag: {kw}")

        # Priority bonus
        try:
            priority = int(meta.get("priority", "0"))
            if priority >= 7:
                score += 1
                reasons.append("priority >= 7")
        except ValueError:
            pass

        return score, reasons

    def match(self, query):
        """Find vault notes matching a text query. Returns result dict."""
        keywords, llm_result = self._extract_keywords(query)
        if not keywords:
            return {"query": query, "matches": [], "keywords_extracted": []}

        notes = self._scan_notes()
        scored = []

        for filepath, meta, body in notes:
            score, reasons = self._score_note(keywords, meta, body)
            if score >= self.min_hits:
                scored.append({
                    "file": os.path.basename(filepath),
                    "title": meta.get("title", os.path.basename(filepath)),
                    "type": meta.get("type", "unknown"),
                    "priority": int(meta.get("priority", "0")) if meta.get("priority", "").isdigit() else 0,
                    "match_reasons": reasons,
                    "snippet": body[:80].strip() if body else "",
                    "score": score,
                })

        # Sort by score descending, then priority descending
        scored.sort(key=lambda x: (x["score"], x["priority"]), reverse=True)
        matches = scored[:self.max_results]

        # Remove internal score from output
        for m in matches:
            del m["score"]

        self.log_run(
            input_tokens=llm_result["input_tokens"],
            output_tokens=llm_result["output_tokens"],
            input_summary=f"query: {query[:80]}",
            output_summary=f"{len(matches)} matches from {len(notes)} notes",
        )

        return {
            "query": query,
            "matches": matches,
            "keywords_extracted": keywords,
        }

    def match_from_briefing(self, gmail_id):
        """Find vault notes related to a specific email insight from briefing-input.json."""
        briefing_path = os.path.join(_workspace_dir, "briefing-input.json")
        if not os.path.exists(briefing_path):
            return {"error": "briefing-input.json not found", "matches": []}

        with open(briefing_path) as f:
            data = json.load(f)

        # Search email insights for the gmail_id
        for insight in data.get("email_insights", []):
            if insight.get("gmail_id") == gmail_id:
                query = f"{insight.get('subject', '')} {insight.get('insight', '')} {insight.get('reason', '')}"
                return self.match(query.strip())

        return {"error": f"gmail_id {gmail_id} not found in briefing-input.json", "matches": []}

    def run(self, input_data=None):
        raise NotImplementedError("Use match() or match_from_briefing()")


def main():
    parser = argparse.ArgumentParser(description="Vault connector — find related notes")
    sub = parser.add_subparsers(dest="command", required=True)

    match_p = sub.add_parser("match", help="Find notes matching a text query")
    match_p.add_argument("--query", required=True)

    email_p = sub.add_parser("match-email", help="Find notes related to an email insight")
    email_p.add_argument("--gmail-id", required=True)

    event_p = sub.add_parser("match-event", help="Find notes related to a calendar event")
    event_p.add_argument("--summary", required=True)

    args = parser.parse_args()
    connector = VaultConnector()

    if args.command == "match":
        result = connector.match(args.query)
    elif args.command == "match-email":
        result = connector.match_from_briefing(args.gmail_id)
    elif args.command == "match-event":
        result = connector.match(args.summary)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
