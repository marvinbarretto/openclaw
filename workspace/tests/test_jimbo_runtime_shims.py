"""Tests for compatibility shim CLIs that forward into the top-level tool."""

import importlib.util
import os
import sys
import unittest
from unittest import mock


WORKSPACE_DIR = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, WORKSPACE_DIR)


def load_module(filename, module_name):
    module_path = os.path.join(WORKSPACE_DIR, filename)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestJimboRuntimeShims(unittest.TestCase):

    def test_cli_shim_routes_to_top_level_tool(self):
        runtime_cli = load_module('jimbo_runtime_cli.py', 'jimbo_runtime_cli_module')

        with mock.patch('jimbo_runtime_tool.main', return_value=0) as tool_main:
            exit_code = runtime_cli.main(['--intake-file', '/tmp/intake.json'])

        self.assertEqual(exit_code, 0)
        tool_main.assert_called_once_with(['resolve', '--intake-file', '/tmp/intake.json'])

    def test_summary_shim_routes_to_top_level_tool(self):
        runtime_summary = load_module('jimbo_runtime_summary.py', 'jimbo_runtime_summary_module')

        with mock.patch('jimbo_runtime_tool.main', return_value=0) as tool_main:
            exit_code = runtime_summary.main(['--intake-file', '/tmp/intake.json'])

        self.assertEqual(exit_code, 0)
        tool_main.assert_called_once_with(['summary', '--intake-file', '/tmp/intake.json'])

    def test_report_shim_routes_to_top_level_tool(self):
        runtime_report = load_module('jimbo_runtime_report.py', 'jimbo_runtime_report_module')

        with mock.patch('jimbo_runtime_tool.main', return_value=0) as tool_main:
            exit_code = runtime_report.main(['--producer', 'dispatch-proposal'])

        self.assertEqual(exit_code, 0)
        tool_main.assert_called_once_with(['report', '--producer', 'dispatch-proposal'])

    def test_roundtrip_shim_routes_to_top_level_tool(self):
        runtime_roundtrip = load_module('jimbo_runtime_roundtrip.py', 'jimbo_runtime_roundtrip_module')

        with mock.patch('jimbo_runtime_tool.main', return_value=0) as tool_main:
            exit_code = runtime_roundtrip.main(['--producer', 'dispatch-proposal'])

        self.assertEqual(exit_code, 0)
        tool_main.assert_called_once_with(['roundtrip', '--producer', 'dispatch-proposal'])


if __name__ == '__main__':
    unittest.main()
