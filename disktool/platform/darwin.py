"""macOS-specific disk enumeration using diskutil and IOKit (via subprocess)."""

from __future__ import annotations

import re
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


def _apfs_physical_store(container_ref: str) -> str | None:
    """Return the physical whole-disk identifier backing an APFS container.

    Runs ``diskutil apfs list -plist`` to find which physical partition
    (e.g. ``disk0s2``) backs *container_ref* (e.g. ``disk3``), then strips
    the partition suffix to return the physical whole-disk name
    (e.g. ``disk0``).

    Returns ``None`` if the lookup fails or the container is not found.
    """
    try:
        import plistlib

        result = subprocess.run(
            ["diskutil", "apfs", "list", "-plist"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        data = plistlib.loads(result.stdout.encode())
    except Exception:
        return None

    for container in data.get("Containers", []):
        if container.get("ContainerReference") != container_ref:
            continue
        # Prefer the single "DesignatedPhysicalStore" key when present
        store = container.get("DesignatedPhysicalStore", "")
        if not store:
            # Fall back to the first entry in the PhysicalStores list
            stores = container.get("PhysicalStores", [])
            if stores:
                store = stores[0].get("DeviceIdentifier", "")
        if store:
            # e.g. "disk0s2" → "disk0"
            m = re.match(r"(disk\d+)s\d+", store)
            if m:
                return m.group(1)
    return None


def _get_boot_whole_disk() -> str | None:
    """Return the whole-disk identifier (e.g. ``disk0``) that contains ``/``.

    Works for both traditional partition layouts (e.g. root on ``disk0s2``
    → strips to ``disk0``) **and** modern macOS APFS layouts where the root
    volume lives on a synthesised APFS container disk (e.g. ``disk3s1s1`` →
    strips to ``disk3`` → APFS lookup → physical store ``disk0s2`` →
    ``disk0``).

    Returns ``None`` if the boot disk cannot be determined.
    """
    # 1. Ask diskutil about the volume mounted at "/"
    info = _diskutil("info", "/")
    if not info:
        return None
    dev_id = info.get("DeviceIdentifier", "")  # e.g. "disk3s1s1" or "disk0s2"
    if not dev_id:
        return None

    # 2. Get the set of known physical whole disks
    list_data = _diskutil_list()
    whole_disks: set[str] = set(list_data.get("WholeDisks", [])) if list_data else set()

    # 3. Walk up by stripping trailing "sN" suffixes until we hit a whole disk
    #    e.g. "disk3s1s1" → "disk3s1" → "disk3"  (may not be in whole_disks)
    #         "disk0s2"   → "disk0"               (in whole_disks → return)
    candidate = dev_id
    while True:
        if candidate in whole_disks:
            return candidate
        m = re.match(r"(.+)s\d+$", candidate)
        if not m:
            break
        candidate = m.group(1)

    # 4. candidate is a virtual APFS disk (e.g. "disk3") – look it up in the
    #    APFS container list to find the backing physical partition → whole disk.
    if candidate:
        physical = _apfs_physical_store(candidate)
        if physical and physical in whole_disks:
            return physical

    return None


def is_system_disk(disk_id: str) -> bool:
    """Return True if the disk contains the boot volume."""
    info = _diskutil_info(disk_id)
    if not info:
        return False
    # Legacy: some macOS / diskutil versions set these fields directly on the disk
    if info.get("SystemImage") or info.get("BootVolume"):
        return True
    # Modern macOS APFS: trace the root volume back to its physical whole disk
    return _get_boot_whole_disk() == disk_id


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

    # Determine the boot disk once up-front to avoid one subprocess call per drive
    boot_disk = _get_boot_whole_disk()

    for idx, disk_id in enumerate(disk_list):
        info = _diskutil_info(disk_id)
        if not info:
            continue
        size_bytes = info.get("TotalSize", 0)
        model = info.get("MediaName", disk_id)

        # A disk is the system disk if diskutil reports it as such (legacy fields)
        # OR if it is the physical disk that backs the root volume.
        system = bool(
            info.get("SystemImage")
            or info.get("BootVolume")
            or (boot_disk is not None and boot_disk == disk_id)
        )

        drives.append(
            {
                "index": idx,
                "name": disk_id,
                "path": f"/dev/{disk_id}",
                "size_bytes": size_bytes,
                "size_gb": round(size_bytes / 1_073_741_824, 2),
                "model": model,
                "is_removable": is_removable(disk_id),
                "is_system": system,
                "partitions": _get_partitions(disk_id),
            }
        )
    return drives
