"""Static inventory of browser-side API routes.

The completion checker historically inspected only Python consumers.  This
module intentionally keeps the Web scan small and conservative: it records
literal route strings and fails closed when a source file is malformed rather
than silently claiming that the consumer is governed.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence


class RouteScanConfigurationError(ValueError):
    """Raised when a Web route scan cannot safely establish evidence."""


@dataclass(frozen=True)
class RouteUse:
    source: str
    line: int
    column: int
    route: str
    kind: str
    method: str | None


@dataclass(frozen=True)
class RouteScanReport:
    roots: tuple[str, ...]
    legacy_prefixes: tuple[str, ...]
    routes: tuple[RouteUse, ...]

    @property
    def legacy_count(self) -> int:
        return sum(route.kind == "legacy" for route in self.routes)

    @property
    def capability_count(self) -> int:
        return sum(route.kind == "capability" for route in self.routes)

    @property
    def allowlisted_count(self) -> int:
        return sum(route.kind == "allowlisted" for route in self.routes)

    @property
    def total_count(self) -> int:
        return len(self.routes)

    def serialized(self) -> dict[str, object]:
        return {
            "roots": list(self.roots),
            "legacy_prefixes": list(self.legacy_prefixes),
            "counts": {
                "legacy": self.legacy_count,
                "capability": self.capability_count,
                "allowlisted": self.allowlisted_count,
                "total": self.total_count,
            },
            "routes": [asdict(route) for route in self.routes],
        }

    def json(self) -> str:
        return json.dumps(self.serialized(), ensure_ascii=False, indent=2) + "\n"


_SOURCE_SUFFIXES = {".cjs", ".html", ".js", ".jsx", ".mjs", ".ts", ".tsx"}
_SKIP_DIRECTORIES = {".git", "__tests__", "dist", "node_modules", "tests"}
_ROUTE_LITERAL = re.compile(r"(?P<quote>['\"`])(?P<route>/api/[A-Za-z0-9_./:{}$-]+)")
_EMPTY_ASSIGNMENT = re.compile(r"\b(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*;")


def _mask_comments(source: str) -> str:
    """Blank JS/HTML comments while preserving offsets and line numbers."""

    chars = list(source)
    quote: str | None = None
    escaped = False
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
            index += 1
            continue
        if source.startswith("//", index) or source.startswith("<!--", index):
            end = source.find("\n", index)
            if end < 0:
                end = length
            for position in range(index, end):
                chars[position] = " "
            index = end
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            end = length if end < 0 else end + 2
            for position in range(index, end):
                if chars[position] not in {"\r", "\n"}:
                    chars[position] = " "
            index = end
            continue
        index += 1
    return "".join(chars)


def _relative_path(root: Path, value: str) -> Path:
    pure = PurePosixPath(value)
    if not value or "\\" in value or pure.is_absolute() or ".." in pure.parts:
        raise RouteScanConfigurationError("Web consumer root must be repository-relative")
    return root.joinpath(*pure.parts)


def _validate_source(source: str, relative: str, path: Path) -> None:
    if _EMPTY_ASSIGNMENT.search(source):
        raise RouteScanConfigurationError(f"Web source cannot be parsed: {relative}")
    if path.suffix.lower() in {".cjs", ".js", ".mjs"} and shutil.which("node"):
        result = subprocess.run(
            ["node", "--check", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise RouteScanConfigurationError(f"Web source cannot be parsed: {relative}")


def _route_kind(
    route: str,
    legacy_prefixes: Sequence[str],
    allowlisted_legacy_routes: Sequence[str],
) -> str | None:
    if "/capabilities/" in route or "/capability/" in route:
        return "capability"
    if any(route == prefix or route.startswith(prefix + "/") for prefix in legacy_prefixes):
        return "allowlisted" if route in allowlisted_legacy_routes else "legacy"
    return None


def _method_for_line(line: str) -> str | None:
    match = re.search(r"\bmethod\s*:\s*['\"]([A-Za-z]+)['\"]", line)
    return match.group(1).upper() if match else None


def _iter_sources(root: Path, roots: Sequence[str]):
    seen: set[Path] = set()
    for value in roots:
        path = _relative_path(root, value)
        if not path.exists():
            raise RouteScanConfigurationError(f"Web consumer root is missing: {value}")
        candidates = path.rglob("*") if path.is_dir() else (path,)
        for candidate in candidates:
            if not candidate.is_file() or candidate in seen:
                continue
            if candidate.suffix.lower() not in _SOURCE_SUFFIXES:
                continue
            if any(part in _SKIP_DIRECTORIES for part in candidate.relative_to(root).parts):
                continue
            seen.add(candidate)
            yield candidate


def scan_web_routes(
    root: Path,
    *,
    roots: Sequence[str],
    legacy_prefixes: Sequence[str],
    allowlisted_legacy_routes: Sequence[str] = (),
) -> RouteScanReport:
    """Return literal browser route evidence for configured source roots."""

    root = root.resolve()
    if not roots or not all(isinstance(value, str) and value for value in roots):
        raise RouteScanConfigurationError("Web consumer roots must contain paths")
    if not legacy_prefixes or not all(
        isinstance(value, str) and value.startswith("/api/") for value in legacy_prefixes
    ):
        raise RouteScanConfigurationError("legacy route prefixes must be /api/ paths")
    if any(not isinstance(value, str) or not value.startswith("/api/") for value in allowlisted_legacy_routes):
        raise RouteScanConfigurationError("allowlisted routes must be /api/ paths")

    routes: list[RouteUse] = []
    for path in _iter_sources(root, roots):
        relative = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        _validate_source(source, relative, path)
        lines = source.splitlines()
        scan_source = _mask_comments(source)
        for match in _ROUTE_LITERAL.finditer(scan_source):
            route = match.group("route")
            kind = _route_kind(route, legacy_prefixes, allowlisted_legacy_routes)
            if kind is None:
                continue
            line = source.count("\n", 0, match.start()) + 1
            line_start = source.rfind("\n", 0, match.start()) + 1
            column = match.start() - line_start + 1
            routes.append(
                RouteUse(
                    source=relative,
                    line=line,
                    column=column,
                    route=route,
                    kind=kind,
                    method=_method_for_line(lines[line - 1]),
                )
            )
    routes.sort(key=lambda item: (item.source, item.line, item.column, item.route))
    return RouteScanReport(
        roots=tuple(roots),
        legacy_prefixes=tuple(legacy_prefixes),
        routes=tuple(routes),
    )


__all__ = [
    "RouteScanConfigurationError",
    "RouteScanReport",
    "RouteUse",
    "scan_web_routes",
]
