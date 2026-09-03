"""Craft-owned adapters consumed by Simulation without exposing Craft storage."""
from __future__ import annotations

from typing import Any, Mapping

from backend.capability_v2.provider_contracts import CapabilityBusinessError

from ..capabilities.bop_structure import get_execution_structure
from ..capabilities.process_screenshot import ProcessScreenshotProvider


class CraftExecutionPlanAdapter:
    def get_execution_plan(self, reference: Mapping[str, Any], context: Any) -> Mapping[str, Any]:
        structure = get_execution_structure(
            {"version_gid": str(reference["version_gid"])}, context,
        ).data
        source = structure.get("source") or {}
        if (
            int(source.get("revision") or 0) != int(reference["revision"])
            or str(structure.get("content_hash") or "") != str(reference["content_hash"])
        ):
            raise CapabilityBusinessError(
                "source_version_mismatch",
                "Craft execution plan no longer matches the pinned reference",
            )
        return structure


class CraftScreenshotAdapter:
    def __init__(self, provider: ProcessScreenshotProvider | None = None) -> None:
        self._provider = provider or ProcessScreenshotProvider()

    def attach_screenshot(self, *, context: Any, **payload: Any) -> Mapping[str, Any]:
        return self._provider.attach(payload, context).data


__all__ = ["CraftExecutionPlanAdapter", "CraftScreenshotAdapter"]
