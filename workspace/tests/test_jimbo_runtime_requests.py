"""Tests for the Jimbo runtime request contract."""

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock


WORKSPACE_DIR = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, WORKSPACE_DIR)


def load_runtime_requests():
    module_path = os.path.join(WORKSPACE_DIR, 'jimbo_runtime_requests.py')
    spec = importlib.util.spec_from_file_location('jimbo_runtime_requests_module', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestJimboRuntimeRequests(unittest.TestCase):

    def test_load_runtime_request_from_file(self):
        runtime_requests = load_runtime_requests()
        request = {"command": "emit", "producer": "dispatch-proposal"}

        with tempfile.NamedTemporaryFile("w+", delete=False) as tmp:
            json.dump(request, tmp)
            tmp_path = tmp.name

        try:
            loaded = runtime_requests.load_runtime_request(request_file=tmp_path)
        finally:
            os.unlink(tmp_path)

        self.assertEqual(loaded, request)

    def test_load_runtime_request_from_stdin(self):
        runtime_requests = load_runtime_requests()
        request = {"command": "emit", "producer": "dispatch-proposal"}

        with mock.patch.object(runtime_requests.sys, "stdin", io.StringIO(json.dumps(request))):
            loaded = runtime_requests.load_runtime_request(request_file="-")

        self.assertEqual(loaded, request)

    def test_normalize_runtime_request_requires_supported_command(self):
        runtime_requests = load_runtime_requests()

        with self.assertRaisesRegex(ValueError, "Unsupported runtime request command"):
            runtime_requests.normalize_runtime_request({"command": "nope"})

    def test_normalize_emit_request_requires_producer(self):
        runtime_requests = load_runtime_requests()

        with self.assertRaisesRegex(ValueError, "emit requests require producer"):
            runtime_requests.normalize_runtime_request({"command": "emit"})

    def test_normalize_resolve_request_accepts_producer_source(self):
        runtime_requests = load_runtime_requests()

        normalized = runtime_requests.normalize_runtime_request({
            "request_id": "req-1",
            "command": "resolve",
            "producer": "dispatch-proposal",
            "live": True,
        })

        self.assertEqual(normalized["request_id"], "req-1")
        self.assertEqual(normalized["command"], "resolve")
        self.assertEqual(normalized["producer"], "dispatch-proposal")
        self.assertTrue(normalized["live"])

    def test_normalize_summary_request_rejects_live(self):
        runtime_requests = load_runtime_requests()

        with self.assertRaisesRegex(ValueError, "do not support live execution"):
            runtime_requests.normalize_runtime_request({
                "command": "summary",
                "producer": "dispatch-proposal",
                "live": True,
            })

    def test_normalize_report_request_requires_single_producer_source(self):
        runtime_requests = load_runtime_requests()

        with self.assertRaisesRegex(ValueError, "report requests require exactly one producer source"):
            runtime_requests.normalize_runtime_request({
                "command": "report",
                "producer": "dispatch-proposal",
                "intake_json": "{}",
            })

    def test_iter_runtime_requests_reads_newline_delimited_json(self):
        runtime_requests = load_runtime_requests()

        with tempfile.NamedTemporaryFile("w+", delete=False) as tmp:
            tmp.write('{"command":"emit","producer":"dispatch-proposal"}\n')
            tmp.write('\n')
            tmp.write('{"command":"summary","producer":"vault-triage"}\n')
            tmp_path = tmp.name

        try:
            loaded = list(runtime_requests.iter_runtime_requests(request_file=tmp_path))
        finally:
            os.unlink(tmp_path)

        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]["command"], "emit")
        self.assertEqual(loaded[1]["producer"], "vault-triage")
