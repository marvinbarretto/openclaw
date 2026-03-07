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

    def test_prompt_uses_custom_categories(self):
        emails = [{"gmail_id": "abc", "sender": {"name": "S", "email": "s@e.com"},
                    "subject": "Test", "body_snippet": "snip",
                    "date": "2026-02-24T06:00:00Z", "labels": []}]
        categories = ["newsletter", "football", "job-alert"]
        prompt = build_triage_prompt(emails, {}, categories=categories)
        self.assertIn('"football"', prompt)
        self.assertIn('"job-alert"', prompt)

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


class TestPromptCalibration(unittest.TestCase):
    """Tests for prompt calibration — target shortlist rate and examples reference."""

    def test_prompt_includes_target_shortlist_rate(self):
        emails = [{"gmail_id": "abc", "sender": {"name": "S", "email": "s@e.com"},
                    "subject": "Test", "body_snippet": "snip",
                    "date": "2026-02-24T06:00:00Z", "labels": []}]
        prompt = build_triage_prompt(emails, {})
        # Prompt must guide Flash toward a 10-20% shortlist rate
        self.assertIn("10-20%", prompt)

    def test_prompt_includes_minimum_shortlist_floor(self):
        emails = [{"gmail_id": f"id_{i}", "sender": {"name": "S", "email": "s@e.com"},
                    "subject": f"Email {i}", "body_snippet": "snip",
                    "date": "2026-02-24T06:00:00Z", "labels": []}
                   for i in range(50)]
        prompt = build_triage_prompt(emails, {})
        # Must mention a minimum floor so Flash never returns 0
        self.assertRegex(prompt, r"at least \d+")

    def test_prompt_references_examples_when_provided(self):
        examples_content = "## High Value\n### Stack Overflow Newsletter\nMatches active projects"
        context = {"EMAIL_EXAMPLES.md": examples_content}
        emails = [{"gmail_id": "abc", "sender": {"name": "S", "email": "s@e.com"},
                    "subject": "Test", "body_snippet": "snip",
                    "date": "2026-02-24T06:00:00Z", "labels": []}]
        prompt = build_triage_prompt(emails, context)
        # Prompt must explicitly tell Flash to use the examples for calibration
        self.assertIn("EMAIL_EXAMPLES", prompt)
        self.assertIn("calibrat", prompt.lower())

    def test_prompt_no_longer_says_no_target_number(self):
        emails = [{"gmail_id": "abc", "sender": {"name": "S", "email": "s@e.com"},
                    "subject": "Test", "body_snippet": "snip",
                    "date": "2026-02-24T06:00:00Z", "labels": []}]
        prompt = build_triage_prompt(emails, {})
        # The old "there is no target number" phrasing caused Flash to shortlist 0
        self.assertNotIn("There is no target number", prompt)


class TestWorkerLogging(unittest.TestCase):
    """Tests for diagnostic stderr logging."""

    def test_get_context_logs_loaded_files(self):
        worker = EmailTriageWorker()
        with patch("workers.base_worker.load_context_file") as mock_load:
            mock_load.side_effect = lambda f: f"content of {f}" if f != "EMAIL_EXAMPLES.md" else None
            with patch("sys.stderr") as mock_stderr:
                mock_stderr.write = unittest.mock.MagicMock()
                context = worker.get_context()
                # Should log which files loaded and which were missing
                all_output = "".join(
                    call.args[0] for call in mock_stderr.write.call_args_list
                )
                self.assertIn("INTERESTS.md", all_output)
                self.assertIn("EMAIL_EXAMPLES.md", all_output)

    @patch("workers.base_worker.call_model")
    def test_run_logs_batch_info_to_stderr(self, mock_call):
        mock_call.return_value = {
            "text": json.dumps({
                "shortlist": [
                    {"gmail_id": "abc", "rank": 1, "category": "newsletter",
                     "reason": "test", "time_sensitive": False, "deadline": None}
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
                 "subject": "AI News", "body_snippet": "snip",
                 "date": "2026-02-24T06:00:00Z", "labels": ["INBOX"]}
            ] * 5
        }
        import io
        captured = io.StringIO()
        with patch("sys.stderr", captured):
            result = worker.run(digest)
        output = captured.getvalue()
        # Should log batch processing info
        self.assertIn("batch", output.lower())
        self.assertIn("shortlisted", output.lower())


if __name__ == "__main__":
    unittest.main()
