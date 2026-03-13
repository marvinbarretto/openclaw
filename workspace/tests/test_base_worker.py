import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from workers.base_worker import BaseWorker, load_task_config, call_google_ai, call_anthropic, call_openrouter, call_model


class TestLoadTaskConfig(unittest.TestCase):
    def test_loads_email_triage_config(self):
        config = load_task_config("email-triage")
        self.assertEqual(config["task_id"], "email-triage")
        self.assertEqual(config["default_model"], "gemini-2.5-flash")

    def test_missing_config_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_task_config("nonexistent-task")


class TestBaseWorker(unittest.TestCase):
    def test_worker_init_loads_config(self):
        worker = BaseWorker("email-triage")
        self.assertEqual(worker.task_id, "email-triage")
        self.assertEqual(worker.config["default_model"], "gemini-2.5-flash")
        self.assertIsNotNone(worker.run_id)

    @patch("subprocess.run")
    def test_worker_log_run_calls_tracker_script(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='{"status":"ok","run_id":"run_test","cost_usd":0.001}', stderr='')
        worker = BaseWorker("email-triage")
        worker.log_run(
            model="gemini-2.5-flash",
            input_tokens=5000,
            output_tokens=500,
            input_summary="200 emails",
            output_summary="30 shortlisted",
        )
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertIn("experiment-tracker.py", cmd[1])
        self.assertIn("--task", cmd)
        self.assertIn("email-triage", cmd)


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


class TestCallModelTracing(unittest.TestCase):
    @patch("workers.base_worker.trace_to_langfuse")
    @patch("workers.base_worker.urllib.request.urlopen")
    def test_call_model_traces_to_langfuse(self, mock_urlopen, mock_trace):
        """call_model() calls trace_to_langfuse after getting a response."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        from workers.base_worker import call_model
        result = call_model("test prompt", model="gemini-2.5-flash", api_key="fake")

        self.assertEqual(result["text"], "ok")
        mock_trace.assert_called_once()
        call_args = mock_trace.call_args
        self.assertEqual(call_args.kwargs["model"], "gemini-2.5-flash")
        self.assertEqual(call_args.kwargs["prompt"], "test prompt")
        self.assertEqual(call_args.kwargs["response"], "ok")


class TestOpenRouterRouting(unittest.TestCase):
    def test_call_model_routes_openrouter_prefix(self):
        """Models with openrouter/ prefix should route to call_openrouter."""
        with self.assertRaises(RuntimeError) as ctx:
            call_model("test", model="openrouter/moonshotai/kimi-k2:free")
        self.assertIn("OPENROUTER_API_KEY", str(ctx.exception))

    def test_call_model_routes_openrouter_provider(self):
        """Provider='openrouter' should route to call_openrouter."""
        with self.assertRaises(RuntimeError) as ctx:
            call_model("test", model="some-model", provider="openrouter")
        self.assertIn("OPENROUTER_API_KEY", str(ctx.exception))

    def test_call_model_routes_gemini(self):
        """Gemini models should route to Google AI."""
        saved = os.environ.pop("GOOGLE_AI_API_KEY", None)
        try:
            with self.assertRaises(RuntimeError) as ctx:
                call_model("test", model="gemini-2.5-flash")
            self.assertIn("GOOGLE_AI_API_KEY", str(ctx.exception))
        finally:
            if saved is not None:
                os.environ["GOOGLE_AI_API_KEY"] = saved

    def test_call_model_routes_claude(self):
        """Claude models should route to Anthropic."""
        with self.assertRaises(RuntimeError) as ctx:
            call_model("test", model="claude-haiku-4.5")
        self.assertIn("ANTHROPIC_API_KEY", str(ctx.exception))

    @patch("workers.base_worker.trace_to_langfuse")
    @patch("workers.base_worker.urllib.request.urlopen")
    def test_openrouter_strips_prefix(self, mock_urlopen, mock_trace):
        """call_model should strip openrouter/ prefix before sending to API."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        os.environ["OPENROUTER_API_KEY"] = "fake-key"
        try:
            result = call_model("test", model="openrouter/moonshotai/kimi-k2:free")
            self.assertEqual(result["text"], "ok")
            # Verify the request body has prefix stripped
            req = mock_urlopen.call_args[0][0]
            body = json.loads(req.data)
            self.assertEqual(body["model"], "moonshotai/kimi-k2:free")
        finally:
            del os.environ["OPENROUTER_API_KEY"]


class TestMultimodalGoogleAI(unittest.TestCase):
    @patch("workers.base_worker.urllib.request.urlopen")
    def test_call_google_ai_builds_multimodal_parts(self, mock_urlopen):
        """When images are provided, call_google_ai should include inline_data parts."""
        import base64

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "test response"}]}}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = call_google_ai(
            "Describe this image",
            api_key="fake-key",
            images=[{"data": base64.b64encode(b"fake-png").decode(), "mime_type": "image/png"}],
        )

        self.assertEqual(result["text"], "test response")

        # Verify the request body includes image parts
        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data)
        parts = body["contents"][0]["parts"]
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0]["text"], "Describe this image")
        self.assertEqual(parts[1]["inline_data"]["mime_type"], "image/png")

    @patch("workers.base_worker.urllib.request.urlopen")
    def test_call_google_ai_text_only_no_images(self, mock_urlopen):
        """Without images, call_google_ai should have only text part."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "hello"}]}}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        call_google_ai("test", api_key="fake-key")

        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data)
        parts = body["contents"][0]["parts"]
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0]["text"], "test")


if __name__ == "__main__":
    unittest.main()
