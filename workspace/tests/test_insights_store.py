#!/usr/bin/env python3
"""Tests for insights_store.py (ADR-045)."""

import json
import os
import sys
import tempfile
import time
import unittest

# Add workspace to path so we can import insights_store
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import insights_store


class TestInsightsStore(unittest.TestCase):
    """Test insight storage, search, and pruning."""

    def setUp(self):
        """Use a temp file for each test."""
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self._orig_path = insights_store.INSIGHTS_PATH
        insights_store.INSIGHTS_PATH = self.tmp.name
        # Start clean
        os.unlink(self.tmp.name)

    def tearDown(self):
        insights_store.INSIGHTS_PATH = self._orig_path
        if os.path.exists(self.tmp.name):
            os.unlink(self.tmp.name)

    def test_add_insight(self):
        entry = insights_store.add_insight(
            module="vault-reader",
            run_id="run_abc123",
            insight_type="connection",
            text="AI bookmarks connect to LocalShout priority",
            tags=["ai", "localshout"],
            confidence=0.8,
        )
        self.assertTrue(entry["id"].startswith("ins_"))
        self.assertEqual(entry["source_module"], "vault-reader")
        self.assertEqual(entry["type"], "connection")
        self.assertEqual(entry["tags"], ["ai", "localshout"])
        self.assertEqual(entry["confidence"], 0.8)

    def test_add_multiple_and_load(self):
        insights_store.add_insight("mod-a", "run1", "pattern", "Pattern A", ["x"])
        insights_store.add_insight("mod-b", "run2", "suggestion", "Suggestion B", ["y"])

        stats = insights_store.get_stats()
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["by_type"]["pattern"], 1)
        self.assertEqual(stats["by_type"]["suggestion"], 1)
        self.assertEqual(stats["by_module"]["mod-a"], 1)

    def test_search_finds_relevant(self):
        insights_store.add_insight("vault-reader", "r1", "connection",
                                   "Finance bookmarks consistently match SIPP timing task",
                                   ["finance", "sipp", "bookmarks"])
        insights_store.add_insight("vault-reader", "r2", "pattern",
                                   "AI agent architecture papers cluster around LocalShout",
                                   ["ai", "agents", "localshout"])

        results = insights_store.search_insights("finance SIPP")
        self.assertGreater(len(results), 0)
        self.assertIn("finance", results[0]["entry"]["text"].lower())

    def test_search_empty_query(self):
        insights_store.add_insight("mod", "r1", "pattern", "Something", ["x"])
        self.assertEqual(insights_store.search_insights(""), [])
        self.assertEqual(insights_store.search_insights("   "), [])

    def test_search_no_match(self):
        insights_store.add_insight("mod", "r1", "pattern", "Apples and oranges", ["fruit"])
        results = insights_store.search_insights("quantum computing")
        self.assertEqual(results, [])

    def test_search_includes_tags(self):
        insights_store.add_insight("mod", "r1", "connection",
                                   "Some generic text about things",
                                   ["watford", "football"])
        results = insights_store.search_insights("watford")
        self.assertGreater(len(results), 0)

    def test_temporal_decay(self):
        # Recent entry should score higher than old one with same content
        insights_store.add_insight("mod", "r1", "pattern",
                                   "Travel deals on Tuesday", ["travel"])

        # Manually age the first entry
        store = insights_store._load_store()
        store["entries"][0]["timestamp"] = int(time.time()) - (90 * 86400)  # 90 days ago
        insights_store._save_store(store)

        insights_store.add_insight("mod", "r2", "pattern",
                                   "Travel deals on Tuesday evening", ["travel"])

        results = insights_store.search_insights("travel deals tuesday")
        self.assertEqual(len(results), 2)
        # Newer entry should score higher due to less decay
        self.assertGreater(results[0]["decay"], results[1]["decay"])

    def test_prune_drops_oldest_lowest_confidence(self):
        # Add 5 entries, prune to 3
        for i in range(5):
            insights_store.add_insight(
                "mod", f"r{i}", "pattern", f"Insight {i}",
                ["tag"], confidence=0.1 * (i + 1),
            )

        removed = insights_store.prune(max_entries=3)
        self.assertEqual(removed, 2)

        stats = insights_store.get_stats()
        self.assertEqual(stats["total"], 3)

    def test_auto_prune_on_overflow(self):
        # Set max to 3, add 5
        store = {"entries": [], "max_entries": 3}
        with open(insights_store.INSIGHTS_PATH, "w") as f:
            json.dump(store, f)

        for i in range(5):
            insights_store.add_insight(
                "mod", f"r{i}", "pattern", f"Insight {i}",
                ["tag"], confidence=0.5,
            )

        stats = insights_store.get_stats()
        self.assertLessEqual(stats["total"], 3)

    def test_has_similar_insight_detects_duplicate(self):
        insights_store.add_insight("mod", "r1", "connection",
                                   "Finance bookmarks match SIPP task",
                                   ["finance", "sipp", "bookmarks"])

        # Very similar text and tags — should be detected
        self.assertTrue(insights_store.has_similar_insight(
            "Finance bookmarks connect to SIPP timing",
            ["finance", "sipp", "bookmarks"],
        ))

    def test_has_similar_insight_allows_different(self):
        insights_store.add_insight("mod", "r1", "connection",
                                   "Finance bookmarks match SIPP task",
                                   ["finance", "sipp"])

        # Different topic entirely — should not be detected
        self.assertFalse(insights_store.has_similar_insight(
            "AI agents revolutionise code review",
            ["ai", "agents", "code"],
        ))

    def test_stats_empty_store(self):
        stats = insights_store.get_stats()
        self.assertEqual(stats["total"], 0)
        self.assertEqual(stats["avg_confidence"], 0)

    def test_tags_as_string(self):
        entry = insights_store.add_insight(
            "mod", "r1", "pattern", "Test", "ai, agents, tools",
        )
        self.assertEqual(entry["tags"], ["ai", "agents", "tools"])

    def test_tokenize(self):
        tokens = insights_store._tokenize("BM25-lite scoring for vault-connector!")
        self.assertIn("bm25", tokens)
        self.assertIn("lite", tokens)
        self.assertIn("vault", tokens)
        self.assertIn("connector", tokens)


