"""SHA-256 (and optional SHA-512) verification helpers."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1 * 1024 * 1024  # 1 MiB

#: Algorithms always guaranteed by :mod:`hashlib` on all supported platforms.
COMMON_ALGORITHMS: list[str] = ["md5", "sha1", "sha256", "sha512"]


def multi_hash(
    path: str | Path,
    algorithms: list[str] | None = None,
    progress_callback: Callable[[int], None] | None = None,
) -> dict[str, str]:
    """Compute multiple hash digests in a **single read pass**.

    Args:
        path:       File (or block device) to hash.
        algorithms: List of algorithm names accepted by :mod:`hashlib`.
                    Defaults to :data:`COMMON_ALGORITHMS`
                    (``["md5", "sha1", "sha256", "sha512"]``).
        progress_callback: Optional callable receiving cumulative bytes read.

    Returns:
        Dict mapping each algorithm name to its lowercase hex digest.

    Raises:
        FileNotFoundError: If *path* does not exist.
        ValueError:        If any algorithm is not supported by :mod:`hashlib`.
    """
    if algorithms is None:
        algorithms = list(COMMON_ALGORITHMS)

    # Validate all algorithms up-front so we fail fast.
    hashers: dict[str, Any] = {}
    for algo in algorithms:
        try:
            hashers[algo] = hashlib.new(algo)
        except ValueError as exc:
            raise ValueError(f"Unsupported hash algorithm {algo!r}: {exc}") from exc

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    total = 0
    with open(path, "rb") as fh:
        while chunk := fh.read(CHUNK_SIZE):
            for h in hashers.values():
                h.update(chunk)
            total += len(chunk)
            if progress_callback:
                progress_callback(total)

    return {algo: h.hexdigest() for algo, h in hashers.items()}


def hash_file(
    path: str | Path,
    algorithm: str = "sha256",
    progress_callback: Callable[[int], None] | None = None,
) -> str:
    """Compute the hex digest of *path* using *algorithm*.

    Args:
        path: File (or block device) to hash.
        algorithm: Hash algorithm name accepted by :mod:`hashlib`.
        progress_callback: Optional callable receiving cumulative bytes read.

    Returns:
        Lowercase hex digest string.
    """
    h = hashlib.new(algorithm)
    total = 0
    with open(path, "rb") as fh:
        while chunk := fh.read(CHUNK_SIZE):
            h.update(chunk)
            total += len(chunk)
            if progress_callback:
                progress_callback(total)
    return h.hexdigest()


def verify_file(
    path: str | Path,
    expected_hash: str,
    algorithm: str = "sha256",
    progress_callback: Callable[[int], None] | None = None,
) -> bool:
    """Return True if the file's digest matches *expected_hash* (case-insensitive).

    Args:
        path: File to verify.
        expected_hash: Expected hex digest.
        algorithm: Hash algorithm.
        progress_callback: Optional progress callback.
    """
    actual = hash_file(path, algorithm=algorithm, progress_callback=progress_callback)
    match = actual.lower() == expected_hash.lower()
    if not match:
        logger.warning(
            "Hash mismatch for %s: expected %s got %s",
            path,
            expected_hash.lower(),
            actual,
        )
    return match


def write_sidecar(image_path: str | Path, digest: str, algorithm: str = "sha256") -> Path:
    """Write a *.sha256* (or similar) sidecar file next to *image_path*.

    Returns the path of the written sidecar file.
    """
    image_path = Path(image_path)
    sidecar = image_path.with_suffix(image_path.suffix + f".{algorithm}")
    sidecar.write_text(f"{digest}  {image_path.name}\n", encoding="utf-8")
    logger.info("Sidecar written: %s", sidecar)
    return sidecar


def read_sidecar(image_path: str | Path) -> tuple[str, str] | None:
    """Read the sidecar file for *image_path*.

    Returns ``(algorithm, digest)`` or *None* if not found.
    """
    image_path = Path(image_path)
    for algo in ("sha256", "sha512", "md5"):
        sidecar = image_path.with_suffix(image_path.suffix + f".{algo}")
        if sidecar.exists():
            content = sidecar.read_text(encoding="utf-8").strip()
            digest = content.split()[0]
            return algo, digest
    return None
