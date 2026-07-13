"""
A simple system-wide text clipboard with history.

This OS's on-screen Keyboard has no text-selection primitive (no
drag-to-select a range), so apps that want to share text offer a
whole-content "Copy"/"Paste" button instead of selection -- and all of
them go through here, rather than each app inventing its own private
clipboard, so text can move between Notes, Text Editor, Browser
bookmarks, and anywhere else that adds a Copy/Paste button later.
"""

import json
import os
import time

STORE_PATH = os.path.expanduser("~/.kos_clipboard.json")
MAX_HISTORY = 30

_items = []


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


_items[:] = _load()


def copy(text, source="Kos"):
    """Adds text to the clipboard (most-recent-first). Re-copying
    something already in history just moves it back to the front
    rather than creating a duplicate entry."""
    text = (text or "").strip()
    if not text:
        return
    _items[:] = [it for it in _items if it["text"] != text]
    _items.insert(0, {"text": text, "source": source, "time": time.time()})
    del _items[MAX_HISTORY:]
    _save()


def latest():
    return _items[0]["text"] if _items else ""


def history():
    return list(_items)


def remove(index):
    if 0 <= index < len(_items):
        _items.pop(index)
        _save()


def clear():
    _items.clear()
    _save()
