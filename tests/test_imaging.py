"""Tests for disktool.core.imaging (using temporary files, no real devices)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from disktool.core.imaging import (
    _get_device_size,
    _resolve_source,
    _unmount_disk_darwin,
    backup,
    clone,
    erase,
    flash,
    restore,
)


def _tmp_file(tmp_path: Path, data: bytes, name: str = "file.img") -> Path:
    """Write *data* to *tmp_path/name* and return the Path."""
    p = tmp_path / name
    p.write_bytes(data)
    return p


class TestGetDeviceSize:
    def test_regular_file(self, tmp_path: Path) -> None:
        data = b"x" * 512
        f = _tmp_file(tmp_path, data)
        assert _get_device_size(str(f)) == 512

    def test_missing_file(self) -> None:
        assert _get_device_size("/nonexistent/file.img") == 0


class TestResolveSource:
    def test_plain_img(self, tmp_path: Path) -> None:
        f = _tmp_file(tmp_path, b"plain")
        assert _resolve_source(f) == f

    def test_zip_extraction(self, tmp_path: Path) -> None:
        import zipfile

        img_data = b"\xee" * 2048
        zip_path = tmp_path / "archive.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("image.img", img_data)
        result = _resolve_source(zip_path)
        assert result.suffix == ".img"
        assert result.read_bytes() == img_data

    def test_zip_no_image(self, tmp_path: Path) -> None:
        import zipfile

        zip_path = tmp_path / "bad.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("readme.txt", "no image here")
        with pytest.raises(ValueError, match="No .img/.iso"):
            _resolve_source(zip_path)


class TestBackup:
    def test_basic_backup(self, tmp_path: Path) -> None:
        src = _tmp_file(tmp_path, b"A" * 4096, "src.img")
        dst = tmp_path / "dst.img"
        digest = backup(str(src), str(dst))
        assert dst.exists()
        assert dst.read_bytes() == src.read_bytes()
        assert digest == hashlib.sha256(b"A" * 4096).hexdigest()

    def test_progress_called(self, tmp_path: Path) -> None:
        src = _tmp_file(tmp_path, b"B" * 8192, "src.img")
        dst = tmp_path / "dst.img"
        calls: list[tuple[int, int, float]] = []
        backup(str(src), str(dst), progress_callback=lambda a, b, c: calls.append((a, b, c)))
        assert calls, "progress_callback should have been called"

    def test_dry_run(self, tmp_path: Path) -> None:
        src = _tmp_file(tmp_path, b"C" * 1024, "src.img")
        dst = tmp_path / "dst.img"
        result = backup(str(src), str(dst), dry_run=True)
        assert result == ""
        assert not dst.exists()

    def test_missing_source(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            backup("/nonexistent/device", str(tmp_path / "out.img"))

    def test_sidecar_created(self, tmp_path: Path) -> None:
        src = _tmp_file(tmp_path, b"sidecar", "src.img")
        dst = tmp_path / "dst.img"
        digest = backup(str(src), str(dst))
        sidecar = tmp_path / "dst.img.sha256"
        assert sidecar.exists()
        content = sidecar.read_text()
        assert digest in content

    def test_metadata_created(self, tmp_path: Path) -> None:
        src = _tmp_file(tmp_path, b"meta", "src.img")
        dst = tmp_path / "dst.img"
        backup(str(src), str(dst))
        meta = tmp_path / "dst.json"
        assert meta.exists()
        import json
        data = json.loads(meta.read_text())
        assert "sha256" in data
        assert "size_bytes" in data


class TestRestore:
    def test_basic_restore(self, tmp_path: Path) -> None:
        img = _tmp_file(tmp_path, b"D" * 4096, "image.img")
        dst = tmp_path / "disk.img"
        dst.write_bytes(b"\x00" * 4096)
        ok = restore(str(img), str(dst), verify=False)
        assert ok is True
        assert dst.read_bytes() == img.read_bytes()

    def test_dry_run(self, tmp_path: Path) -> None:
        img = _tmp_file(tmp_path, b"E" * 1024, "image.img")
        dst = tmp_path / "disk.img"
        ok = restore(str(img), str(dst), dry_run=True)
        assert ok is True
        assert not dst.exists()

    def test_missing_image(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            restore("/nonexistent/image.img", str(tmp_path / "disk.img"))


class TestFlash:
    def test_flash_is_alias_of_restore(self, tmp_path: Path) -> None:
        img = _tmp_file(tmp_path, b"F" * 2048, "ubuntu.iso")
        dst = tmp_path / "usb.img"
        dst.write_bytes(b"\x00" * 2048)
        ok = flash(str(img), str(dst), verify=False)
        assert ok is True
        assert dst.read_bytes() == img.read_bytes()


class TestErase:
    def test_erase_creates_zeros(self, tmp_path: Path) -> None:
        f = _tmp_file(tmp_path, b"X" * 512)
        ok = erase(str(f), passes=1)
        assert ok is True
        assert f.read_bytes() == b"\x00" * 512

    def test_erase_dry_run(self, tmp_path: Path) -> None:
        data = b"original"
        f = _tmp_file(tmp_path, data)
        ok = erase(str(f), passes=1, dry_run=True)
        assert ok is True
        assert f.read_bytes() == data  # unchanged

    def test_erase_missing_target(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            erase("/nonexistent/target.img")

    def test_erase_progress_callback(self, tmp_path: Path) -> None:
        f = _tmp_file(tmp_path, b"Y" * 1024)
        calls: list[tuple[int, int, float]] = []
        erase(str(f), passes=1,
              progress_callback=lambda a, b, c: calls.append((a, b, c)))
        assert calls, "progress_callback should be called"


class TestClone:
    def test_basic_clone(self, tmp_path: Path) -> None:
        src = _tmp_file(tmp_path, b"G" * 4096, "src.img")
        dst = tmp_path / "dst.img"
        digest = clone(str(src), str(dst), verify=False)
        assert dst.exists()
        assert dst.read_bytes() == src.read_bytes()
        assert digest == hashlib.sha256(b"G" * 4096).hexdigest()

    def test_clone_dry_run(self, tmp_path: Path) -> None:
        src = _tmp_file(tmp_path, b"H" * 1024, "src.img")
        dst = tmp_path / "dst.img"
        result = clone(str(src), str(dst), dry_run=True, verify=False)
        assert result == ""
        assert not dst.exists()

    def test_clone_missing_source(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            clone("/nonexistent/source.img", str(tmp_path / "dst.img"))

    def test_clone_same_path(self, tmp_path: Path) -> None:
        src = _tmp_file(tmp_path, b"I" * 512, "src.img")
        with pytest.raises(ValueError, match="different paths"):
            clone(str(src), str(src))

    def test_clone_progress_called(self, tmp_path: Path) -> None:
        src = _tmp_file(tmp_path, b"J" * 8192, "src.img")
        dst = tmp_path / "dst.img"
        calls: list[tuple[int, int, float]] = []
        clone(str(src), str(dst), verify=False,
              progress_callback=lambda a, b, c: calls.append((a, b, c)))
        assert calls, "progress_callback should have been called"


class TestUnmountDiskDarwin:
    """Tests for _unmount_disk_darwin – the macOS Resource-busy fix."""

    def test_noop_on_non_darwin(self, tmp_path: Path) -> None:
        """On non-darwin platforms _unmount_disk_darwin is a no-op."""
        from unittest.mock import patch

        with patch("sys.platform", "linux"):
            with patch("subprocess.run") as mock_run:
                _unmount_disk_darwin("/dev/sdb")
                mock_run.assert_not_called()

    def test_noop_for_regular_file_path(self, tmp_path: Path) -> None:
        """For paths that don't start with /dev/, no unmount is attempted."""
        from unittest.mock import patch

        with patch("sys.platform", "darwin"):
            with patch("subprocess.run") as mock_run:
                _unmount_disk_darwin(str(tmp_path / "image.img"))
                mock_run.assert_not_called()

    def test_calls_diskutil_for_dev_disk(self) -> None:
        """On darwin, diskutil unmountDisk is called for /dev/diskN paths."""
        from unittest.mock import MagicMock, patch

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Unmount of all volumes on disk4 was successful"

        with patch("sys.platform", "darwin"):
            with patch("subprocess.run", return_value=mock_result) as mock_run:
                _unmount_disk_darwin("/dev/disk4")
                mock_run.assert_called_once()
                cmd = mock_run.call_args[0][0]
                assert "diskutil" in cmd
                assert "unmountDisk" in cmd
                assert "/dev/disk4" in cmd

    def test_normalises_rdisk_to_disk(self) -> None:
        """rdiskN paths are normalised to diskN before calling diskutil."""
        from unittest.mock import MagicMock, patch

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Unmount of all volumes on disk4 was successful"

        with patch("sys.platform", "darwin"):
            with patch("subprocess.run", return_value=mock_result) as mock_run:
                _unmount_disk_darwin("/dev/rdisk4")
                cmd = mock_run.call_args[0][0]
                assert "/dev/disk4" in cmd  # rdisk4 → disk4

    def test_normalises_partition_to_whole_disk(self) -> None:
        """Partition paths like /dev/disk4s1 are mapped to /dev/disk4."""
        from unittest.mock import MagicMock, patch

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Unmount of all volumes on disk4 was successful"

        with patch("sys.platform", "darwin"):
            with patch("subprocess.run", return_value=mock_result) as mock_run:
                _unmount_disk_darwin("/dev/disk4s1")
                cmd = mock_run.call_args[0][0]
                assert "/dev/disk4" in cmd

    def test_handles_diskutil_failure_gracefully(self) -> None:
        """If diskutil returns non-zero, no exception is raised."""
        from unittest.mock import MagicMock, patch

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "disk4 was already unmounted or is not mounted"

        with patch("sys.platform", "darwin"):
            with patch("subprocess.run", return_value=mock_result):
                _unmount_disk_darwin("/dev/disk4")  # must not raise

    def test_handles_subprocess_exception_gracefully(self) -> None:
        """If subprocess.run raises (e.g. diskutil not on PATH), no exception propagates."""
        from unittest.mock import patch

        with patch("sys.platform", "darwin"):
            with patch("subprocess.run", side_effect=FileNotFoundError("diskutil not found")):
                _unmount_disk_darwin("/dev/disk4")  # must not raise

    def test_noop_for_non_disk_dev_path(self) -> None:
        """Paths like /dev/null or /dev/zero don't trigger diskutil."""
        from unittest.mock import patch

        with patch("sys.platform", "darwin"):
            with patch("subprocess.run") as mock_run:
                _unmount_disk_darwin("/dev/null")
                mock_run.assert_not_called()
