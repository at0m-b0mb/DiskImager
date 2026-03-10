"""Cross-platform disk image mounting and unmounting.

Mount helpers
-------------
Linux
    Uses ``losetup`` to attach the image as a loop device, then ``mount``
    to attach it to a mountpoint.  Requires root.

macOS
    Uses ``hdiutil attach`` which handles most image formats automatically.

Windows
    Uses PowerShell ``Mount-DiskImage`` (requires elevation).

Example::

    >>> from disktool.core.mount import mount_image, unmount_image
    >>> info = mount_image("backup.img", dry_run=True)
    >>> info["dry_run"]
    True
    >>> unmount_image("backup.img", dry_run=True)
    True
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SUBPROCESS_TIMEOUT = 60  # seconds – generous for slow/large images
_CLEANUP_TIMEOUT = 10    # seconds – shorter for best-effort cleanup ops


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def mount_image(
    image: str,
    mountpoint: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Mount *image* and return information about the mount.

    Args:
        image:      Path to a disk image file.
        mountpoint: Where to mount.  If ``None`` a temporary directory is
                    created on Linux (macOS and Windows pick their own).
        dry_run:    Simulate without executing.

    Returns:
        Dict with keys ``image``, ``mountpoint``, ``loop_device``
        (Linux only), ``dry_run``.

    Raises:
        FileNotFoundError: If *image* does not exist.
        ValueError:        On unsupported platforms.
        OSError:           If the mount command fails.
    """
    image_path = Path(image)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image}")

    logger.info("Mount %s  mountpoint=%s  dry_run=%s", image, mountpoint, dry_run)

    if sys.platform.startswith("linux"):
        return _mount_linux(image_path, mountpoint, dry_run)
    if sys.platform == "darwin":
        return _mount_darwin(image_path, mountpoint, dry_run)
    if sys.platform == "win32":
        return _mount_windows(image_path, dry_run)

    raise ValueError(f"Unsupported platform for mount: {sys.platform}")


def unmount_image(
    image_or_mountpoint: str,
    dry_run: bool = False,
) -> bool:
    """Unmount a mounted disk image.

    Args:
        image_or_mountpoint: Path to the original image *or* to the mountpoint.
        dry_run:             Simulate without executing.

    Returns:
        ``True`` on success.

    Raises:
        ValueError: On unsupported platforms.
        OSError:    If the unmount command fails.
    """
    logger.info("Unmount %s  dry_run=%s", image_or_mountpoint, dry_run)

    if sys.platform.startswith("linux"):
        return _unmount_linux(image_or_mountpoint, dry_run)
    if sys.platform == "darwin":
        return _unmount_darwin(image_or_mountpoint, dry_run)
    if sys.platform == "win32":
        return _unmount_windows(image_or_mountpoint, dry_run)

    raise ValueError(f"Unsupported platform for unmount: {sys.platform}")


# ---------------------------------------------------------------------------
# Linux
# ---------------------------------------------------------------------------

def _mount_linux(
    image: Path,
    mountpoint: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "image": str(image),
        "mountpoint": mountpoint,
        "loop_device": None,
        "dry_run": dry_run,
    }

    if dry_run:
        logger.info("[DRY RUN] Would run: losetup -f --show %s", image)
        logger.info("[DRY RUN] Would run: mount <loop> %s", mountpoint or "<tmpdir>")
        return result

    # Step 1: attach image as a loop device
    loop_result = subprocess.run(
        ["losetup", "-f", "--show", "--partscan", str(image)],
        capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT,
    )
    if loop_result.returncode != 0:
        raise OSError(
            f"losetup failed (exit {loop_result.returncode}): "
            f"{loop_result.stderr.strip() or loop_result.stdout.strip()}"
        )
    loop_dev = loop_result.stdout.strip()
    result["loop_device"] = loop_dev
    logger.info("Loop device: %s", loop_dev)

    # Step 2: create mountpoint if needed
    if mountpoint is None:
        mountpoint = tempfile.mkdtemp(prefix="disktool_mount_")
    else:
        Path(mountpoint).mkdir(parents=True, exist_ok=True)
    result["mountpoint"] = mountpoint

    # Step 3: mount
    mount_result = subprocess.run(
        ["mount", "-o", "ro", loop_dev, mountpoint],
        capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT,
    )
    if mount_result.returncode != 0:
        # Clean up loop device on failure
        subprocess.run(["losetup", "-d", loop_dev], capture_output=True, timeout=_CLEANUP_TIMEOUT)
        raise OSError(
            f"mount failed (exit {mount_result.returncode}): "
            f"{mount_result.stderr.strip() or mount_result.stdout.strip()}"
        )

    logger.info("Mounted %s at %s (loop: %s)", image, mountpoint, loop_dev)
    return result


