"""Tests for disktool.core.compress and the 'compress' CLI command."""

from __future__ import annotations

import gzip
import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from disktool.cli import main
from disktool.core.compress import (
    compress_image,
    decompress_image,
    detect_algorithm,
    list_supported_algorithms,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_img(tmp_path: Path, size: int = 4096, name: str = "test.img") -> Path:
    p = tmp_path / name
    # Use pseudo-random-ish but deterministic data that compresses well
    p.write_bytes(b"\xAB\xCD" * (size // 2))
    return p


# ---------------------------------------------------------------------------
# list_supported_algorithms
# ---------------------------------------------------------------------------

class TestListSupportedAlgorithms:
    def test_gzip_always_present(self) -> None:
        algos = list_supported_algorithms()
        assert "gzip" in algos

    def test_returns_list(self) -> None:
        assert isinstance(list_supported_algorithms(), list)

    def test_no_lz4_when_import_fails(self) -> None:
        with patch.dict("sys.modules", {"lz4": None, "lz4.frame": None}):
            algos = list_supported_algorithms()
        # gzip must still be there
        assert "gzip" in algos

    def test_no_zstd_when_import_fails(self) -> None:
        with patch.dict("sys.modules", {"zstandard": None}):
            algos = list_supported_algorithms()
        assert "gzip" in algos
        assert "zstd" not in algos


# ---------------------------------------------------------------------------
# detect_algorithm
# ---------------------------------------------------------------------------

class TestDetectAlgorithm:
    def test_gz(self) -> None:
        assert detect_algorithm("backup.img.gz") == "gzip"

    def test_lz4(self) -> None:
        assert detect_algorithm("backup.img.lz4") == "lz4"

    def test_zst(self) -> None:
        assert detect_algorithm("backup.img.zst") == "zstd"

    def test_plain_img(self) -> None:
        assert detect_algorithm("backup.img") is None

    def test_uppercase_extension(self) -> None:
        # Path.suffix is case-sensitive on some OS, but we normalise to lower
        assert detect_algorithm("backup.img.GZ") == "gzip"

    def test_path_object(self, tmp_path: Path) -> None:
        p = tmp_path / "file.img.gz"
        assert detect_algorithm(p) == "gzip"


# ---------------------------------------------------------------------------
# compress_image – gzip
# ---------------------------------------------------------------------------

class TestCompressGzip:
    def test_creates_gz_file(self, tmp_path: Path) -> None:
        src = _make_img(tmp_path)
        out = compress_image(str(src), algorithm="gzip")
        assert out.suffix == ".gz"
        assert out.exists()

    def test_default_output_path(self, tmp_path: Path) -> None:
        src = _make_img(tmp_path, name="disk.img")
        out = compress_image(str(src), algorithm="gzip")
        assert out == src.with_suffix(".img.gz")

    def test_custom_output_path(self, tmp_path: Path) -> None:
        src = _make_img(tmp_path)
        custom = tmp_path / "custom_output.gz"
        out = compress_image(str(src), output=str(custom), algorithm="gzip")
        assert out == custom
        assert custom.exists()

    def test_gzip_decompressable(self, tmp_path: Path) -> None:
        data = b"Hello, DiskImager!\n" * 500
        src = tmp_path / "hello.img"
        src.write_bytes(data)
        out = compress_image(str(src), algorithm="gzip")
        with gzip.open(str(out), "rb") as f:
            decompressed = f.read()
        assert decompressed == data

    def test_progress_callback_called(self, tmp_path: Path) -> None:
        src = _make_img(tmp_path, size=8192)
        calls: list[tuple[int, int, float]] = []
        compress_image(str(src), algorithm="gzip",
                       progress_callback=lambda a, b, c: calls.append((a, b, c)))
        assert len(calls) >= 1

    def test_missing_source_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Source not found"):
            compress_image("/nonexistent/file.img", algorithm="gzip")

    def test_unsupported_algorithm_raises(self, tmp_path: Path) -> None:
        src = _make_img(tmp_path)
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            compress_image(str(src), algorithm="bzip2")


# ---------------------------------------------------------------------------
# decompress_image – gzip
# ---------------------------------------------------------------------------

class TestDecompressGzip:
    def test_roundtrip(self, tmp_path: Path) -> None:
        data = b"\xDE\xAD\xBE\xEF" * 1024
        src = tmp_path / "data.img"
        src.write_bytes(data)
        compressed = compress_image(str(src), algorithm="gzip")
        decompressed = decompress_image(str(compressed))
        assert decompressed.read_bytes() == data

    def test_default_output_path(self, tmp_path: Path) -> None:
        src = _make_img(tmp_path, name="disk.img")
        compressed = compress_image(str(src), algorithm="gzip")
        # compressed is disk.img.gz → decompress removes .gz → disk.img
        out = decompress_image(str(compressed))
        assert out.suffix == ".img"

    def test_custom_output_path(self, tmp_path: Path) -> None:
        src = _make_img(tmp_path)
        compressed = compress_image(str(src), algorithm="gzip")
        custom = tmp_path / "restored.img"
        out = decompress_image(str(compressed), output=str(custom))
        assert out == custom
        assert custom.exists()

    def test_progress_callback_called(self, tmp_path: Path) -> None:
        src = _make_img(tmp_path, size=8192)
        compressed = compress_image(str(src), algorithm="gzip")
        calls: list[tuple[int, int, float]] = []
        decompress_image(str(compressed),
                         progress_callback=lambda a, b, c: calls.append((a, b, c)))
        assert len(calls) >= 1

    def test_missing_source_raises(self) -> None:
        with pytest.raises(FileNotFoundError, match="Source not found"):
            decompress_image("/nonexistent/file.img.gz")

    def test_unknown_extension_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "file.img"
        f.write_bytes(b"raw")
        with pytest.raises(ValueError, match="Cannot determine compression algorithm"):
            decompress_image(str(f))

    def test_digest_preserved(self, tmp_path: Path) -> None:
        data = b"checksum test" * 200
        src = tmp_path / "ck.img"
        src.write_bytes(data)
        orig_digest = hashlib.sha256(data).hexdigest()
        compressed = compress_image(str(src), algorithm="gzip")
        restored = decompress_image(str(compressed))
        assert hashlib.sha256(restored.read_bytes()).hexdigest() == orig_digest


# ---------------------------------------------------------------------------
# CLI: compress
# ---------------------------------------------------------------------------

class TestCLICompress:
    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["compress", "--help"])
        assert result.exit_code == 0
        assert "compress" in result.output.lower()
        assert "--algorithm" in result.output

    def test_compress_gzip(self, tmp_path: Path) -> None:
        src = _make_img(tmp_path, size=4096)
        runner = CliRunner()
        result = runner.invoke(main, ["compress", str(src)])
        assert result.exit_code == 0, result.output
        assert "Compressed" in result.output
        gz = src.with_suffix(".img.gz")
        assert gz.exists()

    def test_decompress_flag(self, tmp_path: Path) -> None:
        src = _make_img(tmp_path, size=4096)
        gz = src.with_suffix(".img.gz")
        compress_image(str(src), algorithm="gzip")
        runner = CliRunner()
        result = runner.invoke(main, ["compress", str(gz), "--decompress"])
        assert result.exit_code == 0, result.output
        assert "Decompressed" in result.output

    def test_missing_file_exits_nonzero(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["compress", "/nonexistent/file.img"])
        assert result.exit_code != 0

    def test_unavailable_algorithm_exits_nonzero(self, tmp_path: Path) -> None:
        src = _make_img(tmp_path)
        runner = CliRunner()
        # Simulate lz4 not being available
        with patch("disktool.core.compress.list_supported_algorithms", return_value=["gzip"]):
            result = runner.invoke(main, ["compress", str(src), "--algorithm", "lz4"])
        assert result.exit_code != 0

    def test_compress_shows_savings(self, tmp_path: Path) -> None:
        src = _make_img(tmp_path, size=8192)
        runner = CliRunner()
        result = runner.invoke(main, ["compress", str(src)])
        assert result.exit_code == 0
        assert "%" in result.output  # space savings shown
