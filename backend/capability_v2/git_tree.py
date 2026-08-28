"""Small immutable Git-tree reader for generated governance evidence."""
from __future__ import annotations

from dataclasses import dataclass
import io
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Sequence


_FULL_SHA = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class GitBlob:
    path: str
    oid: str


def _git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"Git tree read failed: {detail or 'unknown error'}")
    return result.stdout


def resolve_revision(repo: Path, revision: str = "HEAD") -> str:
    repo = repo.resolve()
    top = Path(_git(repo, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if top != repo:
        raise ValueError(f"Git repository root mismatch: {repo}")
    commit = _git(repo, "rev-parse", f"{revision}^{{commit}}").decode().strip()
    if _FULL_SHA.fullmatch(commit) is None:
        raise ValueError("full Git commit revision is unavailable")
    return commit


def list_blobs(repo: Path, revision: str, roots: Sequence[str]) -> tuple[GitBlob, ...]:
    raw = _git(
        repo.resolve(), "ls-tree", "-r", "-z", "--full-tree", revision, "--", *roots
    )
    blobs = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        _mode, kind, oid = metadata.decode("ascii").split()
        if kind != "blob":
            continue
        path = raw_path.decode("utf-8")
        pure = PurePosixPath(path)
        if pure.is_absolute() or ".." in pure.parts:
            raise ValueError(f"unsafe Git tree path: {path}")
        blobs.append(GitBlob(path=path, oid=oid))
    return tuple(sorted(blobs, key=lambda item: item.path))


def read_blob(repo: Path, oid: str) -> bytes:
    return _git(repo.resolve(), "cat-file", "blob", oid)


def read_blobs(repo: Path, blobs: Sequence[GitBlob]) -> dict[str, bytes]:
    if not blobs:
        return {}
    result = subprocess.run(
        ["git", "-C", str(repo.resolve()), "cat-file", "--batch"],
        input="".join(f"{blob.oid}\n" for blob in blobs).encode("ascii"),
        check=False,
        capture_output=True,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"Git blob batch read failed: {detail or 'unknown error'}")
    values: dict[str, bytes] = {}
    offset = 0
    for blob in blobs:
        header_end = result.stdout.index(b"\n", offset)
        oid, kind, raw_size = result.stdout[offset:header_end].decode("ascii").split()
        if oid != blob.oid or kind != "blob":
            raise ValueError(f"Git blob batch mismatch: {blob.path}")
        size = int(raw_size)
        start = header_end + 1
        values[blob.oid] = result.stdout[start:start + size]
        offset = start + size + 1
    return values


def read_path(repo: Path, revision: str, relative: str) -> bytes:
    pure = PurePosixPath(relative)
    if not relative or pure.is_absolute() or ".." in pure.parts or "\\" in relative:
        raise ValueError(f"unsafe Git tree path: {relative}")
    return _git(repo.resolve(), "cat-file", "blob", f"{revision}:{relative}")


def read_text(repo: Path, revision: str, relative: str) -> str:
    return decode_text(read_path(repo, revision, relative))


def decode_text(payload: bytes) -> str:
    with io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8") as stream:
        return stream.read()


def path_exists(repo: Path, revision: str, relative: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo.resolve()), "cat-file", "-e", f"{revision}:{relative}"],
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def require_clean_paths(repo: Path, roots: Sequence[str]) -> None:
    status = _git(
        repo.resolve(), "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", *roots
    )
    if status:
        raise ValueError("dirty deployable worktree: tracked or untracked deployable paths changed")
