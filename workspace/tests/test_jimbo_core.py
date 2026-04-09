"""Tests for Jimbo's canonical orchestration helpers."""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestJimboCore(unittest.TestCase):

    def test_intake_includes_canonical_loop_metadata(self):
        from jimbo_core import JimboCore, JimboTask
        task = JimboTask(
            task_id='note_1',
            title='Fix auth bug',
            task_source='vault',
            workflow='dispatch',
        )
        logger = mock.Mock(return_value='act_123')
        activity_id = JimboCore(task, logger=logger).intake(
            reason='Task selected from ready queue',
            intake={'trigger': 'dispatch-propose'},
        )
        self.assertEqual(activity_id, 'act_123')
        args, kwargs = logger.call_args
        self.assertEqual(args[0], 'intake')
        self.assertEqual(args[1], 'note_1')
        self.assertEqual(kwargs['metadata']['workflow'], 'dispatch')
        self.assertEqual(kwargs['metadata']['intake']['trigger'], 'dispatch-propose')
        self.assertEqual(kwargs['metadata']['canonical_loop'][0], 'intake')

    def test_report_uses_task_defaults(self):
        from jimbo_core import JimboCore, JimboTask
        task = JimboTask(
            task_id='batch-1',
            title='2 tasks: 2 proposed',
            task_source='dispatch-batch',
            workflow='dispatch',
            model='claude-sonnet-4-6',
        )
        logger = mock.Mock(return_value='act_456')
        JimboCore(task, logger=logger).report(
            report={'status': 'proposed', 'summary': '2 tasks: 2 proposed'},
            reason='Batch state updated',
        )
        args, kwargs = logger.call_args
        self.assertEqual(args[0], 'report')
        self.assertEqual(kwargs['task_source'], 'dispatch-batch')
        self.assertEqual(kwargs['model'], 'claude-sonnet-4-6')
        self.assertEqual(kwargs['report']['status'], 'proposed')


if __name__ == '__main__':
    unittest.main()
