"""Lightweight persistent settings store for DiskImager.

Settings are stored as JSON in ~/.disktool/settings.json.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SETTINGS_DIR = Path.home() / ".disktool"
_SETTINGS_FILE = _SETTINGS_DIR / "settings.json"


def load() -> dict[str, Any]:
    """Load settings from disk.  Returns an empty dict on any error."""
    try:
        if _SETTINGS_FILE.exists():
            text = _SETTINGS_FILE.read_text(encoding="utf-8")
            return json.loads(text)
    except Exception as exc:
        logger.debug("Could not load settings: %s", exc)
    return {}


def save(data: dict[str, Any]) -> None:
    """Persist *data* to disk.  Silently ignores I/O errors."""
    try:
        _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        _SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.debug("Could not save settings: %s", exc)


def get(key: str, default: Any = None) -> Any:
    """Return the value for *key* from persisted settings."""
    return load().get(key, default)


def set_key(key: str, value: Any) -> None:
    """Update a single *key* in the persisted settings."""
    data = load()
    data[key] = value
    save(data)


def add_recent(list_key: str, value: str, max_items: int = 8) -> None:
    """Prepend *value* to a recents list, keeping at most *max_items* entries."""
    if not value or not value.strip():
        return
    data = load()
    lst: list[str] = data.get(list_key, [])
    value = value.strip()
    if value in lst:
        lst.remove(value)
    lst.insert(0, value)
    data[list_key] = lst[:max_items]
    save(data)


def get_recent(list_key: str) -> list[str]:
    """Return the recents list for *list_key*."""
    return load().get(list_key, [])
