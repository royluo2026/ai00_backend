"""Transport-neutral Project Management value objects."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectObjectRef:
    object_ref: str
    title: str
    owner: str = "project_management"

    def __post_init__(self) -> None:
        if not self.object_ref or ":" not in self.object_ref:
            raise ValueError("object_ref must be a typed Project Management reference")
        if not self.title.strip():
            raise ValueError("title is required")
