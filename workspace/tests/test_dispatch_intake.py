"""Tests for dispatch intake normalization."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestHydrateTask(unittest.TestCase):

    def test_hydrates_vault_task(self):
        from dispatch_intake import hydrate_task

        task = {
            "task_id": "note_1",
            "agent_type": "coder",
        }
        note = {
            "title": "Fix auth bug",
            "definition_of_done": "PR opened",
        }

        hydrated = hydrate_task(task, lambda task_id: note if task_id == "note_1" else None)
        self.assertEqual(hydrated["task_source"], "vault")
        self.assertEqual(hydrated["title"], "Fix auth bug")
        self.assertEqual(hydrated["definition_of_done"], "PR opened")
        self.assertEqual(hydrated["vault_task"], note)

    def test_skips_missing_vault_task(self):
        from dispatch_intake import hydrate_task

        hydrated = hydrate_task({"task_id": "note_missing"}, lambda _: None)
        self.assertIsNone(hydrated)

    def test_hydrates_github_task_without_vault_lookup(self):
        from dispatch_intake import hydrate_task

        calls = []

        def fetch(_):
            calls.append(True)
            return None

        hydrated = hydrate_task(
            {
                "task_id": "marvinbarretto/localshout-next#12",
                "task_source": "github",
                "title": "Fix flaky auth test",
                "definition_of_done": "PR with fix",
            },
            fetch,
        )
        self.assertEqual(hydrated["task_source"], "github")
        self.assertEqual(hydrated["title"], "Fix flaky auth test")
        self.assertEqual(hydrated["definition_of_done"], "PR with fix")
        self.assertEqual(calls, [])


class TestHydrateBatch(unittest.TestCase):

    def test_filters_missing_vault_items(self):
        from dispatch_intake import hydrate_batch

        note = {"title": "Fix auth bug", "definition_of_done": "PR opened"}
        hydrated = hydrate_batch(
            [
                {"task_id": "note_1"},
                {"task_id": "note_missing"},
                {"task_id": "repo#1", "task_source": "github"},
            ],
            lambda task_id: note if task_id == "note_1" else None,
        )
        self.assertEqual([item["task_id"] for item in hydrated], ["note_1", "repo#1"])


if __name__ == '__main__':
    unittest.main()
