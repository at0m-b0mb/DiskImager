"""Disk enumeration – wraps platform-specific logic into a unified interface."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_drives() -> list[dict[str, Any]]:
    """Return a list of physical drives on the current platform.

    Each entry contains:
        index       – sequential integer ID
        name        – OS device name (e.g. 'sda', 'PhysicalDrive0')
        path        – full device path (e.g. '/dev/sda' on Linux, '.\\PhysicalDrive0' on Windows)
        size_bytes  – total size in bytes
        size_gb     – total size in GB (rounded to 2 decimals)
        model       – hardware model string
        is_removable – True for USB/SD/external devices
        is_system   – True if the disk contains an OS mount point
        partitions  – list of partition dicts (name, path, size_*, mountpoint)
    """
    try:
        from disktool.platform import list_physical_drives  # type: ignore[import]

        drives = list_physical_drives()
    except Exception as exc:
        logger.warning("Platform drive enumeration failed: %s", exc)
        drives = []

    if not drives:
        # Fall back to psutil-based enumeration (less detailed but cross-platform)
        drives = _psutil_fallback()

    return drives


def _psutil_fallback() -> list[dict[str, Any]]:
    """Minimal fallback using psutil – does not detect physical disks directly."""
    import psutil

    seen_devices: set[str] = set()
    partitions: list[dict[str, Any]] = []

    for part in psutil.disk_partitions(all=False):
        device = part.device
        if device in seen_devices:
            continue
        seen_devices.add(device)
        try:
            usage = psutil.disk_usage(part.mountpoint)
            total_bytes = usage.total
        except PermissionError:
            total_bytes = 0

        partitions.append(
            {
                "name": device.lstrip("/dev/").lstrip("\\\\.\\"),
                "path": device,
                "size_bytes": total_bytes,
                "size_gb": round(total_bytes / 1_073_741_824, 2),
                "mountpoint": part.mountpoint,
                "filesystem": part.fstype,
            }
        )

    if partitions:
        return [
            {
                "index": 0,
                "name": "disk0",
                "path": partitions[0]["path"],
                "size_bytes": partitions[0]["size_bytes"],
                "size_gb": partitions[0]["size_gb"],
                "model": "Unknown",
                "is_removable": False,
                "is_system": True,
                "partitions": partitions,
            }
        ]
    return []


def format_size(size_bytes: int) -> str:
    """Human-readable size string."""
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:6.1f} {unit}"
        size_bytes /= 1024.0  # type: ignore[assignment]
    return f"{size_bytes:.1f} EB"
