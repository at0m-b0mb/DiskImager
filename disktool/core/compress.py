"""Streaming disk-image compression and decompression.

Supported algorithms
--------------------
* **gzip** – ``.img.gz``   Always available (stdlib :mod:`gzip`).
* **lz4**  – ``.img.lz4``  Requires ``pip install lz4``.
* **zstd** – ``.img.zst``  Requires ``pip install zstandard``.

Functions
---------
compress_image(source, algorithm, level, output, progress_callback)
    Compress *source* to *output* (or an auto-named sibling file).

decompress_image(source, output, progress_callback)
    Decompress *source* to *output* (or an auto-named sibling file).

detect_algorithm(path)
    Return the compression algorithm name for a path, or ``None``.

list_supported_algorithms()
    Return algorithms available in the current environment.

Example::

    >>> from disktool.core.compress import compress_image, decompress_image
    >>> compress_image("backup.img", algorithm="gzip")
    PosixPath('backup.img.gz')
    >>> decompress_image("backup.img.gz")
    PosixPath('backup.img')
"""

from __future__ import annotations

import gzip
import io
import logging
import os
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

CHUNK_SIZE = 4 * 1024 * 1024  # 4 MiB

#: Default gzip compression level (1=fastest, 9=best compression).
DEFAULT_GZIP_LEVEL: int = 9

# Mapping: algorithm name → file extension
_EXTENSIONS: dict[str, str] = {
    "gzip": ".gz",
    "lz4":  ".lz4",
    "zstd": ".zst",
}

# Reverse mapping: extension → algorithm name
_EXT_TO_ALGO: dict[str, str] = {v: k for k, v in _EXTENSIONS.items()}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def list_supported_algorithms() -> list[str]:
    """Return the compression algorithms available in this Python environment."""
    algos = ["gzip"]  # always available via stdlib
    try:
        import lz4.frame  # type: ignore[import]
        algos.append("lz4")
    except ImportError:
        pass
    try:
        import zstandard  # type: ignore[import]
        algos.append("zstd")
    except ImportError:
        pass
    return algos


def detect_algorithm(path: str | Path) -> str | None:
    """Return the compression algorithm name for *path*, or ``None`` for plain files.

    Detection is based on the file extension:
    ``.gz`` → ``"gzip"``, ``.lz4`` → ``"lz4"``, ``.zst`` → ``"zstd"``.
    """
    path = Path(path)
    ext = path.suffix.lower()
    return _EXT_TO_ALGO.get(ext)


# ---------------------------------------------------------------------------
# Compress
# ---------------------------------------------------------------------------

def compress_image(
    source: str | Path,
    algorithm: str = "gzip",
    level: int | None = None,
    output: str | Path | None = None,
    progress_callback: Callable[[int, int, float], None] | None = None,
) -> Path:
    """Compress *source* disk image.

    Args:
        source:    Path to the source image file.
        algorithm: ``"gzip"``, ``"lz4"``, or ``"zstd"``.
        level:     Compression level.  ``None`` uses the algorithm default.
        output:    Destination path.  If ``None`` the compressed file is placed
                   next to *source* with the appropriate extension appended
                   (e.g. ``backup.img`` → ``backup.img.gz``).
        progress_callback: Called with ``(bytes_done, total_bytes, speed_bps)``.

    Returns:
        Path of the written compressed file.

    Raises:
        FileNotFoundError: If *source* does not exist.
        ValueError:        If *algorithm* is unsupported or not available.
        RuntimeError:      If the required third-party library is not installed.
    """
    import time

    source_path = Path(source)
    if not source_path.exists():
        raise FileNotFoundError(f"Source not found: {source}")

    algorithm = algorithm.lower().strip()
    if algorithm not in _EXTENSIONS:
        raise ValueError(
            f"Unsupported algorithm {algorithm!r}. "
            f"Supported: {', '.join(_EXTENSIONS)}"
        )

    supported = list_supported_algorithms()
    if algorithm not in supported:
        raise RuntimeError(
            f"Algorithm {algorithm!r} is not available. "
            f"Install the required package first "
            f"({'pip install lz4' if algorithm == 'lz4' else 'pip install zstandard'})."
        )

    ext = _EXTENSIONS[algorithm]
    dest_path = Path(output) if output else source_path.with_suffix(source_path.suffix + ext)

    total_bytes = source_path.stat().st_size
    bytes_done = 0
    start = time.monotonic()

    logger.info("Compress %s → %s  algorithm=%s", source, dest_path, algorithm)

    with open(str(source_path), "rb") as src:
        with _open_writer(dest_path, algorithm, level) as dst:
            while True:
                chunk = src.read(CHUNK_SIZE)
                if not chunk:
                    break
                dst.write(chunk)
                bytes_done += len(chunk)
                elapsed = time.monotonic() - start
                speed = bytes_done / elapsed if elapsed > 0 else 0.0
                if progress_callback:
                    progress_callback(bytes_done, total_bytes, speed)

    logger.info("Compress complete → %s", dest_path)
    return dest_path


