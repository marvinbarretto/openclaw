import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "experiment-tracker.py")


class TestLogCommand(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "experiment-tracker.db")
        self.env = {**os.environ, "EXPERIMENT_TRACKER_DB": self.db_path}

    def test_log_creates_run_and_returns_json(self):
        result = subprocess.run(
            [
                sys.executable, SCRIPT, "log",
                "--task", "email-triage",
                "--model", "gemini-2.5-flash",
                "--input-tokens", "5000",
                "--output-tokens", "500",
                "--quality", '{"cited_articles": true}',
            ],
            capture_output=True, text=True, env=self.env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["status"], "ok")
        self.assertIn("run_id", data)
        self.assertIn("cost_usd", data)
        self.assertGreater(data["cost_usd"], 0)

    def test_log_writes_to_database(self):
        subprocess.run(
            [
                sys.executable, SCRIPT, "log",
                "--task", "newsletter-deep-read",
                "--model", "claude-haiku-4.5",
                "--input-tokens", "40000",
                "--output-tokens", "3000",
            ],
            capture_output=True, text=True, env=self.env,
        )
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM runs").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["task_id"], "newsletter-deep-read")
        self.assertEqual(row["model"], "claude-haiku-4.5")
        self.assertEqual(row["input_tokens"], 40000)
        db.close()


class TestCompareCommand(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "experiment-tracker.db")
        self.env = {**os.environ, "EXPERIMENT_TRACKER_DB": self.db_path}
        for model in ["gemini-2.5-flash", "claude-haiku-4.5"]:
            subprocess.run(
                [sys.executable, SCRIPT, "log",
                 "--task", "email-triage", "--model", model,
                 "--input-tokens", "5000", "--output-tokens", "500",
                 "--conductor-rating", "7"],
                capture_output=True, text=True, env=self.env,
            )

    def test_compare_returns_both_models(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "compare",
             "--task", "email-triage", "--days", "1"],
            capture_output=True, text=True, env=self.env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(len(data["models"]), 2)


class TestRateCommand(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "experiment-tracker.db")
        self.env = {**os.environ, "EXPERIMENT_TRACKER_DB": self.db_path}
        result = subprocess.run(
            [sys.executable, SCRIPT, "log",
             "--task", "email-triage", "--model", "gemini-2.5-flash",
             "--input-tokens", "5000", "--output-tokens", "500"],
            capture_output=True, text=True, env=self.env,
        )
        self.run_id = json.loads(result.stdout)["run_id"]

    def test_rate_updates_run(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "rate", self.run_id,
             "--user-rating", "8", "--notes", "good stuff"],
            capture_output=True, text=True, env=self.env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["user_rating"], 8)

        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT user_rating, user_notes FROM runs WHERE run_id = ?", (self.run_id,)).fetchone()
        self.assertEqual(row["user_rating"], 8)
        self.assertEqual(row["user_notes"], "good stuff")
        db.close()

    def test_rate_nonexistent_run_fails(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "rate", "run_nonexistent",
             "--user-rating", "5"],
            capture_output=True, text=True, env=self.env,
        )
        self.assertNotEqual(result.returncode, 0)


class TestStatsCommand(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "experiment-tracker.db")
        self.env = {**os.environ, "EXPERIMENT_TRACKER_DB": self.db_path}
        subprocess.run(
            [sys.executable, SCRIPT, "log",
             "--task", "email-triage", "--model", "gemini-2.5-flash",
             "--input-tokens", "5000", "--output-tokens", "500"],
            capture_output=True, text=True, env=self.env,
        )

    def test_stats_returns_summary(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "stats", "--days", "1"],
            capture_output=True, text=True, env=self.env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["totals"]["runs"], 1)
        self.assertGreater(data["totals"]["total_cost"], 0)


class TestExportCommand(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "experiment-tracker.db")
        self.env = {**os.environ, "EXPERIMENT_TRACKER_DB": self.db_path}
        subprocess.run(
            [sys.executable, SCRIPT, "log",
             "--task", "email-triage", "--model", "gemini-2.5-flash",
             "--input-tokens", "5000", "--output-tokens", "500"],
            capture_output=True, text=True, env=self.env,
        )

    def test_export_returns_runs_and_summary(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "export", "--days", "1"],
            capture_output=True, text=True, env=self.env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertIn("runs", data)
        self.assertIn("summary", data)
        self.assertEqual(len(data["runs"]), 1)


if __name__ == "__main__":
    unittest.main()
