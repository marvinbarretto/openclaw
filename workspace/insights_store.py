#!/usr/bin/env python3
"""
Insight accumulation store for Jimbo's autonomous mind (ADR-045).

Stores structured insight entries produced by background workers.
Provides BM25-lite search with temporal decay for retrieval.
CLI interface + importable module.

Python 3.11 stdlib only. No pip dependencies.
"""

import argparse
import json
import math
import os
import re
import sys
import time
import uuid

_workspace_dir = os.path.dirname(os.path.abspath(__file__))
INSIGHTS_PATH = os.path.join(_workspace_dir, "insights.json")
DEFAULT_MAX_ENTRIES = 100
DECAY_HALF_LIFE_DAYS = 60


def _load_store():
    """Load insights store from disk. Returns dict with 'entries' list."""
    if not os.path.exists(INSIGHTS_PATH):
        return {"entries": [], "max_entries": DEFAULT_MAX_ENTRIES}
    with open(INSIGHTS_PATH) as f:
        return json.load(f)


def _save_store(store):
    """Atomic write: temp file then rename."""
    tmp = INSIGHTS_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(store, f, indent=2)
    os.replace(tmp, INSIGHTS_PATH)


def _tokenize(text):
    """Split text into lowercase tokens, strip punctuation."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _build_idf(documents):
    """Compute inverse document frequency for each term across documents.

    IDF(t) = log((N - df(t) + 0.5) / (df(t) + 0.5) + 1)
    This is the BM25 IDF variant that stays positive even when a term appears in all docs.
    """
    n = len(documents)
    if n == 0:
        return {}
    df = {}
    for doc_tokens in documents:
        seen = set(doc_tokens)
        for token in seen:
            df[token] = df.get(token, 0) + 1
    return {
        term: math.log((n - count + 0.5) / (count + 0.5) + 1)
        for term, count in df.items()
    }


def _tf(term, tokens):
    """Term frequency: count of term in tokens."""
    return tokens.count(term)


def _temporal_decay(timestamp, half_life_days=DECAY_HALF_LIFE_DAYS):
    """Exponential decay based on age. Returns multiplier in [0, 1]."""
    age_days = (time.time() - timestamp) / 86400
    if age_days <= 0:
        return 1.0
    lam = math.log(2) / half_life_days
    return math.exp(-lam * age_days)


def add_insight(module, run_id, insight_type, text, tags, confidence=0.7):
    """Add an insight entry to the store. Returns the new entry."""
    store = _load_store()

    entry = {
        "id": "ins_" + uuid.uuid4().hex[:8],
        "source_module": module,
        "source_run": run_id,
        "timestamp": int(time.time()),
        "type": insight_type,
        "text": text,
        "tags": tags if isinstance(tags, list) else [t.strip() for t in tags.split(",")],
        "confidence": confidence,
    }

    store["entries"].append(entry)

    # Prune if over max: drop oldest lowest-confidence first
    max_entries = store.get("max_entries", DEFAULT_MAX_ENTRIES)
    if len(store["entries"]) > max_entries:
        store["entries"].sort(key=lambda e: (e.get("confidence", 0.5), e["timestamp"]))
        store["entries"] = store["entries"][-max_entries:]

    _save_store(store)
    return entry


def search_insights(query, limit=5):
    """BM25-lite search over insights with temporal decay. Returns scored results."""
    store = _load_store()
    entries = store.get("entries", [])
    if not entries or not query.strip():
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    # Build document token lists (text + tags)
    doc_tokens_list = []
    for entry in entries:
        tokens = _tokenize(entry["text"] + " " + " ".join(entry.get("tags", [])))
        doc_tokens_list.append(tokens)

    idf = _build_idf(doc_tokens_list)

    results = []
    for i, entry in enumerate(entries):
        tokens = doc_tokens_list[i]
        if not tokens:
            continue

        # TF-IDF score
        score = 0.0
        for term in query_tokens:
            tf_val = _tf(term, tokens)
            idf_val = idf.get(term, 0)
            score += tf_val * idf_val

        if score <= 0:
            continue

        # Apply temporal decay
        decay = _temporal_decay(entry["timestamp"])
        final_score = score * decay

        results.append({
            "entry": entry,
            "score": round(final_score, 4),
            "decay": round(decay, 4),
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


def has_similar_insight(text, tags, threshold=0.6):
    """Check if a similar insight already exists. Returns True if duplicate-ish."""
    store = _load_store()
    entries = store.get("entries", [])
    if not entries:
        return False

    new_tokens = set(_tokenize(text))
    new_tags = set(t.lower() for t in tags) if isinstance(tags, list) else set(t.strip().lower() for t in tags.split(","))

    for entry in entries:
        existing_tokens = set(_tokenize(entry["text"]))
        existing_tags = set(t.lower() for t in entry.get("tags", []))

        # Token overlap (Jaccard similarity)
        if new_tokens and existing_tokens:
            token_overlap = len(new_tokens & existing_tokens) / len(new_tokens | existing_tokens)
        else:
            token_overlap = 0

        # Tag overlap
        if new_tags and existing_tags:
            tag_overlap = len(new_tags & existing_tags) / len(new_tags | existing_tags)
        else:
            tag_overlap = 0

        # Weighted similarity (tags matter more — they're curated)
        similarity = 0.4 * token_overlap + 0.6 * tag_overlap
        if similarity >= threshold:
            return True

    return False


def get_stats():
    """Return summary stats about the insights store."""
    store = _load_store()
    entries = store.get("entries", [])

    if not entries:
        return {"total": 0, "by_type": {}, "by_module": {}, "avg_confidence": 0}

    by_type = {}
    by_module = {}
    total_confidence = 0

    for e in entries:
        t = e.get("type", "unknown")
        m = e.get("source_module", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
        by_module[m] = by_module.get(m, 0) + 1
        total_confidence += e.get("confidence", 0.5)

    return {
        "total": len(entries),
        "by_type": by_type,
        "by_module": by_module,
        "avg_confidence": round(total_confidence / len(entries), 2),
        "oldest_days": round((time.time() - entries[0]["timestamp"]) / 86400, 1) if entries else 0,
        "newest_days": round((time.time() - entries[-1]["timestamp"]) / 86400, 1) if entries else 0,
    }


def prune(max_entries=None):
    """Prune store to max entries. Drops oldest lowest-confidence first. Returns count removed."""
    store = _load_store()
    max_entries = max_entries or store.get("max_entries", DEFAULT_MAX_ENTRIES)
    before = len(store["entries"])

    if before <= max_entries:
        return 0

    store["entries"].sort(key=lambda e: (e.get("confidence", 0.5), e["timestamp"]))
    store["entries"] = store["entries"][-max_entries:]
    _save_store(store)
    return before - len(store["entries"])


def main():
    parser = argparse.ArgumentParser(description="Jimbo insight accumulation store (ADR-045)")
    sub = parser.add_subparsers(dest="command")

    add_p = sub.add_parser("add", help="Add an insight entry")
    add_p.add_argument("--module", required=True, help="Source module name")
    add_p.add_argument("--run-id", default="manual", help="Source run ID")
    add_p.add_argument("--type", required=True, choices=["connection", "pattern", "suggestion", "reflection"],
                       help="Insight type")
    add_p.add_argument("--text", required=True, help="Insight text")
    add_p.add_argument("--tags", required=True, help="Comma-separated tags")
    add_p.add_argument("--confidence", type=float, default=0.7, help="Confidence score 0-1")
    add_p.add_argument("--check-duplicate", action="store_true", help="Skip if similar insight exists")

    search_p = sub.add_parser("search", help="Search insights")
    search_p.add_argument("--query", required=True, help="Search query")
    search_p.add_argument("--limit", type=int, default=5, help="Max results")

    sub.add_parser("stats", help="Show store statistics")

    prune_p = sub.add_parser("prune", help="Prune old entries")
    prune_p.add_argument("--max", type=int, default=DEFAULT_MAX_ENTRIES, help="Max entries to keep")

    args = parser.parse_args()

    if args.command == "add":
        tags = [t.strip() for t in args.tags.split(",")]
        if args.check_duplicate and has_similar_insight(args.text, tags):
            print(json.dumps({"status": "skipped", "reason": "similar insight exists"}))
            return

        entry = add_insight(
            module=args.module,
            run_id=args.run_id,
            insight_type=args.type,
            text=args.text,
            tags=tags,
            confidence=args.confidence,
        )
        print(json.dumps({"status": "added", "entry": entry}))

    elif args.command == "search":
        results = search_insights(args.query, limit=args.limit)
        print(json.dumps({"results": results}, indent=2))

    elif args.command == "stats":
        stats = get_stats()
        print(json.dumps(stats, indent=2))

    elif args.command == "prune":
        removed = prune(max_entries=args.max)
        print(json.dumps({"removed": removed, "max": args.max}))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
