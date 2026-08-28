"""Generate human and machine contracts from one immutable Catalog Release."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from backend.capability_v2.catalog import CatalogRelease
from backend.capability_v2.contracts import CapabilityDescriptorV2


STANDARD_ERRORS = (
    ("catalog_resolution_failed", "目录 release、能力 ID 或主版本无法解析。"),
    ("consumer_not_allowed", "当前消费者类型未获 exposure 授权。"),
    ("authorization_failed", "授权后端不可用或无法形成可信决策。"),
    ("permission_denied", "调用者缺少能力要求的权限。"),
    ("tenant_scope_denied", "身份与授权租户不一致。"),
    ("resource_scope_denied", "目标资源不在授权或 Delegation 范围内。"),
    ("data_scope_denied", "数据分类不在授权范围内。"),
    ("delegation_required", "Agent/委托消费者缺少服务端 Delegation。"),
    ("delegation_expired", "Delegation 已过期。"),
    ("resource_selector_missing", "描述符要求的资源定位字段缺失。"),
    ("resource_selector_invalid", "资源定位字段不是允许的标量标识。"),
    ("invalid_input", "请求不符合该 release 中冻结的输入 Schema。"),
    ("expected_resource_version_required", "该能力要求信封提供预期资源版本。"),
    ("expected_resource_version_payload_missing", "描述符声明的基线版本字段未出现在 payload。"),
    ("expected_resource_version_mismatch", "信封预期版本与 payload 基线版本不一致。"),
    ("confirmation_required", "写操作需要绑定本次请求的一次性审批。"),
    ("confirmation_rejected", "审批无效、已用、已过期或与请求绑定不一致。"),
    ("idempotency_key_required", "描述符要求写请求提供幂等键。"),
    ("idempotency_payload_conflict", "同一幂等范围被用于不同 payload。"),
    ("idempotency_in_progress", "同一幂等请求仍在执行。"),
    ("rate_limit_exceeded", "租户及消费者配额不足，可按 retryable 指示重试。"),
    ("transaction_participant_required", "强一致写 Provider 未加入领域事务。"),
    ("provider_failed", "领域 Provider 执行失败；错误正文不会泄露内部细节。"),
    ("outcome_persistence_failed", "领域可能已提交但 Outcome 未能确认，必须查询 OperationRef。"),
    ("operation_service_unavailable", "能力要求异步 Operation，但持久化 Operation 服务未配置。"),
    ("operation_create_failed", "异步 Operation 无法持久化，领域任务未派发。"),
    ("operation_create_outcome_failed", "异步 Operation 创建后的命令 Outcome 无法持久化，领域任务未派发。"),
)

CANONICAL_DOMAINS = (
    "base", "agent", "craft", "digital_model", "factory", "project_management",
    "simulation", "ontology", "knowledge", "integration", "device",
)

DOMAIN_DOC_PATHS = {
    "base": "base-platform",
    "agent": "agent",
    "craft": "craft",
    "digital_model": "digital-model",
    "factory": "factory",
    "project_management": "project-management",
    "simulation": "simulation",
    "ontology": "ontology",
    "knowledge": "knowledge",
    "integration": "integration",
    "device": "local-runtime",
}


@dataclass(frozen=True)
class DocumentationBundle:
    machine_catalog: dict[str, Any]
    files: dict[str, str]


def example_for_schema(schema: Mapping[str, Any]) -> Any:
    """Build one deterministic minimal value for the supported boundary subset."""
    if "const" in schema:
        return schema["const"]
    if schema.get("enum"):
        return schema["enum"][0]
    for union in ("oneOf", "anyOf"):
        branches = schema.get(union)
        if branches:
            return example_for_schema(branches[0])
    if schema.get("allOf"):
        values = [example_for_schema(branch) for branch in schema["allOf"]]
        if all(isinstance(value, dict) for value in values):
            merged: dict[str, Any] = {}
            for value in values:
                merged.update(value)
            return merged
        return values[-1]
    if "default" in schema:
        return schema["default"]
    if "example" in schema:
        return schema["example"]
    expected = schema.get("type")
    if expected == "object":
        properties = schema.get("properties") or {}
        return {
            name: example_for_schema(properties.get(name) or {})
            for name in schema.get("required") or ()
        }
    if expected == "array":
        count = max(0, int(schema.get("minItems", 0)))
        return [example_for_schema(schema.get("items") or {}) for _ in range(count)]
    if expected == "integer":
        return int(schema.get("minimum", 0))
    if expected == "number":
        return float(schema.get("minimum", 0))
    if expected == "boolean":
        return False
    if expected == "null":
        return None
    if expected == "string":
        if schema.get("pattern") == "^sha256:[0-9a-f]{64}$":
            return "sha256:" + "0" * 64
        minimum = max(1, int(schema.get("minLength", 0)))
        return "example" if minimum <= 7 else "x" * minimum
    # V1 descriptors may declare a required field without a type. Preserve its
    # openness explicitly while still producing an executable example.
    return "example"


def _contains_untyped_property(schema: Mapping[str, Any]) -> bool:
    properties = schema.get("properties") or {}
    if any(not value for value in properties.values() if isinstance(value, Mapping)):
        return True
    for value in properties.values():
        if isinstance(value, Mapping) and _contains_untyped_property(value):
            return True
    items = schema.get("items")
    return isinstance(items, Mapping) and _contains_untyped_property(items)


def _machine_item(descriptor: CapabilityDescriptorV2, release_id: str) -> dict[str, Any]:
    item = descriptor.model_dump(mode="json")
    item["catalog_release"] = release_id
    item["minimal_input_example"] = example_for_schema(descriptor.input_schema)
    item["invoke"] = {
        "capability_id": descriptor.id,
        "major_version": descriptor.major_version,
        "catalog_release": release_id,
        "payload": item["minimal_input_example"],
    }
    partial_schema = _contains_untyped_property(descriptor.input_schema) or _contains_untyped_property(
        descriptor.output_schema
    )
    item["schema_precision"] = "legacy_partial" if partial_schema else "typed"
    item["exposure_blockers"] = [
        *(["legacy_partial_schema"] if partial_schema else []),
        *([] if descriptor.domain_errors_complete else ["domain_errors_not_declared"]),
        *(["experimental_lifecycle"] if descriptor.lifecycle_status.value == "experimental" else []),
    ]
    item["gateway_errors"] = [code for code, _meaning in STANDARD_ERRORS]
    item["domain_errors_complete"] = descriptor.domain_errors_complete
    return item


def build_documentation(release: CatalogRelease) -> DocumentationBundle:
    unknown_owners = sorted({
        descriptor.owner_domain for descriptor in release.descriptors
        if descriptor.owner_domain not in CANONICAL_DOMAINS
    })
    if unknown_owners:
        raise ValueError(f"catalog contains non-canonical owner domains: {unknown_owners}")
    capabilities = [
        _machine_item(descriptor, release.release_id)
        for descriptor in sorted(release.descriptors, key=lambda value: (value.owner_domain, value.id, value.major_version))
    ]
    agent_tools = [
        {
            **item,
            "name": item["id"],
            "strict": True,
            "inputSchema": item["input_schema"],
        }
        for item in capabilities if item["exposure"]["agent"]
    ]
    mcp_tools = [
        {
            **item,
            "name": item["id"],
            "inputSchema": item["input_schema"],
        }
        for item in capabilities if item["exposure"]["mcp"]
    ]
    openapi_paths = {
        f"/api/v1/capabilities/{item['id']}:invoke": {
            "post": {
                "operationId": f"invoke_{item['id'].replace('.', '_').replace('-', '_')}_v{item['major_version']}",
                "summary": item["title"],
                "description": item["description"],
                "x-ai00-catalog-release": release.release_id,
                "x-ai00-major-version": item["major_version"],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": item["input_schema"]}},
                },
                "responses": {
                    "200": {
                        "description": "CapabilityResultV2",
                        "content": {"application/json": {"schema": _result_schema(item)}},
                    }
                },
            }
        }
        for item in capabilities if item["exposure"]["api"]
    }
    machine = {
        "schema_version": 2,
        "release_id": release.release_id,
        "catalog_hash": release.catalog_hash,
        "provider_artifacts": [item.model_dump(mode="json") for item in release.provider_artifacts],
        "capabilities": capabilities,
        "agent_tools": agent_tools,
        "mcp_tools": mcp_tools,
        "openapi_fragment": {
            "openapi": "3.1.0",
            "info": {"title": "AI00 Capability V2", "version": release.release_id},
            "paths": openapi_paths,
        },
    }
    files = _render_files(machine)
    return DocumentationBundle(machine_catalog=machine, files=files)


def generated_files(release: CatalogRelease) -> dict[str, str]:
    return build_documentation(release).files


def _render_files(machine: dict[str, Any]) -> dict[str, str]:
    capabilities = machine["capabilities"]
    by_domain: dict[str, list[dict[str, Any]]] = {domain: [] for domain in CANONICAL_DOMAINS}
    for item in capabilities:
        by_domain.setdefault(item["owner_domain"], []).append(item)
    counts = {
        consumer: sum(bool(item["exposure"].get(consumer)) for item in capabilities)
        for consumer in ("web", "plugin", "agent", "api", "mcp", "worker", "local_runtime")
    }
    files: dict[str, str] = {
        "README.md": _readme(machine, by_domain, counts),
        "INTEGRATION.md": _integration_guide(machine),
        "SECURITY.md": _security_guide(machine),
        "ERRORS.md": _error_guide(),
        "catalog.v2.json": _json(machine),
        "agent-tools.v2.json": _json({
            "catalog_release": machine["release_id"], "tools": machine["agent_tools"],
        }),
        "mcp-tools.v2.json": _json({
            "catalog_release": machine["release_id"], "tools": machine["mcp_tools"],
        }),
        "openapi-fragment.v2.json": _json(machine["openapi_fragment"]),
    }
    for item in capabilities:
        domain_path = DOMAIN_DOC_PATHS[item["owner_domain"]]
        files[f"{domain_path}/{item['id']}@{item['major_version']}.md"] = _capability_page(item)
    files[".generated-manifest.json"] = _json({
        "schema_version": 1,
        "files": sorted([*files, ".generated-manifest.json"]),
    })
    return dict(sorted(files.items()))


def _readme(machine, by_domain, counts) -> str:
    rows = "\n".join(
        f"| `{domain}` | {len(items)} |"
        for domain, items in sorted(by_domain.items())
    )
    consumer_rows = "\n".join(f"| {name} | {count} |" for name, count in counts.items())
    return f"""# AI00 Capability V2 开发者手册

