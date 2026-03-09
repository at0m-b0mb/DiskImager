"""Tests for disktool.core.disk."""

from __future__ import annotations

from unittest.mock import patch

from disktool.core.disk import format_size, get_drives


class TestFormatSize:
    def test_bytes(self) -> None:
        assert "B" in format_size(512)

    def test_kilobytes(self) -> None:
        assert "KB" in format_size(2048)

    def test_gigabytes(self) -> None:
        assert "GB" in format_size(2 * 1024 ** 3)


class TestGetDrives:
    def test_returns_list(self) -> None:
        drives = get_drives()
        assert isinstance(drives, list)

    def test_drive_structure(self) -> None:
        drives = get_drives()
        for drive in drives:
            assert "index" in drive
            assert "path" in drive
            assert "size_gb" in drive
            assert "model" in drive
            assert "is_removable" in drive
            assert "is_system" in drive
            assert "partitions" in drive

    def test_fallback_on_platform_error(self) -> None:
        """If platform module fails, psutil fallback is used."""
        with patch("disktool.platform.list_physical_drives", side_effect=Exception("no drives")):
            drives = get_drives()
            assert isinstance(drives, list)
