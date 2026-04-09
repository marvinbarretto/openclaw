"""Helpers for dispatch queue transition tracking."""

import json
import os


def load_seen_state(path):
    """Load seen dispatch IDs from disk."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {
                key: list(dict.fromkeys(value))
                for key, value in data.items()
                if isinstance(value, list)
            }
    except Exception:
        pass
    return {}


def save_seen_state(path, state):
    """Persist seen dispatch IDs to disk."""
    with open(path, "w") as f:
        json.dump(state, f, sort_keys=True)


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