本目录由不可变 Catalog Release 自动生成，不接受手工修改。

- Catalog Release：`{machine['release_id']}`
- Catalog Hash：`{machine['catalog_hash']}`
- 描述符数量：{len(machine['capabilities'])}

## 重要边界

只有 `exposure` 对目标消费者为 `true` 的能力才可调用。出现在 User Function Registry、网页路由或源码中，并不等于插件或 Agent 已获授权。当前文档如实显示迁移状态；禁止根据名称猜测能力、主版本、权限或参数。

调用必须固定 `catalog_release + capability_id + major_version`，使用服务端可信身份，经唯一 Gateway 执行。业务字符串对 Agent/MCP 均视为不可信数据。大文件使用 `ArtifactRef`，异步、本地、设备与长任务使用 `OperationRef`。

## 领域覆盖

| 领域 | 已进入 V2 Catalog |
|---|---:|
{rows}

## 消费者可用数量

| 消费者 | 能力数 |
|---|---:|
{consumer_rows}

## 文件

- `catalog.v2.json`：完整机器目录和最小合法示例。
- `agent-tools.v2.json`：仅包含 `exposure.agent=true` 的工具。
- `mcp-tools.v2.json`：仅包含 `exposure.mcp=true` 的工具。
- `openapi-fragment.v2.json`：固定 release 的 API Schema 片段。
- `INTEGRATION.md`、`SECURITY.md`、`ERRORS.md`：接入、安全和错误处理规范。
"""


def _integration_guide(machine) -> str:
    return f"""# 插件与 AI 接入规范

