"""Cross-platform disk formatting support.

Provides :func:`format_disk` which formats a block device or partition with
the requested file system.  All OS-level work is delegated to system utilities
that are present by default on each platform:

* **macOS**  – ``diskutil eraseVolume``
* **Linux**  – ``mkfs.<fs>`` family (``dosfstools``, ``e2fsprogs``, ``ntfs-3g``, …)
* **Windows** – PowerShell ``Format-Volume``

Call :func:`list_supported_filesystems` to obtain the list of file systems
accepted by :func:`format_disk` on the current platform.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from typing import Sequence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported file-system catalogue
# ---------------------------------------------------------------------------

#: Canonical lowercase name → human-readable label shown in the CLI.
_FS_LABELS: dict[str, str] = {
    "fat32": "FAT32",
    "exfat": "exFAT",
    "ntfs": "NTFS",
    "ext4": "ext4",
    "ext3": "ext3",
    "ext2": "ext2",
    "btrfs": "btrfs",
    "hfs+": "HFS+",
    "apfs": "APFS",
}

#: Which canonical names are available on each platform.
_PLATFORM_FS: dict[str, list[str]] = {
    "darwin": ["fat32", "exfat", "hfs+", "apfs"],
    "linux": ["fat32", "exfat", "ntfs", "ext4", "ext3", "ext2", "btrfs"],
    "win32": ["fat32", "exfat", "ntfs"],
}

#: Alternative spellings that map to a canonical name.
_ALIASES: dict[str, str] = {
    "fat": "fat32",
    "vfat": "fat32",
    "msdos": "fat32",
    "ms-dos": "fat32",
    "hfsplus": "hfs+",
    "hfs": "hfs+",
}

# Timeout (seconds) passed to every subprocess call.
_SUBPROCESS_TIMEOUT = 300  # 5 minutes is generous even for large disks


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def list_supported_filesystems() -> list[str]:
    """Return the canonical file-system names accepted on the current platform.

    The list is ordered from most common to least common.

    Example::

        >>> list_supported_filesystems()
        ['fat32', 'exfat', 'ntfs', 'ext4', 'ext3', 'ext2', 'btrfs']
    """
    platform_key = "win32" if sys.platform == "win32" else sys.platform
    return list(_PLATFORM_FS.get(platform_key, []))


def filesystem_label(name: str) -> str:
    """Return the human-readable label for *name* (e.g. ``'fat32'`` → ``'FAT32'``).

    Returns *name* unchanged when not found in the catalogue.
    """
    return _FS_LABELS.get(_normalise_fs(name), name)


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def format_disk(
    device: str,
    filesystem: str,
    label: str = "DISK",
    dry_run: bool = False,
) -> bool:
    """Format *device* with *filesystem*.

    Args:
        device:     Block device path (``/dev/disk4``, ``/dev/sdb``,
                    ``\\\\.\\PhysicalDrive1``, or a drive letter like ``E:``).
        filesystem: File-system name.  Case-insensitive; common aliases
                    (``fat``, ``vfat``, ``hfsplus``, …) are accepted.
                    Run :func:`list_supported_filesystems` for supported values.
        label:      Volume label written to the new file system.  Defaults to
                    ``"DISK"``.  Maximum length is enforced per file system.
        dry_run:    When ``True``, validate inputs and log the command that
                    *would* be run, without actually formatting anything.

    Returns:
        ``True`` on success.

    Raises:
        ValueError: For unsupported file-system names or unsupported platforms.
        FileNotFoundError: If the formatting utility is not installed.
        OSError: If the formatting utility returns a non-zero exit code.
    """
    fs = _normalise_fs(filesystem)
    supported = list_supported_filesystems()
    if fs not in supported:
        raise ValueError(
            f"Unsupported file system {filesystem!r} on {sys.platform}. "
            f"Supported: {', '.join(supported)}"
        )

    label = _sanitise_label(label, fs)
    logger.info("Format %s as %s (label=%r, dry_run=%s)", device, fs, label, dry_run)

    if sys.platform == "darwin":
        return _format_darwin(device, fs, label, dry_run)
    if sys.platform.startswith("linux"):
        return _format_linux(device, fs, label, dry_run)
    if sys.platform == "win32":
        return _format_windows(device, fs, label, dry_run)

    raise ValueError(f"Unsupported platform: {sys.platform}")


# ---------------------------------------------------------------------------
# Internal – normalisation helpers
# ---------------------------------------------------------------------------

def _normalise_fs(name: str) -> str:
    """Return the canonical lower-case file-system name for *name*."""
    lower = name.lower().strip()
    return _ALIASES.get(lower, lower)


def _sanitise_label(label: str, fs: str) -> str:
    """Trim *label* to the maximum length permitted by *fs*.

    Also strips characters that are invalid in volume labels.  Returns a
    non-empty string (falls back to ``"DISK"``).
    """
    # Strip characters that are broadly invalid across FAT/exFAT/NTFS/ext*
    label = re.sub(r'[\\/:*?"<>|]', "", label).strip()
    if not label:
        label = "DISK"
    limits = {"fat32": 11, "exfat": 15, "ntfs": 32, "hfs+": 27, "apfs": 255}
    max_len = limits.get(fs, 255)
    return label[:max_len]


# ---------------------------------------------------------------------------
# Internal – macOS
# ---------------------------------------------------------------------------

# diskutil eraseVolume expects specific fs type strings
_DARWIN_FS_MAP: dict[str, str] = {
    "fat32": "MS-DOS FAT32",
    "exfat": "ExFAT",
    "hfs+": "Journaled HFS+",
    "apfs": "APFS",
}


def _format_darwin(device: str, fs: str, label: str, dry_run: bool) -> bool:
    """Format *device* on macOS using ``diskutil eraseVolume``."""
    from disktool.core.imaging import _unmount_disk_darwin  # avoid circular import

    diskutil_fs = _DARWIN_FS_MAP.get(fs)
    if not diskutil_fs:
        raise ValueError(f"No diskutil mapping for file system {fs!r}")

    # FAT32 labels must be ALL-CAPS (diskutil requirement)
    if fs == "fat32":
        label = label.upper()

    # Normalise /dev/rdiskN → /dev/diskN for diskutil eraseVolume
    disk_node = re.sub(r"^/dev/r(disk\d+.*)", r"/dev/\1", device)

    cmd: list[str] = ["diskutil", "eraseVolume", diskutil_fs, label, disk_node]
    return _run_format_cmd(cmd, device, dry_run)


# ---------------------------------------------------------------------------
# Internal – Linux
# ---------------------------------------------------------------------------

_LINUX_CMD: dict[str, list[str]] = {
    "fat32": ["mkfs.fat", "-F", "32"],
    "exfat": ["mkfs.exfat"],
    "ntfs": ["mkfs.ntfs", "--fast"],
    "ext4": ["mkfs.ext4"],
    "ext3": ["mkfs.ext3"],
    "ext2": ["mkfs.ext2"],
    "btrfs": ["mkfs.btrfs", "--force"],
}

_LINUX_LABEL_FLAGS: dict[str, list[str]] = {
    "fat32": ["-n"],
    "exfat": ["-n"],
    "ntfs": ["-L"],
    "ext4": ["-L"],
    "ext3": ["-L"],
    "ext2": ["-L"],
    "btrfs": ["-L"],
}


def _format_linux(device: str, fs: str, label: str, dry_run: bool) -> bool:
    """Format *device* on Linux using the appropriate ``mkfs.*`` tool."""
    base_cmd = _LINUX_CMD.get(fs)
    if not base_cmd:
        raise ValueError(f"No mkfs mapping for file system {fs!r}")

    label_flags = _LINUX_LABEL_FLAGS.get(fs, [])
    cmd: list[str] = list(base_cmd) + label_flags + [label, device]
    return _run_format_cmd(cmd, device, dry_run)


# ---------------------------------------------------------------------------
# Internal – Windows
# ---------------------------------------------------------------------------

_WINDOWS_FS_MAP: dict[str, str] = {
    "fat32": "FAT32",
    "exfat": "exFAT",
    "ntfs": "NTFS",
}


def _format_windows(device: str, fs: str, label: str, dry_run: bool) -> bool:
    """Format *device* on Windows using PowerShell ``Format-Volume``."""
    ps_fs = _WINDOWS_FS_MAP.get(fs)
    if not ps_fs:
        raise ValueError(f"No Windows mapping for file system {fs!r}")

    # Accept both drive letters ("E:") and physical drive paths
    if re.match(r"^[A-Za-z]:?$", device.rstrip("\\")):
        drive_letter = device.rstrip(":\\").upper()
        target_arg = f"-DriveLetter {drive_letter}"
    else:
        # Fall back to drive letter extraction from a partition on this disk
        target_arg = f"-Path '{device}'"

    script = (
        f"Format-Volume {target_arg} "
        f"-FileSystem {ps_fs} "
        f"-NewFileSystemLabel '{label}' "
        f"-Confirm:$false -Force"
    )
    cmd: list[str] = [
        "powershell", "-NoProfile", "-NonInteractive", "-Command", script
    ]
    return _run_format_cmd(cmd, device, dry_run)


# ---------------------------------------------------------------------------
# Internal – subprocess runner
# ---------------------------------------------------------------------------

def _run_format_cmd(cmd: Sequence[str], device: str, dry_run: bool) -> bool:
    """Execute *cmd* unless *dry_run* is True.

    Raises:
        FileNotFoundError: If the executable is not found.
        OSError: If the command returns a non-zero exit code.
    """
    logger.debug("Format command: %s", " ".join(cmd))

    if dry_run:
        logger.info("[DRY RUN] Would run: %s", " ".join(cmd))
        return True

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
    except FileNotFoundError as exc:
        tool = cmd[0]
        raise FileNotFoundError(
            f"Formatting tool not found: {tool!r}. "
            "Install the required package (e.g. dosfstools, e2fsprogs, ntfs-3g)."
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
            f"Format failed (exit {result.returncode}) for {device}: "
            f"{stderr or stdout or '(no output)'}"
        )

    logger.info("Format complete: %s formatted as %s", device, cmd[0])
    return True
