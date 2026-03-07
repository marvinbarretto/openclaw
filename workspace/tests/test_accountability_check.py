import datetime
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import unittest

# Load accountability-check.py (hyphenated filename)
_module_path = os.path.join(os.path.dirname(__file__), "..", "accountability-check.py")
_spec = importlib.util.spec_from_file_location("accountability_check", _module_path)
accountability_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(accountability_check)

check_briefing_ran = accountability_check.check_briefing_ran
check_gems_produced = accountability_check.check_gems_produced
check_activity_count = accountability_check.check_activity_count
check_vault_tasks_surfaced = accountability_check.check_vault_tasks_surfaced


def today_str():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def create_tracker_db(path):
    """Create experiment-tracker DB with schema and return connection."""
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            parent_run_id TEXT,
            timestamp TEXT NOT NULL,
            model TEXT NOT NULL,
            config_hash TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cost_usd REAL,
            duration_ms INTEGER,
            input_summary TEXT,
            output_summary TEXT,
            quality_scores TEXT,
            conductor_rating INTEGER,
            user_rating INTEGER,
            user_notes TEXT,
            conductor_reasoning TEXT,
            config_snapshot TEXT,
            session TEXT
        );
    """)
    return db


def create_activity_db(path):
    """Create activity-log DB with schema and return connection."""
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS activities (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            task_type TEXT NOT NULL,
            description TEXT NOT NULL,
            outcome TEXT,
            rationale TEXT,
            model_used TEXT,
            cost_id TEXT,
            satisfaction INTEGER,
            notes TEXT
        );
    """)
    return db


class TestCheckBriefingRan(unittest.TestCase):
    """Verify check_briefing_ran looks for the task_ids the pipeline actually uses."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.tracker_path = os.path.join(self.tmpdir, "tracker.db")

    def _insert_run(self, task_id, session=None, conductor_rating=None):
        db = create_tracker_db(self.tracker_path)
        db.execute(
            """INSERT INTO runs (run_id, task_id, timestamp, model, session, conductor_rating)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (f"run_{task_id}", task_id, f"{today_str()}T08:00:00+00:00",
             "pipeline", session, conductor_rating),
        )
        db.commit()
        db.close()

    def test_finds_briefing_prep_runs(self):
        """briefing-prep.py logs as 'briefing-prep' — accountability must find it."""
        self._insert_run("briefing-prep", session="morning")
        orig = accountability_check.TRACKER_DB
        accountability_check.TRACKER_DB = self.tracker_path
        try:
            ok, summary = check_briefing_ran()
            self.assertTrue(ok, f"Should find briefing-prep run, got: {summary}")
            self.assertIn("morning", summary.lower())
        finally:
            accountability_check.TRACKER_DB = orig

    def test_finds_both_sessions(self):
        """Both morning and afternoon briefing-prep runs should be detected."""
        self._insert_run("briefing-prep", session="morning")
        # Insert afternoon run
        db = create_tracker_db(self.tracker_path)
        db.execute(
            """INSERT INTO runs (run_id, task_id, timestamp, model, session)
               VALUES (?, ?, ?, ?, ?)""",
            ("run_afternoon", "briefing-prep", f"{today_str()}T15:00:00+00:00",
             "pipeline", "afternoon"),
        )
        db.commit()
        db.close()

        orig = accountability_check.TRACKER_DB
        accountability_check.TRACKER_DB = self.tracker_path
        try:
            ok, summary = check_briefing_ran()
            self.assertTrue(ok)
            self.assertIn("morning", summary.lower())
            self.assertIn("afternoon", summary.lower())
        finally:
            accountability_check.TRACKER_DB = orig

    def test_empty_db_reports_not_run(self):
        """No runs at all should report failure."""
        create_tracker_db(self.tracker_path).close()
        orig = accountability_check.TRACKER_DB
        accountability_check.TRACKER_DB = self.tracker_path
        try:
            ok, summary = check_briefing_ran()
            self.assertFalse(ok)
        finally:
            accountability_check.TRACKER_DB = orig


class TestCheckGemsProduced(unittest.TestCase):
    """Verify check_gems_produced looks for the right task_id."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.tracker_path = os.path.join(self.tmpdir, "tracker.db")

    def test_finds_newsletter_deep_read_runs(self):
        db = create_tracker_db(self.tracker_path)
        db.execute(
            """INSERT INTO runs (run_id, task_id, timestamp, model)
               VALUES (?, ?, ?, ?)""",
            ("run_gems", "newsletter-deep-read", f"{today_str()}T08:30:00+00:00",
             "claude-haiku-4.5"),
        )
        db.commit()
        db.close()

        orig = accountability_check.TRACKER_DB
        accountability_check.TRACKER_DB = self.tracker_path
        try:
            ok, summary = check_gems_produced()
            self.assertTrue(ok)
            self.assertIn("gems produced", summary)
        finally:
            accountability_check.TRACKER_DB = orig


class TestCheckActivityCount(unittest.TestCase):
    """Verify activity checks work with pipeline-logged entries."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.activity_path = os.path.join(self.tmpdir, "activity.db")

    def test_finds_pipeline_logged_briefing(self):
        """briefing-prep.py should log to activity-log — check must find it."""
        db = create_activity_db(self.activity_path)
        db.execute(
            """INSERT INTO activities (id, timestamp, task_type, description)
               VALUES (?, ?, ?, ?)""",
            ("act_test", f"{today_str()}T08:00:00+00:00", "briefing",
             "Morning briefing pipeline: 45 emails, 8 shortlisted, 3 gems"),
        )
        db.commit()
        db.close()

        orig = accountability_check.ACTIVITY_DB
        accountability_check.ACTIVITY_DB = self.activity_path
        try:
            ok, summary = check_activity_count()
            self.assertTrue(ok)
            self.assertIn("1 activities", summary)
        finally:
            accountability_check.ACTIVITY_DB = orig


class TestCheckVaultTasksSurfaced(unittest.TestCase):
    """Verify vault task check works with pipeline-logged entries."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.activity_path = os.path.join(self.tmpdir, "activity.db")

    def test_finds_vault_in_pipeline_briefing(self):
        db = create_activity_db(self.activity_path)
        db.execute(
            """INSERT INTO activities (id, timestamp, task_type, description)
               VALUES (?, ?, ?, ?)""",
            ("act_test", f"{today_str()}T08:00:00+00:00", "briefing",
             "Morning briefing: 3 gems, 5 vault tasks surfaced"),
        )
        db.commit()
        db.close()

        orig = accountability_check.ACTIVITY_DB
        accountability_check.ACTIVITY_DB = self.activity_path
        try:
            ok, summary = check_vault_tasks_surfaced()
            self.assertTrue(ok)
        finally:
            accountability_check.ACTIVITY_DB = orig


if __name__ == "__main__":
    unittest.main()
