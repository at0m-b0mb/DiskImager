"""Linux-specific disk enumeration using /sys and /proc."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any


def _read_sys(path: str) -> str:
    """Read a sysfs file and return stripped text, or empty string on error."""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _block_devices() -> list[str]:
    """Return names of top-level block devices (e.g. sda, nvme0n1, mmcblk0)."""
    block_dir = Path("/sys/block")
    if not block_dir.exists():
        return []
    devices = []
    for entry in sorted(block_dir.iterdir()):
        name = entry.name
        # Skip loop, ram, dm- devices
        if re.match(r"^(loop|ram|dm-|sr|fd)", name):
            continue
        devices.append(name)
    return devices


def _get_size_bytes(name: str) -> int:
    """Return size in bytes for a block device."""
    size_str = _read_sys(f"/sys/block/{name}/size")
    try:
        # 'size' is in 512-byte sectors
        return int(size_str) * 512
    except ValueError:
        return 0


def _get_model(name: str) -> str:
    """Return model string for a block device."""
    return _read_sys(f"/sys/block/{name}/device/model") or name


def _get_vendor(name: str) -> str:
    return _read_sys(f"/sys/block/{name}/device/vendor").strip()


def is_removable(name: str) -> bool:
    """Return True if the block device is removable (USB, SD card, etc.)."""
    removable = _read_sys(f"/sys/block/{name}/removable")
    return removable == "1"


def is_system_disk(name: str) -> bool:
    """Return True if the device contains a mounted system partition (/, /boot, etc.)."""
    system_mounts = {"/", "/boot", "/boot/efi", "/usr", "/var"}
    try:
        with open("/proc/mounts", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) < 2:
                    continue
                device, mountpoint = parts[0], parts[1]
                if name in device and mountpoint in system_mounts:
                    return True
    except OSError:
        pass
    return False


def _get_partitions(name: str) -> list[dict[str, Any]]:
    """Return partition list for a block device."""
    partitions: list[dict[str, Any]] = []
    block_dir = Path(f"/sys/block/{name}")
    if not block_dir.exists():
        return partitions

    for entry in sorted(block_dir.iterdir()):
        if not entry.name.startswith(name):
            continue
        part_name = entry.name
        size_str = _read_sys(f"/sys/block/{name}/{part_name}/size")
        try:
            size = int(size_str) * 512
        except ValueError:
            size = 0

        # Find mount point
        mountpoint = ""
        try:
            with open("/proc/mounts", encoding="utf-8") as fh:
                for line in fh:
                    ps = line.split()
                    if len(ps) >= 2 and part_name in ps[0]:
                        mountpoint = ps[1]
                        break
        except OSError:
            pass

        partitions.append(
            {
                "name": part_name,
                "path": f"/dev/{part_name}",
                "size_bytes": size,
                "size_gb": round(size / 1_073_741_824, 2),
                "mountpoint": mountpoint,
            }
        )
    return partitions


def list_physical_drives() -> list[dict[str, Any]]:
    """Enumerate physical drives on Linux and return a structured list."""
    drives: list[dict[str, Any]] = []
    for idx, name in enumerate(_block_devices()):
        size_bytes = _get_size_bytes(name)
        model = _get_model(name)
        vendor = _get_vendor(name)
        if vendor and vendor.lower() not in model.lower():
            model = f"{vendor} {model}".strip()

        drives.append(
            {
                "index": idx,
                "name": name,
                "path": f"/dev/{name}",
                "size_bytes": size_bytes,
                "size_gb": round(size_bytes / 1_073_741_824, 2),
                "model": model,
                "is_removable": is_removable(name),
                "is_system": is_system_disk(name),
                "partitions": _get_partitions(name),
            }
        )
    return drives
