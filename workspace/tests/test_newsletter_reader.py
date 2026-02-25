import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from workers.newsletter_reader import NewsletterReaderWorker, build_reader_prompt


class TestBuildReaderPrompt(unittest.TestCase):
    def test_prompt_includes_full_body(self):
        emails = [
            {"gmail_id": "abc", "sender": {"name": "Dense Discovery", "email": "dd@example.com"},
             "subject": "Issue 287", "body": "This week: amazing article about local-first software...",
             "links": ["https://example.com/article"]},
        ]
        context = {"INTERESTS.md": "AI, frontend dev", "PRIORITIES.md": "LocalShout this week"}
        prompt = build_reader_prompt(emails, context)
        self.assertIn("local-first software", prompt)
        self.assertIn("LocalShout this week", prompt)
        self.assertIn("https://example.com/article", prompt)
        self.assertIn("Dense Discovery", prompt)

    def test_prompt_includes_all_context_files(self):
        emails = [{"gmail_id": "x", "sender": {"name": "S", "email": "s@e.com"},
                    "subject": "Test", "body": "body", "links": []}]
        context = {
            "INTERESTS.md": "music, tech",
            "TASTE.md": "niche, surprising",
            "PRIORITIES.md": "Spoons this week",
            "GOALS.md": "ship LocalShout",
        }
        prompt = build_reader_prompt(emails, context)
        for value in context.values():
            self.assertIn(value, prompt)


class TestNewsletterReaderWorker(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ["EXPERIMENT_TRACKER_DB"] = os.path.join(self.tmpdir, "tracker.db")

    def tearDown(self):
        os.environ.pop("EXPERIMENT_TRACKER_DB", None)

    @patch("workers.base_worker.call_model")
    def test_run_returns_gems_and_skipped(self, mock_call):
        mock_call.return_value = {
            "text": json.dumps({
                "gems": [
                    {"gmail_id": "abc", "source": "Dense Discovery", "title": "Local-first article",
                     "why": "Connects to LocalShout architecture", "confidence": 0.85,
                     "links": ["https://example.com"],
                     "time_sensitive": False, "deadline": None, "price": None, "surprise_candidate": True}
                ],
                "skipped": [
                    {"gmail_id": "def", "source": "Generic Sender", "reason": "Marketing fluff, nothing specific"}
                ],
                "stats": {"newsletters_read": 2, "gems_extracted": 1, "links_found": 1, "skipped_count": 1}
            }),
            "input_tokens": 40000,
            "output_tokens": 2000,
        }

        worker = NewsletterReaderWorker()
        shortlist_data = {
            "shortlist": [
                {"gmail_id": "abc", "rank": 1, "category": "newsletter", "reason": "AI content"},
                {"gmail_id": "def", "rank": 2, "category": "newsletter", "reason": "Maybe useful"},
            ],
            "emails": {
                "abc": {"gmail_id": "abc", "sender": {"name": "DD", "email": "dd@e.com"},
                        "subject": "Issue 287", "body": "Full newsletter body here...",
                        "links": ["https://example.com"], "labels": []},
                "def": {"gmail_id": "def", "sender": {"name": "Generic", "email": "g@e.com"},
                        "subject": "Weekly Update", "body": "Buy our stuff...",
                        "links": [], "labels": []},
            }
        }
        result = worker.run(shortlist_data)
        self.assertIn("gems", result)
        self.assertIn("skipped", result)
        self.assertEqual(len(result["gems"]), 1)
        self.assertEqual(len(result["skipped"]), 1)
        self.assertTrue(result["gems"][0]["surprise_candidate"])
        self.assertEqual(result["gems"][0]["confidence"], 0.85)
        self.assertEqual(result["stats"]["skipped_count"], 1)

    @patch("workers.base_worker.call_model")
    def test_run_handles_empty_shortlist(self, mock_call):
        worker = NewsletterReaderWorker()
        result = worker.run({"shortlist": [], "emails": {}})
        self.assertEqual(result["gems"], [])
        mock_call.assert_not_called()

    @patch("workers.base_worker.call_model")
    def test_run_skips_emails_not_in_lookup(self, mock_call):
        mock_call.return_value = {
            "text": json.dumps({"gems": [], "stats": {"newsletters_read": 0, "gems_extracted": 0, "links_found": 0}}),
            "input_tokens": 100, "output_tokens": 50,
        }
        worker = NewsletterReaderWorker()
        shortlist_data = {
            "shortlist": [{"gmail_id": "missing_id", "rank": 1, "category": "newsletter"}],
            "emails": {}  # no matching email
        }
        result = worker.run(shortlist_data)
        self.assertEqual(result["gems"], [])


if __name__ == "__main__":
    unittest.main()
