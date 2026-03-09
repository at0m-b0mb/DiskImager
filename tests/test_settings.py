"""Tests for disktool.settings – persistent key/value store."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

import disktool.settings as settings_mod


@pytest.fixture(autouse=True)
def _patch_settings_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the settings file to a temp dir for each test."""
    fake_dir = tmp_path / ".disktool"
    fake_file = fake_dir / "settings.json"
    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", fake_dir)
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", fake_file)


class TestLoadSave:
    def test_load_empty(self) -> None:
        assert settings_mod.load() == {}

    def test_save_and_load(self) -> None:
        settings_mod.save({"key": "value", "num": 42})
        data = settings_mod.load()
        assert data["key"] == "value"
        assert data["num"] == 42

    def test_save_creates_dir(self, tmp_path: Path) -> None:
        settings_mod.save({"x": 1})
        assert settings_mod._SETTINGS_FILE.exists()


class TestGetSet:
    def test_get_missing_returns_default(self) -> None:
        assert settings_mod.get("nonexistent") is None
        assert settings_mod.get("nonexistent", "fallback") == "fallback"

    def test_set_key_and_get(self) -> None:
        settings_mod.set_key("theme", "light")
        assert settings_mod.get("theme") == "light"

    def test_set_key_updates_existing(self) -> None:
        settings_mod.save({"theme": "dark", "other": "keep"})
        settings_mod.set_key("theme", "light")
        data = settings_mod.load()
        assert data["theme"] == "light"
        assert data["other"] == "keep"


class TestRecent:
    def test_add_recent(self) -> None:
        settings_mod.add_recent("recent_src", "/dev/sda")
        assert settings_mod.get_recent("recent_src") == ["/dev/sda"]

    def test_add_recent_deduplicates(self) -> None:
        settings_mod.add_recent("recent_src", "/dev/sda")
        settings_mod.add_recent("recent_src", "/dev/sdb")
        settings_mod.add_recent("recent_src", "/dev/sda")  # move to front
        lst = settings_mod.get_recent("recent_src")
        assert lst[0] == "/dev/sda"
        assert lst.count("/dev/sda") == 1

    def test_add_recent_max_items(self) -> None:
        for i in range(12):
            settings_mod.add_recent("recent_src", f"/dev/sd{chr(ord('a') + i)}", max_items=8)
        assert len(settings_mod.get_recent("recent_src")) <= 8

    def test_add_recent_ignores_blank(self) -> None:
        settings_mod.add_recent("recent_src", "   ")
        assert settings_mod.get_recent("recent_src") == []

    def test_get_recent_empty(self) -> None:
        assert settings_mod.get_recent("nonexistent_list") == []
