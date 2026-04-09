"""Tests for the Jimbo runtime intake payload contract."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestJimboRuntimeContract(unittest.TestCase):

    def test_normalize_requires_source_and_trigger(self):
        from jimbo_runtime_contract import InvalidIntakePayloadError, normalize_intake_payload

        with self.assertRaisesRegex(InvalidIntakePayloadError, "payload.source"):
            normalize_intake_payload({"task_id": "note_1", "trigger": "dispatch-propose"})

        with self.assertRaisesRegex(InvalidIntakePayloadError, "payload.trigger"):
            normalize_intake_payload({"task_id": "note_1", "source": "dispatch"})

    def test_normalize_requires_intake_or_task_id(self):
        from jimbo_runtime_contract import InvalidIntakePayloadError, normalize_intake_payload

        with self.assertRaisesRegex(InvalidIntakePayloadError, "intake_id or task_id"):
            normalize_intake_payload({"source": "dispatch", "trigger": "dispatch-propose"})

    def test_normalize_promotes_workflow_to_workflow_hint(self):
        from jimbo_runtime_contract import normalize_intake_payload

        normalized = normalize_intake_payload({
            "task_id": "note_1",
            "source": "dispatch",
            "trigger": "dispatch-propose",
            "workflow": "dispatch",
        })

        self.assertEqual(normalized["workflow_hint"], "dispatch")

    def test_live_payload_requires_route(self):
        from jimbo_runtime_contract import InvalidIntakePayloadError, normalize_intake_payload

        with self.assertRaisesRegex(InvalidIntakePayloadError, "payload.route"):
            normalize_intake_payload({
                "task_id": "note_1",
                "source": "dispatch",
                "trigger": "dispatch-propose",
            }, live=True)

    def test_example_payloads_are_valid(self):
        from jimbo_runtime_contract import intake_payload_example, normalize_intake_payload

        self.assertEqual(
            normalize_intake_payload(intake_payload_example())["source"],
            "dispatch",
        )
        self.assertEqual(
            normalize_intake_payload(intake_payload_example(live=True), live=True)["route"]["decision"],
            "proposed",
        )


if __name__ == '__main__':
    unittest.main()
