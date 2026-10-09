"""Deterministic line-level comparison of accepted Feishu, incoming Feishu and OIS."""
from __future__ import annotations

import difflib
from dataclasses import dataclass


@dataclass(frozen=True)
class MergeResult:
    merged: str | None
    conflicts: list[dict]
    source_diff: str
    local_diff: str
    source_changed: bool


def _edits(base: list[str], changed: list[str]) -> list[tuple[int, int, list[str]]]:
    return [(a, b, changed[c:d]) for kind, a, b, c, d in
            difflib.SequenceMatcher(a=base, b=changed, autojunk=False).get_opcodes() if kind != "equal"]


def _overlap(a: tuple, b: tuple) -> bool:
    a0, a1, _ = a; b0, b1, _ = b
    if a0 == a1 and b0 == b1:
        return a0 == b0
    if a0 == a1:
        return b0 <= a0 < b1
    if b0 == b1:
        return a0 <= b0 < a1
    return max(a0, b0) < min(a1, b1)


def merge_markdown(base: str, incoming: str, local: str) -> MergeResult:
    base_lines = base.splitlines(keepends=True)
    source_lines = incoming.splitlines(keepends=True)
    local_lines = local.splitlines(keepends=True)
    source_edits = _edits(base_lines, source_lines)
    local_edits = _edits(base_lines, local_lines)
    conflicts = []
    merged_edits = list(local_edits)
    for source in source_edits:
        overlapping = [edit for edit in local_edits if _overlap(source, edit)]
        if overlapping:
            if len(overlapping) == 1 and source == overlapping[0]:
                continue
            conflicts.append({
                "base_range": [min([source[0]] + [item[0] for item in overlapping]),
                               max([source[1]] + [item[1] for item in overlapping])],
                "incoming": "".join(source[2]),
                "local": "".join("".join(item[2]) for item in overlapping),
            })
        else:
            merged_edits.append(source)
    if conflicts:
        merged = None
    else:
        cursor = 0
        result = []
        for start, end, replacement in sorted(merged_edits, key=lambda edit: (edit[0], edit[1])):
            result.extend(base_lines[cursor:start])
            result.extend(replacement)
            cursor = end
        result.extend(base_lines[cursor:])
        merged = "".join(result)
    return MergeResult(
        merged=merged, conflicts=conflicts,
        source_diff="".join(difflib.unified_diff(base_lines, source_lines, fromfile="accepted-feishu", tofile="incoming-feishu")),
        local_diff="".join(difflib.unified_diff(base_lines, local_lines, fromfile="accepted-feishu", tofile="current-markdown")),
        source_changed=incoming != base,
    )
