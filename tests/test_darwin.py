"""Tests for disktool.platform.darwin (macOS disk enumeration)."""

from __future__ import annotations

import re
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


def _make_apfs_list_plist(
    container_ref: str,
    *,
    designated_store: str = "",
    physical_stores: list[str] | None = None,
) -> bytes:
    """Return a ``diskutil apfs list -plist`` response as plist bytes."""
    container: dict = {"ContainerReference": container_ref}
    if designated_store:
        container["DesignatedPhysicalStore"] = designated_store
    if physical_stores is not None:
        container["PhysicalStores"] = [
            {"DeviceIdentifier": s} for s in physical_stores
        ]
    return plistlib.dumps({"Containers": [container]})


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
# _apfs_physical_store tests
# ---------------------------------------------------------------------------

class TestApfsPhysicalStore:
    """Tests for _apfs_physical_store (maps APFS container → physical disk)."""

    def test_found_via_designated_store(self) -> None:
        """Finds physical disk using DesignatedPhysicalStore."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = _make_apfs_list_plist(
            "disk3", designated_store="disk0s2"
        ).decode()
        with patch("subprocess.run", return_value=mock_result):
            assert darwin._apfs_physical_store("disk3") == "disk0"

    def test_found_via_physical_stores_list(self) -> None:
        """Falls back to PhysicalStores list when DesignatedPhysicalStore is absent."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = _make_apfs_list_plist(
            "disk3", physical_stores=["disk0s2"]
        ).decode()
        with patch("subprocess.run", return_value=mock_result):
            assert darwin._apfs_physical_store("disk3") == "disk0"

    def test_container_not_found_returns_none(self) -> None:
        """Returns None when the requested container reference is not in the list."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = _make_apfs_list_plist("disk5", designated_store="disk1s2").decode()
        with patch("subprocess.run", return_value=mock_result):
            assert darwin._apfs_physical_store("disk3") is None

    def test_diskutil_failure_returns_none(self) -> None:
        """Returns None when diskutil apfs list fails."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert darwin._apfs_physical_store("disk3") is None

    def test_nonzero_returncode_returns_none(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            assert darwin._apfs_physical_store("disk3") is None


# ---------------------------------------------------------------------------
# _get_boot_whole_disk tests
# ---------------------------------------------------------------------------

class TestGetBootWholeDisk:
    """Tests for _get_boot_whole_disk (find physical disk that contains /)."""

    def _make_run(self, root_dev_id: str, whole_disks: list[str], apfs_plist: bytes | None = None) -> object:
        """Return a subprocess.run side_effect covering the three calls made by
        _get_boot_whole_disk: ``diskutil info /``, ``diskutil list physical``,
        and optionally ``diskutil apfs list -plist``."""
        info_plist = plistlib.dumps({"DeviceIdentifier": root_dev_id}).decode()
        list_plist = _make_list_plist(
            whole_disks,
            [{"DeviceIdentifier": d, "Partitions": [], "Size": 0} for d in whole_disks],
        ).decode()

        def side_effect(*_args: object, **_kwargs: object) -> MagicMock:
            cmd: list[str] = _args[0]  # type: ignore[index]
            result = MagicMock()
            result.returncode = 0
            # diskutil info -plist /
            if cmd == ["diskutil", "info", "-plist", "/"]:
                result.stdout = info_plist
            # diskutil list -plist physical
            elif cmd == ["diskutil", "list", "-plist", "physical"]:
                result.stdout = list_plist
            # diskutil apfs list -plist
            elif cmd == ["diskutil", "apfs", "list", "-plist"] and apfs_plist is not None:
                result.stdout = apfs_plist.decode()
            else:
                result.returncode = 1
                result.stdout = ""
            return result

        return side_effect

    def test_simple_partition_layout(self) -> None:
        """Root on disk0s2 (Intel / non-APFS layout) → strips to disk0."""
        side_effect = self._make_run("disk0s2", ["disk0", "disk1"])
        with patch("subprocess.run", side_effect=side_effect):
            assert darwin._get_boot_whole_disk() == "disk0"

    def test_apfs_layout_apple_silicon(self) -> None:
        """Root on disk3s1s1 (Apple Silicon APFS) → APFS lookup → disk0."""
        apfs_plist = _make_apfs_list_plist("disk3", designated_store="disk0s2")
        side_effect = self._make_run("disk3s1s1", ["disk0", "disk4"], apfs_plist)
        with patch("subprocess.run", side_effect=side_effect):
            assert darwin._get_boot_whole_disk() == "disk0"

    def test_whole_disk_directly_in_list(self) -> None:
        """Root DeviceIdentifier is already a whole disk (unusual but valid)."""
        side_effect = self._make_run("disk0", ["disk0"])
        with patch("subprocess.run", side_effect=side_effect):
            assert darwin._get_boot_whole_disk() == "disk0"

    def test_diskutil_info_failure_returns_none(self) -> None:
        """Returns None when diskutil info / fails."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert darwin._get_boot_whole_disk() is None

    def test_apfs_lookup_fails_returns_none(self) -> None:
        """Returns None when root is on a virtual disk and APFS lookup also fails."""
        # Root is on disk3s1s1, physical list has disk0 and disk4.
        # APFS lookup returns non-zero → _apfs_physical_store returns None.
        def side_effect(*_args: object, **_kwargs: object) -> MagicMock:
            cmd: list[str] = _args[0]  # type: ignore[index]
            result = MagicMock()
            if cmd == ["diskutil", "info", "-plist", "/"]:
                result.returncode = 0
                result.stdout = plistlib.dumps({"DeviceIdentifier": "disk3s1s1"}).decode()
            elif cmd == ["diskutil", "list", "-plist", "physical"]:
                result.returncode = 0
                result.stdout = _make_list_plist(
                    ["disk0", "disk4"],
                    [
                        {"DeviceIdentifier": "disk0", "Partitions": [], "Size": 0},
                        {"DeviceIdentifier": "disk4", "Partitions": [], "Size": 0},
                    ],
                ).decode()
            else:
                result.returncode = 1
                result.stdout = ""
            return result

        with patch("subprocess.run", side_effect=side_effect):
            assert darwin._get_boot_whole_disk() is None


# ---------------------------------------------------------------------------
# is_system_disk – modern macOS (APFS, no BootVolume on whole disk)
# ---------------------------------------------------------------------------

class TestIsSystemDiskModernMacOS:
    """is_system_disk must identify the boot disk even when diskutil info does
    NOT set BootVolume / SystemImage on the physical whole-disk record (the
    real behaviour on macOS 12+ with APFS)."""

    def _make_run(self, disk_id: str, *, apfs_root: str, apfs_store: str) -> object:
        """Build a side_effect that simulates a modern macOS APFS setup where
        *disk_id* is the physical boot disk but its info plist has no
        BootVolume/SystemImage flags."""
        # Info for the physical disk – no BootVolume, no SystemImage
        disk_info = plistlib.dumps({
            "DeviceIdentifier": disk_id,
            "MediaName": "APPLE SSD",
            "TotalSize": 1_000_555_581_440,
            "BusProtocol": "Apple Fabric",
            "RemovableMedia": False,
            "RemovableMediaOrExternalDevice": False,
            "Virtual": False,
            "SystemImage": False,
            "BootVolume": False,
        }).decode()
        root_info = plistlib.dumps({"DeviceIdentifier": apfs_root}).decode()
        # Derive container identifier: "disk3s1s1" → "disk3"
        m = re.match(r"(disk\d+)", apfs_root)
        container = m.group(1) if m else apfs_root

        apfs_plist = _make_apfs_list_plist(container, designated_store=apfs_store).decode()
        list_plist = _make_list_plist(
            [disk_id],
            [{"DeviceIdentifier": disk_id, "Partitions": [], "Size": 0}],
        ).decode()

        def side_effect(*_args: object, **_kwargs: object) -> MagicMock:
            cmd: list[str] = _args[0]  # type: ignore[index]
            result = MagicMock()
            result.returncode = 0
            if cmd == ["diskutil", "info", "-plist", disk_id]:
                result.stdout = disk_info
            elif cmd == ["diskutil", "info", "-plist", "/"]:
                result.stdout = root_info
            elif cmd == ["diskutil", "list", "-plist", "physical"]:
                result.stdout = list_plist
            elif cmd == ["diskutil", "apfs", "list", "-plist"]:
                result.stdout = apfs_plist
            else:
                result.returncode = 1
                result.stdout = ""
            return result

        return side_effect

    def test_boot_disk_identified_via_apfs(self) -> None:
        """disk0 is correctly flagged as the system disk when root is on
        disk3s1s1 (Apple Silicon APFS layout) and BootVolume is False."""
        side_effect = self._make_run("disk0", apfs_root="disk3s1s1", apfs_store="disk0s2")
        with patch("subprocess.run", side_effect=side_effect):
            assert darwin.is_system_disk("disk0") is True

    def test_non_boot_disk_not_flagged(self) -> None:
        """A second physical disk (disk4) is not flagged as system even though
        BootVolume is False (same as disk0's raw info)."""
        # Root is on disk0 chain; disk4 has no BootVolume either
        disk4_info = plistlib.dumps({
            "DeviceIdentifier": "disk4",
            "MediaName": "USB Drive",
            "TotalSize": 87_960_117_248,
            "BusProtocol": "USB",
            "RemovableMedia": True,
            "RemovableMediaOrExternalDevice": True,
            "Virtual": False,
            "SystemImage": False,
            "BootVolume": False,
        }).decode()
        root_info = plistlib.dumps({"DeviceIdentifier": "disk3s1s1"}).decode()
        list_plist = _make_list_plist(
            ["disk0", "disk4"],
            [
                {"DeviceIdentifier": "disk0", "Partitions": [], "Size": 0},
                {"DeviceIdentifier": "disk4", "Partitions": [], "Size": 0},
            ],
        ).decode()
        apfs_plist = _make_apfs_list_plist("disk3", designated_store="disk0s2").decode()

        def side_effect(*_args: object, **_kwargs: object) -> MagicMock:
            cmd: list[str] = _args[0]  # type: ignore[index]
            result = MagicMock()
            result.returncode = 0
            if cmd == ["diskutil", "info", "-plist", "disk4"]:
                result.stdout = disk4_info
            elif cmd == ["diskutil", "info", "-plist", "/"]:
                result.stdout = root_info
            elif cmd == ["diskutil", "list", "-plist", "physical"]:
                result.stdout = list_plist
            elif cmd == ["diskutil", "apfs", "list", "-plist"]:
                result.stdout = apfs_plist
            else:
                result.returncode = 1
                result.stdout = ""
            return result

        with patch("subprocess.run", side_effect=side_effect):
            assert darwin.is_system_disk("disk4") is False


# ---------------------------------------------------------------------------
# list_physical_drives integration test (fully mocked)
# ---------------------------------------------------------------------------

class TestListPhysicalDrives:
    def _subprocess_side_effect(self, *_args, **_kwargs) -> MagicMock:
        """Dispatch mock plist responses based on the command args.

        Covers both the standard _diskutil calls (["diskutil", verb, "-plist", *rest])
        and the direct apfs call (["diskutil", "apfs", "list", "-plist"]).
        """
        cmd: list[str] = _args[0]

        mock_result = MagicMock()
        mock_result.returncode = 0

        # APFS list (direct call – different arg order, no -plist after verb)
        if cmd == ["diskutil", "apfs", "list", "-plist"]:
            # In this fixture disk0 uses the legacy BootVolume path so no APFS lookup needed
            mock_result.returncode = 1
            mock_result.stdout = ""
            return mock_result

        # Standard _diskutil calls: ["diskutil", <verb>, "-plist", *rest]
        verb = cmd[1] if len(cmd) > 1 else ""
        rest = cmd[3:] if len(cmd) > 3 else []
        target = rest[0] if rest else None

        if verb == "list" and target == "physical":
            mock_result.stdout = _make_list_plist(
                ["disk0", "disk1"],
                [
                    {"DeviceIdentifier": "disk0", "Partitions": [], "Size": 256_060_514_304},
                    {"DeviceIdentifier": "disk1", "Partitions": [], "Size": 32_000_000_000},
                ],
            ).decode()
        elif verb == "info" and target == "/":
            # Simulate: root is on disk0s2 (simple layout) → strips to disk0
            mock_result.stdout = plistlib.dumps({"DeviceIdentifier": "disk0s2"}).decode()
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

    def test_apple_silicon_apfs_boot_detection(self) -> None:
        """list_physical_drives correctly marks disk0 as system when boot is
        detected via the APFS chain (disk3s1s1 → disk3 → disk0s2 → disk0),
        i.e. without relying on the legacy BootVolume / SystemImage flags."""
        list_plist = _make_list_plist(
            ["disk0", "disk4"],
            [
                {"DeviceIdentifier": "disk0", "Partitions": [], "Size": 1_000_555_581_440},
                {"DeviceIdentifier": "disk4", "Partitions": [], "Size": 87_960_117_248},
            ],
        ).decode()
        disk0_info = _make_info_plist(
            "disk0", total_size=1_000_555_581_440, media_name="APPLE SSD AP1024Z",
            boot_volume=False,  # no legacy flag – must be found via APFS
        ).decode()
        disk4_info = _make_info_plist(
            "disk4", total_size=87_960_117_248, media_name="Built In SDXC Reader",
            removable=True,
        ).decode()
        root_info = plistlib.dumps({"DeviceIdentifier": "disk3s1s1"}).decode()
        apfs_plist = _make_apfs_list_plist("disk3", designated_store="disk0s2").decode()

        def side_effect(*_args: object, **_kwargs: object) -> MagicMock:
            cmd: list[str] = _args[0]  # type: ignore[index]
            result = MagicMock()
            result.returncode = 0
            if cmd == ["diskutil", "apfs", "list", "-plist"]:
                result.stdout = apfs_plist
            elif cmd[:3] == ["diskutil", "info", "-plist"]:
                target = cmd[3] if len(cmd) > 3 else ""
                if target == "/":
                    result.stdout = root_info
                elif target == "disk0":
                    result.stdout = disk0_info
                elif target == "disk4":
                    result.stdout = disk4_info
                else:
                    result.returncode = 1
                    result.stdout = ""
            elif cmd[:3] == ["diskutil", "list", "-plist"]:
                target = cmd[3] if len(cmd) > 3 else ""
                if target == "physical":
                    result.stdout = list_plist
                elif target == "disk0":
                    result.stdout = _make_disk_list_plist("disk0", []).decode()
                elif target == "disk4":
                    result.stdout = _make_disk_list_plist("disk4", []).decode()
                else:
                    result.returncode = 1
                    result.stdout = ""
            else:
                result.returncode = 1
                result.stdout = ""
            return result

        with patch("subprocess.run", side_effect=side_effect):
            drives = darwin.list_physical_drives()

        assert len(drives) == 2
        disk0 = drives[0]
        disk4 = drives[1]
        assert disk0["name"] == "disk0"
        assert disk0["is_system"] is True, "disk0 should be the system disk"
        assert disk4["name"] == "disk4"
        assert disk4["is_system"] is False, "disk4 (USB) should not be the system disk"
