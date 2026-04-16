"""Tests for the scoring gate module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scoring_gate import pre_filter, parse_llm_rejection, MIN_BODY_CHARS


# ── pre_filter ────────────────────────────────────────────────────────────────

class TestPreFilter:
    def test_title_only_rejected(self):
        result = pre_filter({"id": "n1", "title": "Fix the thing", "body": None})
        assert result["pass"] is False
        assert any("Title-only" in r for r in result["reasons"])

    def test_empty_body_rejected(self):
        result = pre_filter({"id": "n2", "title": "Fix the thing", "body": ""})
        assert result["pass"] is False

    def test_whitespace_body_rejected(self):
        result = pre_filter({"id": "n3", "title": "Fix", "body": "   \n  "})
        assert result["pass"] is False

    def test_short_body_rejected(self):
        result = pre_filter({"id": "n4", "title": "Fix", "body": "look into this"})
        assert result["pass"] is False
        assert any("too thin" in r for r in result["reasons"])

    def test_body_at_threshold_passes(self):
        body = "x" * MIN_BODY_CHARS
        result = pre_filter({"id": "n5", "title": "Task", "body": body})
        assert result["pass"] is True

    def test_body_below_threshold_rejected(self):
        body = "x" * (MIN_BODY_CHARS - 1)
        result = pre_filter({"id": "n6", "title": "Task", "body": body})
        assert result["pass"] is False

    def test_adequate_body_passes(self):
        body = "Migrate the user table from Postgres to the new schema, updating all foreign keys and running backfill for existing rows."
        result = pre_filter({"id": "n7", "title": "DB migration", "body": body})
        assert result["pass"] is True

    def test_rationale_is_human_readable(self):
        result = pre_filter({"id": "n8", "title": "Stuff", "body": None})
        assert isinstance(result["rationale"], str)
        assert len(result["rationale"]) > 20


# ── parse_llm_rejection ──────────────────────────────────────────────────────

class TestParseLlmRejection:
    def test_scoreable_true_returns_none(self):
        result = parse_llm_rejection({"id": 42, "scoreable": True, "priority": 2})
        assert result is None

    def test_missing_scoreable_returns_none(self):
        result = parse_llm_rejection({"id": 42, "priority": 2})
        assert result is None

    def test_scoreable_false_returns_rejection(self):
        result = parse_llm_rejection({
            "id": 42,
            "scoreable": False,
            "rejection_reasons": ["No body", "Ambiguous title"],
        })
        assert result is not None
        assert result["actionability"] == "needs-context"
        assert "No body" in result["rationale"]
        assert "Ambiguous title" in result["rationale"]

    def test_rejection_with_subtasks(self):
        result = parse_llm_rejection({
            "id": 42,
            "scoreable": False,
            "rejection_reasons": ["Vague scope"],
            "suggested_subtasks": ["Research: check which tables are affected"],
        })
        assert "Suggested research" in result["rationale"]
        assert "check which tables" in result["rationale"]

    def test_rejection_defaults_when_reasons_missing(self):
        result = parse_llm_rejection({"id": 42, "scoreable": False})
        assert result is not None
        assert "Insufficient context" in result["rationale"]

    def test_rationale_truncated_at_500(self):
        result = parse_llm_rejection({
            "id": 42,
            "scoreable": False,
            "rejection_reasons": ["x" * 600],
        })
        assert len(result["rationale"]) <= 500
