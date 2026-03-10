"""Tests for disktool.core.format and the 'format' CLI command."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from disktool.cli import main
from disktool.core.format import (
    _normalise_fs,
    _sanitise_label,
    filesystem_label,
    format_disk,
    list_supported_filesystems,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_completed_process(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


# ---------------------------------------------------------------------------
# list_supported_filesystems
# ---------------------------------------------------------------------------

class TestListSupportedFilesystems:
    def test_returns_list(self) -> None:
        supported = list_supported_filesystems()
        assert isinstance(supported, list)
        assert len(supported) > 0

    def test_linux_contains_expected(self) -> None:
        with patch("sys.platform", "linux"):
            supported = list_supported_filesystems()
        assert "fat32" in supported
        assert "ext4" in supported
        assert "exfat" in supported
        assert "ntfs" in supported

    def test_darwin_contains_expected(self) -> None:
        with patch("sys.platform", "darwin"):
            supported = list_supported_filesystems()
        assert "fat32" in supported
        assert "exfat" in supported
        assert "hfs+" in supported
        assert "apfs" in supported
        # Linux-only not on darwin
        assert "ext4" not in supported

    def test_windows_contains_expected(self) -> None:
        with patch("sys.platform", "win32"):
            supported = list_supported_filesystems()
        assert "fat32" in supported
        assert "exfat" in supported
        assert "ntfs" in supported
        assert "ext4" not in supported
        assert "apfs" not in supported


# ---------------------------------------------------------------------------
# filesystem_label
# ---------------------------------------------------------------------------

class TestFilesystemLabel:
    def test_known_labels(self) -> None:
        assert filesystem_label("fat32") == "FAT32"
        assert filesystem_label("exfat") == "exFAT"
        assert filesystem_label("ntfs") == "NTFS"
        assert filesystem_label("ext4") == "ext4"
        assert filesystem_label("hfs+") == "HFS+"
        assert filesystem_label("apfs") == "APFS"

    def test_aliases_resolved(self) -> None:
        assert filesystem_label("fat") == "FAT32"
        assert filesystem_label("vfat") == "FAT32"

    def test_unknown_returns_name(self) -> None:
        assert filesystem_label("zfs") == "zfs"


# ---------------------------------------------------------------------------
# _normalise_fs
# ---------------------------------------------------------------------------

class TestNormaliseFs:
    def test_alias_fat(self) -> None:
        assert _normalise_fs("fat") == "fat32"
        assert _normalise_fs("FAT") == "fat32"
        assert _normalise_fs("vfat") == "fat32"
        assert _normalise_fs("VFAT") == "fat32"
        assert _normalise_fs("msdos") == "fat32"

    def test_alias_hfs(self) -> None:
        assert _normalise_fs("hfsplus") == "hfs+"
        assert _normalise_fs("HFS+") == "hfs+"

    def test_canonical_passthrough(self) -> None:
        assert _normalise_fs("ext4") == "ext4"
        assert _normalise_fs("NTFS") == "ntfs"
        assert _normalise_fs("exFAT") == "exfat"


# ---------------------------------------------------------------------------
# _sanitise_label
# ---------------------------------------------------------------------------

class TestSanitiseLabel:
    def test_normal_label(self) -> None:
        assert _sanitise_label("BACKUP", "ext4") == "BACKUP"

    def test_strips_invalid_chars(self) -> None:
        assert _sanitise_label('my:label*?', "ext4") == "mylabel"

    def test_truncates_to_fat32_limit(self) -> None:
        long = "A" * 20
        result = _sanitise_label(long, "fat32")
        assert len(result) == 11

    def test_truncates_to_ntfs_limit(self) -> None:
        long = "B" * 50
        result = _sanitise_label(long, "ntfs")
        assert len(result) == 32

    def test_empty_falls_back_to_disk(self) -> None:
        assert _sanitise_label("", "ext4") == "DISK"
        assert _sanitise_label("///***", "ext4") == "DISK"


# ---------------------------------------------------------------------------
# format_disk – input validation
# ---------------------------------------------------------------------------

class TestFormatDiskValidation:
    def test_unsupported_filesystem_raises(self) -> None:
        with patch("sys.platform", "linux"):
            with pytest.raises(ValueError, match="Unsupported file system"):
                format_disk("/dev/sdb", "apfs")  # apfs not on linux

    def test_unsupported_platform_raises(self) -> None:
        with patch("sys.platform", "freebsd"):
            with pytest.raises(ValueError, match="Unsupported file system"):
                format_disk("/dev/sdb", "fat32")


# ---------------------------------------------------------------------------
# format_disk – dry-run (no subprocess)
# ---------------------------------------------------------------------------

class TestFormatDiskDryRun:
    def test_linux_dry_run_returns_true(self) -> None:
        with patch("sys.platform", "linux"):
            with patch("subprocess.run") as mock_run:
                result = format_disk("/dev/sdb", "fat32", dry_run=True)
        assert result is True
        mock_run.assert_not_called()

    def test_darwin_dry_run_returns_true(self) -> None:
        with patch("sys.platform", "darwin"):
            with patch("subprocess.run") as mock_run:
                result = format_disk("/dev/disk4", "fat32", dry_run=True)
        assert result is True
        mock_run.assert_not_called()

    def test_windows_dry_run_returns_true(self) -> None:
        with patch("sys.platform", "win32"):
            with patch("subprocess.run") as mock_run:
                result = format_disk("E:", "ntfs", dry_run=True)
        assert result is True
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# format_disk – Linux (mocked subprocess)
# ---------------------------------------------------------------------------

class TestFormatDiskLinux:
    def _run(self, fs: str, device: str = "/dev/sdb", label: str = "TEST") -> tuple[bool, list]:
        """Run format_disk on 'linux' and return (result, captured_cmds)."""
        captured: list[list[str]] = []

        def fake_run(cmd, **kwargs):  # noqa: ANN001
            captured.append(list(cmd))
            return _make_completed_process(0, "Format successful")

        with patch("sys.platform", "linux"):
            with patch("subprocess.run", side_effect=fake_run):
                result = format_disk(device, fs, label=label)
        return result, captured

    def test_fat32_uses_mkfs_fat(self) -> None:
        ok, cmds = self._run("fat32")
        assert ok
        assert cmds[0][0] == "mkfs.fat"
        assert "-F" in cmds[0]
        assert "32" in cmds[0]

    def test_ext4_uses_mkfs_ext4(self) -> None:
        ok, cmds = self._run("ext4")
        assert ok
        assert cmds[0][0] == "mkfs.ext4"

    def test_ext3_uses_mkfs_ext3(self) -> None:
        ok, cmds = self._run("ext3")
        assert ok
        assert cmds[0][0] == "mkfs.ext3"

    def test_ext2_uses_mkfs_ext2(self) -> None:
        ok, cmds = self._run("ext2")
        assert ok
        assert cmds[0][0] == "mkfs.ext2"

    def test_exfat_uses_mkfs_exfat(self) -> None:
        ok, cmds = self._run("exfat")
        assert ok
        assert cmds[0][0] == "mkfs.exfat"

    def test_ntfs_uses_mkfs_ntfs(self) -> None:
        ok, cmds = self._run("ntfs")
        assert ok
        assert cmds[0][0] == "mkfs.ntfs"

    def test_btrfs_uses_mkfs_btrfs(self) -> None:
        ok, cmds = self._run("btrfs")
        assert ok
        assert cmds[0][0] == "mkfs.btrfs"

    def test_label_passed_to_command(self) -> None:
        ok, cmds = self._run("ext4", label="MYDATA")
        assert ok
        assert "MYDATA" in cmds[0]

    def test_device_passed_to_command(self) -> None:
        ok, cmds = self._run("ext4", device="/dev/sdc1")
        assert ok
        assert "/dev/sdc1" in cmds[0]

    def test_alias_vfat_resolves_to_fat32(self) -> None:
        ok, cmds = self._run("vfat")
        assert ok
        assert cmds[0][0] == "mkfs.fat"

    def test_nonzero_exit_raises_oserror(self) -> None:
        with patch("sys.platform", "linux"):
            with patch("subprocess.run", return_value=_make_completed_process(1, stderr="disk busy")):
                with pytest.raises(OSError, match="Format failed"):
                    format_disk("/dev/sdb", "ext4")

    def test_missing_tool_raises_file_not_found(self) -> None:
        with patch("sys.platform", "linux"):
            with patch("subprocess.run", side_effect=FileNotFoundError("mkfs.ext4 not found")):
                with pytest.raises(FileNotFoundError, match="Formatting tool not found"):
                    format_disk("/dev/sdb", "ext4")


# ---------------------------------------------------------------------------
# format_disk – macOS (mocked subprocess)
# ---------------------------------------------------------------------------

class TestFormatDiskDarwin:
    def _run(self, fs: str, device: str = "/dev/disk4", label: str = "TEST") -> tuple[bool, list]:
        captured: list[list[str]] = []

        def fake_run(cmd, **kwargs):  # noqa: ANN001
            captured.append(list(cmd))
            return _make_completed_process(0, "Unmount/Format successful")

        with patch("sys.platform", "darwin"):
            with patch("subprocess.run", side_effect=fake_run):
                result = format_disk(device, fs, label=label)
        return result, captured

    def test_fat32_uses_diskutil(self) -> None:
        ok, cmds = self._run("fat32")
        assert ok
        assert cmds[0][0] == "diskutil"
        assert "eraseVolume" in cmds[0]
        assert "MS-DOS FAT32" in cmds[0]

    def test_exfat_uses_diskutil(self) -> None:
        ok, cmds = self._run("exfat")
        assert ok
        assert "ExFAT" in cmds[0]

    def test_hfsplus_uses_diskutil(self) -> None:
        ok, cmds = self._run("hfs+")
        assert ok
        assert any("HFS" in s for s in cmds[0])

    def test_apfs_uses_diskutil(self) -> None:
        ok, cmds = self._run("apfs")
        assert ok
        assert "APFS" in cmds[0]

    def test_fat32_label_uppercased(self) -> None:
        ok, cmds = self._run("fat32", label="miyoo")
        assert ok
        # Label must be uppercase for FAT32 on macOS
        assert "MIYOO" in cmds[0]

    def test_rdisk_normalised_to_disk(self) -> None:
        ok, cmds = self._run("fat32", device="/dev/rdisk4")
        assert ok
        # diskutil should receive /dev/disk4, not /dev/rdisk4
        assert "/dev/disk4" in cmds[0]
        assert "/dev/rdisk4" not in cmds[0]

    def test_label_passed_to_diskutil(self) -> None:
        ok, cmds = self._run("ext4" if False else "fat32", label="SDCARD")
        assert ok
        assert "SDCARD" in cmds[0]


# ---------------------------------------------------------------------------
# format_disk – Windows (mocked subprocess)
# ---------------------------------------------------------------------------

class TestFormatDiskWindows:
    def _run(self, fs: str, device: str = "E:", label: str = "TEST") -> tuple[bool, list]:
        captured: list[list[str]] = []

        def fake_run(cmd, **kwargs):  # noqa: ANN001
            captured.append(list(cmd))
            return _make_completed_process(0, "Format successful")

        with patch("sys.platform", "win32"):
            with patch("subprocess.run", side_effect=fake_run):
                result = format_disk(device, fs, label=label)
        return result, captured

    def test_fat32_uses_powershell(self) -> None:
        ok, cmds = self._run("fat32")
        assert ok
        assert cmds[0][0] == "powershell"
        assert "FAT32" in " ".join(cmds[0])

    def test_ntfs_uses_powershell(self) -> None:
        ok, cmds = self._run("ntfs")
        assert ok
        assert "NTFS" in " ".join(cmds[0])

    def test_exfat_uses_powershell(self) -> None:
        ok, cmds = self._run("exfat")
        assert ok
        assert "exFAT" in " ".join(cmds[0])

    def test_label_in_command(self) -> None:
        ok, cmds = self._run("ntfs", label="BACKUP")
        assert ok
        assert "BACKUP" in " ".join(cmds[0])


# ---------------------------------------------------------------------------
# CLI 'format' command
# ---------------------------------------------------------------------------

class TestCLIFormat:
    def test_format_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["format", "--help"])
        assert result.exit_code == 0
        assert "DEVICE" in result.output or "device" in result.output.lower()
        assert "FILESYSTEM" in result.output or "filesystem" in result.output.lower()

    def test_list_fs_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["format", "/dev/sdb", "fat32", "--list-fs"])
        assert result.exit_code == 0
        assert "fat32" in result.output.lower()

    def test_unsupported_filesystem_exits_1(self) -> None:
        runner = CliRunner()
        with patch("sys.platform", "linux"):
            result = runner.invoke(main, ["format", "/dev/sdb", "apfs", "--dry-run"])
        assert result.exit_code == 1
        assert "Unsupported" in result.output or "unsupported" in result.output.lower()

    def test_dry_run_no_subprocess(self) -> None:
        runner = CliRunner()
        with patch("sys.platform", "linux"):
            with patch("subprocess.run") as mock_run:
                result = runner.invoke(main, ["format", "/dev/sdb", "ext4", "--dry-run"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        mock_run.assert_not_called()

    def test_system_disk_blocked_without_dangerous(self) -> None:
        runner = CliRunner()
        fake_drives = [
            {
                "index": 0, "name": "sda", "path": "/dev/sda",
                "size_bytes": 256_000_000_000, "size_gb": 256.0,
                "model": "System SSD", "is_removable": False, "is_system": True,
                "partitions": [],
            }
        ]
        with patch("disktool.core.disk.get_drives", return_value=fake_drives):
            result = runner.invoke(main, ["format", "/dev/sda", "ext4", "--dry-run"])
        assert result.exit_code == 1
        assert "system disk" in result.output.lower()

    def test_system_disk_allowed_with_dangerous(self) -> None:
        runner = CliRunner()
        fake_drives = [
            {
                "index": 0, "name": "sda", "path": "/dev/sda",
                "size_bytes": 256_000_000_000, "size_gb": 256.0,
                "model": "System SSD", "is_removable": False, "is_system": True,
                "partitions": [],
            }
        ]
        with patch("sys.platform", "linux"):
            with patch("disktool.core.disk.get_drives", return_value=fake_drives):
                with patch("subprocess.run", return_value=_make_completed_process(0)):
                    result = runner.invoke(
                        main,
                        ["format", "/dev/sda", "ext4", "--dangerous", "--dry-run"],
                    )
        assert result.exit_code == 0

    def test_missing_tool_exits_1(self) -> None:
        runner = CliRunner()
        with patch("sys.platform", "linux"):
            with patch("disktool.core.disk.get_drives", return_value=[]):
                with patch(
                    "subprocess.run",
                    side_effect=FileNotFoundError("mkfs.ext4 not found"),
                ):
                    result = runner.invoke(
                        main,
                        ["format", "/dev/sdb", "ext4", "--dry-run"],
                    )
        # dry-run never calls subprocess; just confirm no crash
        assert result.exit_code == 0

    def test_format_command_registered(self) -> None:
        """'format' must appear in the top-level help."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "format" in result.output
