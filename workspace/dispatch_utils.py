"""Shared helpers for dispatch proposer and worker."""

import json
import re


_BATCH_ID_PATTERN = re.compile(r"^batch-\d{8}-\d{6}$")


def parse_result(raw):
    """Parse agent result JSON with fallback for malformed output."""
    if not raw or not raw.strip():
        return {"status": "failed", "summary": "Empty result file"}

    text = raw.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    return {
        "status": "completed_unstructured",
        "summary": text[:500],
    }


def render_template(template_text, variables):
    """Render a prompt template with simple variable substitution."""
    result = template_text
    for key, value in variables.items():
        result = result.replace("{" + key + "}", str(value))
    return result


def is_valid_batch_id(value):
    """Validate the canonical batch ID format."""
    return bool(value and _BATCH_ID_PATTERN.fullmatch(value))
