import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from workers.vault_connector import VaultConnector


class TestVaultConnector(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
