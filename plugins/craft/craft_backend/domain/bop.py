from __future__ import annotations

from dataclasses import dataclass


SIX_LEVEL_BOP = ("bop_version", "line_process", "station_process", "work_position", "process", "operation")


class InvalidBopHierarchy(ValueError): pass
class StalePbomReference(ValueError): pass
class FactoryResourceUnavailable(ValueError): pass


def validate_six_level_plan(levels) -> None:
    if tuple(levels) != SIX_LEVEL_BOP:
        raise InvalidBopHierarchy(f"expected {' -> '.join(SIX_LEVEL_BOP)}")


@dataclass(frozen=True)
class BopSourceRefs:
    pbom_commit_ref: str
    ontology_release_ref: str

    def __post_init__(self):
        if not self.pbom_commit_ref.startswith("craft://pbom/"):
            raise StalePbomReference("exact PBOM CommitRef required")
        if not self.ontology_release_ref.startswith("ontology:"):
            raise ValueError("immutable Ontology release ref required")


__all__ = ["BopSourceRefs", "FactoryResourceUnavailable", "InvalidBopHierarchy", "SIX_LEVEL_BOP", "StalePbomReference", "validate_six_level_plan"]
