"""Tests for dispatch queue transition tracking."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestCollectNewItems(unittest.TestCase):

    def test_collects_unseen_items(self):
        from dispatch_transitions import collect_new_items
        items = [{"id": 1}, {"id": 2}]
        new_items, state = collect_new_items({}, "approved", items)
        self.assertEqual(new_items, items)
        self.assertEqual(state["approved"], [1, 2])

    def test_skips_seen_items(self):
        from dispatch_transitions import collect_new_items
        items = [{"id": 1}, {"id": 2}, {"id": 3}]
        new_items, state = collect_new_items({"approved": [1, 2]}, "approved", items)
        self.assertEqual(new_items, [{"id": 3}])
        self.assertEqual(state["approved"], [1, 2, 3])

    def test_trims_seen_state(self):
        from dispatch_transitions import collect_new_items
        items = [{"id": 4}]
        new_items, state = collect_new_items({"approved": [1, 2, 3]}, "approved", items, max_seen=2)
        self.assertEqual(new_items, [{"id": 4}])
        self.assertEqual(state["approved"], [3, 4])


class TestSeenStateSerialization(unittest.TestCase):

    def test_normalize_seen_state_from_json(self):
        from dispatch_transitions import normalize_seen_state
        loaded = normalize_seen_state('{"approved":[1,2,2],"failed":[5]}')
        self.assertEqual(loaded, {"approved": [1, 2], "failed": [5]})

    def test_serialize_seen_state(self):
        from dispatch_transitions import serialize_seen_state
        payload = serialize_seen_state({"approved": [2, 1, 2]})
        self.assertEqual(payload, '{"approved": [2, 1]}')


if __name__ == '__main__':
    unittest.main()
