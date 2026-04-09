"""Submission and drain helpers for the API-backed Jimbo runtime inbox."""

import datetime
import json

from jimbo_runtime_ops import load_producer_payloads
from jimbo_runtime_queue import (
    claim_next_inbox_item,
    complete_inbox_item,
    complete_runtime_run,
    create_runtime_run,
    enqueue_runtime_requests,
    fail_inbox_item,
    fail_runtime_run,
)
from jimbo_runtime_request_service import execute_runtime_request
from jimbo_runtime_routing import build_route_policy, build_route_response


def _now_stamp():
    return datetime.datetime.now(datetime.UTC).strftime("%Y%m%d%H%M%S")


def build_inbox_requests_from_payloads(payloads, *, producer, live=True):
    """Wrap normalized intake payloads as runtime requests for the inbox."""
    if not isinstance(payloads, list):
        payloads = [payloads]

    requests = []
    batch_stamp = _now_stamp()
    for index, payload in enumerate(payloads, start=1):
        intake_id = payload.get("intake_id") or payload.get("task_id") or f"item-{index}"
        requests.append({
            "request_id": f"{producer}-{intake_id}-{batch_stamp}-{index}",
            "command": "resolve",
            "intake_json": json.dumps(payload, sort_keys=True),
            "live": bool(live),
            "route_policy": build_route_policy(payload, producer=producer),
        })
    return requests


def enqueue_payloads(payloads, *, producer, source=None, live=True):
    """Submit one payload or payload batch into the runtime inbox."""
    requests = build_inbox_requests_from_payloads(payloads, producer=producer, live=live)
    items = enqueue_runtime_requests(
        requests,
        source=source or producer,
        producer=producer,
    )
    return {
        "producer": producer,
        "source": source or producer,
        "live": bool(live),
        "count": len(items),
        "items": items,
    }


def enqueue_producer_requests(producer, *, live=True):
    """Load one producer's payloads and submit them to the runtime inbox."""
    return enqueue_payloads(
        load_producer_payloads(producer),
        producer=producer,
        source=f"producer:{producer}",
        live=live,
    )


def process_next_inbox_item(*, claimant):
    """Claim, execute, and persist the next pending runtime inbox item."""
    item = claim_next_inbox_item(claimant=claimant)
    if not item:
        return {"status": "idle"}

    run = create_runtime_run(item, claimant=claimant)
    try:
        route_policy = dict(item.get("route_policy") or {})
        if route_policy.get("execution") == "record":
            response = build_route_response(item)
        else:
            response = execute_runtime_request(item["request"])
        complete_runtime_run(run["id"], response=response)
        complete_inbox_item(item["id"], run_id=run["id"], response=response)
        return {
            "status": "completed",
            "item_id": item["id"],
            "request_id": item.get("request_id"),
            "run_id": run["id"],
            "route": route_policy.get("route"),
            "response": response,
        }
    except Exception as exc:
        error = str(exc)
        fail_runtime_run(run["id"], error=error)
        fail_inbox_item(item["id"], run_id=run["id"], error=error)
        return {
            "status": "failed",
            "item_id": item["id"],
            "request_id": item.get("request_id"),
            "run_id": run["id"],
            "error": error,
        }


def drain_runtime_inbox(*, claimant, limit=None):
    """Process pending runtime inbox items until idle or limit is reached."""
    processed = []
    completed = 0
    failed = 0

    while limit is None or len(processed) < limit:
        outcome = process_next_inbox_item(claimant=claimant)
        if outcome["status"] == "idle":
            break
        processed.append(outcome)
        if outcome["status"] == "completed":
            completed += 1
        elif outcome["status"] == "failed":
            failed += 1

    return {
        "status": "idle" if not processed else "processed",
        "processed": len(processed),
        "completed": completed,
        "failed": failed,
        "results": processed,
        "claimant": claimant,
        "limit": limit,
    }
