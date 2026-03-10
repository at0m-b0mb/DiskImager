"""Tests for disktool.core.partition and the 'partition' CLI command."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from disktool.cli import main
from disktool.core.partition import (
    SUPPORTED_SCHEMES,
    _parse_size_to_mb,
    _win_disk_num,
    add_partition,
    create_partition_table,
    list_partition_schemes,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


# ---------------------------------------------------------------------------
# list_partition_schemes
# ---------------------------------------------------------------------------

class TestListPartitionSchemes:
    def test_returns_list(self) -> None:
        schemes = list_partition_schemes()
        assert isinstance(schemes, list)
        assert "mbr" in schemes
        assert "gpt" in schemes

    def test_independent_copy(self) -> None:
        a = list_partition_schemes()
        a.clear()
        assert list_partition_schemes()  # original not mutated


# ---------------------------------------------------------------------------
# _parse_size_to_mb
# ---------------------------------------------------------------------------

class TestParseSizeToMb:
    def test_megabytes(self) -> None:
        assert _parse_size_to_mb("512M") == 512
        assert _parse_size_to_mb("512MB") == 512

    def test_gigabytes(self) -> None:
        assert _parse_size_to_mb("8G") == 8 * 1024

    def test_terabytes(self) -> None:
        assert _parse_size_to_mb("1T") == 1024 * 1024

    def test_percentage_returns_none(self) -> None:
        assert _parse_size_to_mb("100%") is None
        assert _parse_size_to_mb("50%") is None

    def test_unknown_returns_none(self) -> None:
        assert _parse_size_to_mb("all") is None

    def test_enforces_minimum_1mb(self) -> None:
        # 1K is less than 1 MB; the function enforces a minimum of 1 MB
        assert _parse_size_to_mb("1K") >= 1

    def test_lowercase_units(self) -> None:
        assert _parse_size_to_mb("8g") == 8 * 1024
        assert _parse_size_to_mb("512m") == 512


# ---------------------------------------------------------------------------
# _win_disk_num
# ---------------------------------------------------------------------------

class TestWinDiskNum:
    def test_physical_drive(self) -> None:
        assert _win_disk_num(r"\\.\PhysicalDrive2") == "2"

    def test_no_trailing_digit(self) -> None:
        assert _win_disk_num(r"\\.\PhysicalDrive") == "0"

    def test_single_digit(self) -> None:
        assert _win_disk_num(r"\\.\PhysicalDrive0") == "0"


# ---------------------------------------------------------------------------
# create_partition_table – unsupported scheme / platform
# ---------------------------------------------------------------------------

class TestCreatePartitionTableValidation:
    def test_unsupported_scheme_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported partition scheme"):
            create_partition_table("/dev/sdb", "zfs_table")

    def test_unsupported_platform_raises(self) -> None:
        with patch("sys.platform", "freebsd13"):
            with pytest.raises(ValueError, match="Unsupported platform"):
                create_partition_table("/dev/da0", "gpt")

    def test_scheme_case_insensitive(self) -> None:
        with patch("disktool.core.partition._create_linux") as mock_fn:
            mock_fn.return_value = True
            with patch("sys.platform", "linux"):
                result = create_partition_table("/dev/sdb", "GPT")
        assert result is True
        mock_fn.assert_called_once_with("/dev/sdb", "gpt", False)


# ---------------------------------------------------------------------------
# create_partition_table – dry-run (no subprocess calls)
# ---------------------------------------------------------------------------

class TestCreatePartitionTableDryRun:
    def test_dry_run_linux(self) -> None:
        with patch("sys.platform", "linux"):
            with patch("subprocess.run") as mock_run:
                result = create_partition_table("/dev/sdb", "gpt", dry_run=True)
        assert result is True
        mock_run.assert_not_called()

    def test_dry_run_darwin(self) -> None:
        with patch("sys.platform", "darwin"):
            with patch("subprocess.run") as mock_run:
                result = create_partition_table("/dev/disk4", "gpt", dry_run=True)
        assert result is True
        mock_run.assert_not_called()

    def test_dry_run_windows(self) -> None:
        with patch("sys.platform", "win32"):
            with patch("subprocess.run") as mock_run:
                result = create_partition_table(r"\\.\PhysicalDrive1", "gpt", dry_run=True)
        assert result is True
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# create_partition_table – real subprocess call (mocked)
# ---------------------------------------------------------------------------

class TestCreatePartitionTableLinux:
    def test_gpt_calls_parted(self) -> None:
        with patch("sys.platform", "linux"):
            with patch("subprocess.run", return_value=_completed()) as mock_run:
                result = create_partition_table("/dev/sdb", "gpt")
        assert result is True
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "parted"
        assert "gpt" in cmd

    def test_mbr_calls_parted(self) -> None:
        with patch("sys.platform", "linux"):
            with patch("subprocess.run", return_value=_completed()) as mock_run:
                result = create_partition_table("/dev/sdb", "mbr")
        assert result is True
        cmd = mock_run.call_args[0][0]
        assert "msdos" in cmd

    def test_nonzero_exit_raises_oserror(self) -> None:
        with patch("sys.platform", "linux"):
            with patch("subprocess.run", return_value=_completed(1, stderr="error")):
                with pytest.raises(OSError, match="Partition operation failed"):
                    create_partition_table("/dev/sdb", "gpt")

    def test_tool_not_found_raises(self) -> None:
        with patch("sys.platform", "linux"):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                with pytest.raises(FileNotFoundError, match="Partitioning tool not found"):
                    create_partition_table("/dev/sdb", "gpt")


class TestCreatePartitionTableDarwin:
    def test_gpt_calls_diskutil(self) -> None:
        with patch("sys.platform", "darwin"):
            with patch("subprocess.run", return_value=_completed()) as mock_run:
                result = create_partition_table("/dev/disk4", "gpt")
        assert result is True
        cmd = mock_run.call_args[0][0]
        assert "diskutil" in cmd
        assert "GPTFormat" in cmd

    def test_mbr_calls_diskutil(self) -> None:
        with patch("sys.platform", "darwin"):
            with patch("subprocess.run", return_value=_completed()) as mock_run:
                create_partition_table("/dev/disk4", "mbr")
        cmd = mock_run.call_args[0][0]
        assert "MBRFormat" in cmd


class TestCreatePartitionTableWindows:
    def test_gpt_calls_diskpart(self) -> None:
        with patch("sys.platform", "win32"):
            with patch("subprocess.run", return_value=_completed()) as mock_run:
                with patch("os.unlink"):
                    result = create_partition_table(r"\\.\PhysicalDrive1", "gpt")
        assert result is True
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "diskpart"


# ---------------------------------------------------------------------------
# add_partition – dry-run
# ---------------------------------------------------------------------------

class TestAddPartitionDryRun:
    def test_dry_run_linux(self) -> None:
        with patch("sys.platform", "linux"):
            with patch("subprocess.run") as mock_run:
                result = add_partition("/dev/sdb", size="100%", dry_run=True)
        assert result is True
        mock_run.assert_not_called()

    def test_dry_run_darwin(self) -> None:
        with patch("sys.platform", "darwin"):
            with patch("subprocess.run") as mock_run:
                result = add_partition("/dev/disk4", size="50%", dry_run=True)
        assert result is True
        mock_run.assert_not_called()


class TestAddPartitionLinux:
    def test_add_with_fs(self) -> None:
        with patch("sys.platform", "linux"):
            with patch("subprocess.run", return_value=_completed()) as mock_run:
                result = add_partition("/dev/sdb", size="100%", filesystem="ext4", label="data")
        assert result is True
        cmd = mock_run.call_args[0][0]
        assert "parted" in cmd
        assert "mkpart" in cmd
        assert "ext4" in cmd

    def test_add_fat32_partition(self) -> None:
        with patch("sys.platform", "linux"):
            with patch("subprocess.run", return_value=_completed()) as mock_run:
                add_partition("/dev/sdb", size="8G", filesystem="fat32", label="BOOT")
        cmd = mock_run.call_args[0][0]
        assert "fat32" in cmd

    def test_add_no_fs(self) -> None:
        with patch("sys.platform", "linux"):
            with patch("subprocess.run", return_value=_completed()) as mock_run:
                add_partition("/dev/sdb", size="100%")
        # Should still succeed; no fs_type appended
        cmd = mock_run.call_args[0][0]
        assert "parted" in cmd

    def test_unsupported_platform(self) -> None:
        with patch("sys.platform", "freebsd13"):
            with pytest.raises(ValueError, match="Unsupported platform"):
                add_partition("/dev/da0", size="100%")


# ---------------------------------------------------------------------------
# CLI: partition
# ---------------------------------------------------------------------------

class TestCLIPartition:
    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["partition", "--help"])
        assert result.exit_code == 0
        assert "DEVICE" in result.output
        assert "SCHEME" in result.output
        assert "--add" in result.output

    def test_dry_run_gpt(self) -> None:
        runner = CliRunner()
        with patch("disktool.core.partition._create_linux") as mock_fn:
            mock_fn.return_value = True
            with patch("sys.platform", "linux"):
                with patch("disktool.core.disk.get_drives", return_value=[]):
                    result = runner.invoke(main, [
                        "partition", "/dev/sdb", "gpt", "--dry-run"
                    ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_dry_run_with_partitions(self) -> None:
        runner = CliRunner()
        with patch("disktool.core.partition._create_linux") as mock_create:
            mock_create.return_value = True
            with patch("disktool.core.partition._add_partition_linux") as mock_add:
                mock_add.return_value = True
                with patch("sys.platform", "linux"):
                    with patch("disktool.core.disk.get_drives", return_value=[]):
                        result = runner.invoke(main, [
                            "partition", "/dev/sdb", "gpt",
                            "--add", "8G:fat32:BOOT",
                            "--add", "100%:ext4:ROOT",
                            "--dry-run",
                        ])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_unsupported_scheme_exits_nonzero(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, [
            "partition", "/dev/sdb", "zfs_scheme",
        ])
        assert result.exit_code != 0

    def test_system_disk_blocked(self) -> None:
        runner = CliRunner()
        fake_drive = [{"path": "/dev/sda", "is_system": True, "size_gb": 500, "model": "Samsung"}]
        with patch("disktool.core.disk.get_drives", return_value=fake_drive):
            result = runner.invoke(main, ["partition", "/dev/sda", "gpt"])
        assert result.exit_code != 0
        assert "system disk" in result.output

    def test_dangerous_overrides_system_guard(self) -> None:
        runner = CliRunner()
        fake_drive = [{"path": "/dev/sda", "is_system": True, "size_gb": 500, "model": "Samsung"}]
        with patch("disktool.core.disk.get_drives", return_value=fake_drive):
            with patch("disktool.core.partition._create_linux") as mock_fn:
                mock_fn.return_value = True
                with patch("sys.platform", "linux"):
                    result = runner.invoke(main, [
                        "partition", "/dev/sda", "gpt",
                        "--dry-run", "--dangerous",
                    ])
        assert result.exit_code == 0
