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
class SourceAnchor:
    source_path: str
    start_line: int
    end_line: int
    sha256: str


@dataclass(frozen=True)
class WrapperSignature:
    route_argument: int
    method_source: str
    method_argument: int | None = None
    default_method: str | None = None
    method: str | None = None


@dataclass(frozen=True)
class WrapperContract:
    source: str
    source_sha256: str
    callee: str
    signature: WrapperSignature
    definition: SourceAnchor
    expected_definition: str


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
class LexicalNonRoute:
    source: str
    line: int
    column: int
    reason: str

    @property
    def token_id(self) -> str:
        return f"{self.source}:{self.line}:{self.column}:/api/"


@dataclass(frozen=True)
class LexicalAudit:
    token_count: int
    token_hash: str
    mapped_count: int
    reviewed_non_route_tokens: tuple[str, ...]
    unmatched_tokens: tuple[str, ...]

    def serialized(self) -> dict[str, object]:
        return {
            "token_count": self.token_count,
            "token_hash": self.token_hash,
            "mapped_count": self.mapped_count,
            "reviewed_non_route_count": len(self.reviewed_non_route_tokens),
            "reviewed_non_route_tokens": list(self.reviewed_non_route_tokens),
            "unmatched_count": len(self.unmatched_tokens),
            "unmatched_tokens": list(self.unmatched_tokens),
        }


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
    wrapper_contracts_hash: str
    scan_roots: tuple[str, ...]
    excluded_roots: tuple[str, ...]
    routes: tuple[RouteUse, ...]
    lexical_audit: LexicalAudit
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
            "wrapper_contracts_hash": self.wrapper_contracts_hash,
            "scan_roots": list(self.scan_roots),
            "excluded_roots": list(self.excluded_roots),
            "counts": self.counts,
            "lexical_audit": self.lexical_audit.serialized(),
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
_DIRECT_METHOD = re.compile(
    r"(?:\bmethod\b|['\"]method['\"])\s*:\s*['\"]([A-Za-z]+)['\"]"
)
_METHOD_ARGUMENT = re.compile(
    r"^\s*['\"](DELETE|GET|PATCH|POST|PUT)['\"]\s*,\s*$", re.IGNORECASE
)
_METHOD_VALUE = re.compile(
    r"^\s*['\"](DELETE|GET|PATCH|POST|PUT)['\"]\s*$", re.IGNORECASE
)
_METHOD_KEY = re.compile(r"(?:\bmethod\b|['\"]method['\"])\s*:")
_CALLEE = re.compile(r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*$")
_CONTRACT_CALLEE = re.compile(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_HTTP_METHODS = {"DELETE", "GET", "PATCH", "POST", "PUT"}
_WILDCARDS = frozenset("*?[]")
_DEFAULT_GET_CALLS = {"fetch"}
_METHOD_FIRST_CALLS = {"_cf"}
_OPTIONS_METHOD_CALLS = {"fetch", "_cloudFetch"}


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


def _direct_options_method(source: str, literal_end: int, call_end: int) -> str | None:
    index = literal_end
    while index < call_end and source[index].isspace():
        index += 1
    if index >= call_end or source[index] != ",":
        return None
    index += 1
    while index < call_end and source[index].isspace():
        index += 1
    if index >= call_end or source[index] != "{":
        return None
    depth = 0
    quote: str | None = None
    escaped = False
    while index < call_end:
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
        if depth == 1:
            match = _DIRECT_METHOD.match(source, index)
            if match:
                return match.group(1).upper()
        if char in {"'", '"', "`"}:
            quote = char
            index += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return None
        index += 1
    return None


def _call_arguments(
    source: str, open_paren: int, call_end: int
) -> tuple[tuple[int, int], ...]:
    arguments: list[tuple[int, int]] = []
    start = open_paren + 1
    depths = {"(": 0, "[": 0, "{": 0}
    closing = {")": "(", "]": "[", "}": "{"}
    quote: str | None = None
    escaped = False
    index = start
    while index < call_end:
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
        elif char in depths:
            depths[char] += 1
        elif char in closing:
            opened = closing[char]
            if depths[opened]:
                depths[opened] -= 1
        elif char == "," and not any(depths.values()):
            arguments.append((start, index))
            start = index + 1
        index += 1
    if source[start:call_end].strip() or arguments:
        arguments.append((start, call_end))
    return tuple(arguments)


def _object_options_method(value: str, default_method: str) -> str | None:
    stripped = value.strip()
    if not stripped:
        return default_method
    if stripped == "undefined":
        return default_method
    if not stripped.startswith("{") or not stripped.endswith("}"):
        return None
    depth = 0
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(stripped):
        char = stripped[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if depth == 1:
            direct = _DIRECT_METHOD.match(stripped, index)
            if direct:
                method = direct.group(1).upper()
                return method if method in _HTTP_METHODS else None
            if _METHOD_KEY.match(stripped, index):
                return None
        if char in {"'", '"', "`"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1
    return default_method


def _contract_method(
    contract: WrapperContract,
    source: str,
    open_paren: int,
    literal_start: int,
    literal_end: int,
) -> str | None:
    call_end = _matching_paren(source, open_paren)
    arguments = _call_arguments(source, open_paren, call_end)
    signature = contract.signature
    if signature.route_argument >= len(arguments):
        return None
    route_start, route_end = arguments[signature.route_argument]
    if not (route_start <= literal_start and literal_end <= route_end):
        return None
    if signature.method_source == "constant":
        return signature.method
    assert signature.method_argument is not None
    if signature.method_source == "method_argument":
        if signature.method_argument >= len(arguments):
            return None
        start, end = arguments[signature.method_argument]
        match = _METHOD_VALUE.fullmatch(source[start:end])
        return match.group(1).upper() if match else None
    if signature.method_argument >= len(arguments):
        return signature.default_method
    start, end = arguments[signature.method_argument]
    assert signature.default_method is not None
    return _object_options_method(source[start:end], signature.default_method)


def _method_for_occurrence(
    source: str,
    literal_start: int,
    literal_end: int,
    wrapper_contract: WrapperContract | None = None,
) -> str | None:
    call = _find_call(source, literal_start)
    if call is None:
        return None
    callee, open_paren = call
    if wrapper_contract is not None and wrapper_contract.callee == callee:
        return _contract_method(
            wrapper_contract, source, open_paren, literal_start, literal_end
        )
    method_argument = _METHOD_ARGUMENT.match(source[open_paren + 1:literal_start])
    if method_argument and callee in _METHOD_FIRST_CALLS:
        return method_argument.group(1).upper()
    call_end = _matching_paren(source, open_paren)
    explicit = (
        _direct_options_method(source, literal_end, call_end)
        if callee in _OPTIONS_METHOD_CALLS
        else None
    )
    if explicit:
        return explicit
    if callee in _DEFAULT_GET_CALLS:
        return "GET"
    return None


def _raw_route(source: str, literal_end: int, fragment: str) -> str:
    if fragment.endswith("/") and re.match(
        r"\s*\+\s*[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*",
        source[literal_end:literal_end + 160],
    ):
        return fragment + "${dynamic}"
    return fragment


def canonical_route_index(
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


def load_lexical_non_routes(path: Path) -> tuple[LexicalNonRoute, ...]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RouteScanConfigurationError(f"invalid lexical non-route exclusions: {path}") from exc
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise RouteScanConfigurationError("unsupported lexical non-route schema version")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise RouteScanConfigurationError("lexical non-route entries must be an array")
    parsed: list[LexicalNonRoute] = []
    seen: set[str] = set()
    for raw in entries:
        if (
            not isinstance(raw, dict)
            or set(raw) != {"source", "line", "column", "reason"}
            or not isinstance(raw.get("source"), str)
            or not raw["source"]
            or not isinstance(raw.get("line"), int)
            or raw["line"] < 1
            or not isinstance(raw.get("column"), int)
            or raw["column"] < 1
            or not isinstance(raw.get("reason"), str)
            or not raw["reason"].strip()
        ):
            raise RouteScanConfigurationError("lexical non-route entry has invalid fields")
        item = LexicalNonRoute(**raw)
        if item.token_id in seen:
            raise RouteScanConfigurationError(
                f"duplicate lexical non-route exclusion: {item.token_id}"
            )
        seen.add(item.token_id)
        parsed.append(item)
    return tuple(parsed)


def _exact_source_path(value: object, context: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise RouteScanConfigurationError(f"invalid wrapper contract {context}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts:
        raise RouteScanConfigurationError(f"invalid wrapper contract {context}")
    if any(character in value for character in _WILDCARDS):
        raise RouteScanConfigurationError(f"wrapper contract wildcard is forbidden: {context}")
    return value


def _wrapper_signature(raw: object) -> WrapperSignature:
    if not isinstance(raw, dict):
        raise RouteScanConfigurationError("wrapper contract signature must be an object")
    route_argument = raw.get("route_argument")
    method_source = raw.get("method_source")
    if not isinstance(route_argument, int) or isinstance(route_argument, bool) or route_argument < 0:
        raise RouteScanConfigurationError("wrapper contract route argument is invalid")
    if method_source == "constant":
        if set(raw) != {"route_argument", "method_source", "method"}:
            raise RouteScanConfigurationError("wrapper constant signature has invalid fields")
        method = raw.get("method")
        if not isinstance(method, str) or method.upper() not in _HTTP_METHODS:
            raise RouteScanConfigurationError("wrapper constant method is invalid")
        return WrapperSignature(route_argument, method_source, method=method.upper())
    if method_source == "method_argument":
        if set(raw) != {"route_argument", "method_source", "method_argument"}:
            raise RouteScanConfigurationError("wrapper method-argument signature has invalid fields")
        method_argument = raw.get("method_argument")
        if (
            not isinstance(method_argument, int)
            or isinstance(method_argument, bool)
            or method_argument < 0
            or method_argument == route_argument
        ):
            raise RouteScanConfigurationError("wrapper method argument is invalid")
        return WrapperSignature(route_argument, method_source, method_argument=method_argument)
    if method_source == "options_argument":
        if set(raw) != {
            "route_argument", "method_source", "method_argument", "default_method"
        }:
            raise RouteScanConfigurationError("wrapper options signature has invalid fields")
        method_argument = raw.get("method_argument")
        default_method = raw.get("default_method")
        if (
            not isinstance(method_argument, int)
            or isinstance(method_argument, bool)
            or method_argument < 0
            or method_argument == route_argument
            or not isinstance(default_method, str)
            or default_method.upper() not in _HTTP_METHODS
        ):
            raise RouteScanConfigurationError("wrapper options argument is invalid")
        return WrapperSignature(
            route_argument,
            method_source,
            method_argument=method_argument,
            default_method=default_method.upper(),
        )
    raise RouteScanConfigurationError("wrapper contract method source is invalid")


def load_wrapper_contracts(path: Path) -> tuple[WrapperContract, ...]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RouteScanConfigurationError(f"invalid wrapper contracts: {path}") from exc
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise RouteScanConfigurationError("unsupported wrapper contracts schema version")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise RouteScanConfigurationError("wrapper contracts entries must be an array")
    expected = {
        "source", "source_sha256", "callee", "signature", "definition",
        "expected_definition",
    }
    parsed: list[WrapperContract] = []
    seen: set[tuple[str, str]] = set()
    for raw in entries:
        if not isinstance(raw, dict) or set(raw) != expected:
            raise RouteScanConfigurationError("wrapper contract has invalid fields")
        source = _exact_source_path(raw["source"], "source")
        source_sha256 = raw["source_sha256"]
        callee = raw["callee"]
        expected_definition = raw["expected_definition"]
        if not isinstance(source_sha256, str) or _SHA256.fullmatch(source_sha256) is None:
            raise RouteScanConfigurationError("wrapper contract source hash is invalid")
        if (
            not isinstance(callee, str)
            or any(character in callee for character in _WILDCARDS)
            or _CONTRACT_CALLEE.fullmatch(callee) is None
        ):
            if isinstance(callee, str) and any(character in callee for character in _WILDCARDS):
                raise RouteScanConfigurationError("wrapper contract wildcard is forbidden: callee")
            raise RouteScanConfigurationError("wrapper contract callee is invalid")
        if not isinstance(expected_definition, str) or not expected_definition:
            raise RouteScanConfigurationError("wrapper expected definition is required")
        anchor = raw["definition"]
        if not isinstance(anchor, dict) or set(anchor) != {
            "source_path", "start_line", "end_line", "sha256"
        }:
            raise RouteScanConfigurationError("wrapper definition anchor is invalid")
        source_path = _exact_source_path(anchor["source_path"], "definition source")
        start_line = anchor["start_line"]
        end_line = anchor["end_line"]
        sha256 = anchor["sha256"]
        if (
            not isinstance(start_line, int)
            or isinstance(start_line, bool)
            or not isinstance(end_line, int)
            or isinstance(end_line, bool)
            or start_line < 1
            or end_line < start_line
            or not isinstance(sha256, str)
            or _SHA256.fullmatch(sha256) is None
        ):
            raise RouteScanConfigurationError("wrapper definition anchor is invalid")
        key = source, callee
        if key in seen:
            raise RouteScanConfigurationError(
                f"ambiguous wrapper contract: {source}:{callee}"
            )
        seen.add(key)
        parsed.append(
            WrapperContract(
                source=source,
                source_sha256=source_sha256,
                callee=callee,
                signature=_wrapper_signature(raw["signature"]),
                definition=SourceAnchor(source_path, start_line, end_line, sha256),
                expected_definition=expected_definition,
            )
        )
    return tuple(parsed)


def _validate_wrapper_contracts(
    contracts: Sequence[WrapperContract],
    sources: Mapping[str, str],
) -> dict[tuple[str, str], WrapperContract]:
    result: dict[tuple[str, str], WrapperContract] = {}
    for contract in contracts:
        if not isinstance(contract, WrapperContract):
            raise RouteScanConfigurationError("wrapper contract must be an object")
        key = contract.source, contract.callee
        if key in result:
            raise RouteScanConfigurationError(
                f"ambiguous wrapper contract: {contract.source}:{contract.callee}"
            )
        source = sources.get(contract.source)
        if source is None:
            raise RouteScanConfigurationError(
                f"wrapper contract source is stale: {contract.source}"
            )
        if hashlib.sha256(source.encode("utf-8")).hexdigest() != contract.source_sha256:
            raise RouteScanConfigurationError(
                f"wrapper contract source hash is stale: {contract.source}"
            )
        anchor = contract.definition
        definition_source = sources.get(anchor.source_path)
        if definition_source is None:
            raise RouteScanConfigurationError(
                f"wrapper contract definition source is stale: {anchor.source_path}"
            )
        lines = definition_source.splitlines(keepends=True)
        if anchor.end_line > len(lines):
            raise RouteScanConfigurationError(
                f"wrapper contract definition range is stale: {anchor.source_path}"
            )
        definition = "".join(lines[anchor.start_line - 1:anchor.end_line])
        if hashlib.sha256(definition.encode("utf-8")).hexdigest() != anchor.sha256:
            raise RouteScanConfigurationError(
                f"wrapper contract definition hash is stale: {anchor.source_path}"
            )
        if contract.expected_definition not in definition:
            raise RouteScanConfigurationError(
                f"wrapper contract definition is ambiguous: {anchor.source_path}"
            )
        result[key] = contract
    return result


def wrapper_contracts_hash(contracts: Sequence[WrapperContract]) -> str:
    serialized: list[dict[str, object]] = []
    for contract in sorted(contracts, key=lambda item: (item.source, item.callee)):
        signature = {
            "route_argument": contract.signature.route_argument,
            "method_source": contract.signature.method_source,
            "method_argument": contract.signature.method_argument,
            "default_method": contract.signature.default_method,
            "method": contract.signature.method,
        }
        serialized.append({
            "source": contract.source,
            "source_sha256": contract.source_sha256,
            "callee": contract.callee,
            "signature": signature,
            "definition": {
                "source_path": contract.definition.source_path,
                "start_line": contract.definition.start_line,
                "end_line": contract.definition.end_line,
                "sha256": contract.definition.sha256,
            },
            "expected_definition": contract.expected_definition,
        })
    payload = json.dumps(
        serialized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def classify_route_disposition(
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
    lexical_non_routes: Sequence[LexicalNonRoute] = (),
    wrapper_contracts: Sequence[WrapperContract] = (),
) -> RouteScanReport:
    """Discover every source ``/api/`` occurrence and assign one disposition."""

    if not isinstance(frontend_revision, str) or not frontend_revision:
        raise RouteScanConfigurationError("frontend revision is required")
    common_base, sources = _iter_sources(roots)
    source_documents: dict[str, str] = {}
    for path in sources:
        relative = path.relative_to(common_base).as_posix()
        source = path.read_text(encoding="utf-8")
        _validate_source(source, relative, path)
        source_documents[relative] = source
    contract_index = _validate_wrapper_contracts(wrapper_contracts, source_documents)
    legacy_keys = canonical_route_index(legacy_index)
    bff_keys = canonical_route_index(bff_index)
    operations = _validate_exclusions(exclusions)
    operations_keys = {item.key for item in operations}
    prefixes = tuple(sorted(set(classification_prefixes)))
    routes: list[RouteUse] = []
    lexical_tokens: list[str] = []
    route_token_ids: set[str] = set()
    digest = hashlib.sha256()
    for path in sources:
        relative = path.relative_to(common_base).as_posix()
        source = source_documents[relative]
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(source.encode("utf-8"))
        digest.update(b"\0")
        for token in re.finditer(r"/api/", source):
            token_line = source.count("\n", 0, token.start()) + 1
            token_line_start = source.rfind("\n", 0, token.start()) + 1
            token_column = token.start() - token_line_start + 1
            lexical_tokens.append(
                f"{relative}:{token_line}:{token_column}:/api/"
            )
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
            call = _find_call(scan_source, literal_start)
            contract = contract_index.get((relative, call[0])) if call else None
            method = _method_for_occurrence(
                scan_source, literal_start, literal_end, contract
            )
            disposition = classify_route_disposition(
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
            route_token_ids.add(f"{relative}:{line}:{column}:/api/")
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
    lexical_token_set = set(lexical_tokens)
    if len(lexical_token_set) != len(lexical_tokens):
        raise RouteScanConfigurationError("duplicate lexical token identity")
    reviewed_non_routes = {item.token_id for item in lexical_non_routes}
    stale_non_routes = reviewed_non_routes - lexical_token_set
    if stale_non_routes:
        raise RouteScanConfigurationError(
            f"stale lexical non-route exclusion: {min(stale_non_routes)}"
        )
    overlapping_non_routes = reviewed_non_routes & route_token_ids
    if overlapping_non_routes:
        raise RouteScanConfigurationError(
            f"lexical non-route exclusion hides route: {min(overlapping_non_routes)}"
        )
    unmatched_tokens = tuple(
        sorted(lexical_token_set - route_token_ids - reviewed_non_routes)
    )
    lexical_hash = hashlib.sha256()
    for token_id in sorted(lexical_token_set):
        lexical_hash.update(token_id.encode("utf-8"))
        lexical_hash.update(b"\0")
    scan_roots = tuple(
        Path(path).resolve().relative_to(common_base).as_posix() for path in roots
    )
    return RouteScanReport(
        frontend_revision=frontend_revision,
        content_hash=digest.hexdigest(),
        wrapper_contracts_hash=wrapper_contracts_hash(wrapper_contracts),
        scan_roots=scan_roots,
        excluded_roots=_EXCLUDED_ROOTS,
        routes=tuple(routes),
        lexical_audit=LexicalAudit(
            token_count=len(lexical_token_set),
            token_hash=lexical_hash.hexdigest(),
            mapped_count=len(route_token_ids),
            reviewed_non_route_tokens=tuple(sorted(reviewed_non_routes)),
            unmatched_tokens=unmatched_tokens,
        ),
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
    "SourceAnchor",
    "WrapperContract",
    "WrapperSignature",
    "OperationsExclusion",
    "LexicalAudit",
    "LexicalNonRoute",
    "RouteScanConfigurationError",
    "RouteScanReport",
    "RouteUse",
    "canonical_route_index",
    "classify_route_disposition",
    "load_operations_exclusions",
    "load_lexical_non_routes",
    "load_wrapper_contracts",
    "wrapper_contracts_hash",
    "normalize_route",
    "scan_web_api_routes",
    "scan_web_routes",
]