目录版本：`{machine['release_id']}`。

1. Host 在安装、挂载或 Agent Run 创建时固定 Catalog Release 与主版本授权。
2. 消费者提交 payload、幂等键、预期资源版本；不得提交权限或伪造消费者身份。
3. 写操作先获取与消费者、资源、策略版本和 payload hash 绑定的一次性审批。
4. `completed` 可消费结果；`accepted` 必须轮询 `OperationRef`；`outcome_unknown` 禁止盲目重试写操作。
5. 大型数模、CAD、仿真结果只通过 `ArtifactRef` 交换，内部对象键不属于公共合同。

完整调用信封至少包含 `catalog_release`、`capability_id`、`major_version`、`payload`、可信 `identity`、`request_id` 和 `trace_id`。`idempotency_policy=required` 时必须增加 `idempotency_key`；`concurrency_policy=expected_version` 时必须增加 `expected_resource_version`，并令其与描述符 `expected_version_payload_path` 指向的 payload 值完全一致；需要确认时再传服务端签发的 `approval_reference`。

`catalog.v2.json` 每项的 `invoke` 只给出能力定位与 payload 最小结构，不包含可信身份、幂等、并发和审批字段。示例仅用于结构验证，业务标识必须替换为当前租户内已授权资源。
"""


def _security_guide(machine) -> str:
    return f"""# Capability V2 安全模型

