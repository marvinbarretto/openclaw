"""Tests for dispatch result review validation."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestValidateResult(unittest.TestCase):

    def test_rejects_completed_unstructured(self):
        from dispatch_review import validate_result
        review = validate_result(
            {"flow": "commission"},
            {"status": "completed_unstructured", "summary": "Did the work"},
        )
        self.assertFalse(review["accepted"])
        self.assertEqual(review["review_status"], "rejected")

    def test_requires_pr_url_for_commission(self):
        from dispatch_review import validate_result
        review = validate_result(
            {"flow": "commission"},
            {"status": "completed", "summary": "Opened branch only"},
        )
        self.assertFalse(review["accepted"])
        self.assertIn("pr_url", review["reason"])

    def test_accepts_commission_with_pr_url(self):
        from dispatch_review import validate_result
        review = validate_result(
            {"flow": "commission"},
            {"status": "completed", "summary": "Done", "pr_url": "https://github.com/o/r/pull/1"},
        )
        self.assertTrue(review["accepted"])
        self.assertEqual(review["review_status"], "completed")

    def test_requires_artifact_path_and_commit_sha_for_recon(self):
        from dispatch_review import validate_result
        review = validate_result(
            {"flow": "recon"},
            {"status": "completed", "summary": "Researched"},
        )
        self.assertFalse(review["accepted"])
        self.assertIn("artifact_path", review["reason"])
        self.assertIn("commit_sha", review["reason"])

    def test_accepts_blocked_with_summary(self):
        from dispatch_review import validate_result
        review = validate_result(
            {"flow": "commission"},
            {"status": "blocked", "summary": "Missing token", "blockers": ["missing token"]},
        )
        self.assertTrue(review["accepted"])
        self.assertEqual(review["review_status"], "blocked")


if __name__ == '__main__':
    unittest.main()
