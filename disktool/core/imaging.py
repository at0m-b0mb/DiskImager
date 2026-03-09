"""Core imaging, restore, and flash operations."""

from __future__ import annotations

import json
import logging
import os
import platform
import sys
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

CHUNK_SIZE = 4 * 1024 * 1024  # 4 MiB – good balance of speed and memory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _open_device(path: str, mode: str):
    """Open a device or file with OS-level unbuffered access."""
    if sys.platform == "win32":
        import ctypes
        import ctypes.wintypes

        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        FILE_SHARE_READ = 0x00000001
        FILE_SHARE_WRITE = 0x00000002
        OPEN_EXISTING = 3
        FILE_FLAG_NO_BUFFERING = 0x20000000
        FILE_FLAG_SEQUENTIAL_SCAN = 0x08000000

        if "r" in mode and "w" not in mode:
            access = GENERIC_READ
        elif "w" in mode and "r" not in mode:
            access = GENERIC_WRITE
        else:
            access = GENERIC_READ | GENERIC_WRITE

        share = FILE_SHARE_READ | FILE_SHARE_WRITE
        flags = FILE_FLAG_NO_BUFFERING | FILE_FLAG_SEQUENTIAL_SCAN
        handle = ctypes.windll.kernel32.CreateFileW(  # type: ignore[attr-defined]
            path, access, share, None, OPEN_EXISTING, flags, None
        )
        if handle == -1:
            raise OSError(f"Cannot open device {path}")
        # Wrap the handle in a Python file-like object
        fd = ctypes.windll.msvcrt.open_osfhandle(handle, os.O_RDONLY if "r" in mode else os.O_WRONLY)  # type: ignore[attr-defined]
        return os.fdopen(fd, mode + "b")
    else:
        return open(path, mode + "b", buffering=0)


def _get_device_size(path: str) -> int:
    """Return the size in bytes of a block device or file."""
    try:
        stat = os.stat(path)
        if stat.st_size > 0:
            return stat.st_size
    except OSError:
        pass

    # For block devices on Linux
    if sys.platform.startswith("linux"):
        try:
            import fcntl
            import struct

            BLKGETSIZE64 = 0x80081272
            with open(path, "rb") as fh:
                buf = b" " * 8
                buf = fcntl.ioctl(fh.fileno(), BLKGETSIZE64, buf)
                return struct.unpack("Q", buf)[0]
        except Exception:
            pass

    # Seek to end
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            return fh.tell()
    except OSError:
        return 0


def _write_metadata(image_path: Path, source_path: str, size_bytes: int, digest: str) -> None:
    meta = {
        "source": source_path,
        "size_bytes": size_bytes,
        "sha256": digest,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "platform": platform.system(),
        "disktool_version": "1.0.0",
    }
    meta_path = image_path.with_suffix(".json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    logger.info("Metadata written: %s", meta_path)


# ---------------------------------------------------------------------------
# Backup / imaging
# ---------------------------------------------------------------------------

def backup(
    source: str,
    dest: str,
    dry_run: bool = False,
    progress_callback: Callable[[int, int, float], None] | None = None,
) -> str:
    """Copy *source* device/file to *dest* image file.

    Args:
        source: Path to source block device or file.
        dest: Destination image file path.
        dry_run: If True, simulate without writing.
        progress_callback: Called with (bytes_done, total_bytes, speed_bps).

    Returns:
        SHA-256 hex digest of the written image.
    """
    import hashlib

    source_path = Path(source)
    dest_path = Path(dest)

    if not source_path.exists():
        raise FileNotFoundError(f"Source not found: {source}")

    total_bytes = _get_device_size(source)
    logger.info("Backup %s -> %s  (%d bytes)", source, dest, total_bytes)

    if dry_run:
        logger.info("[DRY RUN] No data written.")
        return ""

    h = hashlib.sha256()
    bytes_done = 0
    start_time = time.monotonic()

    with open(source, "rb", buffering=0) as src, open(dest, "wb") as dst:
        while True:
            chunk = src.read(CHUNK_SIZE)
            if not chunk:
                break
            dst.write(chunk)
            h.update(chunk)
            bytes_done += len(chunk)
            elapsed = time.monotonic() - start_time
            speed = bytes_done / elapsed if elapsed > 0 else 0
            if progress_callback:
                progress_callback(bytes_done, total_bytes, speed)

    digest = h.hexdigest()
    _write_metadata(dest_path, source, bytes_done, digest)

    from disktool.core.verify import write_sidecar

    write_sidecar(dest_path, digest)
    logger.info("Backup complete. SHA-256: %s", digest)
    return digest


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

def restore(
    image: str,
    dest: str,
    dry_run: bool = False,
    verify: bool = True,
    progress_callback: Callable[[int, int, float], None] | None = None,
) -> bool:
    """Write *image* file to *dest* block device.

    Args:
        image: Source image path (.img / .iso / .zip).
        dest: Destination block device path.
        dry_run: Simulate without writing.
        verify: Verify destination after write.
        progress_callback: Called with (bytes_done, total_bytes, speed_bps).

    Returns:
        True on success (and verification pass if enabled).
    """
    import hashlib

    image_path = Path(image)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image}")

    source = _resolve_source(image_path)  # handles .zip extraction
    total_bytes = source.stat().st_size
    logger.info("Restore %s -> %s  (%d bytes)", source, dest, total_bytes)

    if dry_run:
        logger.info("[DRY RUN] No data written.")
        return True

    h = hashlib.sha256()
    bytes_done = 0
    start_time = time.monotonic()

    with open(str(source), "rb") as src, open(dest, "wb") as dst:
        while True:
            chunk = src.read(CHUNK_SIZE)
            if not chunk:
                break
            dst.write(chunk)
            h.update(chunk)
            bytes_done += len(chunk)
            elapsed = time.monotonic() - start_time
            speed = bytes_done / elapsed if elapsed > 0 else 0
            if progress_callback:
                progress_callback(bytes_done, total_bytes, speed)

    written_digest = h.hexdigest()
    logger.info("Write complete. SHA-256: %s", written_digest)

    if verify:
        return _verify_destination(dest, written_digest, progress_callback)
    return True


