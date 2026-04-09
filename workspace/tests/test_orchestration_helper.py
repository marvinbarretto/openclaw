"""Tests for orchestration activity logging helpers."""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestLogDecision(unittest.TestCase):

    def test_retries_after_transient_failure(self):
        import orchestration_helper
        with mock.patch.object(
            orchestration_helper,
            '_request',
            side_effect=[RuntimeError('temporary'), {'id': 'act_123'}],
        ) as request_mock:
            activity_id = orchestration_helper.log_decision(
                'report',
                'note_1',
                report={'status': 'approved'},
                retries=1,
                retry_delay_s=0,
            )
        self.assertEqual(activity_id, 'act_123')
        self.assertEqual(request_mock.call_count, 2)

    def test_returns_none_after_exhausting_retries(self):
        import orchestration_helper
        with mock.patch.object(
            orchestration_helper,
            '_request',
            side_effect=RuntimeError('still broken'),
        ) as request_mock:
            activity_id = orchestration_helper.log_decision(
                'report',
                'note_1',
                report={'status': 'approved'},
                retries=2,
                retry_delay_s=0,
            )
        self.assertIsNone(activity_id)
        self.assertEqual(request_mock.call_count, 3)


if __name__ == '__main__':
    unittest.main()
