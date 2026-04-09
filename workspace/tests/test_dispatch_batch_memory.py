"""Tests for dispatch batch projection helpers."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestBatchProjection(unittest.TestCase):

    def test_build_batch_sets_default_status_for_proposals(self):
        from dispatch_batch_memory import build_batch, summarize_batch
        batch = build_batch('batch-1', [
            {'id': 1, 'task_id': 'note_1', 'title': 'Task one', 'agent_type': 'coder', 'flow': 'commission'},
            {'id': 2, 'task_id': 'note_2', 'title': 'Task two', 'agent_type': 'researcher', 'flow': 'recon'},
        ], default_status='proposed')
        self.assertEqual(batch['items']['1']['status'], 'proposed')
        self.assertEqual(batch['items']['2']['status'], 'proposed')
        self.assertEqual(summarize_batch(batch), '2 tasks: 2 proposed')

    def test_build_batches_maps_queue_statuses(self):
        from dispatch_batch_memory import batch_report_status, build_batches, summarize_batch
        batches = build_batches([
            {'id': 1, 'batch_id': 'batch-1', 'task_id': 'note_1', 'status': 'approved'},
            {'id': 2, 'batch_id': 'batch-1', 'task_id': 'note_2', 'status': 'running'},
            {'id': 3, 'batch_id': 'batch-1', 'task_id': 'note_3', 'status': 'rejected'},
        ])
        batch = batches['batch-1']
        self.assertEqual(summarize_batch(batch), '3 tasks: 1 approved, 1 picked_up, 1 rejected')
        self.assertEqual(batch_report_status(batch), 'mixed')

    def test_failed_timeout_is_projected_as_timeout(self):
        from dispatch_batch_memory import build_batches
        batches = build_batches([
            {
                'id': 1,
                'batch_id': 'batch-1',
                'task_id': 'note_1',
                'status': 'failed',
                'error_message': 'Timeout after 900s (limit for researcher)',
            },
        ])
        batch = batches['batch-1']
        self.assertEqual(batch['items']['1']['status'], 'timeout')

    def test_status_override_wins_over_queue_projection(self):
        from dispatch_batch_memory import build_batches
        batches = build_batches([
            {'id': 1, 'batch_id': 'batch-1', 'task_id': 'note_1', 'status': 'failed'},
        ], status_overrides={'1': 'timeout'})
        batch = batches['batch-1']
        self.assertEqual(batch['items']['1']['status'], 'timeout')


if __name__ == '__main__':
    unittest.main()
