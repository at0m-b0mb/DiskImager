"""Cross-platform partition table management.

Provides :func:`create_partition_table` which writes a fresh MBR or GPT
partition table to a block device, and :func:`add_partition` which appends a
partition to an existing table.  All OS-level work is delegated to:

* **macOS**  – ``diskutil partitionDisk`` / ``diskutil addPartition``
* **Linux**  – ``parted``
* **Windows** – ``diskpart`` (script-based)

Call :func:`list_partition_schemes` to see accepted scheme values.

Example::

    >>> from disktool.core.partition import create_partition_table, add_partition
    >>> create_partition_table("/dev/sdb", "gpt", dry_run=True)
    True
    >>> add_partition("/dev/sdb", size="100%", filesystem="fat32", dry_run=True)
    True
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from typing import Sequence

logger = logging.getLogger(__name__)

_SUBPROCESS_TIMEOUT = 120  # seconds

# ---------------------------------------------------------------------------
# Supported schemes
# ---------------------------------------------------------------------------

#: Canonical scheme names accepted by :func:`create_partition_table`.
SUPPORTED_SCHEMES: list[str] = ["mbr", "gpt"]


def list_partition_schemes() -> list[str]:
    """Return the supported partition-table scheme names."""
    return list(SUPPORTED_SCHEMES)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_partition_table(
    device: str,
    scheme: str,
    dry_run: bool = False,
) -> bool:
    """Create a new partition table on *device*.

    .. warning::
        **All existing partitions and data on** *device* **will be destroyed.**

    Args:
        device:   Block device path (e.g. ``/dev/sdb``, ``\\\\.\\PhysicalDrive1``).
        scheme:   ``'mbr'`` (DOS/MBR) or ``'gpt'`` (GUID Partition Table).
        dry_run:  Simulate without writing.

    Returns:
        ``True`` on success.

    Raises:
        ValueError: For unsupported scheme or platform.
        FileNotFoundError: If the required tool is not installed.
        OSError: If the tool returns a non-zero exit code.
    """
    scheme = scheme.lower().strip()
    if scheme not in SUPPORTED_SCHEMES:
        raise ValueError(
            f"Unsupported partition scheme {scheme!r}. "
            f"Supported: {', '.join(SUPPORTED_SCHEMES)}"
        )

    logger.info(
        "Create partition table: %s  scheme=%s  dry_run=%s", device, scheme, dry_run
    )

    if sys.platform == "darwin":
        return _create_darwin(device, scheme, dry_run)
    if sys.platform.startswith("linux"):
        return _create_linux(device, scheme, dry_run)
    if sys.platform == "win32":
        return _create_windows(device, scheme, dry_run)

    raise ValueError(f"Unsupported platform: {sys.platform}")


def add_partition(
    device: str,
    size: str = "100%",
    filesystem: str | None = None,
    label: str | None = None,
    dry_run: bool = False,
) -> bool:
    """Add a partition to an existing partition table on *device*.

    Args:
        device:     Block device path.
        size:       Partition size as a percentage (``"50%"``, ``"100%"``) or
                    a size with a unit (``"8G"``, ``"512M"``).
                    Use ``"100%"`` to fill the remaining space.
        filesystem: Optional hint for the partition type flag (e.g. ``"fat32"``,
                    ``"ext4"``).  The partition is **not** formatted – use
                    :func:`~disktool.core.format.format_disk` for that.
        label:      Partition name / label (supported on GPT and macOS).
        dry_run:    Simulate without writing.

    Returns:
        ``True`` on success.

    Raises:
        ValueError: For unsupported platform or invalid parameters.
        FileNotFoundError: If the required tool is not installed.
        OSError: If the tool returns a non-zero exit code.
    """
    logger.info(
        "Add partition: %s  size=%s  fs=%s  label=%s  dry_run=%s",
        device, size, filesystem, label, dry_run,
    )

    if sys.platform.startswith("linux"):
        return _add_partition_linux(device, size, filesystem, label, dry_run)
    if sys.platform == "darwin":
        return _add_partition_darwin(device, size, filesystem, label, dry_run)
    if sys.platform == "win32":
        return _add_partition_windows(device, size, filesystem, label, dry_run)

    raise ValueError(f"Unsupported platform: {sys.platform}")


# ---------------------------------------------------------------------------
# Internal – macOS
# ---------------------------------------------------------------------------

_DARWIN_SCHEME_MAP: dict[str, str] = {
    "mbr": "MBRFormat",
    "gpt": "GPTFormat",
}

_DARWIN_FS_MAP: dict[str, str] = {
    "fat32": "MS-DOS FAT32",
    "exfat": "ExFAT",
    "hfs+": "Journaled HFS+",
    "apfs": "APFS",
    "free": "Free Space",
}


def _create_darwin(device: str, scheme: str, dry_run: bool) -> bool:
    disk_fmt = _DARWIN_SCHEME_MAP[scheme]
    # partitionDisk with a single "Free Space" placeholder creates the table
    # without writing any partition data, leaving the disk blank.
    cmd: list[str] = [
        "diskutil", "partitionDisk", device, disk_fmt,
        "Free Space", "%noformat%", "100%",
    ]
    return _run_cmd(cmd, device, dry_run)


def _add_partition_darwin(
    device: str,
    size: str,
    filesystem: str | None,
    label: str | None,
    dry_run: bool,
) -> bool:
    fs_key = (filesystem or "").lower()
    fs = _DARWIN_FS_MAP.get(fs_key, "Free Space")
    part_name = label or "UNTITLED"
    cmd: list[str] = ["diskutil", "addPartition", device, fs, part_name, size]
    return _run_cmd(cmd, device, dry_run)


# ---------------------------------------------------------------------------
# Internal – Linux
# ---------------------------------------------------------------------------

_PARTED_SCHEME_MAP: dict[str, str] = {
    "mbr": "msdos",
    "gpt": "gpt",
}

_PARTED_FS_TYPE_MAP: dict[str, str] = {
    "fat32": "fat32",
    "exfat": "fat32",   # parted type hint; actual format done separately
    "ntfs": "ntfs",
    "ext4": "ext4",
    "ext3": "ext3",
    "ext2": "ext2",
    "btrfs": "btrfs",
    "linux-swap": "linux-swap",
    "xfs": "xfs",
}


def _create_linux(device: str, scheme: str, dry_run: bool) -> bool:
    parted_label = _PARTED_SCHEME_MAP[scheme]
    cmd: list[str] = ["parted", "-s", device, "mklabel", parted_label]
    return _run_cmd(cmd, device, dry_run)


def _add_partition_linux(
    device: str,
    size: str,
    filesystem: str | None,
    label: str | None,
    dry_run: bool,
) -> bool:
    fs_type = _PARTED_FS_TYPE_MAP.get((filesystem or "").lower(), "")
    name = label or "data"
    # parted mkpart <name> [fs-type] <start> <end>
    cmd: list[str] = ["parted", "-s", device, "mkpart", name]
    if fs_type:
        cmd.append(fs_type)
    cmd += ["0%", size if size.endswith("%") else size]
    return _run_cmd(cmd, device, dry_run)


# ---------------------------------------------------------------------------
# Internal – Windows
# ---------------------------------------------------------------------------

def _create_windows(device: str, scheme: str, dry_run: bool) -> bool:
    disk_num = _win_disk_num(device)
    script = f"select disk {disk_num}\nclean\nconvert {scheme}\nexit\n"
    return _run_diskpart(script, device, dry_run)


def _add_partition_windows(
    device: str,
    size: str,
    filesystem: str | None,
    label: str | None,
    dry_run: bool,
) -> bool:
    disk_num = _win_disk_num(device)
    size_mb = _parse_size_to_mb(size)
    cmd = f"select disk {disk_num}\ncreate partition primary"
    if size_mb is not None:
        cmd += f" size={size_mb}"
    cmd += "\nexit\n"
    return _run_diskpart(cmd, device, dry_run)


def _win_disk_num(device: str) -> str:
    """Extract trailing digits from a Windows physical drive path."""
    m = re.search(r"(\d+)$", device.rstrip("\\"))
    return m.group(1) if m else "0"


def _parse_size_to_mb(size: str) -> int | None:
    """Convert a size string (``'8G'``, ``'512M'``, ``'100%'``) to megabytes.

    Returns ``None`` for percentage strings (caller should omit the size
    argument to let ``diskpart`` use the full remaining space).
    """
    size = size.strip().upper()
    if size.endswith("%"):
        return None
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([KMGT]?)B?$", size)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2)
    factors: dict[str, float] = {"": 1.0, "K": 1.0 / 1024, "M": 1.0, "G": 1024.0, "T": 1_048_576.0}
    return max(1, int(val * factors.get(unit, 1.0)))


def _run_diskpart(script: str, device: str, dry_run: bool) -> bool:
    """Write *script* to a temp file and run ``diskpart /s <script>``."""
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(script)
        script_path = fh.name

    try:
        return _run_cmd(["diskpart", "/s", script_path], device, dry_run)
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Internal – subprocess runner
# ---------------------------------------------------------------------------

def _run_cmd(cmd: Sequence[str], device: str, dry_run: bool) -> bool:
    """Execute *cmd* unless *dry_run* is True.

    Raises:
        FileNotFoundError: If the executable is not found.
        OSError: If the command returns a non-zero exit code.
    """
    logger.debug("Partition command: %s", " ".join(str(a) for a in cmd))

    if dry_run:
        logger.info("[DRY RUN] Would run: %s", " ".join(str(a) for a in cmd))
        return True

    try:
        result = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
    except FileNotFoundError as exc:
        tool = cmd[0]
        raise FileNotFoundError(
            f"Partitioning tool not found: {tool!r}. "
            "Install the required package (e.g. parted, util-linux)."
        ) from exc

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()

    if stdout:
        logger.info("%s", stdout)
    if stderr:
        log = logger.debug if result.returncode == 0 else logger.error
        log("%s", stderr)

    if result.returncode != 0:
        raise OSError(
            f"Partition operation failed (exit {result.returncode}) for {device}: "
            f"{stderr or stdout or '(no output)'}"
        )

    logger.info("Partition operation complete on %s", device)
    return True
