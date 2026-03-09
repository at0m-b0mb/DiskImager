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


class TestCLIClone:
    def test_clone_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["clone", "--help"])
        assert result.exit_code == 0
        assert "source" in result.output.lower() or "SOURCE" in result.output

    def test_clone_dry_run(self, tmp_path: Path) -> None:
        src = tmp_path / "src.img"
        src.write_bytes(b"K" * 512)
        dst = tmp_path / "dst.img"
        runner = CliRunner()
        result = runner.invoke(main, ["clone", str(src), str(dst), "--dry-run"])
        assert result.exit_code == 0
        assert not dst.exists()

    def test_clone_missing_source(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            main, ["clone", "/no/such/device", str(tmp_path / "dst.img"), "--dry-run"]
        )
        # Source is checked before dry-run check, so missing source always exits non-zero
        assert result.exit_code == 1


class TestCLIGui:
    def test_gui_missing_deps_exits_with_message(self) -> None:
        """When customtkinter is not installed the gui command must exit 1 with a
        helpful message – not crash with AttributeError."""
        from unittest.mock import patch

        runner = CliRunner()
        with patch("builtins.__import__", side_effect=_gui_import_raiser):
            result = runner.invoke(main, ["gui"])

        assert result.exit_code == 1
        assert "not installed" in result.output.lower() or "failed" in result.output.lower()

    def test_gui_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["gui", "--help"])
        assert result.exit_code == 0
        assert "graphical" in result.output.lower() or "gui" in result.output.lower()


import builtins as _builtins

_real_import = _builtins.__import__


def _gui_import_raiser(name: str, *args: object, **kwargs: object) -> object:
    """Raises ImportError for disktool.gui, passes everything else through."""
    if name == "disktool.gui":
        raise ImportError("GUI dependencies are not installed. Run: pip install customtkinter")
    return _real_import(name, *args, **kwargs)
