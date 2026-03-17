#!/usr/bin/env python3
"""
Vault connector worker.

Finds vault notes related to input text via keyword extraction + BM25-lite scoring
with temporal decay (ADR-045). Also searches insights.json for operational memory.

Usage:
    python3 workers/vault_connector.py match --query "Fed rate outlook and mortgage impact"
    python3 workers/vault_connector.py match-email --gmail-id 19cf919de37e57bc
    python3 workers/vault_connector.py match-event --summary "Watford vs Wrexham"
"""

import argparse
import json
import math
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from workers.base_worker import BaseWorker
from workers.vault_utils import parse_frontmatter
import insights_store

_workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

KEYWORD_SYSTEM_PROMPT = """Extract 5-10 keywords and named entities from this text.
Return JSON only — no markdown fences, no explanation.
Schema: {"keywords": ["keyword1", "keyword2", ...]}"""


# Temporal decay half-lives per note type (days). ADR-045.
TYPE_DECAY_HALF_LIFE = {
    "bookmark": None,       # No decay — reference material stays relevant
    "idea": 90,             # Gentle decay
    "task": 30,             # Moderate decay — stale tasks less relevant
    "recipe": 14,           # Steep decay — time-sensitive
    "travel": 14,
    "event": 14,
    "reference": None,      # No decay
}
DEFAULT_DECAY_HALF_LIFE = 60  # For types not listed


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

    def _tokenize(self, text):
        """Split text into lowercase tokens."""
        return re.findall(r"[a-z0-9]+", text.lower())

    def _temporal_decay(self, note_type, mtime):
        """Compute temporal decay based on note type. Returns multiplier in [0, 1]."""
        half_life = TYPE_DECAY_HALF_LIFE.get(note_type, DEFAULT_DECAY_HALF_LIFE)
        if half_life is None:
            return 1.0  # No decay for this type
        age_days = (time.time() - mtime) / 86400
        if age_days <= 0:
            return 1.0
        lam = math.log(2) / half_life
        return math.exp(-lam * age_days)

    def _score_note_bm25(self, keywords, meta, body, filepath):
        """BM25-lite scoring with temporal decay (ADR-045). Returns (score, reasons)."""
        reasons = []

        # Build document tokens from title + body + tags
        title = meta.get("title", "")
        tags_raw = meta.get("tags", "[]")
        doc_text = f"{title} {title} {title} {body} {tags_raw} {tags_raw}"  # Title/tags boosted 3x/2x
        doc_tokens = self._tokenize(doc_text)

        if not doc_tokens:
            return 0, reasons

        # Score each keyword against document
        score = 0
        for kw in keywords:
            kw_lower = kw.lower()
            kw_tokens = self._tokenize(kw_lower)
            for token in kw_tokens:
                count = doc_tokens.count(token)
                if count > 0:
                    # BM25-style TF saturation: tf / (tf + 1)
                    tf_score = count / (count + 1)
                    score += tf_score

                    # Track match location for reasons
                    if kw_lower in title.lower():
                        reasons.append(f"title: {kw}")
                    elif kw_lower in tags_raw.lower():
                        reasons.append(f"tag: {kw}")
                    else:
                        reasons.append(f"keyword: {kw}")

        if score <= 0:
            return 0, reasons

        # Priority bonus
        try:
            priority = int(meta.get("priority", "0"))
            if priority >= 7:
                score *= 1.3
                reasons.append("priority >= 7")
        except ValueError:
            pass

        # Temporal decay based on note type
        note_type = meta.get("type", "other")
        mtime = os.path.getmtime(filepath)
        decay = self._temporal_decay(note_type, mtime)
        score *= decay

        return score, reasons

    def match(self, query):
        """Find vault notes matching a text query. Returns result dict with BM25-lite scoring."""
        keywords, llm_result = self._extract_keywords(query)
        if not keywords:
            return {"query": query, "matches": [], "keywords_extracted": []}

        notes = self._scan_notes()
        scored = []

        for filepath, meta, body in notes:
            score, reasons = self._score_note_bm25(keywords, meta, body, filepath)
            if score > 0 and len(reasons) >= self.min_hits:
                scored.append({
                    "file": os.path.basename(filepath),
                    "title": meta.get("title", os.path.basename(filepath)),
                    "type": meta.get("type", "unknown"),
                    "priority": int(meta.get("priority", "0")) if meta.get("priority", "").isdigit() else 0,
                    "match_reasons": reasons,
                    "snippet": body[:80].strip() if body else "",
                    "score": score,
                    "source": "vault",
                })

        # Also search insights store (ADR-045)
        insight_results = insights_store.search_insights(query, limit=3)
        for ir in insight_results:
            entry = ir["entry"]
            scored.append({
                "file": f"insight:{entry['id']}",
                "title": entry["text"][:60],
                "type": "insight",
                "priority": 0,
                "match_reasons": [f"insight ({entry['type']}) from {entry['source_module']}"],
                "snippet": entry["text"][:80],
                "score": ir["score"],
                "source": "insight",
            })

        # Sort by score descending
        scored.sort(key=lambda x: x["score"], reverse=True)
        matches = scored[:self.max_results]

        # Remove internal score from output
        for m in matches:
            del m["score"]

        self.log_run(
            input_tokens=llm_result["input_tokens"],
            output_tokens=llm_result["output_tokens"],
            input_summary=f"query: {query[:80]}",
            output_summary=f"{len(matches)} matches from {len(notes)} notes + insights",
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
