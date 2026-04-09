"""API-backed runtime inbox and run ledger stored in the settings API."""

import datetime
import json
import os
import urllib.error
import urllib.request
import uuid


API_URL = os.environ.get("JIMBO_API_URL", "http://localhost:3100")
API_KEY = os.environ.get("JIMBO_API_KEY", os.environ.get("API_KEY", ""))

INBOX_SETTING_KEY = "jimbo_runtime_inbox"
RUNS_SETTING_KEY = "jimbo_runtime_runs"


def _now_iso():
    return datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")


def _request(method, path, body=None):
    url = f"{API_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-API-Key", API_KEY)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def fetch_setting_value(key):
    try:
        payload = _request("GET", f"/api/settings/{key}")
        return payload.get("value")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def store_setting_value(key, value):
    _request("PUT", f"/api/settings/{key}", {"value": value})
    return value


def _normalize_state(value, collection_key):
    if isinstance(value, dict):
        state = dict(value)
    elif isinstance(value, list):
        state = {collection_key: list(value)}
    else:
        state = {}
    state.setdefault(collection_key, [])
    state.setdefault("updated_at", None)
    return state


def load_inbox_state():
    return _normalize_state(fetch_setting_value(INBOX_SETTING_KEY), "items")


def save_inbox_state(state):
    payload = dict(state)
    payload["updated_at"] = _now_iso()
    return store_setting_value(INBOX_SETTING_KEY, payload)


def load_run_state():
    return _normalize_state(fetch_setting_value(RUNS_SETTING_KEY), "runs")


def save_run_state(state):
    payload = dict(state)
    payload["updated_at"] = _now_iso()
    return store_setting_value(RUNS_SETTING_KEY, payload)


def _new_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex}"


def _matches_route_filters(entry, *, route=None, workflow=None, capability=None):
    route_policy = dict(entry.get("route_policy") or {})
    if route is not None and route_policy.get("route") != route:
        return False
    if workflow is not None and route_policy.get("workflow") != workflow:
        return False
    if capability is not None and route_policy.get("capability") != capability:
        return False
    return True


def list_inbox_items(*, status=None, route=None, workflow=None, capability=None):
    items = list(load_inbox_state().get("items", []))
    filtered = []
    for item in items:
        if status is not None and item.get("status") != status:
            continue
        if not _matches_route_filters(item, route=route, workflow=workflow, capability=capability):
            continue
        filtered.append(item)
    return filtered


def list_runtime_runs(*, status=None, route=None, workflow=None, capability=None):
    runs = list(load_run_state().get("runs", []))
    filtered = []
    for run in runs:
        if status is not None and run.get("status") != status:
            continue
        if not _matches_route_filters(run, route=route, workflow=workflow, capability=capability):
            continue
        filtered.append(run)
    return filtered


def enqueue_runtime_requests(requests, *, source, producer=None):
    if not isinstance(requests, list):
        requests = [requests]
    state = load_inbox_state()
    created_at = _now_iso()
    new_items = []
    for request in requests:
        request_payload = dict(request)
        item = {
            "id": _new_id("runtime-inbox"),
            "request_id": request_payload.get("request_id"),
            "source": source,
            "producer": producer,
            "route_policy": request_payload.get("route_policy"),
            "status": "pending",
            "created_at": created_at,
            "claimed_at": None,
            "claimed_by": None,
            "completed_at": None,
            "run_id": None,
            "error": None,
            "request": request_payload,
        }
        state["items"].append(item)
        new_items.append(item)
    save_inbox_state(state)
    return new_items


def claim_next_inbox_item(*, claimant):
    state = load_inbox_state()
    claimed_at = _now_iso()
    for item in state.get("items", []):
        if item.get("status") == "pending":
            item["status"] = "claimed"
            item["claimed_at"] = claimed_at
            item["claimed_by"] = claimant
            save_inbox_state(state)
            return item
    return None


def complete_inbox_item(item_id, *, run_id, response):
    state = load_inbox_state()
    completed_at = _now_iso()
    for item in state.get("items", []):
        if item.get("id") == item_id:
            item["status"] = "completed"
            item["run_id"] = run_id
            item["completed_at"] = completed_at
            item["response"] = response
            item["error"] = None
            save_inbox_state(state)
            return item
    raise ValueError(f"Unknown inbox item: {item_id}")


def fail_inbox_item(item_id, *, run_id, error):
    state = load_inbox_state()
    completed_at = _now_iso()
    for item in state.get("items", []):
        if item.get("id") == item_id:
            item["status"] = "failed"
            item["run_id"] = run_id
            item["completed_at"] = completed_at
            item["error"] = error
            save_inbox_state(state)
            return item
    raise ValueError(f"Unknown inbox item: {item_id}")


def create_runtime_run(item, *, claimant):
    state = load_run_state()
    run = {
        "id": _new_id("runtime-run"),
        "request_id": item.get("request_id"),
        "inbox_item_id": item["id"],
        "status": "running",
        "claimant": claimant,
        "started_at": _now_iso(),
        "completed_at": None,
        "route_policy": item.get("route_policy"),
        "command": item.get("request", {}).get("command"),
        "request": item.get("request"),
        "response": None,
        "error": None,
    }
    state["runs"].append(run)
    save_run_state(state)
    return run


def complete_runtime_run(run_id, *, response):
    state = load_run_state()
    for run in state.get("runs", []):
        if run.get("id") == run_id:
            run["status"] = "completed"
            run["completed_at"] = _now_iso()
            run["response"] = response
            run["error"] = None
            save_run_state(state)
            return run
    raise ValueError(f"Unknown runtime run: {run_id}")


def fail_runtime_run(run_id, *, error):
    state = load_run_state()
    for run in state.get("runs", []):
        if run.get("id") == run_id:
            run["status"] = "failed"
            run["completed_at"] = _now_iso()
            run["error"] = error
            save_run_state(state)
            return run
    raise ValueError(f"Unknown runtime run: {run_id}")
