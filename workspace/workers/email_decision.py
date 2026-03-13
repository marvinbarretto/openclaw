#!/usr/bin/env python3
"""
Email decision worker.

Takes structured email reports (from Ralph's email deep reader) and scores
them for relevance against the user's priorities, interests, and goals.
Uses an LLM to produce a briefing-ready insight per email.

Runs standalone via cron. Fetches undecided reports from jimbo-api,
scores each one, and PATCHes the decision back.

Usage:
    python3 workers/email_decision.py
"""

import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from workers.base_worker import BaseWorker, call_model

_workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_cost_tracker = os.path.join(_workspace_dir, "cost-tracker.py")

VISION_MODELS = {
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-pro",
    "gemini-2.0-pro",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
}

SYSTEM_PROMPT = """You are an email relevance scorer. You receive a structured email report
(extracted by a local agent) and the user's current priorities, interests,
and goals. Your job is to judge relevance and synthesize a briefing-ready
insight. Return JSON only.

Response schema:
{
  "relevance_score": <1-10 integer>,
  "category": "<event|deadline|action-needed|informational|personal|financial|noise>",
  "suggested_action": "<surface-in-briefing|note-for-later|ignore>",
  "reason": "<one sentence explaining why>",
  "insight": "<briefing-ready paragraph synthesizing the email and links>",
  "connections": ["<matched interest or priority>", ...],
  "time_sensitive": <true|false>,
  "deadline": "<YYYY-MM-DD or null>"
}"""


def build_decision_prompt(context, report):
    """Build the user prompt for the decision model.

    Args:
        context: dict of {filename: content} from context files.
        report: structured email report from jimbo-api.

    Returns:
        Prompt string.
    """
    # User context section
    context_block = ""
    for filename, content in context.items():
        context_block += f"\n## {filename}\n{content}\n"

    # Email body analysis
    body = report.get("body_analysis", {})
    entities = body.get("entities", [])
    events = body.get("events", [])
    deadlines = body.get("deadlines", [])
    key_asks = body.get("key_asks", [])

    email_block = (
        f"Subject: {report.get('subject', '')}\n"
        f"From: {report.get('from_email', '')}\n"
        f"Content type: {body.get('content_type', 'unknown')}\n"
        f"Summary: {body.get('summary', '')}\n"
    )
    if entities:
        email_block += f"Entities: {', '.join(str(e) for e in entities)}\n"
    if events:
        for ev in events:
            email_block += f"Event: {ev.get('what', '')} — {ev.get('when', '')}\n"
    if deadlines:
        for dl in deadlines:
            email_block += f"Deadline: {dl}\n"
    if key_asks:
        for ask in key_asks:
            email_block += f"Key ask: {ask}\n"

    # Links section
    links_block = ""
    links = report.get("links", [])
    if links:
        for link in links:
            links_block += f"\n### {link.get('page_title', 'Link')}\n"
            links_block += f"URL: {link.get('url', '')}\n"
            page_summary = link.get("page_summary", "")
            if page_summary:
                links_block += f"Summary: {page_summary}\n"
            link_entities = link.get("entities", [])
            if link_entities:
                links_block += f"Entities: {', '.join(str(e) for e in link_entities)}\n"
            link_events = link.get("events", [])
            if link_events:
                for ev in link_events:
                    links_block += f"Event: {ev.get('what', '')} — {ev.get('when', '')}\n"

            # Note screenshots for low/medium confidence
            confidence = (link.get("extraction_confidence") or "").lower()
            screenshot_url = link.get("screenshot_url")
            if confidence in ("low", "medium") and screenshot_url:
                links_block += "[Screenshot attached — check the image for details the text extraction may have missed]\n"

    prompt = f"""# User Context
{context_block}

# Email Report
{email_block}"""

    if links_block:
        prompt += f"\n# Links\n{links_block}"

    prompt += "\n\nScore this email's relevance and return the JSON decision."
    return prompt


def get_images_for_report(report, model):
    """Fetch screenshot images for low/medium confidence links if model supports vision.

    Args:
        report: structured email report.
        model: model name string.

    Returns:
        List of image dicts or None.
    """
    # Strip openrouter/ prefix for vision check
    check_model = model.removeprefix("openrouter/")
    if check_model not in VISION_MODELS:
        return None

    images = []
    for link in report.get("links", []):
        confidence = (link.get("extraction_confidence") or "").lower()
        screenshot_url = link.get("screenshot_url")
        if confidence in ("low", "medium") and screenshot_url:
            try:
                req = urllib.request.Request(screenshot_url)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    image_bytes = resp.read()
                b64 = base64.b64encode(image_bytes).decode()
                images.append({"data": b64, "mime_type": "image/png"})
            except Exception as e:
                sys.stderr.write(f"[email-decision] failed to fetch screenshot {screenshot_url}: {e}\n")

    return images if images else None


