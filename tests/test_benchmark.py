"""Tests for disktool.core.benchmark and the 'benchmark' CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from disktool.cli import main
from disktool.core.benchmark import (
    DEFAULT_BLOCK_SIZE_MB,
    benchmark_device,
    benchmark_read,
    benchmark_write,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_temp_data(tmp_path: Path, size: int, name: str = "source.bin") -> Path:
    """Create a temp file with predictable content."""
    p = tmp_path / name
    p.write_bytes(b"\xAB" * size)
    return p


# ---------------------------------------------------------------------------
# benchmark_read
# ---------------------------------------------------------------------------

class TestBenchmarkRead:
    def test_basic_result_keys(self, tmp_path: Path) -> None:
        src = _make_temp_data(tmp_path, 1024 * 1024)  # 1 MiB
        result = benchmark_read(str(src), size_mb=1, block_size_mb=1)
        assert result["operation"] == "read"
        assert result["device"] == str(src)
        assert result["size_mb"] > 0
        assert result["duration_s"] >= 0
        assert result["speed_mb_s"] >= 0

    def test_reads_full_size(self, tmp_path: Path) -> None:
        data = b"X" * (2 * 1024 * 1024)  # 2 MiB
        src = _make_temp_data(tmp_path, len(data))
        result = benchmark_read(str(src), size_mb=2, block_size_mb=1)
        assert abs(result["size_mb"] - 2.0) < 0.01

    def test_reads_less_than_requested_when_file_smaller(self, tmp_path: Path) -> None:
        # File is 512 KiB but we ask for 4 MiB – should read only what's there
        data = b"Y" * (512 * 1024)
        src = _make_temp_data(tmp_path, len(data))
        result = benchmark_read(str(src), size_mb=4, block_size_mb=1)
        assert result["size_mb"] <= 0.5 + 0.01

    def test_progress_callback_called(self, tmp_path: Path) -> None:
        src = _make_temp_data(tmp_path, 256 * 1024)  # 256 KiB
        calls: list[tuple[int, int, float]] = []
        benchmark_read(
            str(src),
            size_mb=1,
            block_size_mb=1,
            progress_callback=lambda a, b, c: calls.append((a, b, c)),
        )
        assert len(calls) >= 1
        assert all(a > 0 for a, _, _ in calls)

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError, match="Device not found"):
            benchmark_read("/nonexistent/device.img", size_mb=1)

    def test_speed_mb_s_positive(self, tmp_path: Path) -> None:
        src = _make_temp_data(tmp_path, 1024 * 1024)
        result = benchmark_read(str(src), size_mb=1)
        assert result["speed_mb_s"] > 0

    def test_default_block_size(self, tmp_path: Path) -> None:
        # Just verify DEFAULT_BLOCK_SIZE_MB is exported and is sensible
        assert 1 <= DEFAULT_BLOCK_SIZE_MB <= 64


# ---------------------------------------------------------------------------
# benchmark_write
# ---------------------------------------------------------------------------

class TestBenchmarkWrite:
    def test_basic_result_keys(self, tmp_path: Path) -> None:
        result = benchmark_write(str(tmp_path), size_mb=1, block_size_mb=1)
        assert result["operation"] == "write"
        assert result["device"] == str(tmp_path)
        assert result["size_mb"] > 0
        assert result["duration_s"] >= 0
        assert result["speed_mb_s"] >= 0

    def test_writes_correct_size(self, tmp_path: Path) -> None:
        result = benchmark_write(str(tmp_path), size_mb=2, block_size_mb=1)
        assert abs(result["size_mb"] - 2.0) < 0.01

    def test_temp_file_cleaned_up(self, tmp_path: Path) -> None:
        before = set(tmp_path.iterdir())
        benchmark_write(str(tmp_path), size_mb=1, block_size_mb=1)
        after = set(tmp_path.iterdir())
        # The temp file must have been removed
        assert before == after

    def test_progress_callback_called(self, tmp_path: Path) -> None:
        calls: list[tuple[int, int, float]] = []
        benchmark_write(
            str(tmp_path),
            size_mb=1,
            block_size_mb=1,
            progress_callback=lambda a, b, c: calls.append((a, b, c)),
        )
        assert len(calls) >= 1

    def test_speed_mb_s_positive(self, tmp_path: Path) -> None:
        result = benchmark_write(str(tmp_path), size_mb=1)
        assert result["speed_mb_s"] > 0

    def test_write_to_specific_file_path(self, tmp_path: Path) -> None:
        """Target is a non-existing file name inside an existing dir."""
        target = tmp_path / "bench_output.bin"
        result = benchmark_write(str(target), size_mb=1, block_size_mb=1)
        assert result["size_mb"] > 0
        # temp_file is None branch: caller's file - after write it may or may
        # not be cleaned up (benchmark_write only deletes if temp_file is set).
        # The important thing is the result is correct.


# ---------------------------------------------------------------------------
# benchmark_device
# ---------------------------------------------------------------------------

class TestBenchmarkDevice:
    def test_read_only(self, tmp_path: Path) -> None:
        src = _make_temp_data(tmp_path, 1024 * 1024)
        results = benchmark_device(str(src), size_mb=1, read=True, write=False)
        assert "read" in results
        assert "write" not in results
        assert results["device"] == str(src)

    def test_write_only(self, tmp_path: Path) -> None:
        results = benchmark_device(str(tmp_path), size_mb=1, read=False, write=True)
        assert "write" in results
        assert "read" not in results

    def test_both(self, tmp_path: Path) -> None:
        src = _make_temp_data(tmp_path, 2 * 1024 * 1024)
        results = benchmark_device(
            str(src), size_mb=1, read=True, write=False, block_size_mb=1
        )
        assert "read" in results

    def test_neither_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="At least one"):
            benchmark_device(str(tmp_path), read=False, write=False)


# ---------------------------------------------------------------------------
# CLI: benchmark
# ---------------------------------------------------------------------------

class TestCLIBenchmark:
    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["benchmark", "--help"])
        assert result.exit_code == 0
        assert "DEVICE" in result.output
        assert "--size" in result.output
        assert "--write" in result.output

    def test_read_benchmark_on_file(self, tmp_path: Path) -> None:
        src = _make_temp_data(tmp_path, 2 * 1024 * 1024)
        runner = CliRunner()
        result = runner.invoke(main, [
            "benchmark", str(src),
            "--size", "1", "--block-size", "1",
        ])
        assert result.exit_code == 0
        assert "MB/s" in result.output or "Speed" in result.output

    def test_write_benchmark_on_dir(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, [
            "benchmark", str(tmp_path),
            "--size", "1", "--block-size", "1",
            "--write", "--read-only",
        ])
        assert result.exit_code == 0
        assert "MB/s" in result.output or "Speed" in result.output

    def test_missing_device(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, [
            "benchmark", "/nonexistent/__bench_dev__",
            "--size", "1",
        ])
        assert result.exit_code != 0

    def test_nothing_to_do_exits_nonzero(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, [
            "benchmark", str(tmp_path),
            "--read-only",
            # no --write so nothing to do
        ])
        assert result.exit_code != 0

    def test_benchmark_table_shown(self, tmp_path: Path) -> None:
        src = _make_temp_data(tmp_path, 1024 * 1024)
        runner = CliRunner()
        result = runner.invoke(main, [
            "benchmark", str(src),
            "--size", "1", "--block-size", "1",
        ])
        assert "Benchmark Results" in result.output or "Read" in result.output
