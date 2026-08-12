"""Activation-gate validation independent of transport and persistence."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

REQUIRED_PROVIDERS = frozenset({"migration", "rules", "capabilities", "plugins"})


def validate_attestations(attestations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_provider = {str(item.get("provider") or ""): item for item in attestations if isinstance(item, Mapping)}
    missing = sorted(REQUIRED_PROVIDERS - by_provider.keys())
    failed = sorted(
        provider for provider in REQUIRED_PROVIDERS & by_provider.keys()
        if by_provider[provider].get("status") != "passed" or int(by_provider[provider].get("blocking_count") or 0) != 0
    )
    return {"ok": not missing and not failed, "missing": missing, "failed": failed}
