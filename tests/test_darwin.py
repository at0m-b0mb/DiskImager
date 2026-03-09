"""Tests for disktool.platform.darwin (macOS disk enumeration)."""

from __future__ import annotations

import plistlib
from unittest.mock import MagicMock, patch

import disktool.platform.darwin as darwin

# Fields every drive dict returned by list_physical_drives() must contain.
EXPECTED_DRIVE_FIELDS = (
    "index", "name", "path", "size_bytes", "size_gb",
    "model", "is_removable", "is_system", "partitions",
)


# ---------------------------------------------------------------------------
# Helpers – build minimal diskutil plist responses
# ---------------------------------------------------------------------------

def _make_list_plist(whole_disks: list[str], disk_entries: list[dict]) -> bytes:
    """Return a ``diskutil list -plist physical`` response as plist bytes."""
    return plistlib.dumps(
        {
            "AllDisks": whole_disks,
            "AllDisksAndPartitions": disk_entries,
            "VolumesFromDisks": [],
            "WholeDisks": whole_disks,
        }
    )


def _make_info_plist(
    disk_id: str,
    *,
    total_size: int = 256_060_514_304,
    media_name: str = "APPLE SSD",
    bus_protocol: str = "NVMe",
    removable: bool = False,
    boot_volume: bool = False,
) -> bytes:
    return plistlib.dumps(
        {
            "DeviceIdentifier": disk_id,
            "MediaName": media_name,
            "TotalSize": total_size,
            "BusProtocol": bus_protocol,
            "RemovableMedia": removable,
            "RemovableMediaOrExternalDevice": removable,
            "Virtual": False,
            "SystemImage": False,
            "BootVolume": boot_volume,
        }
    )


def _make_disk_list_plist(disk_id: str, partitions: list[dict]) -> bytes:
    """Return a ``diskutil list -plist disk0`` response as plist bytes."""
    return plistlib.dumps(
        {
            "AllDisks": [disk_id] + [p["DeviceIdentifier"] for p in partitions],
            "AllDisksAndPartitions": [
                {
                    "DeviceIdentifier": disk_id,
                    "Partitions": partitions,
                    "Size": 256_060_514_304,
                }
            ],
            "VolumesFromDisks": [],
            "WholeDisks": [disk_id],
        }
    )


# ---------------------------------------------------------------------------
# _diskutil argument-order tests
# ---------------------------------------------------------------------------

class TestDiskutilArgOrder:
    """Verify that -plist is placed directly after the verb, not at the end."""

    def test_info_plist_flag_position(self) -> None:
        """`_diskutil('info', 'disk0')` must call `diskutil info -plist disk0`."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = _make_info_plist("disk0").decode()

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            darwin._diskutil("info", "disk0")

        called_args = mock_run.call_args[0][0]
        assert called_args == ["diskutil", "info", "-plist", "disk0"], (
            f"Expected ['diskutil', 'info', '-plist', 'disk0'], got {called_args}"
        )

    def test_list_plist_flag_position(self) -> None:
        """`_diskutil('list', 'physical')` must call `diskutil list -plist physical`."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = _make_list_plist([], []).decode()

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            darwin._diskutil("list", "physical")

        called_args = mock_run.call_args[0][0]
        assert called_args == ["diskutil", "list", "-plist", "physical"], (
            f"Expected ['diskutil', 'list', '-plist', 'physical'], got {called_args}"
        )

    def test_empty_args_returns_none(self) -> None:
        assert darwin._diskutil() is None

    def test_nonzero_returncode_returns_none(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            assert darwin._diskutil("info", "disk0") is None

    def test_exception_returns_none(self) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError("diskutil not found")):
            assert darwin._diskutil("info", "disk0") is None


# ---------------------------------------------------------------------------
# list_physical_drives integration test (fully mocked)
# ---------------------------------------------------------------------------

class TestListPhysicalDrives:
    def _subprocess_side_effect(self, *_args, **_kwargs) -> MagicMock:
        """Dispatch mock plist responses based on the command args."""
        cmd: list[str] = _args[0]
        # cmd format after fix: ["diskutil", <verb>, "-plist", *rest]
        verb = cmd[1] if len(cmd) > 1 else ""
        rest = cmd[3:] if len(cmd) > 3 else []
        target = rest[0] if rest else None

        mock_result = MagicMock()
        mock_result.returncode = 0

        if verb == "list" and target == "physical":
            mock_result.stdout = _make_list_plist(
                ["disk0", "disk1"],
                [
                    {"DeviceIdentifier": "disk0", "Partitions": [], "Size": 256_060_514_304},
                    {"DeviceIdentifier": "disk1", "Partitions": [], "Size": 32_000_000_000},
                ],
            ).decode()
        elif verb == "info" and target == "disk0":
            mock_result.stdout = _make_info_plist(
                "disk0", total_size=256_060_514_304, media_name="APPLE SSD", boot_volume=True
            ).decode()
        elif verb == "info" and target == "disk1":
            mock_result.stdout = _make_info_plist(
                "disk1", total_size=32_000_000_000, media_name="USB Drive", removable=True
            ).decode()
        elif verb == "list" and target == "disk0":
            mock_result.stdout = _make_disk_list_plist(
                "disk0",
                [
                    {"DeviceIdentifier": "disk0s1", "Size": 209_715_200, "MountPoint": "/boot/efi", "Content": "EFI"},
                    {"DeviceIdentifier": "disk0s2", "Size": 255_850_799_104, "MountPoint": "/", "Content": "Apple_APFS"},
                ],
            ).decode()
        elif verb == "list" and target == "disk1":
            mock_result.stdout = _make_disk_list_plist("disk1", []).decode()
        else:
            mock_result.returncode = 1
            mock_result.stdout = ""

        return mock_result

    def test_returns_two_drives(self) -> None:
        with patch("subprocess.run", side_effect=self._subprocess_side_effect):
            drives = darwin.list_physical_drives()
        assert len(drives) == 2

    def test_drive_fields_present(self) -> None:
        with patch("subprocess.run", side_effect=self._subprocess_side_effect):
            drives = darwin.list_physical_drives()
        for drive in drives:
            for field in EXPECTED_DRIVE_FIELDS:
                assert field in drive, f"Missing field '{field}' in {drive}"

    def test_first_drive_is_internal_system(self) -> None:
        with patch("subprocess.run", side_effect=self._subprocess_side_effect):
            drives = darwin.list_physical_drives()
        disk0 = drives[0]
        assert disk0["name"] == "disk0"
        assert disk0["path"] == "/dev/disk0"
        assert disk0["model"] == "APPLE SSD"
        assert disk0["is_system"] is True
        assert disk0["is_removable"] is False

    def test_second_drive_is_removable(self) -> None:
        with patch("subprocess.run", side_effect=self._subprocess_side_effect):
            drives = darwin.list_physical_drives()
        disk1 = drives[1]
        assert disk1["name"] == "disk1"
        assert disk1["is_removable"] is True
        assert disk1["is_system"] is False

    def test_partitions_parsed(self) -> None:
        with patch("subprocess.run", side_effect=self._subprocess_side_effect):
            drives = darwin.list_physical_drives()
        parts = drives[0]["partitions"]
        assert len(parts) == 2
        assert parts[0]["name"] == "disk0s1"
        assert parts[0]["mountpoint"] == "/boot/efi"
        assert parts[1]["name"] == "disk0s2"
        assert parts[1]["mountpoint"] == "/"

    def test_empty_list_when_diskutil_fails(self) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError("no diskutil")):
            drives = darwin.list_physical_drives()
        assert drives == []
