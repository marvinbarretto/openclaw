"""Tests for dispatch batch memory."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestBatchState(unittest.TestCase):

    def test_initialize_batch_sets_all_items_proposed(self):
        from dispatch_batch_memory import initialize_batch, summarize_batch
        state = initialize_batch({}, 'batch-1', [
            {'id': 1, 'task_id': 'note_1', 'title': 'Task one', 'agent_type': 'coder', 'flow': 'commission'},
            {'id': 2, 'task_id': 'note_2', 'title': 'Task two', 'agent_type': 'researcher', 'flow': 'recon'},
        ])
        batch = state['batch-1']
        self.assertEqual(batch['items']['1']['status'], 'proposed')
        self.assertEqual(batch['items']['2']['status'], 'proposed')
        self.assertEqual(summarize_batch(batch), '2 tasks: 2 proposed')

    def test_record_item_status_updates_batch_summary(self):
        from dispatch_batch_memory import (
            batch_report_status, initialize_batch, record_item_status, summarize_batch,
        )
        state = initialize_batch({}, 'batch-1', [
            {'id': 1, 'task_id': 'note_1', 'title': 'Task one', 'agent_type': 'coder', 'flow': 'commission'},
            {'id': 2, 'task_id': 'note_2', 'title': 'Task two', 'agent_type': 'researcher', 'flow': 'recon'},
        ])
        state = record_item_status(state, 'batch-1', {'id': 1, 'task_id': 'note_1', 'title': 'Task one'}, 'approved')
        state = record_item_status(state, 'batch-1', {'id': 2, 'task_id': 'note_2', 'title': 'Task two'}, 'rejected')
        batch = state['batch-1']
        self.assertEqual(summarize_batch(batch), '2 tasks: 1 approved, 1 rejected')
        self.assertEqual(batch_report_status(batch), 'mixed')

    def test_record_queue_item_maps_running_to_picked_up(self):
        from dispatch_batch_memory import initialize_batch, record_queue_item, summarize_batch
        state = initialize_batch({}, 'batch-1', [
            {'id': 1, 'task_id': 'note_1', 'title': 'Task one', 'agent_type': 'coder', 'flow': 'commission'},
        ])
        state = record_queue_item(state, {
            'id': 1,
            'batch_id': 'batch-1',
            'task_id': 'note_1',
            'title': 'Task one',
            'agent_type': 'coder',
            'flow': 'commission',
            'status': 'running',
        })
        batch = state['batch-1']
        self.assertEqual(batch['items']['1']['status'], 'picked_up')
        self.assertEqual(summarize_batch(batch), '1 tasks: 1 picked_up')

    def test_record_queue_item_ignores_unknown_status(self):
        from dispatch_batch_memory import initialize_batch, record_queue_item
        state = initialize_batch({}, 'batch-1', [
            {'id': 1, 'task_id': 'note_1', 'title': 'Task one', 'agent_type': 'coder', 'flow': 'commission'},
        ])
        updated = record_queue_item(state, {
            'id': 1,
            'batch_id': 'batch-1',
            'task_id': 'note_1',
            'status': 'mystery',
        })
        self.assertEqual(updated, state)

    def test_load_and_save_batch_state(self):
        from dispatch_batch_memory import load_batch_state, save_batch_state
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'batch-state.json')
            save_batch_state(path, {'batch-1': {'items': {'1': {'status': 'proposed'}}}})
            loaded = load_batch_state(path)
            self.assertEqual(loaded['batch-1']['items']['1']['status'], 'proposed')


if __name__ == '__main__':
    unittest.main()
