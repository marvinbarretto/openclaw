import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from workers.vault_reader import VaultReader, fetch_url_text


class TestFetchUrlText(unittest.TestCase):
    @patch("workers.vault_reader.urllib.request.urlopen")
    def test_fetches_and_strips_html(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html><body><p>Article content here.</p></body></html>"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.headers = {"content-type": "text/html"}
        mock_urlopen.return_value = mock_resp

        text = fetch_url_text("https://example.com/article")
        self.assertIn("Article content here", text)
        self.assertNotIn("<p>", text)

    @patch("workers.vault_reader.urllib.request.urlopen")
    def test_truncates_long_content(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = ("<p>" + "x" * 10000 + "</p>").encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.headers = {"content-type": "text/html"}
        mock_urlopen.return_value = mock_resp

        text = fetch_url_text("https://example.com/long", max_chars=5000)
        self.assertLessEqual(len(text), 5000)

    @patch("workers.vault_reader.urllib.request.urlopen")
    def test_handles_timeout(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("timeout")
        text = fetch_url_text("https://example.com/slow")
        self.assertIsNone(text)


class TestVaultReader(unittest.TestCase):
    def _make_bookmark(self, tmpdir, filename="bookmark-test.md", url="https://example.com/article", enriched=False):
        content = f"---\nid: note_test\ntype: bookmark\nstatus: active\ntags: [\"ai\"]\ntitle: Test Bookmark\n"
        if enriched:
            content += "enriched: true\nenriched_at: 2026-03-17T00:00:00Z\n"
        content += f"---\n\n## Links\n- {url}\n"
        path = os.path.join(tmpdir, filename)
        with open(path, "w") as f:
            f.write(content)
        return path

    @patch("workers.vault_reader.fetch_url_text")
    @patch("workers.base_worker.call_model")
    def test_read_enriches_bookmark(self, mock_call, mock_fetch):
        mock_fetch.return_value = "Article about agent architectures and tool use patterns."
        mock_call.return_value = {
            "text": json.dumps({
                "summary": "Overview of agent architectures.",
                "themes": ["agents", "tool-use"],
                "entities": ["LangChain", "OpenAI"],
                "connections": ["LocalShout AI pipeline"]
            }),
            "input_tokens": 1000,
            "output_tokens": 200,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._make_bookmark(tmpdir)
            worker = VaultReader(vault_dir=tmpdir)
            result = worker.read(path)

            self.assertEqual(result["status"], "enriched")
            self.assertIn("agent architectures", result["summary"])

            # Verify file was updated
            with open(path) as f:
                content = f.read()
            self.assertIn("enriched: true", content)
            self.assertIn("Overview of agent architectures", content)

    @patch("workers.vault_reader.fetch_url_text")
    def test_read_skips_already_enriched(self, mock_fetch):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._make_bookmark(tmpdir, enriched=True)
            worker = VaultReader(vault_dir=tmpdir)
            result = worker.read(path)
            self.assertEqual(result["status"], "already_enriched")
            mock_fetch.assert_not_called()

    def test_read_no_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "note.md")
            with open(path, "w") as f:
                f.write("---\ntype: task\ntitle: No URL\n---\n\nJust a task.\n")
            worker = VaultReader(vault_dir=tmpdir)
            result = worker.read(path)
            self.assertEqual(result["status"], "no_url")

    def test_next_picks_oldest_unread(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two bookmarks — older one should be picked first
            self._make_bookmark(tmpdir, "old.md", "https://example.com/old")
            import time; time.sleep(0.1)
            self._make_bookmark(tmpdir, "new.md", "https://example.com/new")

            worker = VaultReader(vault_dir=tmpdir)
            path = worker.find_next()
            self.assertTrue(path.endswith("old.md"))

    def test_stats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_bookmark(tmpdir, "a.md", enriched=False)
            self._make_bookmark(tmpdir, "b.md", enriched=True)
            self._make_bookmark(tmpdir, "c.md", enriched=False)

            worker = VaultReader(vault_dir=tmpdir)
            stats = worker.stats()
            self.assertEqual(stats["total_bookmarks"], 3)
            self.assertEqual(stats["enriched"], 1)
            self.assertEqual(stats["unread"], 2)


if __name__ == "__main__":
    unittest.main()