# ---------------------------------------------------------------------------
# Decompress
# ---------------------------------------------------------------------------

def decompress_image(
    source: str | Path,
    output: str | Path | None = None,
    progress_callback: Callable[[int, int, float], None] | None = None,
) -> Path:
    """Decompress a compressed disk image back to raw.

    Args:
        source:   Path to the compressed image (``.img.gz``, ``.img.lz4``,
                  ``.img.zst``).
        output:   Destination path.  If ``None`` the extension is stripped from
                  *source* (e.g. ``backup.img.gz`` → ``backup.img``).
        progress_callback: Called with ``(bytes_done, total_bytes, speed_bps)``.

    Returns:
        Path of the decompressed output file.

    Raises:
        FileNotFoundError: If *source* does not exist.
        ValueError:        If the file extension is not recognised.
        RuntimeError:      If the required third-party library is not installed.
    """
    import time

    source_path = Path(source)
    if not source_path.exists():
        raise FileNotFoundError(f"Source not found: {source}")

    algorithm = detect_algorithm(source_path)
    if algorithm is None:
        raise ValueError(
            f"Cannot determine compression algorithm from extension {source_path.suffix!r}. "
            f"Supported extensions: {', '.join(_EXT_TO_ALGO)}"
        )

    supported = list_supported_algorithms()
    if algorithm not in supported:
        raise RuntimeError(
            f"Algorithm {algorithm!r} is not available. "
            f"Install the required package first."
        )

    dest_path = Path(output) if output else source_path.with_suffix("")

    # Get compressed size for progress (actual decompressed size unknown upfront)
    compressed_size = source_path.stat().st_size
    bytes_done = 0
    start = time.monotonic()

    logger.info("Decompress %s → %s  algorithm=%s", source, dest_path, algorithm)

    with _open_reader(source_path, algorithm) as src:
        with open(str(dest_path), "wb") as dst:
            while True:
                chunk = src.read(CHUNK_SIZE)
                if not chunk:
                    break
                dst.write(chunk)
                bytes_done += len(chunk)
                elapsed = time.monotonic() - start
                speed = bytes_done / elapsed if elapsed > 0 else 0.0
                if progress_callback:
                    # Use compressed size as rough total (decompressed may be larger)
                    progress_callback(bytes_done, compressed_size, speed)

    logger.info("Decompress complete → %s", dest_path)
    return dest_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class _open_writer:
    """Context manager that opens a compressed output stream."""

    def __init__(self, dest: Path, algorithm: str, level: int | None) -> None:
        self._dest = dest
        self._algorithm = algorithm
        self._level = level
        self._fh = None

    def __enter__(self) -> io.RawIOBase:
        alg = self._algorithm
        lvl = self._level

        if alg == "gzip":
            self._fh = gzip.open(str(self._dest), "wb", compresslevel=lvl if lvl is not None else DEFAULT_GZIP_LEVEL)
        elif alg == "lz4":
            import lz4.frame  # type: ignore[import]
            kwargs: dict = {}
            if lvl is not None:
                kwargs["compression_level"] = lvl
            self._fh = lz4.frame.open(str(self._dest), "wb", **kwargs)
        elif alg == "zstd":
            import zstandard  # type: ignore[import]
            cctx = zstandard.ZstdCompressor(level=lvl if lvl is not None else 3)
            self._raw = open(str(self._dest), "wb")
            self._fh = cctx.stream_writer(self._raw, closefd=False)
        else:
            raise ValueError(f"Unknown algorithm: {alg}")

        return self._fh  # type: ignore[return-value]

    def __exit__(self, *args: object) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except Exception:
                pass
        if hasattr(self, "_raw"):
            try:
                self._raw.close()
            except Exception:
                pass


class _open_reader:
    """Context manager that opens a compressed input stream."""

    def __init__(self, source: Path, algorithm: str) -> None:
        self._source = source
        self._algorithm = algorithm
        self._fh = None

    def __enter__(self) -> io.RawIOBase:
        alg = self._algorithm
        if alg == "gzip":
            self._fh = gzip.open(str(self._source), "rb")
        elif alg == "lz4":
            import lz4.frame  # type: ignore[import]
            self._fh = lz4.frame.open(str(self._source), "rb")
        elif alg == "zstd":
            import zstandard  # type: ignore[import]
            self._raw = open(str(self._source), "rb")
            dctx = zstandard.ZstdDecompressor()
            self._fh = dctx.stream_reader(self._raw)
        else:
            raise ValueError(f"Unknown algorithm: {alg}")
        return self._fh  # type: ignore[return-value]

    def __exit__(self, *args: object) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except Exception:
                pass
        if hasattr(self, "_raw"):
            try:
                self._raw.close()
            except Exception:
                pass
