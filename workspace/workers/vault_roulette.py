#!/usr/bin/env python3
"""
Vault roulette worker.

Picks a random or decaying vault note and returns it with context
about why it's being surfaced.

Usage:
    python3 workers/vault_roulette.py spin
    python3 workers/vault_roulette.py spin --decaying --days 30
    python3 workers/vault_roulette.py spin --type idea
"""

import argparse
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from workers.base_worker import BaseWorker
from workers.vault_utils import parse_frontmatter
import insights_store


class VaultRoulette(BaseWorker):
    def __init__(self, vault_dir=None):
        super().__init__("vault-roulette")
        self.vault_dir = vault_dir or os.path.join("/workspace", "vault", "notes")
        self.type_weights = self.config.get("type_weights", {"idea": 3, "bookmark": 2, "task": 1})
        self.exclude_types = set(self.config.get("exclude_types", ["journal"]))
        self.default_decay_days = self.config.get("decay_threshold_days", 30)

    def _scan_notes(self):
        """Scan vault notes, return list of (filepath, meta, mtime) tuples."""
        notes = []
        if not os.path.exists(self.vault_dir):
            return notes
        for filename in os.listdir(self.vault_dir):
            if not filename.endswith(".md"):
                continue
            filepath = os.path.join(self.vault_dir, filename)
            try:
                with open(filepath) as f:
                    content = f.read(2000)
                meta, _ = parse_frontmatter(content)
                if meta.get("status") != "active":
                    continue
                mtime = os.path.getmtime(filepath)
                notes.append((filepath, meta, mtime))
            except OSError:
                continue
        return notes

    def spin(self, decaying=False, decay_days=None, note_type=None):
        """Pick a random vault note. Returns result dict."""
        decay_days = decay_days or self.default_decay_days
        now = time.time()

        notes = self._scan_notes()

        # Filter excluded types
        notes = [(fp, m, mt) for fp, m, mt in notes if m.get("type") not in self.exclude_types]

        # Filter by type if specified
        if note_type:
            notes = [(fp, m, mt) for fp, m, mt in notes if m.get("type") == note_type]

        # Filter by decay if requested
        if decaying:
            threshold = now - (decay_days * 86400)
            notes = [(fp, m, mt) for fp, m, mt in notes if mt < threshold]

        if not notes:
            return {"status": "no_candidates"}

        # Weighted random selection
        weights = []
        for filepath, meta, mtime in notes:
            note_type_val = meta.get("type", "other")
            type_weight = self.type_weights.get(note_type_val, 1)
            age_days = (now - mtime) / 86400
            age_weight = min(age_days / 30, 3)  # Cap at 3x for very old notes
            priority_weight = 1
            try:
                priority = int(meta.get("priority", "0"))
                if priority >= 7:
                    priority_weight = 1.5
            except ValueError:
                pass
            weights.append(type_weight * age_weight * priority_weight)

        # Weighted random choice
        chosen_idx = random.choices(range(len(notes)), weights=weights, k=1)[0]
        filepath, meta, mtime = notes[chosen_idx]

        age_days = int((now - mtime) / 86400)
        filename = os.path.basename(filepath)

        # Read body preview
        try:
            with open(filepath) as f:
                content = f.read()
            _, body = parse_frontmatter(content)
            preview = body[:200].strip() if body else ""
        except OSError:
            preview = ""

        result = {
            "file": filename,
            "title": meta.get("title", filename),
            "type": meta.get("type", "unknown"),
            "days_since_touched": age_days,
            "reason": f"Untouched for {age_days} days." if age_days > 0 else "Random pick.",
            "content_preview": preview,
        }

        # Insight production (ADR-045): if a dormant note gets surfaced frequently,
        # that's a pattern worth noting. Check if this note type keeps coming up.
        if age_days > 30:
            note_type_val = meta.get("type", "other")
            insight_text = f"Dormant {note_type_val} note '{meta.get('title', filename)}' surfaced after {age_days} days"
            tags_raw = meta.get("tags", "[]")
            # Parse tags if they look like a JSON array
            try:
                note_tags = json.loads(tags_raw) if tags_raw.startswith("[") else [tags_raw]
            except (json.JSONDecodeError, TypeError):
                note_tags = []
            insight_tags = [note_type_val] + note_tags[:3]
            if not insights_store.has_similar_insight(insight_text, insight_tags):
                insights_store.add_insight(
                    module="vault-roulette",
                    run_id=self.run_id,
                    insight_type="reflection",
                    text=insight_text,
                    tags=insight_tags,
                    confidence=0.5,
                )

        return result

    def run(self, input_data=None):
        raise NotImplementedError("Use spin()")


def main():
    parser = argparse.ArgumentParser(description="Vault roulette — random note picker")
    sub = parser.add_subparsers(dest="command", required=True)

    spin_p = sub.add_parser("spin", help="Pick a random note")
    spin_p.add_argument("--decaying", action="store_true", help="Only pick notes older than threshold")
    spin_p.add_argument("--days", type=int, default=None, help="Decay threshold in days")
    spin_p.add_argument("--type", dest="note_type", default=None, help="Filter to specific note type")

    args = parser.parse_args()
    roulette = VaultRoulette()

    result = roulette.spin(
        decaying=args.decaying,
        decay_days=args.days,
        note_type=args.note_type,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
