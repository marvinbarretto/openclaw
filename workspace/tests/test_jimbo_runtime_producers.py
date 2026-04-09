"""Tests for the shared Jimbo runtime producer registry."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestJimboRuntimeProducers(unittest.TestCase):

    def test_build_producer_commands_includes_known_emitters(self):
        from jimbo_runtime_producers import build_producer_commands

        commands = build_producer_commands()

        self.assertIn('dispatch-proposal', commands)
        self.assertIn('dispatch-worker', commands)
        self.assertIn('vault-triage', commands)
        self.assertIn('dispatch.py', commands['dispatch-proposal'][1])
        self.assertIn('--emit-intake', commands['dispatch-worker'])
        self.assertIn('prioritise-tasks.py', commands['vault-triage'][1])

    def test_get_producer_command_returns_copy(self):
        from jimbo_runtime_producers import get_producer_command

        cmd = get_producer_command('dispatch-proposal')
        cmd.append('--mutated')

        fresh_cmd = get_producer_command('dispatch-proposal')
        self.assertNotIn('--mutated', fresh_cmd)

    def test_get_producer_command_rejects_unknown_name(self):
        from jimbo_runtime_producers import get_producer_command

        with self.assertRaisesRegex(ValueError, 'Unknown producer'):
            get_producer_command('nope')


if __name__ == '__main__':
    unittest.main()
