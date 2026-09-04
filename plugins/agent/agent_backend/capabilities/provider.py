from __future__ import annotations

import hashlib
import json

from backend.capability_v2.provider_contracts import CapabilityOutput, EvidenceRef
from backend.capability_v2.contracts import AutomationLevel, BusinessInvariantContract, CapabilityDescriptorV2, DomainErrorContract, ExecutionMode, ExposurePolicy, LifecycleStatus, SideEffectLevel
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec


ERRORS = tuple(DomainErrorContract(code=code, meaning=meaning, retryable=retryable) for code, meaning, retryable in (
    ("invalid_input", "The Agent request is invalid.", False),
    ("permission_denied", "The caller cannot access the Agent resource.", False),
    ("resource_not_found", "The Agent resource does not exist.", False),
    ("version_conflict", "The Agent resource changed concurrently.", False),
    ("catalog_release_unavailable", "The pinned Catalog release is unavailable.", True),
    ("delegation_expired", "The Agent delegation is missing or expired.", False),
    ("approval_required", "The delegated operation requires Base approval.", False),
    ("provider_unavailable", "The Agent canvas runtime adapter is unavailable.", True),
    ("runtime_timeout", "The bounded Agent canvas runtime timed out.", True),
    ("idempotency_conflict", "The Agent canvas invocation conflicts with an earlier request.", False),
    ("outcome_unknown", "The Agent canvas outcome must be reconciled.", True),
))

_CANVAS_COMMANDS = {"agent.canvas.execution.start", "agent.canvas.execution.resume"}
_CANVAS_SYNC = {"agent.workflow.node.test.execute", "agent.canvas.options.resolve"}
_MODEL_HIDDEN = {
    "agent.runtime.config.read",
}

_ORCHESTRATION_EFFECTS = {
    "agent.orchestration.panorama.read": "为授权项目读取业务全景清单，供编排画布展示当前版本。",
    "agent.orchestration.graph.read": "为授权项目读取指定版本的业务流、数据流、命令流和语义绑定图。",
    "agent.orchestration.graph.save": "将项目编排草稿以新修订版本持久化，保留可审计的节点与连线关系。",
    "agent.orchestration.version.publish": "发布经过业务契约和 Capability 引用校验的项目编排版本。",
    "agent.orchestration.binding.delete": "从项目草稿移除一个 Capability 绑定并记录变更审计。",
    "agent.orchestration.run.start": "基于已发布编排版本创建一次冻结上下文的运行实例。",
    "agent.orchestration.run.transition": "追加运行实例的受授权状态事件并保持状态机一致。",
    "agent.orchestration.metric.read": "读取项目版本的有效智能作业率与自动化流程统计快照。",
}
_ORCHESTRATION_INVARIANTS = {
    "agent.orchestration.panorama.read": ("读取结果必须受租户与项目作用域约束。", "agent.orchestration.repository.scope", "orchestration_scope_denied"),
    "agent.orchestration.graph.read": ("读取图必须对应授权项目的现行版本。", "agent.orchestration.repository.scope", "orchestration_scope_denied"),
    "agent.orchestration.graph.save": ("草稿保存必须通过修订号并保持业务流 DAG。", "agent.orchestration.repository.save_graph", "version_conflict"),
    "agent.orchestration.version.publish": ("发布版本必须通过业务契约与 Capability Catalog 校验。", "agent.orchestration.service.publish", "publish_blocked"),
    "agent.orchestration.binding.delete": ("绑定删除必须限于项目草稿并留下审计事件。", "agent.orchestration.repository.delete_binding", "orchestration_scope_denied"),
    "agent.orchestration.run.start": ("运行实例必须冻结已发布版本上下文。", "agent.orchestration.runtime.start", "invalid_transition"),
    "agent.orchestration.run.transition": ("运行状态只能沿受控状态机前进。", "agent.orchestration.runtime.advance", "invalid_transition"),
    "agent.orchestration.metric.read": ("指标只能读取通过安全和业务验收的证据快照。", "agent.orchestration.metrics.repository_evidence", "untrusted_workload_evidence"),
}


def descriptor_for(spec) -> CapabilityDescriptorV2:
    base = descriptor_from_provider_spec(spec); write = base.side_effect_level is not SideEffectLevel.READ
    interaction = spec.id in {"agent.interaction.request", "agent.script.generate", *_CANVAS_COMMANDS}
    values = {
        **base.model_dump(), "owner_domain": "agent", "lifecycle_status": LifecycleStatus.STABLE,
        "exposure": ExposurePolicy(
            web=True, api=True, plugin=True,
            agent=spec.id not in _MODEL_HIDDEN,
            mcp=spec.id not in _MODEL_HIDDEN,
        ),
        "exposure_policy_source": "provider_explicit",
        "automation_level": AutomationLevel.A1 if write else AutomationLevel.A2,
        "authorization_policy": "agent.v2:" + ",".join(spec.permissions),
        "data_classification": "confidential", "delegation_policy": "scoped",
        "agent_output_schema": base.output_schema,
        "execution_mode": ExecutionMode.CLOUD_ASYNC if interaction else base.execution_mode,
        "operation_policy": "required" if interaction else ("optional" if write and spec.id not in _CANVAS_SYNC else "none"),
        "idempotency_policy": "required" if write else "none",
        "consistency_policy": "eventual" if write else "strong",
        "evidence_policy": "required" if write else "optional",
        "domain_errors": ERRORS, "domain_errors_complete": True,
    }
    if spec.id in _ORCHESTRATION_EFFECTS:
        statement, enforcement_ref, error_code = _ORCHESTRATION_INVARIANTS[spec.id]
        effect = _ORCHESTRATION_EFFECTS[spec.id]
        values.update({
            "title": effect,
            "description": f"编排中心原子能力：{effect}",
            "business_effect": f"系统交付可审计的{effect.rstrip('。')}结果。",
            "business_acceptance_criteria": ("结果仅包含请求项目作用域内的数据。",),
            "business_invariants": (BusinessInvariantContract(
                rule_id=f"agent.orchestration.{spec.id.rsplit('.', 1)[-1]}.invariant",
                version=1, statement=statement, applies_when="每次编排中心 Gateway 调用",
                enforcement_ref=enforcement_ref, error_code=error_code,
                test_refs=("backend/tests/test_orchestration_gateway_main_e2e.py",),
            ),),
            "no_business_invariant_reason": None,
        })
    return CapabilityDescriptorV2.model_validate(values)


def write_output(capability_id: str, value, context) -> CapabilityOutput:
    """Return a committed Agent write with a durable owning-domain evidence pointer."""
    if isinstance(value, CapabilityOutput):
        return value
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    candidates = value if isinstance(value, dict) else {}
    resource_id = next((
        str(candidates[key]) for key in (
            "resource_gid", "session_gid", "run_id", "run_gid", "skill_gid",
            "flow_gid", "interaction_id", "gid",
        ) if candidates.get(key)
    ), str(getattr(context, "request_id", "") or digest.removeprefix("sha256:")))
    return CapabilityOutput(
        data=value,
        evidence=(EvidenceRef(
            kind="agent.change",
            reference=f"agent://{capability_id}/{resource_id}",
            digest=digest,
            summary="Provider-owned Agent write result.",
        ),),
    )

__all__ = ["descriptor_for", "write_output"]