目录版本：`{machine['release_id']}`。

- 身份：仅 Host/Backend 可签发 Web、Plugin Mount、Agent Delegation、MCP、Worker 与 Local Runtime 身份。
- 授权：能力权限、资源范围、数据分类和 delegation 取交集；任一缺失均 fail closed。
- 数据：Agent/MCP 只接收 allowlist 投影；秘密、PII、原始路径和内部异常被移除。
- 可靠性：写操作以消费者维度幂等，强一致写必须加入领域事务；Outcome 与 Audit Outbox 持久化。
- 制品：Host 生成对象键并流式校验 SHA-256/大小；租户和资源授权在下载前再次检查。
- 操作：状态转换使用版本 CAS；终态不可重开，`outcome_unknown` 只能经对账解析。

客户端报送的插件 ID、Agent Run ID、permission、source header 或对象键均不构成可信授权依据。
"""


def _error_guide() -> str:
    rows = "\n".join(f"| `{code}` | {meaning} |" for code, meaning in STANDARD_ERRORS)
    return f"""# 统一错误处理

调用方只依赖 `error.code`、`retryable`、`operation_ref` 和 correlation；不得解析展示文案或内部异常。

| 错误码 | 含义 |
|---|---|
{rows}

对于写操作，网络超时不等于失败。先用同一幂等键查询/重放 Outcome；若为 `outcome_unknown`，按 Operation 协议对账。
"""


def _capability_page(item: dict[str, Any]) -> str:
    exposure = "\n".join(
        f"| {name} | {'可用' if allowed else '不可用'} |"
        for name, allowed in item["exposure"].items()
    )
    selectors = (
        "\n".join(
            f"- `{value['resource_type']}` ← `{value['payload_path']}`（{'必填' if value['required'] else '可选'}）"
            for value in item["resource_selectors"]
        ) or "- 无资源选择器；仍受租户、身份与权限策略约束。"
    )
    errors = "\n".join(f"- `{code}`：{meaning}" for code, meaning in STANDARD_ERRORS)
    domain_errors = "\n".join(
        f"- `{value['code']}`：{value['meaning']}（retryable={str(value['retryable']).lower()}）"
        for value in item["domain_errors"]
    ) or "- 尚未声明完整领域错误；该能力不得扩大插件或 Agent 暴露。"
    concurrency_note = (
        f"- 信封 `expected_resource_version` 必须等于 payload `{item['expected_version_payload_path']}`。"
        if item.get("expected_version_payload_path") else "- 无预期版本信封要求。"
    )
    output_note = (
        "首次调用返回 `status=accepted`、`data=null` 和持久化 `operation_ref`；"
        "下列输出 Schema 适用于 Operation 完成后的领域结果。"
        if item["operation_policy"] == "required"
        else "领域数据必须符合下列 Schema，并封装在完整 `CapabilityResultV2` 中："
    )
    return f"""# {item['id']}@{item['major_version']}

{item['description']}

## 使用判断

- 适用：{item['use_when']}
- 不适用：{item['do_not_use_when']}
- 生命周期：`{item['lifecycle_status']}`
- 所属领域：`{item['owner_domain']}`
- Catalog Release：`{item['catalog_release']}`
- Schema 精度：`{item['schema_precision']}`
- 暂未开放原因：{', '.join(f'`{value}`' for value in item['exposure_blockers']) or '无'}

## 消费者可用性

| 消费者 | 状态 |
|---|---|
{exposure}

插件和 Agent 只有在上表对应值为“可用”，且安装/Mount 或 Delegation 明确授权时才可调用。

## 授权与数据边界

- 授权策略：`{item['authorization_policy']}`
- 自动化等级：`{item['automation_level']}`
- 数据分类：`{item['data_classification']}`
- Delegation：`{item['delegation_policy']}`
- 认证新鲜度：{item['required_auth_freshness_seconds']} 秒

