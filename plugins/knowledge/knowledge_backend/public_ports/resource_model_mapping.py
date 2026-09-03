"""Knowledge-owned resource-model mapping adapter for Simulation."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..capabilities.resource_model_mapping import ResourceModelMappingProvider


class KnowledgeResourceModelMappingAdapter:
    def __init__(self, provider: ResourceModelMappingProvider | None = None) -> None:
        self._provider = provider or ResourceModelMappingProvider()

    def resolve_resource_models(
        self, items: Sequence[Mapping[str, Any]], context: Any,
    ) -> Mapping[str, Any]:
        return self._provider.resolve({"items": list(items)}, context).data


__all__ = ["KnowledgeResourceModelMappingAdapter"]