# ---------------------------------------------------------------------------
# Flash
# ---------------------------------------------------------------------------

def flash(
    image: str,
    dest: str,
    dry_run: bool = False,
    verify: bool = True,
    progress_callback: Callable[[int, int, float], None] | None = None,
) -> bool:
    """Flash *image* (.img / .iso / .zip) to *dest* drive.

    Alias for :func:`restore` with slightly different logging.
    """
    logger.info("Flash %s -> %s", image, dest)
    return restore(
        image=image,
        dest=dest,
        dry_run=dry_run,
        verify=verify,
        progress_callback=progress_callback,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_source(image_path: Path) -> Path:
    """If *image_path* is a .zip, extract the first .img/.iso and return its path."""
    if image_path.suffix.lower() != ".zip":
        return image_path

    import tempfile
    import zipfile

    tmpdir = Path(tempfile.mkdtemp(prefix="disktool_"))
    logger.info("Extracting zip archive %s -> %s", image_path, tmpdir)
    with zipfile.ZipFile(image_path, "r") as zf:
        members = [m for m in zf.namelist() if m.lower().endswith((".img", ".iso"))]
        if not members:
            raise ValueError(f"No .img/.iso found inside {image_path}")
        zf.extract(members[0], tmpdir)
        return tmpdir / members[0]


# ---------------------------------------------------------------------------
# Erase
# ---------------------------------------------------------------------------

def erase(
    dest: str,
    passes: int = 1,
    dry_run: bool = False,
    progress_callback: Callable[[int, int, float], None] | None = None,
) -> bool:
    """Overwrite *dest* with zeros (or random data for multiple passes).

    Args:
        dest: Path to the block device or file to erase.
        passes: Number of overwrite passes (1 = zeros, 2+ = random then zeros).
        dry_run: Simulate without writing.
        progress_callback: Called with (bytes_done, total_bytes, speed_bps).

    Returns:
        True on success.
    """
    import os
    import secrets

    dest_path = Path(dest)
    if not dest_path.exists():
        raise FileNotFoundError(f"Target not found: {dest}")

    total_bytes = _get_device_size(dest)
    if total_bytes <= 0:
        raise ValueError(
            f"Cannot determine size of {dest}. "
            "Only regular files and known block devices are supported."
        )
    logger.info("Erase %s  (%d bytes, %d pass(es))", dest, total_bytes, passes)

    if dry_run:
        logger.info("[DRY RUN] No data written.")
        return True

    start_time = time.monotonic()
    for pass_num in range(passes):
        use_random = (passes > 1) and (pass_num < passes - 1)
        bytes_done = 0
        with open(dest, "wb") as fh:
            while bytes_done < total_bytes:
                remaining = total_bytes - bytes_done
                chunk_len = min(CHUNK_SIZE, remaining)
                chunk = secrets.token_bytes(chunk_len) if use_random else b"\x00" * chunk_len
                written = fh.write(chunk)
                bytes_done += written
                elapsed = time.monotonic() - start_time
                speed = bytes_done / elapsed if elapsed > 0 else 0
                if progress_callback:
                    progress_callback(bytes_done, total_bytes, speed)
                if total_bytes > 0 and bytes_done >= total_bytes:
                    break
        logger.info("Erase pass %d/%d complete.", pass_num + 1, passes)

    logger.info("Erase complete.")
    return True


def _verify_destination(
    dest: str,
    expected_digest: str,
    progress_callback: Callable[[int, int, float], None] | None = None,
) -> bool:
    """Read *dest* back and compare SHA-256 to *expected_digest*."""
    import hashlib

    logger.info("Verifying destination %s …", dest)
    h = hashlib.sha256()
    total_bytes = _get_device_size(dest)
    bytes_done = 0
    start_time = time.monotonic()

    try:
        with open(dest, "rb", buffering=0) as fh:
            while True:
                chunk = fh.read(CHUNK_SIZE)
                if not chunk:
                    break
                h.update(chunk)
                bytes_done += len(chunk)
                elapsed = time.monotonic() - start_time
                speed = bytes_done / elapsed if elapsed > 0 else 0
                if progress_callback:
                    progress_callback(bytes_done, total_bytes, speed)
    except OSError as exc:
        logger.error("Verification read error: %s", exc)
        return False

    actual = h.hexdigest()
    if actual.lower() == expected_digest.lower():
        logger.info("Verification PASSED.")
        return True

    logger.error("Verification FAILED: expected %s got %s", expected_digest, actual)
    return False