def _unmount_linux(image_or_mountpoint: str, dry_run: bool) -> bool:
    if dry_run:
        logger.info("[DRY RUN] Would run: umount %s", image_or_mountpoint)
        return True

    result = subprocess.run(
        ["umount", image_or_mountpoint],
        capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT,
    )
    if result.returncode != 0:
        raise OSError(
            f"umount failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )

    # If a loop device was associated, detach it
    _detach_loop(image_or_mountpoint)
    logger.info("Unmounted %s", image_or_mountpoint)
    return True


def _detach_loop(mountpoint: str) -> None:
    """Best-effort loop device detach after umount."""
    try:
        result = subprocess.run(
            ["losetup", "-j", mountpoint],
            capture_output=True, text=True, timeout=_CLEANUP_TIMEOUT,
        )
        for line in result.stdout.splitlines():
            m = re.match(r"(/dev/loop\d+)", line)
            if m:
                subprocess.run(["losetup", "-d", m.group(1)], timeout=_CLEANUP_TIMEOUT)
    except Exception as exc:
        logger.debug("loop detach: %s", exc)


# ---------------------------------------------------------------------------
# macOS
# ---------------------------------------------------------------------------

def _mount_darwin(
    image: Path,
    mountpoint: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "image": str(image),
        "mountpoint": mountpoint,
        "loop_device": None,
        "dry_run": dry_run,
    }

    if dry_run:
        logger.info("[DRY RUN] Would run: hdiutil attach %s", image)
        return result

    cmd = ["hdiutil", "attach", str(image), "-readonly"]
    if mountpoint:
        cmd += ["-mountpoint", mountpoint]

    attach = subprocess.run(
        cmd, capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT,
    )
    if attach.returncode != 0:
        raise OSError(
            f"hdiutil attach failed (exit {attach.returncode}): "
            f"{attach.stderr.strip() or attach.stdout.strip()}"
        )

    # Parse mountpoint from hdiutil output (last column of last content line)
    detected_mp: str | None = None
    for line in attach.stdout.splitlines():
        parts = line.split()
        if parts and parts[0].startswith("/dev/disk"):
            if len(parts) >= 3:
                detected_mp = parts[-1]
    if mountpoint is None and detected_mp:
        result["mountpoint"] = detected_mp

    logger.info("Mounted %s at %s (macOS)", image, result["mountpoint"])
    return result


def _unmount_darwin(image_or_mountpoint: str, dry_run: bool) -> bool:
    if dry_run:
        logger.info("[DRY RUN] Would run: hdiutil detach %s", image_or_mountpoint)
        return True

    result = subprocess.run(
        ["hdiutil", "detach", image_or_mountpoint],
        capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT,
    )
    if result.returncode != 0:
        raise OSError(
            f"hdiutil detach failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    logger.info("Detached %s (macOS)", image_or_mountpoint)
    return True


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def _mount_windows(image: Path, dry_run: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "image": str(image),
        "mountpoint": None,
        "loop_device": None,
        "dry_run": dry_run,
    }

    if dry_run:
        logger.info("[DRY RUN] Would run: Mount-DiskImage %s", image)
        return result

    ps_script = (
        f'Mount-DiskImage -ImagePath "{image}" -Access ReadOnly -PassThru | '
        f'Get-DiskImage | Select-Object -ExpandProperty DevicePath'
    )
    proc = subprocess.run(
        ["powershell", "-NonInteractive", "-Command", ps_script],
        capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT,
    )
    if proc.returncode != 0:
        raise OSError(
            f"Mount-DiskImage failed (exit {proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )

    device_path = proc.stdout.strip()
    result["loop_device"] = device_path
    logger.info("Mounted %s as %s (Windows)", image, device_path)
    return result


def _unmount_windows(image_or_mountpoint: str, dry_run: bool) -> bool:
    if dry_run:
        logger.info("[DRY RUN] Would run: Dismount-DiskImage %s", image_or_mountpoint)
        return True

    ps_script = f'Dismount-DiskImage -ImagePath "{image_or_mountpoint}"'
    result = subprocess.run(
        ["powershell", "-NonInteractive", "-Command", ps_script],
        capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT,
    )
    if result.returncode != 0:
        raise OSError(
            f"Dismount-DiskImage failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    logger.info("Dismounted %s (Windows)", image_or_mountpoint)
    return True
