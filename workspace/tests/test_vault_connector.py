import json
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from workers.vault_connector import VaultConnector
import insights_store


class TestVaultConnector(unittest.TestCase):
    def setUp(self):
        """Redirect insights_store to temp file for test isolation."""
        self._tmp_insights = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tmp_insights.close()
        self._orig_insights_path = insights_store.INSIGHTS_PATH
        insights_store.INSIGHTS_PATH = self._tmp_insights.name
        os.unlink(self._tmp_insights.name)

    def tearDown(self):
        insights_store.INSIGHTS_PATH = self._orig_insights_path
        if os.path.exists(self._tmp_insights.name):
            os.unlink(self._tmp_insights.name)

    def _make_note(self, tmpdir, filename, title, note_type="task", tags="[]", priority="5", body=""):
        content = f"---\ntitle: {title}\ntype: {note_type}\nstatus: active\ntags: {tags}\npriority: {priority}\n---\n\n{body}\n"
        path = os.path.join(tmpdir, filename)
        with open(path, "w") as f:
            f.write(content)
        return path

    @patch("workers.base_worker.call_model")
    def test_match_finds_keyword_hits(self, mock_call):
        mock_call.return_value = {
            "text": json.dumps({"keywords": ["mortgage", "finance", "rates"]}),
            "input_tokens": 100,
            "output_tokens": 50,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_note(tmpdir, "finance.md", "SIPP timing", tags='["finance"]', priority="8",
                            body="Mortgage rates and SIPP contribution timing.")
            self._make_note(tmpdir, "cooking.md", "Lamb tagine", note_type="recipe", tags='["food"]',
                            body="A hearty lamb tagine recipe.")
            self._make_note(tmpdir, "travel.md", "Spain trip", note_type="travel", tags='["travel"]',
                            body="Planning a trip to Spain.")

            connector = VaultConnector(vault_dir=tmpdir)
            result = connector.match("Fed rate outlook and mortgage impact")

            self.assertGreater(len(result["matches"]), 0)
            self.assertEqual(result["matches"][0]["file"], "finance.md")

    @patch("workers.base_worker.call_model")
    def test_match_respects_max_results(self, mock_call):
        mock_call.return_value = {
            "text": json.dumps({"keywords": ["test"]}),
            "input_tokens": 100,
            "output_tokens": 50,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(10):
                self._make_note(tmpdir, f"note{i}.md", f"Test note {i}", body="test content")

            connector = VaultConnector(vault_dir=tmpdir)
            connector.max_results = 3
            result = connector.match("test query")
            self.assertLessEqual(len(result["matches"]), 3)

    @patch("workers.base_worker.call_model")
    def test_match_returns_empty_on_no_hits(self, mock_call):
        mock_call.return_value = {
            "text": json.dumps({"keywords": ["quantum", "physics"]}),
            "input_tokens": 100,
            "output_tokens": 50,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_note(tmpdir, "cooking.md", "Lamb tagine", note_type="recipe", body="A recipe.")

            connector = VaultConnector(vault_dir=tmpdir)
            result = connector.match("quantum physics research")
            self.assertEqual(len(result["matches"]), 0)

    @patch("workers.base_worker.call_model")
    def test_high_priority_note_gets_boost(self, mock_call):
        """BM25-lite: priority >= 7 should boost score by 1.3x (ADR-045)."""
        mock_call.return_value = {
            "text": json.dumps({"keywords": ["finance"]}),
            "input_tokens": 100,
            "output_tokens": 50,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_note(tmpdir, "low.md", "Finance basics", priority="3",
                            body="Basic finance stuff.")
            self._make_note(tmpdir, "high.md", "Finance urgent", priority="9",
                            body="Urgent finance stuff.")

            connector = VaultConnector(vault_dir=tmpdir)
            result = connector.match("finance query")

            self.assertEqual(len(result["matches"]), 2)
            # High priority note should rank first
            self.assertEqual(result["matches"][0]["file"], "high.md")

    @patch("workers.base_worker.call_model")
    def test_match_includes_insights(self, mock_call):
        """vault-connector should search insights.json alongside vault notes (ADR-045)."""
        mock_call.return_value = {
            "text": json.dumps({"keywords": ["finance", "sipp"]}),
            "input_tokens": 100,
            "output_tokens": 50,
        }

        # Add an insight about finance
        insights_store.add_insight(
            "vault-reader", "r1", "connection",
            "Finance bookmarks consistently match SIPP timing task — reliable connection",
            ["finance", "sipp", "bookmarks"],
            confidence=0.8,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_note(tmpdir, "finance.md", "SIPP timing", tags='["finance"]',
                            body="SIPP contribution timing.")

            connector = VaultConnector(vault_dir=tmpdir)
            result = connector.match("finance SIPP")

            # Should have both vault match and insight match
            sources = [m.get("source") for m in result["matches"]]
            self.assertIn("vault", sources)
            self.assertIn("insight", sources)

    @patch("workers.base_worker.call_model")
    def test_match_results_have_source_field(self, mock_call):
        """Each match should indicate whether it came from vault or insight (ADR-045)."""
        mock_call.return_value = {
            "text": json.dumps({"keywords": ["test"]}),
            "input_tokens": 100,
            "output_tokens": 50,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_note(tmpdir, "test.md", "Test note", body="test content here")

            connector = VaultConnector(vault_dir=tmpdir)
            result = connector.match("test")

            for m in result["matches"]:
                self.assertIn("source", m)
                self.assertIn(m["source"], ("vault", "insight"))


class TestBM25LiteScoring(unittest.TestCase):
    """Test the BM25-lite scoring internals of VaultConnector."""

    def test_tokenize(self):
        connector = VaultConnector.__new__(VaultConnector)
        tokens = connector._tokenize("BM25-lite scoring for SIPP!")
        self.assertIn("bm25", tokens)
        self.assertIn("sipp", tokens)

    def test_temporal_decay_bookmark_no_decay(self):
        connector = VaultConnector.__new__(VaultConnector)
        old_time = time.time() - (365 * 86400)  # 1 year ago
        decay = connector._temporal_decay("bookmark", old_time)
        self.assertEqual(decay, 1.0)  # Bookmarks don't decay

    def test_temporal_decay_task_decays(self):
        connector = VaultConnector.__new__(VaultConnector)
        old_time = time.time() - (30 * 86400)  # 30 days ago (= half-life for tasks)
        decay = connector._temporal_decay("task", old_time)
        self.assertAlmostEqual(decay, 0.5, places=1)

    def test_temporal_decay_idea_decays_slowly(self):
        connector = VaultConnector.__new__(VaultConnector)
        old_time = time.time() - (90 * 86400)  # 90 days ago (= half-life for ideas)
        decay = connector._temporal_decay("idea", old_time)
        self.assertAlmostEqual(decay, 0.5, places=1)


if __name__ == "__main__":
    unittest.main()
