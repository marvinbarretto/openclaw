"""Helpers for dispatch queue transition tracking."""

import json


def normalize_seen_state(data):
    """Normalize arbitrary state into the expected dispatch-ID map."""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return {}
    if isinstance(data, dict):
        return {
            key: list(dict.fromkeys(value))
            for key, value in data.items()
            if isinstance(value, list)
        }
    return {}


def serialize_seen_state(state):
    """Serialize transition state for storage in the API settings store."""
    return json.dumps(normalize_seen_state(state), sort_keys=True)


def collect_new_items(seen_state, status, items, *, max_seen=200):
    """Return unseen items for a status and the updated state."""
    seen_ids = list(seen_state.get(status, []))
    seen_lookup = set(seen_ids)
    new_items = []

    for item in items:
        item_id = item.get("id")
        if item_id is None:
            continue
        if item_id in seen_lookup:
            continue
        new_items.append(item)
        seen_ids.append(item_id)
        seen_lookup.add(item_id)

    if len(seen_ids) > max_seen:
        seen_ids = seen_ids[-max_seen:]

    next_state = dict(seen_state)
    next_state[status] = seen_ids
    return new_items, next_state
