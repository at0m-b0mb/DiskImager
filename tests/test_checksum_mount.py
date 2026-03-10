"""Tests for multi_hash in disktool.core.verify, the 'checksum' CLI command,
and the 'mount' / 'unmount' CLI commands (and disktool.core.mount)."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from disktool.cli import main
from disktool.core.verify import COMMON_ALGORITHMS, multi_hash
from disktool.core.mount import mount_image, unmount_image


# ===========================================================================
# multi_hash
# ===========================================================================

class TestMultiHash:
    def test_default_algorithms(self, tmp_path: Path) -> None:
        data = b"hello world"
        f = tmp_path / "f.bin"
        f.write_bytes(data)
        result = multi_hash(f)
        assert set(result.keys()) == set(COMMON_ALGORITHMS)

    def test_single_algorithm(self, tmp_path: Path) -> None:
        data = b"test"
        f = tmp_path / "f.bin"
        f.write_bytes(data)
        result = multi_hash(f, algorithms=["sha256"])
        assert "sha256" in result
        expected = hashlib.sha256(data).hexdigest()
        assert result["sha256"] == expected

    def test_all_digests_correct(self, tmp_path: Path) -> None:
        data = b"disktool multi hash" * 100
        f = tmp_path / "data.bin"
        f.write_bytes(data)
        result = multi_hash(f, algorithms=["md5", "sha1", "sha256", "sha512"])
        assert result["md5"]    == hashlib.md5(data).hexdigest()
        assert result["sha1"]   == hashlib.sha1(data).hexdigest()
        assert result["sha256"] == hashlib.sha256(data).hexdigest()
        assert result["sha512"] == hashlib.sha512(data).hexdigest()

    def test_progress_callback(self, tmp_path: Path) -> None:
        data = b"A" * (2 * 1024 * 1024)  # 2 MiB
        f = tmp_path / "big.bin"
        f.write_bytes(data)
        calls: list[int] = []
        multi_hash(f, progress_callback=lambda n: calls.append(n))
        assert len(calls) >= 1
        assert calls[-1] == len(data)

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError, match="File not found"):
            multi_hash("/nonexistent/file.bin")

    def test_unsupported_algorithm_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "f.bin"
        f.write_bytes(b"x")
        with pytest.raises(ValueError, match="Unsupported hash algorithm"):
            multi_hash(f, algorithms=["notreal_hash_xyz"])

    def test_multiple_algorithms_single_pass_consistent(self, tmp_path: Path) -> None:
        """Results must match individual hash_file calls (same data, same output)."""
        from disktool.core.verify import hash_file
        data = b"consistency check" * 512
        f = tmp_path / "c.bin"
        f.write_bytes(data)
        multi = multi_hash(f, algorithms=["sha256", "sha512"])
        assert multi["sha256"] == hash_file(f, algorithm="sha256")
        assert multi["sha512"] == hash_file(f, algorithm="sha512")

    def test_returns_lowercase(self, tmp_path: Path) -> None:
        f = tmp_path / "lc.bin"
        f.write_bytes(b"lower")
        result = multi_hash(f, algorithms=["sha256"])
        assert result["sha256"] == result["sha256"].lower()


# ===========================================================================
# CLI: checksum
# ===========================================================================

class TestCLIChecksum:
    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["checksum", "--help"])
        assert result.exit_code == 0
        assert "--algorithms" in result.output

    def test_default_checksums(self, tmp_path: Path) -> None:
        f = tmp_path / "data.bin"
        f.write_bytes(b"checksum test " * 50)
        runner = CliRunner()
        result = runner.invoke(main, ["checksum", str(f)])
        assert result.exit_code == 0
        assert "SHA256" in result.output or "sha256" in result.output.lower()
        assert "MD5" in result.output or "md5" in result.output.lower()

    def test_custom_algorithms(self, tmp_path: Path) -> None:
        f = tmp_path / "data.bin"
        f.write_bytes(b"X" * 1024)
        runner = CliRunner()
        result = runner.invoke(main, ["checksum", str(f), "--algorithms", "sha256,sha512"])
        assert result.exit_code == 0
        assert "SHA256" in result.output or "sha256" in result.output.lower()
        assert "SHA512" in result.output or "sha512" in result.output.lower()
        # md5 should NOT appear when not requested
        assert "MD5" not in result.output.upper()

    def test_save_sidecar(self, tmp_path: Path) -> None:
        f = tmp_path / "backup.img"
        f.write_bytes(b"Y" * 2048)
        runner = CliRunner()
        result = runner.invoke(main, [
            "checksum", str(f), "--algorithms", "sha256", "--save"
        ])
        assert result.exit_code == 0
        sidecar = tmp_path / "backup.img.sha256"
        assert sidecar.exists()

    def test_missing_file_exits_nonzero(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["checksum", "/nonexistent/__no_file__.bin"])
        assert result.exit_code != 0

    def test_invalid_algorithm_exits_nonzero(self, tmp_path: Path) -> None:
        f = tmp_path / "f.bin"
        f.write_bytes(b"test")
        runner = CliRunner()
        result = runner.invoke(main, ["checksum", str(f), "--algorithms", "fakehash_xyz"])
        assert result.exit_code != 0

    def test_table_header_shown(self, tmp_path: Path) -> None:
        f = tmp_path / "f.bin"
        f.write_bytes(b"table test")
        runner = CliRunner()
        result = runner.invoke(main, ["checksum", str(f), "--algorithms", "sha256"])
        assert result.exit_code == 0
        # Rich table renders "Checksums" in output
        assert "Checksum" in result.output or "SHA256" in result.output.upper()


# ===========================================================================
# mount_image / unmount_image – core (dry-run, no real devices)
# ===========================================================================

class TestMountImageDryRun:
    def test_dry_run_linux(self, tmp_path: Path) -> None:
        img = tmp_path / "test.img"
        img.write_bytes(b"\x00" * 512)
        with patch("sys.platform", "linux"):
            result = mount_image(str(img), dry_run=True)
        assert result["dry_run"] is True
        assert result["image"] == str(img)

    def test_dry_run_darwin(self, tmp_path: Path) -> None:
        img = tmp_path / "test.img"
        img.write_bytes(b"\x00" * 512)
        with patch("sys.platform", "darwin"):
            result = mount_image(str(img), dry_run=True)
        assert result["dry_run"] is True

    def test_dry_run_windows(self, tmp_path: Path) -> None:
        img = tmp_path / "test.img"
        img.write_bytes(b"\x00" * 512)
        with patch("sys.platform", "win32"):
            result = mount_image(str(img), dry_run=True)
        assert result["dry_run"] is True

    def test_file_not_found_raises(self) -> None:
        with pytest.raises(FileNotFoundError, match="Image not found"):
            mount_image("/nonexistent/__no_img__.img")

    def test_unsupported_platform_raises(self, tmp_path: Path) -> None:
        img = tmp_path / "test.img"
        img.write_bytes(b"\x00" * 512)
        with patch("sys.platform", "unsupported_os"):
            with pytest.raises(ValueError, match="Unsupported platform"):
                mount_image(str(img))

    def test_mountpoint_in_result(self, tmp_path: Path) -> None:
        img = tmp_path / "test.img"
        img.write_bytes(b"\x00" * 512)
        mp = str(tmp_path / "mnt")
        with patch("sys.platform", "linux"):
            result = mount_image(str(img), mountpoint=mp, dry_run=True)
        assert result["mountpoint"] == mp


class TestUnmountImageDryRun:
    def test_dry_run_linux(self) -> None:
        with patch("sys.platform", "linux"):
            result = unmount_image("/mnt/test", dry_run=True)
        assert result is True

    def test_dry_run_darwin(self) -> None:
        with patch("sys.platform", "darwin"):
            result = unmount_image("/Volumes/TEST", dry_run=True)
        assert result is True

    def test_dry_run_windows(self) -> None:
        with patch("sys.platform", "win32"):
            result = unmount_image(r"C:\image.img", dry_run=True)
        assert result is True

    def test_unsupported_platform_raises(self) -> None:
        with patch("sys.platform", "unsupported_os"):
            with pytest.raises(ValueError, match="Unsupported platform"):
                unmount_image("/mnt/test")


class TestMountSubprocessCalled:
    """Verify the right subprocess commands are invoked (mocked)."""

    def _completed(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
        m = MagicMock()
        m.returncode = returncode
        m.stdout = stdout
        m.stderr = stderr
        return m

    def test_linux_losetup_called(self, tmp_path: Path) -> None:
        img = tmp_path / "d.img"
        img.write_bytes(b"\x00" * 512)
        with patch("sys.platform", "linux"):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    self._completed(stdout="/dev/loop0"),  # losetup
                    self._completed(),                     # mount
                ]
                result = mount_image(str(img))
        assert result["loop_device"] == "/dev/loop0"
        first_cmd = mock_run.call_args_list[0][0][0]
        assert "losetup" in first_cmd

    def test_darwin_hdiutil_called(self, tmp_path: Path) -> None:
        img = tmp_path / "d.img"
        img.write_bytes(b"\x00" * 512)
        with patch("sys.platform", "darwin"):
            with patch("subprocess.run", return_value=self._completed()) as mock_run:
                mount_image(str(img))
        cmd = mock_run.call_args[0][0]
        assert "hdiutil" in cmd

    def test_linux_losetup_failure_raises(self, tmp_path: Path) -> None:
        img = tmp_path / "d.img"
        img.write_bytes(b"\x00" * 512)
        with patch("sys.platform", "linux"):
            with patch("subprocess.run", return_value=self._completed(1, stderr="no device")):
                with pytest.raises(OSError, match="losetup failed"):
                    mount_image(str(img))

    def test_unmount_linux_calls_umount(self) -> None:
        with patch("sys.platform", "linux"):
            with patch("subprocess.run", return_value=self._completed()) as mock_run:
                unmount_image("/mnt/test")
        first_cmd = mock_run.call_args_list[0][0][0]
        assert "umount" in first_cmd


# ===========================================================================
# CLI: mount / unmount
# ===========================================================================

class TestCLIMount:
    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["mount", "--help"])
        assert result.exit_code == 0
        assert "IMAGE" in result.output

    def test_dry_run_linux(self, tmp_path: Path) -> None:
        img = tmp_path / "test.img"
        img.write_bytes(b"\x00" * 512)
        runner = CliRunner()
        with patch("sys.platform", "linux"):
            result = runner.invoke(main, ["mount", str(img), "--dry-run"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_missing_image_exits_nonzero(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["mount", "/nonexistent/missing.img"])
        assert result.exit_code != 0

    def test_unsupported_platform_exits_nonzero(self, tmp_path: Path) -> None:
        img = tmp_path / "test.img"
        img.write_bytes(b"\x00" * 512)
        runner = CliRunner()
        with patch("sys.platform", "unsupported_os"):
            result = runner.invoke(main, ["mount", str(img)])
        assert result.exit_code != 0


class TestCLIUnmount:
    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["unmount", "--help"])
        assert result.exit_code == 0
        assert "IMAGE_OR_MOUNTPOINT" in result.output

    def test_dry_run_linux(self) -> None:
        runner = CliRunner()
        with patch("sys.platform", "linux"):
            result = runner.invoke(main, ["unmount", "/mnt/test", "--dry-run"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_unsupported_platform_exits_nonzero(self) -> None:
        runner = CliRunner()
        with patch("sys.platform", "unsupported_os"):
            result = runner.invoke(main, ["unmount", "/mnt/test"])
        assert result.exit_code != 0
