"""Scan every deployable Base web/Electron root for retired authority paths."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.git_tree import (
    list_blobs,
    path_exists,
    read_blobs,
    require_clean_paths,
    resolve_revision,
)


ROOTS = ("dist-production/packages", "dist-production/web", "packages/core/electron")
EXTENSIONS = (".cjs", ".html", ".js", ".mjs")
EXCLUSIONS: tuple[str, ...] = ()
PATTERNS = {
    "retired_electron_url_install": (
        "install-plugin-url", "plugin:install-url", "installPluginFromUrl",
        "installFromUrl(", "/bridge/plugin/install_plugin",
    ),
    "retired_electron_destructive_uninstall": ("uninstall-user-plugin", "uninstallUserPlugin", ".uninstall(", "/bridge/plugin/uninstall_plugin"),
    "stale_saved_view_rest": ("/api/views",),
    "stale_annotation_rest": ("/api/self_ann",),
    "stale_identity_rest": ("/api/users/me",),
    "silent_saved_view_local_authority": (
        "vm_views_",
        "localStorage.getItem('ai00_saved_views",
        'localStorage.getItem("ai00_saved_views',
        "tls_views_", "tls_def_",
    ),
}

_NAMED_VIEW_KEY = re.compile(
    r"(?<![A-Za-z0-9])_?(?:(?:named|saved|default)[_$]?)?views?[_$]?(?:storage[_$]?)?key\b",
    re.IGNORECASE,
)
_TLS_CONFIG_SAVED_VIEW_SIGNATURES = (
    ("vmFilters",),
    ("vmSorts",),
    ("vmFilterMode",),
    ("vmGroupBy",),
    ("field_gids",),
    ("filters", "sort"),
)
_SAVED_VIEW_CONTEXT = (
    "savedView",
    "saved_view",
    "namedView",
    "named_view",
    "view preset",
    "视图预设",
    "vmFilters",
    "vmSorts",
    "base.savedViews",
)
_LOCAL_STORAGE_CALL = re.compile(
    r"\blocalStorage\s*\.\s*(getItem|setItem|removeItem)\s*\(",
)
_LS_KEY_CALL = re.compile(r"\bthis\s*\.\s*_lsKey\s*\(\s*\)")
_FUNCTION_DECLARATION = re.compile(
    r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{",
)


def _balanced_end(text: str, start: int, opening: str, closing: str) -> int | None:
    """Return the matching delimiter without attempting to parse JavaScript."""
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in ("'", '"', "`"):
            quote = char
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index
    return None


def _split_call_arguments(arguments: str) -> list[str]:
    parts: list[str] = []
    start = 0
    stack: list[str] = []
    quote: str | None = None
    escaped = False
    pairs = {")": "(", "]": "[", "}": "{"}
    for index, char in enumerate(arguments):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in ("'", '"', "`"):
            quote = char
        elif char in "([{":
            stack.append(char)
        elif char in ")]}" and stack and stack[-1] == pairs[char]:
            stack.pop()
        elif char == "," and not stack:
            parts.append(arguments[start:index].strip())
            start = index + 1
    parts.append(arguments[start:].strip())
    return parts


def _function_scopes(text: str) -> dict[str, list[tuple[int, int]]]:
    scopes: dict[str, list[tuple[int, int]]] = {}
    for match in _FUNCTION_DECLARATION.finditer(text):
        closing = _balanced_end(text, match.end() - 1, "{", "}")
        if closing is not None:
            scopes.setdefault(match.group(1), []).append((match.end(), closing))
    return scopes


def _enclosing_scope(
    scopes: dict[str, list[tuple[int, int]]], position: int
) -> tuple[int, int] | None:
    candidates = [
        scope
        for named_scopes in scopes.values()
        for scope in named_scopes
        if scope[0] <= position <= scope[1]
    ]
    return min(candidates, key=lambda scope: scope[1] - scope[0]) if candidates else None


def _assigned_expression(identifier: str, prefix: str) -> str | None:
    assignments = list(re.finditer(
        rf"\b(?:const|let|var)\s+{re.escape(identifier)}\s*=\s*([^;\n]+)",
        prefix,
    ))
    return assignments[-1].group(1) if assignments else None


def _expression_fragments(
    text: str,
    expression: str,
    prefix: str,
    scopes: dict[str, list[tuple[int, int]]],
) -> list[str]:
    """Expand only direct local assignments and named helper bodies, one level."""
    fragments = [expression]
    identifiers = set(re.findall(r"\b[A-Za-z_$][\w$]*\b", expression))
    for identifier in identifiers:
        assigned = _assigned_expression(identifier, prefix)
        if assigned:
            fragments.append(assigned)
        if re.search(rf"\b{re.escape(identifier)}\s*\(", expression):
            fragments.extend(text[start:end] for start, end in scopes.get(identifier, ()))
    return fragments


def _has_saved_view_state(fragments: list[str]) -> bool:
    combined = "\n".join(fragments)
    return any(
        all(signature in combined for signature in signatures)
        for signatures in _TLS_CONFIG_SAVED_VIEW_SIGNATURES
    ) or any(context.lower() in combined.lower() for context in _SAVED_VIEW_CONTEXT)


def _storage_saved_view_tokens(text: str) -> set[str]:
    scopes = _function_scopes(text)
    tokens: set[str] = set()
    for match in _LOCAL_STORAGE_CALL.finditer(text):
        closing = _balanced_end(text, match.end() - 1, "(", ")")
        if closing is None:
            continue
        arguments = _split_call_arguments(text[match.end():closing])
        if not arguments:
            continue
        scope = _enclosing_scope(scopes, match.start())
        context_start, context_end = scope or (
            max(0, match.start() - 400), min(len(text), closing + 400)
        )
        context = text[context_start:context_end]
        prefix = text[context_start:match.start()]
        key_fragments = _expression_fragments(text, arguments[0], prefix, scopes)
        value_fragments = (
            _expression_fragments(text, arguments[1], prefix, scopes)
            if len(arguments) > 1 else []
        )
        saved_context = _has_saved_view_state(value_fragments or [context])
        if any("tls_cfg_" in fragment for fragment in key_fragments) and saved_context:
            tokens.add("tls_cfg_")
        if any(_LS_KEY_CALL.search(fragment) for fragment in key_fragments) and saved_context:
            tokens.add("_lsKey()")
    return tokens


def _saved_view_local_authority_tokens(text: str) -> list[str]:
    tokens = {
        token
        for token in PATTERNS["silent_saved_view_local_authority"]
        if token in text
    }
    tokens.update(_storage_saved_view_tokens(text))
    if "localStorage." in text:
        for match in _NAMED_VIEW_KEY.finditer(text):
            key_name = match.group(0)
            use = re.compile(
                rf"localStorage\.(?:get|set|remove)Item\s*\(\s*{re.escape(key_name)}\b"
            )
            if use.search(text):
                tokens.add(key_name)
    return sorted(tokens)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_report(
    frontend: Path, *, revision: str = "HEAD", mode: str = "commit"
) -> dict[str, Any]:
    frontend = frontend.resolve()
    if mode not in {"commit", "worktree"}:
        raise ValueError(f"unsupported deployable scan mode: {mode}")
    if mode == "worktree":
        require_clean_paths(frontend, ROOTS)
    commit = resolve_revision(frontend, revision)
    findings: list[dict[str, str]] = []
    root_counts = {root: 0 for root in ROOTS}
    files = []
    blobs = list_blobs(frontend, commit, ROOTS)
    payloads = read_blobs(frontend, blobs)
    for relative_root in ROOTS:
        if not path_exists(frontend, commit, relative_root):
            findings.append({"code": "missing_deployable_root", "path": relative_root, "token": ""})
    for blob in blobs:
        suffix = Path(blob.path).suffix.lower()
        if suffix not in EXTENSIONS:
            continue
        relative_root = next(root for root in ROOTS if blob.path == root or blob.path.startswith(root + "/"))
        payload = payloads[blob.oid]
        files.append({
            "path": blob.path,
            "blob_oid": blob.oid,
            "sha256": hashlib.sha256(payload).hexdigest(),
        })
        root_counts[relative_root] += 1
        text = payload.decode("utf-8", errors="replace")
        for code, tokens in PATTERNS.items():
            electron_check = code.startswith("retired_electron") and relative_root == "packages/core/electron"
            web_check = not code.startswith("retired_electron") and relative_root.startswith("dist-production")
            if code == "silent_saved_view_local_authority":
                if web_check:
                    for token in _saved_view_local_authority_tokens(text):
                        findings.append({"code": code, "path": blob.path, "token": token})
                continue
            if electron_check or web_check:
                for token in tokens:
                    if token in text:
                        findings.append({"code": code, "path": blob.path, "token": token})
    report = {
        "schema_version": 2,
        "scan_mode": mode,
        "frontend_revision": commit,
        "roots": list(ROOTS),
        "extensions": list(EXTENSIONS),
        "exclusions": list(EXCLUSIONS),
        "root_file_counts": root_counts,
        "scanned_files": len(files),
        "files": files,
        "findings": sorted(findings, key=lambda item: (item["path"], item["code"], item["token"])),
    }
    report["content_sha256"] = hashlib.sha256(_canonical(report).encode()).hexdigest()
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", type=Path, required=True)
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--mode", choices=("commit", "worktree"), default="commit")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(args.frontend, revision=args.revision, mode=args.mode)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 1 if report["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
