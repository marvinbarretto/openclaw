"""Scoring gate — decides whether a vault note has enough signal to score.

This module owns all thresholds and logic for the pre-scoring filter.
When tuning scoring strictness, this is the file to change.
"""

# ── Thresholds ────────────────────────────────────────────────────────────────
# Minimum body length (chars, after strip) to pass the pre-filter.
# Notes below this threshold are rejected without an LLM call.
MIN_BODY_CHARS = 50

# ── Pre-scoring gate prompt (interpolated into SCORING_SYSTEM_PROMPT) ─────────
GATE_PROMPT_SECTION = """## Pre-scoring gate — MUST evaluate first

Before scoring any task, assess whether you have enough signal to understand it.
A task is **scoreable** only if you can confidently answer ALL of these:
1. What specifically does this task ask for? (not just a topic — the actual deliverable)
2. What would "done" look like? (you could write at least one acceptance criterion)
3. Is the scope bounded enough to estimate effort?

If ANY answer is "I can't tell from what's here", the task is NOT scoreable.
Return a rejection instead of a score (see response format below).

Common rejection triggers:
- Title-only note with no body
- Body is a single vague sentence with no concrete deliverable
- Topic is clear but the ask is not ("Sort out X" with no detail on what "sorted out" means)
- Cannot determine if this is one task or many without more context

When rejecting, explain specifically what is missing — not generic "needs more detail" but
"Cannot determine scope: is this a config change or a full migration? Body doesn't specify."
If the note would benefit from research to become scoreable, suggest 1-3 concrete subtasks
(e.g. "Research: identify which tables are affected by X")."""


def pre_filter(note):
    """Check whether a note has enough signal to send to the LLM for scoring.

    Args:
        note: dict from the vault API (must have 'body', 'title', 'id')

    Returns:
        dict with:
          - "pass": True if the note should go to the LLM
          - "pass": False, "reasons": [...], "rationale": "..." if rejected
    """
    body = (note.get("body") or "").strip()
    title = note.get("title") or "(untitled)"

    if len(body) < MIN_BODY_CHARS:
        reasons = []
        if not body:
            reasons.append(
                "Title-only note — no body to assess intent, scope, or deliverable."
            )
        else:
            reasons.append(
                f"Body is too thin ({len(body)} chars) to determine scope or next steps."
            )
        reasons.append(
            "Cannot write acceptance criteria without understanding what 'done' looks like."
        )
        return {
            "pass": False,
            "reasons": reasons,
            "rationale": " ".join(reasons),
        }

    return {"pass": True}


def parse_llm_rejection(score_result):
    """Parse an LLM response object and extract rejection data if present.

    Args:
        score_result: single dict from the LLM's JSON array response

    Returns:
        None if the note was scored (scoreable: true or field missing).
        dict with "rationale" and "actionability" if rejected.
    """
    if score_result.get("scoreable") is not False:
        return None

    rejection_reasons = score_result.get("rejection_reasons", ["Insufficient context to score"])
    suggested_subtasks = score_result.get("suggested_subtasks")

    parts = list(rejection_reasons)
    if suggested_subtasks:
        parts.append("Suggested research: " + "; ".join(suggested_subtasks))

    return {
        "rationale": " ".join(parts)[:500],
        "actionability": "needs-context",
    }
