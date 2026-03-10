"""macOS-specific disk enumeration using diskutil and IOKit (via subprocess)."""

from __future__ import annotations

import subprocess
from typing import Any


def _diskutil(*args: str) -> dict[str, Any] | None:
    """Run diskutil and return parsed plist output as a dict.

    The ``-plist`` flag must appear immediately after the verb (subcommand)
    and before any positional arguments.  Placing it at the end causes
    diskutil to ignore the flag and return plain text, which makes
    ``plistlib.loads`` raise an exception and the function return ``None``.
    """
    if not args:
        return None
    try:
        # Correct order: diskutil <verb> -plist [args…]
        result = subprocess.run(
            ["diskutil", args[0], "-plist", *args[1:]],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        import plistlib

        return plistlib.loads(result.stdout.encode())
    except Exception:
        return None


def _diskutil_list() -> dict[str, Any] | None:
    """Run ``diskutil list -plist physical`` and return parsed plist."""
    return _diskutil("list", "physical")


def _diskutil_info(disk: str) -> dict[str, Any] | None:
    return _diskutil("info", disk)


def is_removable(disk_id: str) -> bool:
    """Return True if the disk is removable (USB, SD, etc.)."""
    info = _diskutil_info(disk_id)
    if not info:
        return False
    return bool(
        info.get("RemovableMedia")
        or info.get("RemovableMediaOrExternalDevice")
        or info.get("Virtual")
        or "USB" in str(info.get("BusProtocol", ""))
    )


def is_system_disk(disk_id: str) -> bool:
    """Return True if the disk contains the boot volume."""
    info = _diskutil_info(disk_id)
    if not info:
        return False
    return bool(info.get("SystemImage") or info.get("BootVolume"))


def _get_partitions(disk_id: str) -> list[dict[str, Any]]:
    """Return partitions for *disk_id* using ``diskutil list -plist``."""
    data = _diskutil("list", disk_id)
    if not data:
        return []
    partitions: list[dict[str, Any]] = []
    for disk_entry in data.get("AllDisksAndPartitions", []):
        if disk_entry.get("DeviceIdentifier") != disk_id:
            continue
        for part in disk_entry.get("Partitions", []):
            part_id = part.get("DeviceIdentifier", "")
            size_bytes = part.get("Size", 0)
            partitions.append(
                {
                    "name": part_id,
                    "path": f"/dev/{part_id}",
                    "size_bytes": size_bytes,
                    "size_gb": round(size_bytes / 1_073_741_824, 2),
                    "mountpoint": part.get("MountPoint", ""),
                    "filesystem": part.get("Content", ""),
                }
            )
    return partitions


def list_physical_drives() -> list[dict[str, Any]]:
    """Enumerate physical drives on macOS using diskutil."""
    drives: list[dict[str, Any]] = []
    data = _diskutil_list()
    if not data:
        return drives

    disk_list = data.get("WholeDisks") or []
    for idx, disk_id in enumerate(disk_list):
        info = _diskutil_info(disk_id)
        if not info:
            continue
        size_bytes = info.get("TotalSize", 0)
        model = info.get("MediaName", disk_id)
        drives.append(
            {
                "index": idx,
                "name": disk_id,
                "path": f"/dev/{disk_id}",
                "size_bytes": size_bytes,
                "size_gb": round(size_bytes / 1_073_741_824, 2),
                "model": model,
                "is_removable": is_removable(disk_id),
                "is_system": is_system_disk(disk_id),
                "partitions": _get_partitions(disk_id),
            }
        )
    return drives
