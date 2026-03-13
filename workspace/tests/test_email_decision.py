"""Tests for email decision worker."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from workers.email_decision import build_decision_prompt, parse_decision


def test_build_decision_prompt_includes_context():
    """Prompt should include user context."""
    context = {"PRIORITIES.md": "1. Ship email decision worker"}
    report = {
        "gmail_id": "test-123",
        "subject": "Comedy Night",
        "from_email": "events@watford.com",
        "body_analysis": {
            "summary": "Comedy night at Watford Palace",
            "content_type": "event_listing",
            "entities": ["Watford Palace Theatre"],
            "events": [{"what": "Comedy Night", "when": "Friday 7:30pm"}],
            "deadlines": [],
            "key_asks": [],
        },
        "links": [],
    }

    prompt = build_decision_prompt(context, report)
    assert "Ship email decision worker" in prompt
    assert "Comedy Night" in prompt
    assert "Watford Palace" in prompt


def test_build_decision_prompt_includes_link_summaries():
    """Prompt should include link page_summary and entities from flat format."""
    context = {"PRIORITIES.md": "test priorities"}
    report = {
        "gmail_id": "test-123",
        "subject": "Test",
        "from_email": "test@test.com",
        "body_analysis": {"summary": "Test", "content_type": "newsletter", "entities": [], "events": [], "deadlines": [], "key_asks": []},
        "links": [
            {
                "url": "https://example.com/event",
                "page_title": "Event Page",
                "page_summary": "A great event",
                "entities": ["London"],
                "events": [{"what": "Concert", "when": "Friday"}],
                "extraction_confidence": "high",
                "screenshot_url": None,
            },
        ],
    }

    prompt = build_decision_prompt(context, report)
    assert "A great event" in prompt
    assert "London" in prompt


def test_build_decision_prompt_notes_low_confidence_screenshots():
    """For LOW/MEDIUM confidence links with screenshots, prompt should note to check the image."""
    context = {"PRIORITIES.md": "test"}
    report = {
        "gmail_id": "test-123",
        "subject": "Test",
        "from_email": "test@test.com",
        "body_analysis": {"summary": "Test", "content_type": "newsletter", "entities": [], "events": [], "deadlines": [], "key_asks": []},
        "links": [
            {
                "url": "https://example.com/flyer",
                "page_title": "Flyer",
                "page_summary": "",
                "entities": [],
                "events": [],
                "extraction_confidence": "low",
                "screenshot_url": "https://r2.example.com/screenshots/test/abc.png",
            },
        ],
    }

    prompt = build_decision_prompt(context, report)
    assert "screenshot" in prompt.lower() or "image" in prompt.lower()


def test_parse_decision_valid_json():
    """Should parse valid JSON decision response."""
    response = json.dumps({
        "relevance_score": 8,
        "category": "event",
        "suggested_action": "surface-in-briefing",
        "reason": "Matches local events",
        "insight": "Comedy night Friday",
        "connections": ["local events"],
        "time_sensitive": True,
        "deadline": "2026-03-13",
    })

    decision = parse_decision(response)
    assert decision["relevance_score"] == 8
    assert decision["category"] == "event"


def test_parse_decision_with_markdown_fences():
    """Should handle JSON wrapped in markdown code fences."""
    response = '```json\n{"relevance_score": 5, "category": "noise", "suggested_action": "ignore", "reason": "spam"}\n```'
    decision = parse_decision(response)
    assert decision["relevance_score"] == 5


def test_parse_decision_invalid_returns_none():
    """Should return None for unparseable responses."""
    assert parse_decision("this is not json") is None
    assert parse_decision("") is None
