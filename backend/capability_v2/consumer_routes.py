"""Canonical static evidence for browser-side ``/api/`` route occurrences."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence


class RouteScanConfigurationError(ValueError):
    """Raised when a Web route scan cannot safely establish evidence."""


@dataclass(frozen=True)
class OperationsExclusion:
    route_method: str
    normalized_route: str
    owner: str
    reason: str
    approval_reference: str
    expires_at: str

    @property
    def key(self) -> tuple[str, str]:
        return self.route_method, self.normalized_route


@dataclass(frozen=True)
class RouteUse:
    source: str
    line: int
    column: int
    raw_route: str
    normalized_route: str
    method: str | None
    disposition: str
    occurrence_id: str
    classification_prefix: str | None = None
    legacy_kind: str | None = None

    @property
    def route(self) -> str:
        """Compatibility alias for the original prefix-limited scanner."""

        return self.raw_route

    @property
    def kind(self) -> str:
        """Compatibility alias for the original prefix-limited scanner."""

        return self.legacy_kind or self.disposition

    def serialized(self) -> dict[str, object]:
        value = asdict(self)
        value.pop("legacy_kind")
        if value["classification_prefix"] is None:
            value.pop("classification_prefix")
        return value


_DISPOSITIONS = (
    "capability",
    "legacy_registered",
    "bff_registered",
    "operations_excluded",
    "unresolved",
)


@dataclass(frozen=True)
class RouteScanReport:
    frontend_revision: str
    content_hash: str
    scan_roots: tuple[str, ...]
    excluded_roots: tuple[str, ...]
    routes: tuple[RouteUse, ...]
    legacy_prefixes: tuple[str, ...] = ()

    @property
    def counts(self) -> dict[str, int]:
        return {
            disposition: sum(route.disposition == disposition for route in self.routes)
            for disposition in _DISPOSITIONS
        }

    @property
    def unresolved_count(self) -> int:
        return self.counts["unresolved"]

    @property
    def roots(self) -> tuple[str, ...]:
        return self.scan_roots

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
            "frontend_revision": self.frontend_revision,
            "content_hash": self.content_hash,
            "scan_roots": list(self.scan_roots),
            "excluded_roots": list(self.excluded_roots),
            "counts": self.counts,
            "routes": [route.serialized() for route in self.routes],
        }

    def json(self) -> str:
        return json.dumps(self.serialized(), ensure_ascii=False, indent=2) + "\n"


_SOURCE_SUFFIXES = {".cjs", ".html", ".js", ".jsx", ".mjs", ".ts", ".tsx"}
_SKIP_DIRECTORIES = {
    ".git",
    "__tests__",
    "build",
    "coverage",
    "node_modules",
    "out",
    "tests",
}
_EXCLUDED_ROOTS = (
    "**/.git/**",
    "**/__tests__/**",
    "**/build/**",
    "**/coverage/**",
    "**/dist/**",
    "**/dist-*/**",
    "**/.next*/**",
    "**/node_modules/**",
    "**/out/**",
    "**/tests/**",
    "**/*.bundle.js",
    "**/*.min.js",
    "**/*.spec.*",
    "**/*.test.*",
)
_EMPTY_ASSIGNMENT = re.compile(r"\b(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*;")
_ROUTE_LITERAL = re.compile(
    r"(?P<quote>['\"`])(?P<prefix>\$\{[^}\r\n]+\})?(?P<route>/api/.*?)(?P=quote)"
)
_TEMPLATE_EXPRESSION = re.compile(r"\$\{[^}]+\}")
_ROUTE_PARAMETER = re.compile(r"\{[^/{}]+\}")
_EXPLICIT_METHOD = re.compile(r"\bmethod\s*:\s*['\"]([A-Za-z]+)['\"]")
_METHOD_ARGUMENT = re.compile(
    r"^\s*['\"](DELETE|GET|PATCH|POST|PUT)['\"]\s*,\s*$", re.IGNORECASE
)
_CALLEE = re.compile(r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*$")
_DEFAULT_GET_CALLS = {"_cf", "api", "apiFetch", "cf", "fetch", "fn", "getJSON"}
_HTTP_METHOD_CALLS = {
    "delete": "DELETE",
    "get": "GET",
    "patch": "PATCH",
    "post": "POST",
    "put": "PUT",
}


def _is_skipped_directory(part: str) -> bool:
    lowered = part.lower()
    return (
        lowered in _SKIP_DIRECTORIES
        or lowered == "dist"
        or lowered.startswith("dist-")
        or lowered.startswith(".next")
    )


def _is_excluded_file(path: Path) -> bool:
    lowered = path.name.lower()
    return (
        lowered.endswith(".min.js")
        or lowered.endswith(".bundle.js")
        or ".spec." in lowered
        or ".test." in lowered
    )


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


def _validate_source(source: str, relative: str, path: Path) -> None:
    if _EMPTY_ASSIGNMENT.search(source):
        raise RouteScanConfigurationError(f"Web source cannot be parsed: {relative}")
    if path.suffix.lower() in {".cjs", ".js", ".mjs"} and shutil.which("node"):
        result = subprocess.run(
            ["node", "--check", str(path)], capture_output=True, text=True, check=False
        )
        if result.returncode:
            raise RouteScanConfigurationError(f"Web source cannot be parsed: {relative}")


def _common_base(roots: Sequence[Path]) -> Path:
    candidates = [path if path.is_dir() else path.parent for path in roots]
    common = Path(os.path.commonpath([str(path) for path in candidates]))
    return common.parent if common in candidates else common


def _iter_sources(roots: Sequence[Path]) -> tuple[Path, tuple[Path, ...]]:
    if not roots:
        raise RouteScanConfigurationError("Web scan roots must contain paths")
    resolved = tuple(Path(path).resolve() for path in roots)
    if any(not path.exists() for path in resolved):
        missing = next(path for path in resolved if not path.exists())
        raise RouteScanConfigurationError(f"Web consumer root is missing: {missing}")
    common_base = _common_base(resolved)
    seen: set[Path] = set()
    sources: list[Path] = []
    for root in resolved:
        candidates: Iterable[Path] = root.rglob("*") if root.is_dir() else (root,)
        for candidate in candidates:
            if not candidate.is_file() or candidate in seen:
                continue
            if candidate.suffix.lower() not in _SOURCE_SUFFIXES or _is_excluded_file(candidate):
                continue
            relative_parts = candidate.relative_to(root).parts if root.is_dir() else ()
            if any(_is_skipped_directory(part) for part in relative_parts):
                continue
            seen.add(candidate)
            sources.append(candidate)
    return common_base, tuple(sorted(sources, key=lambda path: path.as_posix()))


def normalize_route(route: str) -> str:
    """Conservatively canonicalize one literal route for exact joins."""

    path = route.split("?", 1)[0].split("#", 1)[0]
    path = _TEMPLATE_EXPRESSION.sub("{dynamic}", path)
    path = _ROUTE_PARAMETER.sub("{dynamic}", path)
    segments: list[str] = []
    for segment in path.split("/"):
        if "{dynamic}" in segment:
            if not segment.startswith("{dynamic}:") and segment != "{dynamic}":
                segment = "{dynamic}"
        segments.append(segment)
    normalized = "/".join(segments)
    if normalized != "/api/":
        normalized = normalized.rstrip("/")
    return normalized


def _find_call(source: str, literal_start: int) -> tuple[str, int] | None:
    open_paren = source.rfind("(", max(0, literal_start - 160), literal_start)
    if open_paren < 0:
        return None
    callee_source = source[max(0, open_paren - 120):open_paren].rstrip()
    if callee_source.endswith("?."):
        callee_source = callee_source[:-2].rstrip()
    match = _CALLEE.search(callee_source)
    if match is None:
        return None
    return match.group(1), open_paren


def _matching_paren(source: str, open_paren: int) -> int:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(open_paren, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return min(len(source), open_paren + 2000)


def _method_for_occurrence(source: str, literal_start: int) -> str | None:
    call = _find_call(source, literal_start)
    if call is None:
        return None
    callee, open_paren = call
    method_argument = _METHOD_ARGUMENT.match(source[open_paren + 1:literal_start])
    if method_argument:
        return method_argument.group(1).upper()
    call_text = source[open_paren:_matching_paren(source, open_paren) + 1]
    explicit = _EXPLICIT_METHOD.search(call_text)
    if explicit:
        return explicit.group(1).upper()
    final_name = callee.rsplit(".", 1)[-1]
    if final_name in _HTTP_METHOD_CALLS:
        return _HTTP_METHOD_CALLS[final_name]
    if final_name in _DEFAULT_GET_CALLS:
        return "GET"
    return None


def _raw_route(source: str, literal_end: int, fragment: str) -> str:
    if fragment.endswith("/") and re.match(
        r"\s*\+\s*[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*",
        source[literal_end:literal_end + 160],
    ):
        return fragment + "${dynamic}"
    return fragment


def _canonical_index(
    index: Iterable[tuple[str, str]] | Mapping[tuple[str, str], object],
) -> set[tuple[str, str]]:
    keys = index.keys() if isinstance(index, Mapping) else index
    result: set[tuple[str, str]] = set()
    for key in keys:
        if (
            not isinstance(key, tuple)
            or len(key) != 2
            or not isinstance(key[0], str)
            or not isinstance(key[1], str)
        ):
            raise RouteScanConfigurationError("route indexes must use (method, route) keys")
        result.add((key[0].upper(), normalize_route(key[1])))
    return result


def _parse_expiry(value: str, context: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RouteScanConfigurationError(f"invalid operations exclusion expiry: {context}") from exc
    if parsed.tzinfo is None:
        raise RouteScanConfigurationError(f"operations exclusion expiry requires timezone: {context}")
    return parsed


def _validate_exclusions(
    exclusions: Sequence[OperationsExclusion],
) -> tuple[OperationsExclusion, ...]:
    seen: set[tuple[str, str]] = set()
    validated: list[OperationsExclusion] = []
    now = datetime.now(timezone.utc)
    for item in exclusions:
        if not isinstance(item, OperationsExclusion):
            raise RouteScanConfigurationError("operations exclusion must be an object")
        method = item.route_method.upper()
        route = normalize_route(item.normalized_route)
        context = f"{method} {route}"
        if not item.normalized_route.startswith("/api/"):
            raise RouteScanConfigurationError(f"invalid operations exclusion route: {context}")
        if "*" in item.normalized_route:
            raise RouteScanConfigurationError(f"operations exclusion wildcard is forbidden: {context}")
        if not item.owner.strip():
            raise RouteScanConfigurationError(f"operations exclusion owner is required: {context}")
        if not item.reason.strip():
            raise RouteScanConfigurationError(f"operations exclusion reason is required: {context}")
        if not item.approval_reference.strip():
            raise RouteScanConfigurationError(f"operations exclusion approval is required: {context}")
        if _parse_expiry(item.expires_at, context).astimezone(timezone.utc) <= now:
            raise RouteScanConfigurationError(f"operations exclusion expired: {context}")
        key = method, route
        if key in seen:
            raise RouteScanConfigurationError(f"duplicate operations exclusion: {context}")
        seen.add(key)
        validated.append(replace(item, route_method=method, normalized_route=route))
    return tuple(validated)


def load_operations_exclusions(path: Path) -> tuple[OperationsExclusion, ...]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RouteScanConfigurationError(f"invalid operations exclusions: {path}") from exc
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise RouteScanConfigurationError("unsupported operations exclusions schema version")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise RouteScanConfigurationError("operations exclusions entries must be an array")
    required = (
        "route_method",
        "normalized_route",
        "owner",
        "reason",
        "approval_reference",
        "expires_at",
    )
    parsed: list[OperationsExclusion] = []
    for raw in entries:
        if (
            not isinstance(raw, dict)
            or set(raw) != set(required)
            or any(not isinstance(raw.get(field), str) for field in required)
        ):
            raise RouteScanConfigurationError("operations exclusion has invalid fields")
        parsed.append(OperationsExclusion(**{field: raw[field] for field in required}))
    return _validate_exclusions(parsed)


def _disposition(
    method: str | None,
    route: str,
    legacy_index: set[tuple[str, str]],
    bff_index: set[tuple[str, str]],
    operations_index: set[tuple[str, str]],
) -> str:
    if route.startswith("/api/v1/capabilities/") or route.startswith("/api/capabilities/"):
        return "capability"
    if method is None:
        return "unresolved"
    key = method, route
    matches = [
        disposition
        for disposition, index in (
            ("legacy_registered", legacy_index),
            ("bff_registered", bff_index),
            ("operations_excluded", operations_index),
        )
        if key in index
    ]
    if len(matches) > 1:
        raise RouteScanConfigurationError(
            f"route has overlapping dispositions: {method} {route}"
        )
    return matches[0] if matches else "unresolved"


def scan_web_api_routes(
    roots: Sequence[Path],
    legacy_index: Iterable[tuple[str, str]] | Mapping[tuple[str, str], object],
    bff_index: Iterable[tuple[str, str]] | Mapping[tuple[str, str], object],
    exclusions: Sequence[OperationsExclusion],
    frontend_revision: str,
    *,
    classification_prefixes: Sequence[str] = (),
) -> RouteScanReport:
    """Discover every source ``/api/`` occurrence and assign one disposition."""

    if not isinstance(frontend_revision, str) or not frontend_revision:
        raise RouteScanConfigurationError("frontend revision is required")
    common_base, sources = _iter_sources(roots)
    legacy_keys = _canonical_index(legacy_index)
    bff_keys = _canonical_index(bff_index)
    operations = _validate_exclusions(exclusions)
    operations_keys = {item.key for item in operations}
    prefixes = tuple(sorted(set(classification_prefixes)))
    routes: list[RouteUse] = []
    digest = hashlib.sha256()
    for path in sources:
        relative = path.relative_to(common_base).as_posix()
        source = path.read_text(encoding="utf-8")
        _validate_source(source, relative, path)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(source.encode("utf-8"))
        digest.update(b"\0")
        scan_source = _mask_comments(source)
        for match in _ROUTE_LITERAL.finditer(scan_source):
            literal_start = match.start()
            literal_end = match.end()
            raw_fragment = source[match.start("route"):match.end("route")]
            raw_route = _raw_route(source, literal_end, raw_fragment)
            normalized = normalize_route(raw_route)
            route_offset = match.start("route")
            line = source.count("\n", 0, route_offset) + 1
            line_start = source.rfind("\n", 0, route_offset) + 1
            column = route_offset - line_start + 1
            method = _method_for_occurrence(source, literal_start)
            disposition = _disposition(
                method, normalized, legacy_keys, bff_keys, operations_keys
            )
            prefix = next(
                (
                    value
                    for value in prefixes
                    if normalized == value or normalized.startswith(value + "/")
                ),
                None,
            )
            occurrence_id = f"{relative}:{line}:{column}:{method or 'UNKNOWN'}:{normalized}"
            routes.append(
                RouteUse(
                    source=relative,
                    line=line,
                    column=column,
                    raw_route=raw_route,
                    normalized_route=normalized,
                    method=method,
                    disposition=disposition,
                    occurrence_id=occurrence_id,
                    classification_prefix=prefix,
                )
            )
    routes.sort(
        key=lambda item: (
            item.source,
            item.line,
            item.column,
            item.method or "",
            item.normalized_route,
        )
    )
    identities = [route.occurrence_id for route in routes]
    if len(identities) != len(set(identities)):
        raise RouteScanConfigurationError("duplicate canonical occurrence identity")
    scan_roots = tuple(
        Path(path).resolve().relative_to(common_base).as_posix() for path in roots
    )
    return RouteScanReport(
        frontend_revision=frontend_revision,
        content_hash=digest.hexdigest(),
        scan_roots=scan_roots,
        excluded_roots=_EXCLUDED_ROOTS,
        routes=tuple(routes),
        legacy_prefixes=prefixes,
    )


def _relative_path(root: Path, value: str) -> Path:
    pure = PurePosixPath(value)
    if not value or "\\" in value or pure.is_absolute() or ".." in pure.parts:
        raise RouteScanConfigurationError("Web consumer root must be repository-relative")
    return root.joinpath(*pure.parts)


def scan_web_routes(
    root: Path,
    *,
    roots: Sequence[str],
    legacy_prefixes: Sequence[str],
    allowlisted_legacy_routes: Sequence[str] = (),
) -> RouteScanReport:
    """Compatibility wrapper for callers of the former prefix-only scanner."""

    if not roots or not all(isinstance(value, str) and value for value in roots):
        raise RouteScanConfigurationError("Web consumer roots must contain paths")
    if not legacy_prefixes or not all(
        isinstance(value, str) and value.startswith("/api/") for value in legacy_prefixes
    ):
        raise RouteScanConfigurationError("legacy route prefixes must be /api/ paths")
    if any(
        not isinstance(value, str) or not value.startswith("/api/")
        for value in allowlisted_legacy_routes
    ):
        raise RouteScanConfigurationError("allowlisted routes must be /api/ paths")
    report = scan_web_api_routes(
        [_relative_path(Path(root).resolve(), value) for value in roots],
        legacy_index=(),
        bff_index=(),
        exclusions=(),
        frontend_revision="compatibility-scan",
        classification_prefixes=legacy_prefixes,
    )
    selected: list[RouteUse] = []
    for route in report.routes:
        if route.disposition == "capability":
            selected.append(replace(route, legacy_kind="capability"))
        elif route.classification_prefix is not None:
            kind = "allowlisted" if route.raw_route in allowlisted_legacy_routes else "legacy"
            selected.append(replace(route, legacy_kind=kind))
    return replace(report, routes=tuple(selected), legacy_prefixes=tuple(legacy_prefixes))


__all__ = [
    "OperationsExclusion",
    "RouteScanConfigurationError",
    "RouteScanReport",
    "RouteUse",
    "load_operations_exclusions",
    "normalize_route",
    "scan_web_api_routes",
    "scan_web_routes",
]
