"""
A small, persisted notification system. Any app (or the OS itself)
posts notifications via notifications.post(...); the status bar shows
an unread-count badge, and swiping down from the status bar (or
tapping it) opens the Quick Settings / Notification panel to review or
dismiss them.

Kept deliberately simple for a hobby device -- no priority levels, no
actions, no channels, just title/body/source/timestamp -- because
that's what actually gets used here. Safe to call from any thread
(a background Wi-Fi scan, an incoming message on its own networking
thread, etc.) -- everything is guarded by a lock.
"""

import json
import os
import threading
import time

STORE_PATH = os.path.expanduser("~/.kos_notifications.json")
MAX_HISTORY = 100

_lock = threading.Lock()


def _load():
    try:
        with open(STORE_PATH) as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _save():
    try:
        with open(STORE_PATH, "w") as f:
            json.dump(_items, f)
    except Exception:
        pass


_items = _load()
_next_id = (max((n.get("id", 0) for n in _items), default=0)) + 1


def post(title, body="", source="Kos", icon=None):
    """Adds a notification (newest first) and returns its id."""
    global _next_id
    with _lock:
        n = {"id": _next_id, "title": title, "body": body, "source": source,
             "icon": icon, "time": time.time(), "read": False}
        _next_id += 1
        _items.insert(0, n)
        del _items[MAX_HISTORY:]
        _save()
        return n["id"]


def list_all():
    with _lock:
        return list(_items)


def unread_count():
    with _lock:
        return sum(1 for n in _items if not n["read"])


def mark_all_read():
    with _lock:
        for n in _items:
            n["read"] = True
        _save()


def mark_read(notif_id):
    with _lock:
        for n in _items:
            if n["id"] == notif_id:
                n["read"] = True
                break
        _save()


def dismiss(notif_id):
    with _lock:
        _items[:] = [n for n in _items if n["id"] != notif_id]
        _save()


def clear_all():
    with _lock:
        _items.clear()
        _save()