资源选择器：
{selectors}

## 执行与可靠性

- 副作用：`{item['side_effect_level']}`
- 执行模式：`{item['execution_mode']}`
- 超时：{item['timeout_seconds']} 秒
- 审批：`{item['confirmation_policy']}`
- 幂等：`{item['idempotency_policy']}`
- 并发：`{item['concurrency_policy']}`
{concurrency_note}
- 一致性：`{item['consistency_policy']}`
- Operation：`{item['operation_policy']}`
- Artifact：`{item['artifact_policy']}`
- 审计：`{item['audit_policy']}`
- Evidence：`{item['evidence_policy']}`
- 配额成本：{item['rate_limit_cost']}

资源预算：

- `memory_class`：`{item['execution_budget']['memory_class']}`
- `max_input_bytes`：{item['execution_budget']['max_input_bytes']}
- `max_output_bytes`：{item['execution_budget']['max_output_bytes']}
- `collection_policy`：`{item['execution_budget']['collection_policy']}`
- `max_page_size`：{item['execution_budget']['max_page_size']}
- `max_parallel_per_consumer`：{item['execution_budget']['max_parallel_per_consumer']}
- `max_parallel_per_tenant`：{item['execution_budget']['max_parallel_per_tenant']}
- `overload_policy`：`{item['execution_budget']['overload_policy']}`

## 输入 Schema

```json
{json.dumps(item['input_schema'], ensure_ascii=False, sort_keys=True, indent=2)}
```

最小结构示例：

```json
{json.dumps(item['invoke'], ensure_ascii=False, sort_keys=True, indent=2)}
```

## 输出 Schema

{output_note}

```json
{json.dumps(item['output_schema'], ensure_ascii=False, sort_keys=True, indent=2)}
```

## 错误

{errors}

领域错误：

{domain_errors}

`domain_errors_complete={str(item['domain_errors_complete']).lower()}`。为 `false` 时，能力不得扩大插件或 Agent 暴露。

## 版本与迁移

主版本固定为 `{item['major_version']}`。同一稳定主版本不得破坏 Schema 或 Agent 投影；升级时并行声明新主版本，调用方显式迁移，不允许“latest”回退。
"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _result_schema(item: dict[str, Any]) -> dict[str, Any]:
    operation_ref = {
        "type": "object",
        "required": ["operation_id", "status", "version"],
        "properties": {
            "operation_id": {"type": "string"},
            "status": {"type": "string", "enum": [
                "accepted", "claimed", "preparing", "running", "post_processing",
                "completed", "failed", "cancelled", "outcome_unknown",
            ]},
            "version": {"type": "integer", "minimum": 1},
        },
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "required": [
            "ok", "status", "capability_id", "major_version", "data",
            "operation_ref", "artifact_refs", "error", "evidence", "warnings", "correlation",
        ],
        "properties": {
            "ok": {"type": "boolean"},
            "status": {"type": "string", "enum": [
                "completed", "accepted", "rejected", "failed", "outcome_unknown",
            ]},
            "capability_id": {"const": item["id"]},
            "major_version": {"const": item["major_version"]},
            "data": {"anyOf": [item["output_schema"], {"type": "null"}]},
            "operation_ref": {"anyOf": [operation_ref, {"type": "null"}]},
            "artifact_refs": {
                "type": "array", "items": {
                    "type": "object",
                    "required": ["artifact_id", "media_type", "sha256", "byte_size", "version"],
                    "properties": {
                        "artifact_id": {"type": "string"}, "media_type": {"type": "string"},
                        "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "byte_size": {"type": "integer", "minimum": 0},
                        "version": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                },
            },
            "error": {"anyOf": [
                {
                    "type": "object", "required": ["code", "message", "retryable", "details"],
                    "properties": {
                        "code": {"type": "string"}, "message": {"type": "string"},
                        "retryable": {"type": "boolean"}, "details": {"type": "object"},
                    }, "additionalProperties": False,
                },
                {"type": "null"},
            ]},
            "evidence": {"type": "array", "items": {"type": "object"}},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "correlation": {
                "type": "object", "required": ["request_id", "trace_id"],
                "properties": {
                    "request_id": {"type": "string"},
                    "trace_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                }, "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }


__all__ = [
    "DOMAIN_DOC_PATHS", "DocumentationBundle", "build_documentation", "example_for_schema",
    "generated_files",
]
