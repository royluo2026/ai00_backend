"""Deterministic process-level reverse capture planning."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Iterable, Mapping


@dataclass(frozen=True)
class ProcessCaptureStep:
    reverse_index: int
    process_gid: str
    operation_gids: tuple[str, ...]
    visible_occurrence_gids: tuple[str, ...]
    highlight_occurrence_gids: tuple[str, ...]
    hide_after_capture_occurrence_gids: tuple[str, ...]
    resource_occurrence_gids: tuple[str, ...]


@dataclass(frozen=True)
class ProcessCapturePlan:
    algorithm_version: str
    source_hashes: dict[str, str]
    steps: tuple[ProcessCaptureStep, ...]
    plan_hash: str


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_process_capture_plan(
    *,
    processes: Iterable[Mapping[str, object]],
    initial_loaded_occurrence_gids: Iterable[str],
    source_hashes: Mapping[str, str],
    algorithm_version: str = "process-capture.v1",
) -> ProcessCapturePlan:
    """Compute forward assembly state, then emit one reverse step per process."""
    required_hashes = {"environment", "snapshot", "bop", "profile"}
    if set(source_hashes) != required_hashes or any(not str(value) for value in source_hashes.values()):
        raise ValueError("source_hashes_invalid")
    ordered = sorted(
        (dict(item) for item in processes),
        key=lambda item: (
            float(item.get("station_order") or 0),
            float(item.get("process_order") or 0),
            str(item.get("process_gid") or ""),
        ),
    )
    loaded = {str(value) for value in initial_loaded_occurrence_gids if str(value)}
    load_owner: dict[str, str] = {}
    forward: list[dict[str, object]] = []
    for process in ordered:
        process_gid = str(process.get("process_gid") or "")
        if not process_gid:
            raise ValueError("process_gid_required")
        operations = tuple(dict(item) for item in (process.get("operations") or ()))
        operation_gids: list[str] = []
        highlights: set[str] = set()
        resources: set[str] = set()
        loads: set[str] = set()
        for operation in operations:
            operation_gid = str(operation.get("operation_gid") or "")
            if operation_gid:
                operation_gids.append(operation_gid)
            resources.update(str(value) for value in operation.get("resources", ()) if str(value))
            for raw_part in operation.get("parts", ()):
                part = dict(raw_part)
                occurrence_gid = str(part.get("occurrence_gid") or "")
                role = str(part.get("role") or "")
                if not occurrence_gid or role not in {"load", "operate"}:
                    raise ValueError("part_binding_invalid")
                highlights.add(occurrence_gid)
                if role == "load":
                    prior_owner = load_owner.setdefault(occurrence_gid, process_gid)
                    if prior_owner != process_gid:
                        raise ValueError("duplicate_load_binding")
                    loads.add(occurrence_gid)
        loaded.update(loads)
        forward.append({
            "process_gid": process_gid,
            "operation_gids": tuple(operation_gids),
            "visible": tuple(sorted(loaded)),
            "highlight": tuple(sorted(highlights)),
            "hide": tuple(sorted(loads)),
            "resources": tuple(sorted(resources)),
        })

    steps = tuple(
        ProcessCaptureStep(
            reverse_index=index,
            process_gid=str(item["process_gid"]),
            operation_gids=item["operation_gids"],  # type: ignore[arg-type]
            visible_occurrence_gids=item["visible"],  # type: ignore[arg-type]
            highlight_occurrence_gids=item["highlight"],  # type: ignore[arg-type]
            hide_after_capture_occurrence_gids=item["hide"],  # type: ignore[arg-type]
            resource_occurrence_gids=item["resources"],  # type: ignore[arg-type]
        )
        for index, item in enumerate(reversed(forward), start=1)
    )
    canonical = {
        "algorithm_version": algorithm_version,
        "source_hashes": dict(sorted((str(key), str(value)) for key, value in source_hashes.items())),
        "steps": [asdict(step) for step in steps],
    }
    return ProcessCapturePlan(
        algorithm_version=algorithm_version,
        source_hashes=canonical["source_hashes"],  # type: ignore[arg-type]
        steps=steps,
        plan_hash=_canonical_hash(canonical),
    )


__all__ = ["ProcessCapturePlan", "ProcessCaptureStep", "build_process_capture_plan"]
