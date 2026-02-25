import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from workers.email_triage import EmailTriageWorker, build_triage_prompt


class TestBuildTriagePrompt(unittest.TestCase):
    def test_prompt_includes_emails_and_context(self):
        emails = [
            {"gmail_id": "abc", "sender": {"name": "Test", "email": "test@example.com"},
             "subject": "Newsletter", "body_snippet": "Great article about AI",
             "body": "Full body here", "date": "2026-02-24T06:00:00Z", "labels": ["INBOX"]},
        ]
        context = {"INTERESTS.md": "AI and agents", "TASTE.md": "Surprising, niche"}
        prompt = build_triage_prompt(emails, context)
        self.assertIn("Newsletter", prompt)
        self.assertIn("AI and agents", prompt)
        self.assertIn("Surprising, niche", prompt)
        self.assertIn("abc", prompt)

    def test_prompt_batches_correctly(self):
        emails = [{"gmail_id": f"id_{i}", "sender": {"name": "S", "email": "s@e.com"},
                    "subject": f"Email {i}", "body_snippet": "snip", "body": "body",
                    "date": "2026-02-24T06:00:00Z", "labels": []}
                   for i in range(100)]
        context = {}
        prompt = build_triage_prompt(emails[:50], context)
        self.assertIn("Email 0", prompt)
        self.assertIn("Email 49", prompt)
        self.assertIn("50 total", prompt)


class TestEmailTriageWorker(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ["EXPERIMENT_TRACKER_DB"] = os.path.join(self.tmpdir, "tracker.db")

    def tearDown(self):
        os.environ.pop("EXPERIMENT_TRACKER_DB", None)

    @patch("workers.base_worker.call_model")
    def test_run_returns_shortlist(self, mock_call):
        mock_call.return_value = {
            "text": json.dumps({
                "shortlist": [
                    {"gmail_id": "abc", "rank": 1, "category": "newsletter",
                     "reason": "AI content", "time_sensitive": False, "deadline": None}
                ],
                "stats": {"total_reviewed": 5, "shortlisted": 1, "skipped": 4}
            }),
            "input_tokens": 5000,
            "output_tokens": 500,
        }

        worker = EmailTriageWorker()
        digest = {
            "items": [
                {"gmail_id": "abc", "sender": {"name": "T", "email": "t@e.com"},
                 "subject": "AI News", "body_snippet": "snip", "body": "full body",
                 "date": "2026-02-24T06:00:00Z", "links": [], "labels": ["INBOX"]}
            ] * 5
        }
        result = worker.run(digest)
        self.assertIn("shortlist", result)
        self.assertEqual(len(result["shortlist"]), 1)
        self.assertEqual(result["shortlist"][0]["gmail_id"], "abc")
        self.assertEqual(result["stats"]["total_reviewed"], 5)

    @patch("workers.base_worker.call_model")
    def test_run_handles_empty_digest(self, mock_call):
        worker = EmailTriageWorker()
        result = worker.run({"items": []})
        self.assertEqual(result["shortlist"], [])
        self.assertEqual(result["stats"]["total_reviewed"], 0)
        mock_call.assert_not_called()

    @patch("workers.base_worker.call_model")
    def test_run_handles_malformed_json_response(self, mock_call):
        mock_call.return_value = {
            "text": "not valid json {{{",
            "input_tokens": 100,
            "output_tokens": 10,
        }
        worker = EmailTriageWorker()
        digest = {
            "items": [
                {"gmail_id": "abc", "sender": {"name": "T", "email": "t@e.com"},
                 "subject": "Test", "body_snippet": "snip", "body": "body",
                 "date": "2026-02-24T06:00:00Z", "links": [], "labels": []}
            ]
        }
        result = worker.run(digest)
        # Should gracefully return empty shortlist, not crash
        self.assertEqual(result["shortlist"], [])


if __name__ == "__main__":
    unittest.main()
