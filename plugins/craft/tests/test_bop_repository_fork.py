import pytest
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext


SOURCE={"source_version_gid":"100","target_project_gid":"200","fork_depth":"process","include_personal_migration":True,"expected_target_slot":0,"idempotency_key":"p1"}
APPLY={"plan_hash":"","expected_target_slot":0,"idempotency_key":"a1","allowed_decisions":[]}


def ctx(): return CapabilityContext(user_gid="30",team_gid="20",resource_refs=("project:200",))


def test_preview_apply_all_depths_and_cross_project_identity():
    from plugins.craft.craft_backend.data.bop_fork import MemoryBopForkStore
    from plugins.craft.craft_backend.capabilities.bop_repository_fork import ForkProvider
    for depth in ("all","operation","process","role","station"):
        provider=ForkProvider(MemoryBopForkStore())
        preview=provider.repository_preview({**SOURCE,"fork_depth":depth},ctx()).data
        applied=provider.repository_apply({**APPLY,"preview_gid":preview["preview_gid"],"plan_hash":preview["plan_hash"],"allowed_decisions":preview["allowed_decisions"]},ctx()).data
        assert applied["repository_gid"] != SOURCE["source_version_gid"]
        assert applied["fork_depth"]==depth


def test_apply_rejects_renderer_verdict_and_changed_plan():
    from plugins.craft.craft_backend.data.bop_fork import MemoryBopForkStore
    from plugins.craft.craft_backend.capabilities.bop_repository_fork import ForkProvider
    provider=ForkProvider(MemoryBopForkStore()); preview=provider.repository_preview(SOURCE,ctx()).data
    with pytest.raises(CapabilityBusinessError) as error:
        provider.repository_apply({**APPLY,"preview_gid":preview["preview_gid"],"plan_hash":"sha256:"+"0"*64,"owner_verdict":"copy"},ctx())
    assert error.value.code=="fork_plan_changed"


def test_personal_retry_reuses_workflow_without_repeating_team_fork():
    from plugins.craft.craft_backend.data.bop_fork import MemoryBopForkStore
    from plugins.craft.craft_backend.capabilities.bop_repository_fork import ForkProvider
    store=MemoryBopForkStore(); provider=ForkProvider(store); preview=provider.repository_preview(SOURCE,ctx()).data
    first=provider.repository_apply({**APPLY,"preview_gid":preview["preview_gid"],"plan_hash":preview["plan_hash"],"allowed_decisions":preview["allowed_decisions"]},ctx()).data
    replay=provider.repository_apply({**APPLY,"preview_gid":preview["preview_gid"],"plan_hash":preview["plan_hash"],"allowed_decisions":preview["allowed_decisions"]},ctx()).data
    assert replay==first and store.team_apply_count==1


def test_target_collision_is_rejected():
    from plugins.craft.craft_backend.data.bop_fork import MemoryBopForkStore
    from plugins.craft.craft_backend.capabilities.bop_repository_fork import ForkProvider
    store=MemoryBopForkStore(); store.occupied_projects.add(("20","200")); provider=ForkProvider(store)
    preview=provider.repository_preview(SOURCE,ctx()).data
    with pytest.raises(CapabilityBusinessError) as error:
        provider.repository_apply({**APPLY,"preview_gid":preview["preview_gid"],"plan_hash":preview["plan_hash"],"allowed_decisions":preview["allowed_decisions"]},ctx())
    assert error.value.code=="target_repository_exists"
