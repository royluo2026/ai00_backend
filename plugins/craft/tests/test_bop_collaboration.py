import pytest


def service_with_proposal():
    from plugins.craft.craft_backend.data.bop_collaboration import CollaborationService
    service=CollaborationService(); proposal=service.create_proposal(repository_gid="10",personal_space_gid="20",personal_version_gid="30",team_base_version_gid="40",components=[{"component_gid":"101"},{"component_gid":"102"}],actor_gid="50")
    service.submit(proposal["proposal_gid"]);service.review(proposal["proposal_gid"],{"101":"accepted","102":"accepted"})
    return service,proposal


def test_partially_applied_is_not_terminal_and_accepted_cannot_withdraw():
    from plugins.craft.craft_backend.data.bop_collaboration import ProposalError
    service,proposal=service_with_proposal(); result=service.apply_component(proposal["proposal_gid"],component_gid="101")
    assert result["apply_status"]=="partially_applied" and result["is_terminal"] is False
    with pytest.raises(ProposalError,match="proposal_not_withdrawable"):service.withdraw(proposal["proposal_gid"])


def test_component_apply_is_idempotent_and_finishes_only_after_all_components():
    service,proposal=service_with_proposal(); first=service.apply_component(proposal["proposal_gid"],component_gid="101"); replay=service.apply_component(proposal["proposal_gid"],component_gid="101")
    assert replay==first
    assert service.apply_component(proposal["proposal_gid"],component_gid="102")["apply_status"]=="applied"


def test_private_export_scope_is_rechecked_for_preview_and_apply():
    from plugins.craft.craft_backend.data.bop_collaboration import CollaborationService,ProposalError
    service=CollaborationService(export_resolver=lambda ref:{"actor_gid":"50","tenant_gid":"60","target_personal_space_gid":"20","target_repository_gid":"10","consumer":"craft.bop.managed_personal_space.import.preview@1","content_hash":"sha256:"+"a"*64})
    preview=service.preview_private_import(export_ref="opaque",actor_gid="50",tenant_gid="60",personal_space_gid="20",repository_gid="10")
    with pytest.raises(ProposalError,match="private_export_invalid"):service.apply_private_import(preview["preview_gid"],export_ref="changed",actor_gid="50",tenant_gid="60",personal_space_gid="20",repository_gid="10")


def test_sync_preview_rejects_stale_team_head():
    from plugins.craft.craft_backend.data.bop_collaboration import CollaborationService,ProposalError
    service=CollaborationService()
    with pytest.raises(ProposalError,match="team_head_advanced"):service.preview_sync(base_version_gid="1",recorded_team_head_gid="2",current_team_head_gid="3")


def test_candidate_create_does_not_accept_renderer_diff_components():
    from plugins.craft.craft_backend.capabilities.bop_collaboration import candidate_specs
    create=next(s for s,_ in candidate_specs() if s.id=="craft.bop.change_proposal.create")
    assert "components" not in create.input_schema["properties"]
    ids={s.id for s,_ in candidate_specs()}
    assert {"craft.bop.repository_diff.start","craft.bop.repository_diff.get","craft.bop.managed_personal_space.sync.apply"}<=ids
    from plugins.craft.craft_backend.capabilities.provider import descriptor_for
    apply=next(s for s,_ in candidate_specs() if s.id=="craft.bop.change_proposal.apply")
    assert descriptor_for(apply).resource_selectors[0].resource_type=="craft-bop-proposal"


def test_mysql_service_resolves_three_way_members_and_uses_operation_ledger():
    from pathlib import Path
    source=Path("plugins/craft/craft_backend/data/bop_collaboration_mysql.py").read_text(encoding="utf-8")
    assert "_resolve_components" in source
    assert "workmanship_craft_bop_space_version_members" in source
    assert "workmanship_craft_bop_space_head_members" in source
    assert "workmanship_craft_bop_operation_ledger" in source
    assert "workmanship_sim_" not in source


def test_review_requires_dependency_closure():
    from plugins.craft.craft_backend.data.bop_collaboration import CollaborationService,ProposalError
    s=CollaborationService();p=s.create_proposal(repository_gid="10",personal_space_gid="20",personal_version_gid="30",team_base_version_gid="40",components=[{"component_gid":"1"},{"component_gid":"2","dependencies":["1"]}],actor_gid="50");s.submit(p["proposal_gid"])
    with pytest.raises(ProposalError,match="dependency_closure_not_accepted"):s.review(p["proposal_gid"],{"1":"rejected","2":"accepted"})


def test_apply_requires_dependency_component_first():
    from plugins.craft.craft_backend.data.bop_collaboration import CollaborationService,ProposalError
    s=CollaborationService();p=s.create_proposal(repository_gid="10",personal_space_gid="20",personal_version_gid="30",team_base_version_gid="40",components=[{"component_gid":"1"},{"component_gid":"2","dependencies":["1"]}],actor_gid="50");s.submit(p["proposal_gid"]);s.review(p["proposal_gid"],{"1":"accepted","2":"accepted"})
    with pytest.raises(ProposalError,match="dependency_closure_not_accepted"):s.apply_component(p["proposal_gid"],component_gid="2")
