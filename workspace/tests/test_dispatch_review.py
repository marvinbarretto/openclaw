"""Tests for dispatch result review validation."""

import os
import subprocess
import sys
import tempfile
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
            {"flow": "commission", "task_id": "note_1"},
            {
                "status": "completed",
                "summary": "Done",
                "pr_url": "https://github.com/o/r/pull/1",
                "branch": "dispatch/note_1",
                "files_changed": ["src/app.ts"],
            },
        )
        self.assertTrue(review["accepted"])
        self.assertEqual(review["review_status"], "completed")

    def test_rejects_commission_without_expected_branch(self):
        from dispatch_review import validate_result
        review = validate_result(
            {"flow": "commission", "task_id": "note_1"},
            {
                "status": "completed",
                "summary": "Done",
                "pr_url": "https://github.com/o/r/pull/1",
                "branch": "feature/note_1",
                "files_changed": ["src/app.ts"],
            },
        )
        self.assertFalse(review["accepted"])
        self.assertIn("dispatch/note_1", review["reason"])

    def test_rejects_commission_without_changed_files(self):
        from dispatch_review import validate_result
        review = validate_result(
            {"flow": "commission", "task_id": "note_1"},
            {
                "status": "completed",
                "summary": "Done",
                "pr_url": "https://github.com/o/r/pull/1",
                "branch": "dispatch/note_1",
                "files_changed": [],
            },
        )
        self.assertFalse(review["accepted"])
        self.assertIn("files_changed", review["reason"])

    def test_requires_artifact_path_commit_sha_and_repo_for_recon(self):
        from dispatch_review import validate_result
        review = validate_result(
            {"flow": "recon"},
            {"status": "completed", "summary": "Researched"},
        )
        self.assertFalse(review["accepted"])
        self.assertIn("artifact_path", review["reason"])
        self.assertIn("commit_sha", review["reason"])
        self.assertIn("repo", review["reason"])

    def test_accepts_recon_with_existing_artifact_and_commit(self):
        from dispatch_review import validate_result
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "jimbo@example.com"], cwd=tmpdir, check=True)
            subprocess.run(["git", "config", "user.name", "Jimbo"], cwd=tmpdir, check=True)
            artifact_path = os.path.join(tmpdir, "notes", "output.md")
            os.makedirs(os.path.dirname(artifact_path), exist_ok=True)
            with open(artifact_path, "w") as f:
                f.write("# Findings\n")
            subprocess.run(["git", "add", "notes/output.md"], cwd=tmpdir, check=True)
            subprocess.run(["git", "commit", "-m", "docs: add output"], cwd=tmpdir, check=True, capture_output=True, text=True)
            commit_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=tmpdir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            review = validate_result(
                {"flow": "recon"},
                {
                    "status": "completed",
                    "summary": "Researched",
                    "artifact_path": "notes/output.md",
                    "repo": "owner/repo",
                    "commit_sha": commit_sha,
                },
                work_dir=tmpdir,
            )
        self.assertTrue(review["accepted"])
        self.assertEqual(review["review_status"], "completed")

    def test_rejects_recon_when_artifact_is_missing(self):
        from dispatch_review import validate_result
        review = validate_result(
            {"flow": "recon"},
            {
                "status": "completed",
                "summary": "Researched",
                "artifact_path": "notes/output.md",
                "repo": "owner/repo",
                "commit_sha": "abcdef1",
            },
            work_dir="/tmp/dispatch-review-missing",
        )
        self.assertFalse(review["accepted"])
        self.assertIn("does not exist", review["reason"])

    def test_accepts_blocked_with_summary(self):
        from dispatch_review import validate_result
        review = validate_result(
            {"flow": "commission"},
            {"status": "blocked", "summary": "Missing token", "blockers": ["missing token"]},
        )
        self.assertTrue(review["accepted"])
        self.assertEqual(review["review_status"], "blocked")

    def test_rejects_blocked_without_blockers(self):
        from dispatch_review import validate_result
        review = validate_result(
            {"flow": "commission"},
            {"status": "blocked", "summary": "Missing token"},
        )
        self.assertFalse(review["accepted"])
        self.assertIn("blockers", review["reason"])


if __name__ == '__main__':
    unittest.main()
