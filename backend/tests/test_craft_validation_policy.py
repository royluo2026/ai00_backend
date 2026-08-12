from pathlib import Path

import pytest

from plugins.craft.craft_backend.validation.checks import inventory_current_vpps_checks
from plugins.craft.craft_backend.validation.policy import (
    PolicyCheck,
    PolicyGovernanceError,
    ValidationPolicy,
    normalize_check,
    publish_policy,
)


def test_mandatory_check_cannot_publish_without_source_and_owner():
    check = PolicyCheck(
        check_id="vpps.name", severity="block", source_ref="", owner="",
        scope="pbom", mechanism="deterministic", version="1", verified=True,
    )
    with pytest.raises(PolicyGovernanceError, match="source_ref.*owner"):
        publish_policy(ValidationPolicy(kind="publish_check", version="1", checks=(check,)))


def test_unverified_experience_can_only_be_hint_severity():
    check = normalize_check(PolicyCheck(
        check_id="experience.1", source_kind="experience", verified=False, severity="block",
        source_ref="case://1", owner="craft", scope="bop", mechanism="advisory", version="1",
    ))
    assert check.severity == "hint"


def test_inventory_reports_current_four_vpps_checks_as_ungoverned():
    report = inventory_current_vpps_checks()
    assert {item.check_id for item in report} == {
        "vpps.master_data", "vpps.parent", "vpps.hierarchy_prefix", "vpps.fastener_main_part",
    }
    assert all(set(item.missing_fields) >= {"source_ref", "owner", "threshold", "algorithm"} for item in report)


def test_publish_check_requires_four_replay_evidence_classes():
    check = PolicyCheck(
        check_id="x", severity="block", source_ref="standard://x", owner="craft-owner",
        scope="pbom", mechanism="deterministic", version="1", verified=True,
        threshold="zero_errors", algorithm="exact-v1",
    )
    with pytest.raises(PolicyGovernanceError, match="historical_replay"):
        publish_policy(ValidationPolicy(
            kind="publish_check", version="1", checks=(check,),
            test_evidence=("positive", "negative", "boundary"),
        ))


def test_migration_is_oceanbase_safe_and_capabilities_remain_unregistered():
    root = Path(__file__).resolve().parents[2]
    sql = (root / "backend/db/migrations/202608060004_craft_validation_policies.sql").read_text(encoding="utf-8")
    assert "JSONB" not in sql.upper() and "RETURNING" not in sql.upper()
    from backend.capability_v2.bootstrap import get_capability_registry
    ids = {spec.id for spec in get_capability_registry().list()}
    assert "craft.bop.version.validate" not in ids
    assert "craft.bop.version.publish" not in ids
    assert "craft.pbom.vpps.validate" not in ids
