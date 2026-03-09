"""Tests for disktool.core.verify."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import pytest

from disktool.core.verify import hash_file, read_sidecar, verify_file, write_sidecar


def _write_temp(data: bytes, tmp_path: Path) -> Path:
    """Write *data* to a temporary file inside *tmp_path* and return its Path."""
    f = tmp_path / "test.img"
    f.write_bytes(data)
    return f


class TestHashFile:
    def test_empty_file(self, tmp_path: Path) -> None:
        f = _write_temp(b"", tmp_path)
        digest = hash_file(f)
        assert digest == hashlib.sha256(b"").hexdigest()

    def test_known_content(self, tmp_path: Path) -> None:
        data = b"Hello, DiskImager!"
        f = _write_temp(data, tmp_path)
        assert hash_file(f) == hashlib.sha256(data).hexdigest()

    def test_progress_callback(self, tmp_path: Path) -> None:
        data = b"x" * 1024
        f = _write_temp(data, tmp_path)
        reported: list[int] = []
        hash_file(f, progress_callback=lambda n: reported.append(n))
        assert reported[-1] == len(data)

    def test_sha512(self, tmp_path: Path) -> None:
        data = b"test"
        f = _write_temp(data, tmp_path)
        assert hash_file(f, algorithm="sha512") == hashlib.sha512(data).hexdigest()

    def test_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            hash_file("/nonexistent/path/file.img")


class TestVerifyFile:
    def test_match(self, tmp_path: Path) -> None:
        data = b"verify me"
        f = _write_temp(data, tmp_path)
        digest = hashlib.sha256(data).hexdigest()
        assert verify_file(f, digest) is True

    def test_mismatch(self, tmp_path: Path) -> None:
        data = b"bad data"
        f = _write_temp(data, tmp_path)
        assert verify_file(f, "0" * 64) is False

    def test_case_insensitive(self, tmp_path: Path) -> None:
        data = b"case"
        f = _write_temp(data, tmp_path)
        digest = hashlib.sha256(data).hexdigest().upper()
        assert verify_file(f, digest) is True


class TestSidecar:
    def test_write_and_read(self, tmp_path: Path) -> None:
        f = _write_temp(b"sidecar test", tmp_path)
        digest = hashlib.sha256(b"sidecar test").hexdigest()
        sidecar = write_sidecar(f, digest)
        assert sidecar.exists()
        result = read_sidecar(f)
        assert result is not None
        algo, read_digest = result
        assert algo == "sha256"
        assert read_digest == digest

    def test_no_sidecar(self, tmp_path: Path) -> None:
        f = _write_temp(b"no sidecar", tmp_path)
        assert read_sidecar(f) is None
