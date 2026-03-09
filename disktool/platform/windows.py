"""Windows-specific disk enumeration using WMI / SetupDi APIs via pywin32."""

from __future__ import annotations

import re
import subprocess
from typing import Any


def _wmic(*args: str) -> str:
    """Run wmic and return stdout."""
    try:
        result = subprocess.run(
            ["wmic", *args],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout
    except Exception:
        return ""


def _parse_wmic_list(output: str) -> list[dict[str, str]]:
    """Parse WMIC /FORMAT:LIST output into a list of dicts."""
    items: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line:
            if current:
                items.append(current)
                current = {}
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            current[key.strip()] = value.strip()
    if current:
        items.append(current)
    return items


def _powershell(script: str) -> str:
    """Run a PowerShell command and return stdout."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout
    except Exception:
        return ""


def _get_removable_flags() -> dict[str, bool]:
    """Use PowerShell to get removable flags for physical drives."""
    script = (
        "Get-Disk | Select-Object Number, BusType | "
        "ConvertTo-Csv -NoTypeInformation"
    )
    output = _powershell(script)
    flags: dict[str, bool] = {}
    lines = [l.strip().strip('"') for l in output.splitlines() if l.strip()]
    if len(lines) < 2:
        return flags
    # header is: "Number","BusType"
    for line in lines[1:]:
        parts = [p.strip().strip('"') for p in line.split(",")]
        if len(parts) >= 2:
            number, bus_type = parts[0], parts[1]
            flags[number] = bus_type.upper() in ("USB", "SD", "MMC")
    return flags


def _get_system_disk_number() -> str:
    """Return the disk number that contains the Windows system drive."""
    script = (
        "$win = (Get-Partition | Where-Object { $_.DriveLetter -eq "
        "[System.IO.Path]::GetPathRoot($env:SystemRoot)[0] }); "
        "if ($win) { $win.DiskNumber } else { '' }"
    )
    return _powershell(script).strip()


def _get_partitions(disk_number: str) -> list[dict[str, Any]]:
    script = (
        f"Get-Partition -DiskNumber {disk_number} | "
        "Select-Object PartitionNumber, Size, DriveLetter, Type | "
        "ConvertTo-Csv -NoTypeInformation"
    )
    output = _powershell(script)
    partitions: list[dict[str, Any]] = []
    lines = [l.strip() for l in output.splitlines() if l.strip()]
    if len(lines) < 2:
        return partitions
    for line in lines[1:]:
        parts = [p.strip().strip('"') for p in line.split(",")]
        if len(parts) < 4:
            continue
        part_num, size_str, drive_letter, ptype = parts[:4]
        try:
            size_bytes = int(size_str)
        except ValueError:
            size_bytes = 0
        mountpoint = f"{drive_letter}:\\" if drive_letter and drive_letter.strip() else ""
        partitions.append(
            {
                "name": f"Partition {part_num}",
                "path": f"\\\\.\\PhysicalDrive{disk_number}",
                "size_bytes": size_bytes,
                "size_gb": round(size_bytes / 1_073_741_824, 2),
                "mountpoint": mountpoint,
                "type": ptype,
            }
        )
    return partitions


def is_removable(disk_number: str) -> bool:
    flags = _get_removable_flags()
    return flags.get(disk_number, False)


def is_system_disk(disk_number: str) -> bool:
    sys_num = _get_system_disk_number()
    return disk_number == sys_num


def list_physical_drives() -> list[dict[str, Any]]:
    """Enumerate physical drives on Windows using WMI/PowerShell."""
    output = _wmic("diskdrive", "list", "/FORMAT:LIST")
    wmic_drives = _parse_wmic_list(output)

    drives: list[dict[str, Any]] = []
    for item in wmic_drives:
        device_id = item.get("DeviceID", "")  # e.g. \\.\PHYSICALDRIVE0
        index_match = re.search(r"(\d+)$", device_id)
        if not index_match:
            continue
        disk_number = index_match.group(1)
        idx = int(disk_number)
        model = item.get("Model", device_id)
        try:
            size_bytes = int(item.get("Size", "0"))
        except ValueError:
            size_bytes = 0

        drives.append(
            {
                "index": idx,
                "name": f"PhysicalDrive{disk_number}",
                "path": f"\\\\.\\PhysicalDrive{disk_number}",
                "size_bytes": size_bytes,
                "size_gb": round(size_bytes / 1_073_741_824, 2),
                "model": model,
                "is_removable": is_removable(disk_number),
                "is_system": is_system_disk(disk_number),
                "partitions": _get_partitions(disk_number),
            }
        )
    return drives
