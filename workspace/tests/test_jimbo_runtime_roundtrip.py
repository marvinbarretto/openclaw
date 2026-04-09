"""Tests for the Jimbo runtime roundtrip helper."""

import importlib.util
import os
import sys
import unittest
from unittest import mock


WORKSPACE_DIR = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, WORKSPACE_DIR)


def load_runtime_roundtrip():
    module_path = os.path.join(WORKSPACE_DIR, 'jimbo_runtime_roundtrip.py')
    spec = importlib.util.spec_from_file_location('jimbo_runtime_roundtrip_module', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestJimboRuntimeRoundtrip(unittest.TestCase):

    def test_build_runtime_cli_command_supports_live_mode(self):
        roundtrip = load_runtime_roundtrip()

        dry_cmd = roundtrip.build_runtime_cli_command(live=False)
        live_cmd = roundtrip.build_runtime_cli_command(live=True)

        self.assertEqual(dry_cmd[-2:], ['--intake-file', '-'])
        self.assertEqual(live_cmd[-3:], ['--intake-file', '-', '--live'])

    def test_run_roundtrip_pipes_producer_output_into_runtime_cli(self):
        roundtrip = load_runtime_roundtrip()

        with mock.patch.object(roundtrip, 'run_subprocess', side_effect=['[{"source":"dispatch"}]', '{"mode":"resolved"}']) as run_subprocess:
            output = roundtrip.run_roundtrip('dispatch-proposal')

        self.assertEqual(output, '{"mode":"resolved"}')
        self.assertEqual(run_subprocess.call_count, 2)
        producer_call = run_subprocess.call_args_list[0]
        runtime_call = run_subprocess.call_args_list[1]
        self.assertIn('dispatch.py', producer_call.args[0][1])
        self.assertIn('jimbo_runtime_cli.py', runtime_call.args[0][1])
        self.assertEqual(runtime_call.kwargs['stdin_text'], '[{"source":"dispatch"}]')

    def test_run_roundtrip_rejects_unknown_producer(self):
        roundtrip = load_runtime_roundtrip()

        with self.assertRaisesRegex(ValueError, 'Unknown producer'):
            roundtrip.run_roundtrip('nope')


if __name__ == '__main__':
    unittest.main()
