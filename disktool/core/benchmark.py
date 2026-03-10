"""Cross-platform sequential read/write disk benchmark.

Provides :func:`benchmark_read`, :func:`benchmark_write`, and the
convenience wrapper :func:`benchmark_device`.

Results are returned as plain dicts so they are easy to display in both the
CLI and GUI.

Example::

    >>> from disktool.core.benchmark import benchmark_device
    >>> results = benchmark_device("/tmp", size_mb=16, read=False, write=True)
    >>> print(results["write"]["speed_mb_s"])
    312.4
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default I/O block size (4 MiB) – good balance between memory and accuracy.
DEFAULT_BLOCK_SIZE_MB: int = 4


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def benchmark_read(
    device: str,
    size_mb: int = 64,
    block_size_mb: int = DEFAULT_BLOCK_SIZE_MB,
    progress_callback: Callable[[int, int, float], None] | None = None,
) -> dict:
    """Measure sequential read throughput on *device*.

    Reads up to *size_mb* megabytes from the start of *device* (or from a
    regular file) and measures the elapsed wall-clock time.

    Args:
        device:          Block device path or regular file path to read.
        size_mb:         Amount of data to read in megabytes.
        block_size_mb:   I/O block size in megabytes.
        progress_callback: Called with ``(bytes_done, total_bytes, speed_bps)``.

    Returns:
        dict with keys ``device``, ``operation``, ``size_mb``,
        ``duration_s``, ``speed_mb_s``.

    Raises:
        FileNotFoundError: If *device* does not exist.
        OSError: On a read error.
    """
    path = Path(device)
    if not path.exists():
        raise FileNotFoundError(f"Device not found: {device}")

    total_bytes = size_mb * 1024 * 1024
    block_size = block_size_mb * 1024 * 1024
    bytes_done = 0
    start = time.monotonic()

    logger.info(
        "Read benchmark: %s  size=%d MB  block=%d MB", device, size_mb, block_size_mb
    )

    with open(device, "rb", buffering=0) as fh:
        while bytes_done < total_bytes:
            to_read = min(block_size, total_bytes - bytes_done)
            chunk = fh.read(to_read)
            if not chunk:
                break  # EOF – file smaller than requested size
            bytes_done += len(chunk)
            elapsed = time.monotonic() - start
            speed = bytes_done / elapsed if elapsed > 0 else 0.0
            if progress_callback:
                progress_callback(bytes_done, total_bytes, speed)

    duration = max(time.monotonic() - start, 1e-9)
    speed_mb_s = (bytes_done / duration) / (1024 * 1024)

    result = {
        "device": device,
        "operation": "read",
        "size_mb": round(bytes_done / (1024 * 1024), 3),
        "duration_s": round(duration, 3),
        "speed_mb_s": round(speed_mb_s, 2),
    }
    logger.info("Read benchmark result: %.2f MB/s  (%.3f s)", speed_mb_s, duration)
    return result


def benchmark_write(
    path: str,
    size_mb: int = 64,
    block_size_mb: int = DEFAULT_BLOCK_SIZE_MB,
    progress_callback: Callable[[int, int, float], None] | None = None,
) -> dict:
    """Measure sequential write throughput at *path*.

    If *path* is a directory a temporary file is created there and removed
    afterwards.  If *path* is a regular file path in an existing directory the
    file is written (and removed) at that location.  If *path* is a block
    device it is written directly – use with extreme care.

    Args:
        path:            Target: directory, file path, or block device.
        size_mb:         Amount of data to write in megabytes.
        block_size_mb:   I/O block size in megabytes.
        progress_callback: Called with ``(bytes_done, total_bytes, speed_bps)``.

    Returns:
        dict with keys ``device``, ``operation``, ``size_mb``,
        ``duration_s``, ``speed_mb_s``.

    Raises:
        OSError: On a write error or when the target is inaccessible.
    """
    import tempfile

    target = Path(path)
    temp_file: Path | None = None

    if target.is_dir():
        # Create (and later remove) a temp file inside the directory.
        fd, tmp = tempfile.mkstemp(prefix="disktool_bench_", dir=target)
        os.close(fd)
        target = Path(tmp)
        temp_file = target
    elif not target.exists() and target.parent.is_dir():
        # Caller supplied a specific file name inside an existing directory.
        temp_file = target
    # else: block device or pre-existing file – write directly, don't delete.

    total_bytes = size_mb * 1024 * 1024
    block_size = block_size_mb * 1024 * 1024
    # Pre-generate a random buffer so we don't measure RNG overhead in the
    # tight loop (secrets.token_bytes is fast but we call it once).
    buf = secrets.token_bytes(block_size)
    bytes_done = 0
    start = time.monotonic()

    logger.info(
        "Write benchmark: %s  size=%d MB  block=%d MB", target, size_mb, block_size_mb
    )

    try:
        with open(str(target), "wb", buffering=0) as fh:
            while bytes_done < total_bytes:
                to_write = min(block_size, total_bytes - bytes_done)
                written = fh.write(buf[:to_write])
                bytes_done += written
                elapsed = time.monotonic() - start
                speed = bytes_done / elapsed if elapsed > 0 else 0.0
                if progress_callback:
                    progress_callback(bytes_done, total_bytes, speed)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass  # some virtual filesystems don't support fsync
    finally:
        if temp_file is not None and temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass

    duration = max(time.monotonic() - start, 1e-9)
    speed_mb_s = (bytes_done / duration) / (1024 * 1024)

    result = {
        "device": path,
        "operation": "write",
        "size_mb": round(bytes_done / (1024 * 1024), 3),
        "duration_s": round(duration, 3),
        "speed_mb_s": round(speed_mb_s, 2),
    }
    logger.info("Write benchmark result: %.2f MB/s  (%.3f s)", speed_mb_s, duration)
    return result


def benchmark_device(
    device: str,
    size_mb: int = 64,
    read: bool = True,
    write: bool = False,
    block_size_mb: int = DEFAULT_BLOCK_SIZE_MB,
    progress_callback: Callable[[int, int, float], None] | None = None,
) -> dict:
    """Run read and/or write benchmark on *device*.

    Args:
        device:          Device path or directory (for write test).
        size_mb:         Amount of data per test phase in megabytes.
        read:            Run read benchmark.
        write:           Run write benchmark.
        block_size_mb:   I/O block size in megabytes.
        progress_callback: Called with ``(bytes_done, total_bytes, speed_bps)``.

    Returns:
        dict with ``device`` key and optional ``read`` / ``write`` sub-dicts.

    Raises:
        ValueError: If neither *read* nor *write* is True.
    """
    if not read and not write:
        raise ValueError("At least one of 'read' or 'write' must be True.")

    results: dict = {"device": device}

    if read:
        results["read"] = benchmark_read(
            device,
            size_mb=size_mb,
            block_size_mb=block_size_mb,
            progress_callback=progress_callback,
        )

    if write:
        results["write"] = benchmark_write(
            device,
            size_mb=size_mb,
            block_size_mb=block_size_mb,
            progress_callback=progress_callback,
        )

    return results
