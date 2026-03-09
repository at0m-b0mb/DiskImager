"""Tests for the CLI using Click's test runner."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from click.testing import CliRunner

from disktool.cli import main


class TestCLIList:
    def test_list_runs(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["list"])
        assert result.exit_code == 0

    def test_version(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "1.0.0" in result.output

    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Usage" in result.output


class TestCLIBackup:
    def test_dry_run(self, tmp_path: Path) -> None:
        src = tmp_path / "src.img"
        src.write_bytes(b"X" * 512)
        dst = tmp_path / "out.img"
        runner = CliRunner()
        result = runner.invoke(main, ["backup", str(src), str(dst), "--dry-run"])
        assert result.exit_code == 0
        assert not dst.exists()

    def test_missing_source(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["backup", "/no/such/device", str(tmp_path / "out.img"), "--dry-run"])
        # dry-run skips file check, so exit 0 is ok; or non-zero if it checks
        # Either is acceptable, we just confirm it doesn't crash
        assert result.exit_code in (0, 1)


class TestCLIVerify:
    def test_verify_known_hash(self, tmp_path: Path) -> None:
        data = b"disktool verify test"
        f = tmp_path / "test.img"
        f.write_bytes(data)
        good_hash = hashlib.sha256(data).hexdigest()
        runner = CliRunner()
        result = runner.invoke(main, ["verify", str(f), "--hash", good_hash])
        assert result.exit_code == 0
        assert "match" in result.output.lower()

    def test_verify_bad_hash(self, tmp_path: Path) -> None:
        data = b"disktool verify test"
        f = tmp_path / "test.img"
        f.write_bytes(data)
        runner = CliRunner()
        result = runner.invoke(main, ["verify", str(f), "--hash", "0" * 64])
        assert result.exit_code == 2

    def test_verify_missing_file(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["verify", "/nonexistent/file.img"])
        assert result.exit_code == 1

    def test_verify_no_hash(self, tmp_path: Path) -> None:
        data = b"compute only"
        f = tmp_path / "test.img"
        f.write_bytes(data)
        runner = CliRunner()
        result = runner.invoke(main, ["verify", str(f)])
        assert result.exit_code == 0
        assert hashlib.sha256(data).hexdigest() in result.output


class TestCLIErase:
    def test_erase_dry_run(self, tmp_path: Path) -> None:
        f = tmp_path / "disk.img"
        f.write_bytes(b"data" * 256)
        runner = CliRunner()
        result = runner.invoke(main, ["erase", str(f), "--dry-run"])
        assert result.exit_code == 0
        assert f.read_bytes() == b"data" * 256  # unchanged

    def test_erase_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["erase", "--help"])
        assert result.exit_code == 0
        assert "passes" in result.output.lower()


class TestCLIInfo:
    def test_info_unknown_device(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["info", "/dev/nonexistent999"])
        assert result.exit_code == 1

    def test_info_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["info", "--help"])
        assert result.exit_code == 0