class TestBM25Scoring(unittest.TestCase):
    """Test the BM25-lite scoring internals."""

    def test_idf_rarer_terms_score_higher(self):
        docs = [
            ["the", "cat", "sat"],
            ["the", "dog", "ran"],
            ["the", "bird", "flew"],
        ]
        idf = insights_store._build_idf(docs)
        # "the" appears in all 3 docs, "cat" in 1
        self.assertGreater(idf["cat"], idf["the"])

    def test_tf_counts_correctly(self):
        tokens = ["ai", "agents", "ai", "tools", "ai"]
        self.assertEqual(insights_store._tf("ai", tokens), 3)
        self.assertEqual(insights_store._tf("tools", tokens), 1)
        self.assertEqual(insights_store._tf("missing", tokens), 0)

    def test_decay_recent_is_near_one(self):
        now = time.time()
        self.assertAlmostEqual(insights_store._temporal_decay(now), 1.0, places=2)

    def test_decay_at_half_life(self):
        half_life = insights_store.DECAY_HALF_LIFE_DAYS
        past = time.time() - (half_life * 86400)
        decay = insights_store._temporal_decay(past)
        self.assertAlmostEqual(decay, 0.5, places=1)

    def test_decay_old_is_near_zero(self):
        very_old = time.time() - (365 * 86400)  # 1 year ago
        decay = insights_store._temporal_decay(very_old)
        self.assertLess(decay, 0.05)


if __name__ == "__main__":
    unittest.main()