def parse_decision(response_text):
    """Parse the LLM decision response.

    Handles raw JSON and markdown-fenced JSON. Returns dict or None.
    """
    if not response_text:
        return None

    text = response_text.strip()

    # Strip markdown code fences
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()

    try:
        decision = json.loads(text)
        if "relevance_score" not in decision:
            return None
        return decision
    except (json.JSONDecodeError, TypeError):
        return None


class EmailDecisionWorker(BaseWorker):
    """Scores email reports for relevance and produces briefing-ready insights."""

    def __init__(self):
        super().__init__("email-decision")
        self.api_url = os.environ.get("JIMBO_API_URL", "http://localhost:3100")
        self.api_key = os.environ.get("JIMBO_API_KEY", "")

    def _api_get(self, path):
        """GET from jimbo-api."""
        url = f"{self.api_url}{path}"
        req = urllib.request.Request(url, headers={"X-API-Key": self.api_key})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())

    def _api_patch(self, path, body):
        """PATCH to jimbo-api."""
        url = f"{self.api_url}{path}"
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method="PATCH", headers={
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())

    def _log_cost(self, model, input_tokens, output_tokens):
        """Log cost via cost-tracker subprocess."""
        provider = "openrouter" if model.startswith("openrouter/") else "google"
        cmd = [
            sys.executable, _cost_tracker, "log",
            "--provider", provider,
            "--model", model,
            "--task", "email-decision",
            "--input-tokens", str(input_tokens),
            "--output-tokens", str(output_tokens),
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        except Exception as e:
            sys.stderr.write(f"[email-decision] cost logging failed: {e}\n")

    def run(self):
        """Score undecided email reports. Returns summary dict."""
        # 1. Fetch undecided reports
        try:
            reports = self._api_get("/emails/reports/undecided")
        except Exception as e:
            sys.stderr.write(f"[email-decision] failed to fetch undecided reports: {e}\n")
            return {"decided": 0, "errors": 1, "model": self.get_model()}

        if not reports:
            sys.stderr.write("[email-decision] no undecided reports\n")
            return {"decided": 0, "errors": 0, "model": self.get_model()}

        # 2. Load context
        context = self.get_context()

        decided = 0
        errors = 0
        total_input_tokens = 0
        total_output_tokens = 0
        model_used = self.get_model()

        # 3. Process each report
        for report in reports:
            gmail_id = report.get("gmail_id", "unknown")
            try:
                prompt = build_decision_prompt(context, report)
                images = get_images_for_report(report, model_used)

                result = self.call(prompt, system=SYSTEM_PROMPT, images=images)
                total_input_tokens += result["input_tokens"]
                total_output_tokens += result["output_tokens"]

                self._log_cost(model_used, result["input_tokens"], result["output_tokens"])

                decision = parse_decision(result["text"])
                if decision is None:
                    sys.stderr.write(f"[email-decision] {gmail_id}: failed to parse decision\n")
                    errors += 1
                    continue

                self._api_patch(f"/emails/reports/{gmail_id}/decide", decision)
                decided += 1
                sys.stderr.write(
                    f"[email-decision] {gmail_id}: "
                    f"score={decision.get('relevance_score')} "
                    f"action={decision.get('suggested_action')} "
                    f"category={decision.get('category')}\n"
                )

            except Exception as e:
                sys.stderr.write(f"[email-decision] {gmail_id}: error — {e}\n")
                errors += 1
                continue

        # 4. Log run for experiment tracker
        self.log_run(
            model=model_used,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            input_summary=f"{len(reports)} undecided reports",
            output_summary=f"{decided} decided, {errors} errors",
        )

        # 5. Summary
        sys.stderr.write(
            f"[email-decision] done: {decided} decided, {errors} errors, "
            f"model={model_used}, tokens={total_input_tokens}+{total_output_tokens}\n"
        )

        return {"decided": decided, "errors": errors, "model": model_used}


if __name__ == "__main__":
    worker = EmailDecisionWorker()
    result = worker.run()
    print(json.dumps(result))
