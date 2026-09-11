import pytest
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext


SOURCE={"source_version_gid":"100","target_project_gid":"200","target_name":"W10 仿真副本","target_project_name":"X11-2026","fork_depth":"process","include_personal_migration":True,"expected_target_slot":0,"idempotency_key":"p1"}
APPLY={"plan_hash":"","expected_target_slot":0,"idempotency_key":"a1","allowed_decisions":[]}


def ctx(): return CapabilityContext(user_gid="30",team_gid="20",resource_refs=("project:200",),active_roles=("super_admin",))


def test_main_repository_fork_requires_trusted_super_admin_role():
    from plugins.craft.craft_backend.data.bop_fork import MemoryBopForkStore
    from plugins.craft.craft_backend.capabilities.bop_repository_fork import ForkProvider
    member=CapabilityContext(user_gid="30",team_gid="20",resource_refs=("project:200",),active_roles=("member",))
    with pytest.raises(CapabilityBusinessError) as error:
        ForkProvider(MemoryBopForkStore()).repository_preview(SOURCE,member)
    assert error.value.code=="repository_fork_super_admin_required"


def test_project_space_fork_rejects_name_equal_to_target_project():
    from plugins.craft.craft_backend.data.bop_fork import MemoryBopForkStore
    from plugins.craft.craft_backend.capabilities.bop_repository_fork import ForkProvider
    with pytest.raises(CapabilityBusinessError) as error:
        ForkProvider(MemoryBopForkStore()).repository_preview(
            {**SOURCE, "target_name": "  x11-2026  "}, ctx()
        )
    assert error.value.code == "fork_name_conflicts_with_project"


def test_preview_apply_all_depths_and_cross_project_identity():
    from plugins.craft.craft_backend.data.bop_fork import MemoryBopForkStore
    from plugins.craft.craft_backend.capabilities.bop_repository_fork import ForkProvider
    for depth in ("all","operation","process","role","station"):
        provider=ForkProvider(MemoryBopForkStore())
        preview=provider.repository_preview({**SOURCE,"fork_depth":depth},ctx()).data
        applied=provider.repository_apply({**APPLY,"preview_gid":preview["preview_gid"],"plan_hash":preview["plan_hash"],"allowed_decisions":preview["allowed_decisions"]},ctx()).data
        assert applied["repository_gid"] != SOURCE["source_version_gid"]
        assert applied["fork_depth"]==depth
        assert applied["target_name"] == "W10 仿真副本"


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


def test_default_provider_uses_persistent_store():
    from plugins.craft.craft_backend.capabilities.bop_repository_fork import ForkProvider
    from plugins.craft.craft_backend.data.bop_fork import MysqlBopForkStore
    assert isinstance(ForkProvider().store, MysqlBopForkStore)


def test_personal_preview_uses_repository_target_and_fixed_workflow():
    from plugins.craft.craft_backend.data.bop_fork import MemoryBopForkStore
    from plugins.craft.craft_backend.capabilities.bop_repository_fork import ForkProvider
    store=MemoryBopForkStore(); provider=ForkProvider(store)
    team=provider.repository_preview(SOURCE,ctx()).data
    personal=provider.personal_preview({"source_version_gid":"100","target_repository_gid":"300",
        "fork_depth":"process","workflow_gid":team["workflow_gid"],"expected_target_slot":0,
        "idempotency_key":"personal-preview"},ctx()).data
    assert personal["workflow_gid"]==team["workflow_gid"]
    assert personal["target_repository_gid"]=="300"


def test_personal_project_space_is_unique_per_user_and_project_repository():
    from plugins.craft.craft_backend.data.bop_fork import BopForkError, MemoryBopForkStore
    store = MemoryBopForkStore()
    first = store.preview_personal(
        tenant_gid="20", actor_gid="30", source_version_gid="100",
        target_repository_gid="300", fork_depth="process", expected_target_slot=0,
        idempotency_key="preview-1",
    )
    store.apply_personal(
        tenant_gid="20", actor_gid="30", preview_gid=first["preview_gid"],
        plan_hash=first["plan_hash"], allowed_decisions=[], expected_target_slot=0,
        idempotency_key="apply-1",
    )
    second = store.preview_personal(
        tenant_gid="20", actor_gid="30", source_version_gid="100",
        target_repository_gid="300", fork_depth="process", expected_target_slot=0,
        idempotency_key="preview-2",
    )
    with pytest.raises(BopForkError, match="managed_personal_space_exists"):
        store.apply_personal(
            tenant_gid="20", actor_gid="30", preview_gid=second["preview_gid"],
            plan_hash=second["plan_hash"], allowed_decisions=[], expected_target_slot=0,
            idempotency_key="apply-2",
        )


def test_completed_fork_exposes_immutable_source_reference_and_projection():
    from plugins.craft.craft_backend.data.bop_fork import MemoryBopForkStore
    from plugins.craft.craft_backend.capabilities.bop_repository_fork import ForkProvider

    store = MemoryBopForkStore()
    store.seed_projection(
        version_gid="100", repository_gid="90", content_hash="sha256:" + "a" * 64,
        nodes=[
            {"node_gid": "101", "parent_gid": None, "node_type": "line", "name": "总装线", "position": 0},
            {"node_gid": "102", "parent_gid": "101", "node_type": "station", "name": "工位 1", "position": 0},
        ],
    )
    provider = ForkProvider(store)
    preview = provider.repository_preview(SOURCE, ctx()).data
    applied = provider.repository_apply({**APPLY, "preview_gid": preview["preview_gid"],
        "plan_hash": preview["plan_hash"], "allowed_decisions": preview["allowed_decisions"]}, ctx()).data

    assert applied["source_repository_gid"] == "90"
    assert applied["source_version_gid"] == "100"
    assert applied["source_content_hash"] == "sha256:" + "a" * 64
    projection = provider.get_projection({"fork_run_gid": applied["fork_run_gid"]}, ctx()).data
    assert projection["fork_operation_gid"] == applied["fork_run_gid"]
    assert projection["nodes"][1]["parent_gid"] == "101"
    assert provider.get_projection({"fork_run_gid": applied["fork_run_gid"]}, ctx()).data == projection
