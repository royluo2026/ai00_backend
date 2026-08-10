"""Semantic Revision adapter for reproducible Simulation runs."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from backend.capability_v2.revision.models import Change


_FIELDS = {"source", "result_artifact_refs"}


class SimulationRevisionAdapter:
    def normalize(self, content: Mapping[str, Any]) -> dict[str, Any]:
        unknown = set(content) - _FIELDS
        if unknown:
            raise ValueError(f"unknown Simulation revision field: {sorted(unknown)[0]}")
        source = content.get("source")
        artifacts = content.get("result_artifact_refs", ())
        if not isinstance(source, Mapping) or not isinstance(artifacts, Sequence):
            raise ValueError("source and result_artifact_refs are required")
        return {"source": deepcopy(dict(source)), "result_artifact_refs": [deepcopy(dict(item)) for item in artifacts]}

    def validate_changeset(self, before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
        self.normalize(before)
        self.normalize(after)

    def diff(self, before: Mapping[str, Any], after: Mapping[str, Any]) -> tuple[Change, ...]:
        old, new = self.normalize(before), self.normalize(after)
        changes: list[Change] = []
        if old["source"] != new["source"]:
            changes.append(Change(change_type="input_change", path="/source", before=old["source"], after=new["source"], breaking=True))
        if old["result_artifact_refs"] != new["result_artifact_refs"]:
            changes.append(Change(change_type="result_add", path="/result_artifact_refs", before=old["result_artifact_refs"], after=new["result_artifact_refs"]))
        return tuple(changes)

    def apply_changeset(self, before: Mapping[str, Any], changes: Sequence[Change]) -> dict[str, Any]:
        result = self.normalize(before)
        for change in changes:
            if change.change_type == "input_change" and change.path == "/source":
                result["source"] = deepcopy(change.after)
            elif change.change_type == "result_add" and change.path == "/result_artifact_refs":
                result["result_artifact_refs"] = deepcopy(change.after)
            else:
                raise ValueError(f"unsupported Simulation change: {change.change_type}")
        return self.normalize(result)

    def classify_conflict(self, path: str, base: Any, ours: Any, theirs: Any) -> str:
        return "simulation_input" if path.startswith("/source") else "simulation_result"


__all__ = ["SimulationRevisionAdapter"]
