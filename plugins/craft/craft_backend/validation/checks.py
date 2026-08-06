from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UngovernedCheck:
    check_id: str
    observed_implementation: str
    missing_fields: tuple[str, ...]


def inventory_current_vpps_checks() -> tuple[UngovernedCheck, ...]:
    missing = ("source_ref", "owner", "threshold", "algorithm", "policy_version", "replay_tests")
    return tuple(
        UngovernedCheck(check_id, "plugins/craft/craft_backend/routers/ebom.py", missing)
        for check_id in (
            "vpps.master_data", "vpps.parent", "vpps.hierarchy_prefix", "vpps.fastener_main_part",
        )
    )
