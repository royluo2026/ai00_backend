"""Resolve TC labels across new rows and rows retained by import deduplication."""
from collections import defaultdict
import json


def fingerprint(row):
    return tuple(row.get(key) or "" for key in ("node_type", "title", "vpps", "vpps_desc")) + (
        row.get("parent_bop_label") or row.get("parent_label") or row.get("parent_bop_title") or "",
    )


def metadata(row):
    value = row.get("meta") or {}
    if isinstance(value, str):
        value = json.loads(value)
    return value if isinstance(value, dict) else {}


def existing_label_index(existing, source):
    """Prefer persisted TC identities/edges; use the full import fingerprint as fallback."""
    labels = defaultdict(set)
    by_fingerprint = defaultdict(set)
    gids = {row["gid"] for row in existing}
    for row in existing:
        by_fingerprint[fingerprint(row)].add(row["gid"])
        meta = metadata(row)
        if meta.get("tc_bom_label"):
            labels[meta["tc_bom_label"]].add(row["gid"])
        parent_label = row.get("parent_bop_label") or row.get("parent_bop_title")
        if parent_label and row.get("parent_gid") in gids:
            labels[parent_label].add(row["parent_gid"])
    fallback = defaultdict(set)
    for row in source:
        label = row.get("bom_row_label") or row.get("label")
        if label:
            fallback[label].update(by_fingerprint[fingerprint(row)])
    for label, candidates in fallback.items():
        if label not in labels and candidates:
            labels[label] = candidates
    return labels


def resolve_parent(label, labels):
    if not label:
        return None
    candidates = labels.get(label)
    if candidates is None and '/' not in label:
        short = label.split('/')[0].strip()
        candidates = set().union(*(gids for key, gids in labels.items() if key.split('/')[0].strip() == short))
    candidates = candidates or set()
    if len(candidates) != 1:
        reason = "ambiguous" if candidates else "missing"
        raise ValueError(f"TC parent is {reason}: {label}")
    return next(iter(candidates))
