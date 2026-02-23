"""Tests for scripts/review_helper.py — vault note frontmatter updates and file moves."""

import json
import os
import shutil
import tempfile

import pytest

# Will import from scripts.review_helper once implemented
from scripts.review_helper import update_and_move, add_context


SAMPLE_NOTE = """---
id: note_85ded1a8
source: google-tasks
source_id: UjMzcy1tdUJqeTVieVpuLQ
source_list: Today
type: reference
status: needs-context
tags: ["unclear"]
created: 2026-01-14
updated: 2026-01-14
processed: 2026-02-22
title: Dopesic
---

Dopesic
"""

SAMPLE_NOTE_WITH_BODY = """---
id: note_b3fdc760
source: google-tasks
source_id: Z253XzBONVZuQ0ZXa2Y4SA
source_list: Follow up / research
type: finance
status: needs-context
tags: ["crypto", "arbitrage", "research"]
created: 2026-01-16
updated: 2026-01-16
processed: 2026-02-22
title: "45 yen beer China 10:1 arbitrage opportunity"
---

45 yen beer china 10:1
"""


@pytest.fixture
def vault(tmp_path):
    """Create a temporary vault structure with needs-context, notes, and archive dirs."""
    needs_context = tmp_path / "needs-context"
    notes = tmp_path / "notes"
    archive = tmp_path / "archive"
    needs_context.mkdir()
    notes.mkdir()
    archive.mkdir()
    return tmp_path


def write_note(vault, filename, content=SAMPLE_NOTE):
    """Write a note file to needs-context/ and return its path."""
    path = vault / "needs-context" / filename
    path.write_text(content)
    return str(path)


# ---------------------------------------------------------------------------
# update_and_move: direct classification
# ---------------------------------------------------------------------------

class TestDirectClassification:
    def test_moves_file_to_notes(self, vault):
        filepath = write_note(vault, "dopesic--note_85ded1a.md")

        update_and_move(filepath, str(vault / "notes"), {
            "type": "media",
            "tags": ["tv", "drama"],
            "status": "active",
            "processed": "2026-02-23",
        })

        assert not os.path.exists(filepath)
        assert os.path.exists(str(vault / "notes" / "dopesic--note_85ded1a.md"))

    def test_updates_frontmatter_fields(self, vault):
        filepath = write_note(vault, "dopesic--note_85ded1a.md")

        update_and_move(filepath, str(vault / "notes"), {
            "type": "media",
            "tags": ["tv", "drama"],
            "status": "active",
            "processed": "2026-02-23",
        })

        dest = vault / "notes" / "dopesic--note_85ded1a.md"
        content = dest.read_text()
        assert "type: media" in content
        assert 'tags: ["tv", "drama"]' in content
        assert "status: active" in content
        assert "processed: 2026-02-23" in content

    def test_preserves_existing_fields(self, vault):
        filepath = write_note(vault, "dopesic--note_85ded1a.md")

        update_and_move(filepath, str(vault / "notes"), {
            "type": "media",
            "tags": ["tv", "drama"],
            "status": "active",
            "processed": "2026-02-23",
        })

        dest = vault / "notes" / "dopesic--note_85ded1a.md"
        content = dest.read_text()
        assert "id: note_85ded1a8" in content
        assert "source: google-tasks" in content
        assert "created: 2026-01-14" in content
        assert "title: Dopesic" in content

    def test_preserves_body(self, vault):
        filepath = write_note(vault, "dopesic--note_85ded1a.md")

        update_and_move(filepath, str(vault / "notes"), {
            "type": "media",
            "tags": ["tv", "drama"],
            "status": "active",
            "processed": "2026-02-23",
        })

        dest = vault / "notes" / "dopesic--note_85ded1a.md"
        content = dest.read_text()
        assert "Dopesic" in content.split("---", 2)[2]


# ---------------------------------------------------------------------------
# update_and_move: archive
# ---------------------------------------------------------------------------

class TestArchive:
    def test_moves_file_to_archive(self, vault):
        filepath = write_note(vault, "dopesic--note_85ded1a.md")

        update_and_move(filepath, str(vault / "archive"), {
            "status": "archived",
            "stale_reason": "stale",
            "processed": "2026-02-23",
        })

        assert not os.path.exists(filepath)
        assert os.path.exists(str(vault / "archive" / "dopesic--note_85ded1a.md"))

    def test_sets_archived_status_and_reason(self, vault):
        filepath = write_note(vault, "dopesic--note_85ded1a.md")

        update_and_move(filepath, str(vault / "archive"), {
            "status": "archived",
            "stale_reason": "stale",
            "processed": "2026-02-23",
        })

        dest = vault / "archive" / "dopesic--note_85ded1a.md"
        content = dest.read_text()
        assert "status: archived" in content
        assert "stale_reason: stale" in content


# ---------------------------------------------------------------------------
# add_context
# ---------------------------------------------------------------------------

class TestAddContext:
    def test_prepends_context_to_body(self, vault):
        filepath = write_note(vault, "beer--note_b3fdc76.md", SAMPLE_NOTE_WITH_BODY)

        add_context(filepath, "This is about cheap beer prices in China, travel note")

        content = open(filepath).read()
        # Context should appear before the original body
        body = content.split("---", 2)[2]
        lines = body.strip().split("\n")
        assert lines[0] == "This is about cheap beer prices in China, travel note"

    def test_adds_review_context_to_frontmatter(self, vault):
        filepath = write_note(vault, "beer--note_b3fdc76.md", SAMPLE_NOTE_WITH_BODY)

        add_context(filepath, "This is about cheap beer prices in China, travel note")

        content = open(filepath).read()
        assert "review_context:" in content
        assert "cheap beer prices in China" in content

    def test_preserves_original_body(self, vault):
        filepath = write_note(vault, "beer--note_b3fdc76.md", SAMPLE_NOTE_WITH_BODY)

        add_context(filepath, "Travel price note")

        content = open(filepath).read()
        assert "45 yen beer china 10:1" in content

    def test_file_stays_in_place(self, vault):
        filepath = write_note(vault, "beer--note_b3fdc76.md", SAMPLE_NOTE_WITH_BODY)

        add_context(filepath, "Travel price note")

        assert os.path.exists(filepath)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_quoted_title_preserved(self, vault):
        filepath = write_note(vault, "beer--note_b3fdc76.md", SAMPLE_NOTE_WITH_BODY)

        update_and_move(filepath, str(vault / "notes"), {
            "type": "travel",
            "tags": ["china", "beer", "prices"],
            "status": "active",
            "processed": "2026-02-23",
        })

        dest = vault / "notes" / "beer--note_b3fdc76.md"
        content = dest.read_text()
        # Title with special chars should still be quoted
        assert "title:" in content

    def test_creates_dest_dir_if_missing(self, vault):
        filepath = write_note(vault, "dopesic--note_85ded1a.md")
        # Remove notes dir
        shutil.rmtree(str(vault / "notes"))

        update_and_move(filepath, str(vault / "notes"), {
            "type": "media",
            "tags": ["tv"],
            "status": "active",
            "processed": "2026-02-23",
        })

        assert os.path.exists(str(vault / "notes" / "dopesic--note_85ded1a.md"))
