import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from workers.base_worker import BaseWorker, load_task_config, call_google_ai, call_anthropic


class TestLoadTaskConfig(unittest.TestCase):
    def test_loads_email_triage_config(self):
        config = load_task_config("email-triage")
        self.assertEqual(config["task_id"], "email-triage")
        self.assertEqual(config["default_model"], "gemini-2.5-flash")

    def test_missing_config_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_task_config("nonexistent-task")


class TestBaseWorker(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "experiment-tracker.db")
        os.environ["EXPERIMENT_TRACKER_DB"] = self.db_path

    def tearDown(self):
        os.environ.pop("EXPERIMENT_TRACKER_DB", None)

    def test_worker_init_loads_config(self):
        worker = BaseWorker("email-triage")
        self.assertEqual(worker.task_id, "email-triage")
        self.assertEqual(worker.config["default_model"], "gemini-2.5-flash")
        self.assertIsNotNone(worker.run_id)

    def test_worker_log_run_writes_to_tracker(self):
        import sqlite3
        worker = BaseWorker("email-triage")
        worker.log_run(
            model="gemini-2.5-flash",
            input_tokens=5000,
            output_tokens=500,
            input_summary="200 emails",
            output_summary="30 shortlisted",
        )
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM runs").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["task_id"], "email-triage")
        db.close()


class TestApiClients(unittest.TestCase):
    @patch("workers.base_worker.urllib.request.urlopen")
    def test_call_google_ai_sends_request(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "hello"}]}}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = call_google_ai("test prompt", model="gemini-2.5-flash", api_key="fake-key")
        self.assertEqual(result["text"], "hello")
        self.assertEqual(result["input_tokens"], 10)
        self.assertEqual(result["output_tokens"], 5)

    @patch("workers.base_worker.urllib.request.urlopen")
    def test_call_anthropic_sends_request(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "content": [{"text": "hello"}],
            "usage": {"input_tokens": 10, "output_tokens": 5}
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = call_anthropic("test prompt", model="claude-haiku-4.5", api_key="fake-key")
        self.assertEqual(result["text"], "hello")
        self.assertEqual(result["input_tokens"], 10)


class TestLangfuseTracing(unittest.TestCase):
    @patch("workers.base_worker.urllib.request.urlopen")
    def test_trace_to_langfuse_posts_batch(self, mock_urlopen):
        """LangFuse tracing POSTs a batch with trace-create and generation-create."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"successes":[],"errors":[]}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        os.environ["LANGFUSE_PUBLIC_KEY"] = "pk-test"
        os.environ["LANGFUSE_SECRET_KEY"] = "sk-test"
        os.environ["LANGFUSE_HOST"] = "https://cloud.langfuse.com"

        from workers.base_worker import trace_to_langfuse
        trace_to_langfuse(
            trace_name="email-triage",
            run_id="run_abc123",
            model="gemini-2.5-flash",
            prompt="test prompt",
            response="test response",
            input_tokens=100,
            output_tokens=50,
            duration_ms=1234,
        )

        # Verify it called urlopen
        self.assertTrue(mock_urlopen.called)
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/api/public/ingestion", req.full_url)

        # Verify auth header is Basic
        auth = req.get_header("Authorization")
        self.assertTrue(auth.startswith("Basic "))

        # Verify batch contains trace-create and generation-create
        body = json.loads(req.data)
        types = [e["type"] for e in body["batch"]]
        self.assertIn("trace-create", types)
        self.assertIn("generation-create", types)

        os.environ.pop("LANGFUSE_PUBLIC_KEY")
        os.environ.pop("LANGFUSE_SECRET_KEY")
        os.environ.pop("LANGFUSE_HOST")

    def test_trace_to_langfuse_noop_without_env(self):
        """LangFuse tracing does nothing if env vars are missing."""
        os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
        os.environ.pop("LANGFUSE_SECRET_KEY", None)

        from workers.base_worker import trace_to_langfuse
        # Should not raise
        trace_to_langfuse(
            trace_name="test",
            run_id="run_123",
            model="test",
            prompt="test",
            response="test",
            input_tokens=0,
            output_tokens=0,
            duration_ms=0,
        )


if __name__ == "__main__":
    unittest.main()
