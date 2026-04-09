"""Tests for the Jimbo runtime operational roundtrip helpers."""

import importlib.util
import os
import sys
import unittest
from unittest import mock


WORKSPACE_DIR = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, WORKSPACE_DIR)


def load_runtime_roundtrip():
    module_path = os.path.join(WORKSPACE_DIR, 'jimbo_runtime_ops.py')
    spec = importlib.util.spec_from_file_location('jimbo_runtime_ops_module', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestJimboRuntimeRoundtrip(unittest.TestCase):

    def test_build_runtime_cli_command_supports_live_mode(self):
        roundtrip = load_runtime_roundtrip()

        dry_cmd = roundtrip.build_runtime_cli_command('dispatch-proposal', live=False)
        live_cmd = roundtrip.build_runtime_cli_command('dispatch-proposal', live=True)
        summary_cmd = roundtrip.build_runtime_cli_command('dispatch-proposal', summary=True)

        self.assertEqual(dry_cmd[-3:], ['resolve', '--producer', 'dispatch-proposal'])
        self.assertEqual(live_cmd[-4:], ['resolve', '--producer', 'dispatch-proposal', '--live'])
        self.assertEqual(summary_cmd[-3:], ['summary', '--producer', 'dispatch-proposal'])
        self.assertIn('jimbo_runtime_tool.py', summary_cmd[1])

    def test_run_roundtrip_executes_runtime_tool_with_producer(self):
        roundtrip = load_runtime_roundtrip()

        with mock.patch.object(roundtrip, 'run_subprocess', return_value='{"mode":"resolved"}') as run_subprocess:
            output = roundtrip.run_roundtrip('dispatch-proposal')

        self.assertEqual(output, '{"mode":"resolved"}')
        run_subprocess.assert_called_once()
        runtime_call = run_subprocess.call_args
        self.assertIn('jimbo_runtime_tool.py', runtime_call.args[0][1])
        self.assertIn('resolve', runtime_call.args[0])
        self.assertIn('--producer', runtime_call.args[0])
        self.assertIn('dispatch-proposal', runtime_call.args[0])

    def test_run_roundtrip_can_target_summary_surface(self):
        roundtrip = load_runtime_roundtrip()

        with mock.patch.object(roundtrip, 'run_subprocess', return_value='{"mode":"summary"}') as run_subprocess:
            output = roundtrip.run_roundtrip('dispatch-proposal', summary=True)

        self.assertEqual(output, '{"mode":"summary"}')
        runtime_call = run_subprocess.call_args
        self.assertIn('jimbo_runtime_tool.py', runtime_call.args[0][1])
        self.assertIn('summary', runtime_call.args[0])
        self.assertIn('--producer', runtime_call.args[0])

    def test_run_roundtrip_rejects_unknown_producer(self):
        roundtrip = load_runtime_roundtrip()

        with mock.patch.object(roundtrip, 'run_subprocess', side_effect=ValueError('Unknown producer: nope')):
            with self.assertRaisesRegex(ValueError, 'Unknown producer'):
                roundtrip.run_roundtrip('nope')

    def test_run_roundtrip_rejects_live_summary_combination(self):
        roundtrip = load_runtime_roundtrip()

        with self.assertRaisesRegex(ValueError, 'does not support live execution'):
            roundtrip.run_roundtrip('dispatch-proposal', live=True, summary=True)


if __name__ == '__main__':
    unittest.main()
