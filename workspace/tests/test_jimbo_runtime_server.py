"""Tests for the Jimbo runtime server entrypoint."""

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


def load_runtime_server():
    module_path = os.path.join(WORKSPACE_DIR, 'jimbo_runtime_server.py')
    spec = importlib.util.spec_from_file_location('jimbo_runtime_server_module', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestJimboRuntimeServer(unittest.TestCase):

    def test_serve_request_stream_writes_all_responses(self):
        runtime_server = load_runtime_server()
        output = io.StringIO()

        with mock.patch.object(runtime_server, 'iter_runtime_requests', return_value=[
            {'request_id': 'req-1', 'command': 'emit', 'producer': 'dispatch-proposal'},
            {'request_id': 'req-2', 'command': 'summary', 'producer': 'vault-triage'},
        ]) as iter_runtime_requests, \
             mock.patch.object(runtime_server, 'stream_runtime_requests', return_value=[
                 {'request_id': 'req-1', 'command': 'emit', 'result': []},
                 {'request_id': 'req-2', 'command': 'summary', 'result': {'mode': 'summary'}},
             ]) as stream_runtime_requests:
            stats = runtime_server.serve_request_stream(
                request_file='-',
                continue_on_error=True,
                output_stream=output,
            )

        iter_runtime_requests.assert_called_once_with(request_file='-')
        stream_runtime_requests.assert_called_once()
        lines = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]['request_id'], 'req-1')
        self.assertEqual(stats['responses'], 2)
        self.assertEqual(stats['errors'], 0)
        self.assertTrue(stats['started_at'].endswith('Z'))
        self.assertTrue(stats['completed_at'].endswith('Z'))
        self.assertEqual(stats['request_file'], '-')

    def test_serve_request_stream_counts_error_responses(self):
        runtime_server = load_runtime_server()
        output = io.StringIO()

        with mock.patch.object(runtime_server, 'iter_runtime_requests', return_value=[]), \
             mock.patch.object(runtime_server, 'stream_runtime_requests', return_value=[
                 {'ok': False, 'request_id': 'req-2', 'error': 'bad request', 'request': {'request_id': 'req-2'}},
             ]):
            stats = runtime_server.serve_request_stream(
                request_file='-',
                continue_on_error=True,
                output_stream=output,
            )

        self.assertEqual(stats['responses'], 1)
        self.assertEqual(stats['errors'], 1)

    def test_write_server_stats_persists_json_file(self):
        runtime_server = load_runtime_server()
        stats = {
            'started_at': '2026-04-09T12:00:00Z',
            'completed_at': '2026-04-09T12:00:01Z',
            'request_file': '-',
            'responses': 2,
            'errors': 0,
            'continue_on_error': True,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, 'runtime-server-stats.json')
            runtime_server.write_server_stats(stats, output_path)
            with open(output_path) as f:
                written = json.load(f)

        self.assertEqual(written['responses'], 2)
        self.assertEqual(written['request_file'], '-')

    def test_main_returns_error_code_on_server_failure(self):
        runtime_server = load_runtime_server()

        with mock.patch.object(runtime_server, 'serve_request_stream', side_effect=ValueError('boom')), \
             mock.patch.object(runtime_server.sys, 'stderr') as stderr:
            exit_code = runtime_server.main(['--request-file', '-'])

        self.assertEqual(exit_code, 1)
        stderr.write.assert_called()

    def test_main_can_write_stats_file(self):
        runtime_server = load_runtime_server()

        with mock.patch.object(runtime_server, 'serve_request_stream', return_value={
            'started_at': '2026-04-09T12:00:00Z',
            'completed_at': '2026-04-09T12:00:01Z',
            'request_file': '-',
            'responses': 1,
            'errors': 0,
            'continue_on_error': True,
        }) as serve_request_stream, \
             mock.patch.object(runtime_server, 'write_server_stats') as write_server_stats:
            exit_code = runtime_server.main(['--request-file', '-', '--stats-file', '/tmp/server-stats.json'])

        self.assertEqual(exit_code, 0)
        serve_request_stream.assert_called_once()
        write_server_stats.assert_called_once_with(
            {
                'started_at': '2026-04-09T12:00:00Z',
                'completed_at': '2026-04-09T12:00:01Z',
                'request_file': '-',
                'responses': 1,
                'errors': 0,
                'continue_on_error': True,
            },
            '/tmp/server-stats.json',
        )
