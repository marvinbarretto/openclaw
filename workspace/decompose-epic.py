#!/usr/bin/env python3
"""
Epic Decomposition Worker

Picks up vault tasks with grooming_status='analysis_pending',
proposes sub-task breakdowns, writes proposals to jimbo-api.

Usage:
  python3 decompose-epic.py              # process all pending epics
  python3 decompose-epic.py --limit 5    # process up to 5
  python3 decompose-epic.py --dry-run    # preview without writing
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

try:
    from alert import send_telegram
except ImportError:
    send_telegram = None

API_URL = os.environ.get("JIMBO_API_URL", "")
API_KEY = os.environ.get("JIMBO_API_KEY", "")

DECOMPOSITION_PROMPT = """You are an experienced engineering manager breaking down an epic into actionable sub-tasks.

## Context

You have access to a team of agents with these capabilities:
- `coder` — implement code changes, fix bugs, refactor
- `researcher` — investigate topics, compare options, validate assumptions
- `extractor` — screenshot URLs, extract structured data from web pages
- `drafter` — write structured text output (summaries, docs, specs)

## Agent Roster

- **Boris** (Claude on m2 machine) — complex tasks, multi-skill, strong reasoning
- **Ralph** (Ollama on MacBook Air) — simple single-skill tasks, CSS/style, non-urgent
- **Marvin** (human) — judgment calls, approvals, product decisions

## Task to Decompose

**Title:** {title}
**Body:** {body}
**Tags:** {tags}
**Current Priority:** {priority}

## Instructions

Break this epic into 3-7 concrete sub-tasks. For each sub-task:

1. Write a clear, specific title (imperative verb)
2. List required_skills (from the skills above)
3. Write acceptance criteria that are specific, verifiable, and bounded
4. Suggest an executor (boris/ralph/marvin) based on complexity
5. Note any dependencies between sub-tasks (blocked_by)

Order sub-tasks so research/validation comes before implementation.
Each sub-task should be a single deliverable (one PR, one doc, one investigation).

## Response Format

Return ONLY valid JSON, no markdown fences:

{{
  "analysis": "Brief explanation of why this is an epic and the decomposition strategy",
  "sub_tasks": [
    {{
      "title": "Imperative verb + specific scope",
      "required_skills": ["researcher"],
      "acceptance_criteria": "Concrete, verifiable AC. Multiple sentences OK.",
      "suggested_executor": "boris",
      "blocked_by": null
    }},
    {{
      "title": "Second sub-task",
      "required_skills": ["coder"],
      "acceptance_criteria": "Specific AC here.",
      "suggested_executor": "boris",
      "blocked_by": "First sub-task title (if dependent)"
    }}
  ]
}}
"""


def api_request(method, path, body=None):
    """Make authenticated request to jimbo-api."""
    if not API_URL or not API_KEY:
        print("ERROR: JIMBO_API_URL and JIMBO_API_KEY must be set", file=sys.stderr)
        sys.exit(1)

    url = f"{API_URL}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"  API error {e.code}: {e.read().decode()}", file=sys.stderr)
        return None


def call_gemini(prompt, system=None, model="gemini-2.5-flash"):
    """Call Gemini API via urllib (stdlib only, no SDK)."""
    api_key = os.environ.get("GOOGLE_AI_API_KEY", "")
    if not api_key:
        print("ERROR: GOOGLE_AI_API_KEY must be set", file=sys.stderr)
        sys.exit(1)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    contents = [{"role": "user", "parts": [{"text": prompt}]}]
    body = {"contents": contents}
    if system:
        body["system_instruction"] = {"parts": [{"text": system}]}

    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode())

    text = result["candidates"][0]["content"]["parts"][0]["text"]
    return text


def fetch_pending_epics(limit=20):
    """Fetch tasks needing decomposition."""
    path = f"/api/vault/notes?grooming_status=analysis_pending&status=active&limit={limit}&sort=ai_priority&order=asc"
    result = api_request("GET", path)
    if not result:
        return []
    return result.get("items", result.get("notes", result if isinstance(result, list) else []))


def decompose_task(task):
    """Send task to LLM for decomposition, return structured proposal."""
    prompt = DECOMPOSITION_PROMPT.format(
        title=task.get("title", ""),
        body=task.get("body", "") or "",
        tags=task.get("tags", "") or "",
        priority=task.get("ai_priority", "unscored"),
    )

    raw = call_gemini(prompt)

    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    text = text.strip()

    return json.loads(text)


def create_proposal(task_id, proposal_data):
    """Write proposal to grooming_proposals API."""
    body = {
        "parent_note_id": task_id,
        "proposed_by": "jimbo",
        "proposal": json.dumps(proposal_data),
    }
    return api_request("POST", "/api/grooming/proposals", body)


def update_grooming_status(task_id, status):
    """Update vault note grooming_status."""
    return api_request("PATCH", f"/api/vault/notes/{task_id}", {"grooming_status": status})


def main():
    parser = argparse.ArgumentParser(description="Decompose epics into sub-tasks")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    epics = fetch_pending_epics(args.limit)
    if not epics:
        print("No epics pending decomposition.")
        return

    print(f"Found {len(epics)} epics to decompose.\n")

    succeeded = []
    failed = []

    for task in epics:
        title = task.get("title", "untitled")
        task_id = task["id"]
        seq = task.get("seq", "?")
        print(f"Decomposing: #{seq} {title} ({task_id})")

        try:
            proposal = decompose_task(task)
            sub_count = len(proposal.get("sub_tasks", []))
            print(f"  → {sub_count} sub-tasks proposed")
            print(f"  → Analysis: {proposal.get('analysis', '')[:100]}...")

            if args.dry_run:
                print(f"  [dry-run] Would create proposal with {sub_count} sub-tasks")
                print(json.dumps(proposal, indent=2))
                succeeded.append((seq, title, sub_count))
                continue

            result = create_proposal(task_id, proposal)
            if result:
                update_grooming_status(task_id, "decomposition_proposed")
                print(f"  ✓ Proposal created (id: {result.get('id')})")
                succeeded.append((seq, title, sub_count))
            else:
                print(f"  ✗ Failed to create proposal")
                failed.append((seq, title, "API write failed"))

        except json.JSONDecodeError as e:
            print(f"  ✗ LLM returned invalid JSON: {e}")
            failed.append((seq, title, f"invalid JSON: {e}"))
        except Exception as e:
            print(f"  ✗ Error: {e}")
            failed.append((seq, title, str(e)))

        print()

    # Summary report
    prefix = "[dry-run] " if args.dry_run else ""
    lines = [f"[Epic Decomposition] {prefix}{len(succeeded)}/{len(epics)} processed"]
    if succeeded:
        for seq, title, count in succeeded:
            lines.append(f"  ✓ #{seq} {title} → {count} sub-tasks")
    if failed:
        lines.append(f"  ✗ {len(failed)} failed:")
        for seq, title, reason in failed:
            lines.append(f"    #{seq} {title}: {reason}")

    summary = "\n".join(lines)
    print(f"\n{summary}")

    if not args.dry_run and send_telegram and (succeeded or failed):
        send_telegram(summary)

    print("Done.")


if __name__ == "__main__":
    main()
