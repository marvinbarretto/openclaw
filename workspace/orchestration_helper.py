#!/usr/bin/env python3
"""
Helpers for API-backed orchestration decision logging.

The current jimbo-api activity endpoint stores flat activity records, so this
module serializes orchestration decisions into a concise human description plus
compact JSON metadata in the outcome field.
"""

import json
import os
import sys
import urllib.error
import urllib.request


API_URL = os.environ.get("JIMBO_API_URL", "http://localhost:3100")
API_KEY = os.environ.get("JIMBO_API_KEY", os.environ.get("API_KEY", ""))
TASK_TYPE = "orchestration"


def _request(method, path, body=None):
    url = f"{API_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-API-Key", API_KEY)
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _compact_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _build_description(stage, task_id, task_source, title,
                       classification=None, route=None, delegate=None,
                       review=None, report=None):
    parts = [f"{stage} {task_source}:{task_id}"]

    badges = []
    classification = classification or {}
    route = route or {}
    delegate = delegate or {}
    review = review or {}
    report = report or {}

    priority = classification.get("priority")
    if priority is not None:
        badges.append(f"P{priority}")
    if classification.get("actionability"):
        badges.append(classification["actionability"])
    if route.get("decision"):
        badges.append(f"route={route['decision']}")
    if delegate.get("agent_type"):
        badges.append(f"agent={delegate['agent_type']}")
    if review.get("status"):
        badges.append(f"review={review['status']}")
    if report.get("status"):
        badges.append(f"report={report['status']}")

    if badges:
        parts.append(f"[{', '.join(badges)}]")
    if title:
        parts.append(title[:80])

    return " ".join(parts)


def _build_rationale(reason, classification=None, route=None, delegate=None):
    if reason:
        return reason

    parts = []
    classification = classification or {}
    route = route or {}
    delegate = delegate or {}

    if classification.get("reason"):
        parts.append(classification["reason"])
    if route.get("reason"):
        parts.append(route["reason"])
    if delegate.get("reason"):
        parts.append(delegate["reason"])

    return " | ".join(parts) if parts else None


def log_decision(stage, task_id, *, title=None, task_source="vault",
                 model=None, reason=None, classification=None, route=None,
                 delegate=None, review=None, report=None, changed=None,
                 metadata=None):
    """Record an orchestration decision via the activity API.

    Returns the created activity record ID when successful, otherwise None.
    """
    classification = classification or None
    route = route or None
    delegate = delegate or None
    review = review or None
    report = report or None
    changed = changed or None
    metadata = metadata or None

    body = {
        "task_type": TASK_TYPE,
        "description": _build_description(
            stage, task_id, task_source, title,
            classification=classification,
            route=route,
            delegate=delegate,
            review=review,
            report=report,
        ),
        "outcome": _compact_json({
            "stage": stage,
            "task_id": task_id,
            "task_source": task_source,
            "classification": classification,
            "route": route,
            "delegate": delegate,
            "review": review,
            "report": report,
            "changed": changed,
            "metadata": metadata,
        }),
    }

    rationale = _build_rationale(
        reason,
        classification=classification,
        route=route,
        delegate=delegate,
    )
    if rationale:
        body["rationale"] = rationale
    if model:
        body["model_used"] = model

    try:
        result = _request("POST", "/api/activity", body)
        return result.get("id")
    except urllib.error.HTTPError as e:
        body_text = e.read().decode() if e.fp else str(e)
        sys.stderr.write(f"[orchestration] API {e.code}: {body_text[:200]}\n")
    except Exception as e:
        sys.stderr.write(f"[orchestration] log failed: {e}\n")
    return None
