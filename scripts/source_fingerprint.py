"""Stable source fingerprints for reproducible evaluation evidence."""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Iterable


SOURCE_FINGERPRINT_VERSION = 2
SOURCE_FINGERPRINT_NORMALIZATION = "lf"
POSTPROCESS_SOURCE_FILES = (
    "backend/rag/utils.py",
    "backend/rag/context.py",
    "backend/rag/rerank.py",
)


def _canonical_relative_path(relative: str) -> str:
    return PurePosixPath(relative.replace("\\", "/")).as_posix()


def _canonical_source_bytes(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def canonical_source_sha256(repo: Path, relative_paths: Iterable[str]) -> str:
    """Hash a path/content manifest independently of checkout line endings."""
    digest = hashlib.sha256()
    digest.update(b"superhermes-source-fingerprint\0v2\0")
    for relative in relative_paths:
        canonical_path = _canonical_relative_path(relative)
        path_bytes = canonical_path.encode("utf-8")
        content = _canonical_source_bytes((repo / canonical_path).read_bytes())
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def postprocess_source_fingerprint(repo: Path) -> dict[str, object]:
    """Return versioned fingerprint metadata for postprocess evaluation inputs."""
    files = list(POSTPROCESS_SOURCE_FILES)
    return {
        "source_fingerprint_version": SOURCE_FINGERPRINT_VERSION,
        "source_fingerprint_normalization": SOURCE_FINGERPRINT_NORMALIZATION,
        "source_files": files,
        "source_sha256": canonical_source_sha256(repo, files),
    }
