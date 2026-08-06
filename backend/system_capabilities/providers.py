"""In-process contracts for bounded cross-domain composition; providers return refs, never rows."""
from __future__ import annotations

from typing import Any


class ProviderRegistry:
    def __init__(self): self.clear()
    def clear(self) -> None:
        self.search = []
        self.activity = []
        self.jobs = {}
        self.identity = []
        self.lineage = []
        self.impact = []
        self.semantic = []
        self.projects = []
    def register_search(self, provider): self.search.append(provider)
    def register_activity(self, provider): self.activity.append(provider)
    def register_jobs(self, provider): self.jobs[str(provider.owner)] = provider
    def register_identity(self, provider): self.identity.append(provider)
    def register_lineage(self, provider): self.lineage.append(provider)
    def register_impact(self, provider): self.impact.append(provider)
    def register_semantic(self, provider): self.semantic.append(provider)
    def register_projects(self, provider): self.projects.append(provider)


provider_registry = ProviderRegistry()


SEARCH_REF_FIELDS = ("object_ref", "title", "summary", "match_reason", "owner")


def stable_ref(raw: dict[str, Any], owner: str) -> dict[str, Any] | None:
    if not raw.get("object_ref"):
        return None
    result = {key: raw.get(key) for key in SEARCH_REF_FIELDS if raw.get(key) is not None}
    result["owner"] = str(result.get("owner") or owner)
    return result
