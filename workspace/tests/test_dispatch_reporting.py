"""Tests for dispatch operator summaries."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestBatchSummary(unittest.TestCase):

    def test_build_batch_summary(self):
        from dispatch_reporting import build_batch_summary
        summary = build_batch_summary(
            "batch-20260409-120000",
            [
                {"task_id": "note_1", "flow": "commission", "agent_type": "coder"},
                {"task_id": "note_2", "flow": "recon", "agent_type": "researcher"},
            ],
            titles={"note_1": "Fix auth bug", "note_2": "Compare VPS options"},
            approve_url="https://example.com/a",
            reject_url="https://example.com/r",
        )
        self.assertIn("Batch batch-20260409-120000 -- 2 tasks ready", summary)
        self.assertIn("[commission] coder -- Fix auth bug", summary)
        self.assertIn("[recon] researcher -- Compare VPS options", summary)
        self.assertIn("Approve all", summary)
        self.assertIn("Reject", summary)


class TestResultSummary(unittest.TestCase):

    def test_build_result_summary_includes_status_and_reason(self):
        from dispatch_reporting import build_result_summary
        summary = build_result_summary(
            {"task_id": "note_1", "flow": "commission", "agent_type": "coder"},
            title="Fix auth bug",
            report_status="rejected",
            summary="Returned prose only",
            review_reason="Agent returned unstructured output instead of the JSON result contract",
            elapsed_seconds=42,
        )
        self.assertIn("[Dispatch] REJECTED", summary)
        self.assertIn("[commission] coder -- Fix auth bug", summary)
        self.assertIn("42s", summary)
        self.assertIn("Returned prose only", summary)
        self.assertIn("reason:", summary)


if __name__ == '__main__':
    unittest.main()
