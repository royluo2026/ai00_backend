# vismockup.capture@1

Capture the active VisMockup view as an ArtifactRef.

## 使用判断

- 适用：Capture the active VisMockup view as an ArtifactRef.
- 不适用：Use the owning domain's governed Capability.
- 生命周期：`deprecated`
- 所属领域：`device`
- Catalog Release：`rel_277fca49891059b565473ae614a948cf`
- Schema 精度：`typed`
- 暂未开放原因：无

## 消费者可用性

| 消费者 | 状态 |
|---|---|
| web | 不可用 |
| plugin | 不可用 |
| agent | 不可用 |
| api | 不可用 |
| mcp | 不可用 |
| worker | 不可用 |
| local_runtime | 可用 |

插件和 Agent 只有在上表对应值为“可用”，且安装/Mount 或 Delegation 明确授权时才可调用。

## 授权与数据边界

- 授权策略：`local-runtime.v2:agent.run`
- 自动化等级：`A1`
- 数据分类：`confidential`
- Delegation：`scoped`
- 认证新鲜度：0 秒

资源选择器：
- `device` ← `device_id`（必填）

## 执行与可靠性

- 副作用：`write`
- 执行模式：`local`
- 超时：30 秒
- 审批：`user`
- 幂等：`required`
- 并发：`none`
- 无预期版本信封要求。
- 一致性：`external`
- Operation：`required`
- Artifact：`output`
- 审计：`standard`
- Evidence：`required`
- 配额成本：1

资源预算：

- `memory_class`：`small`
- `max_input_bytes`：1048576
- `max_output_bytes`：4194304
- `collection_policy`：`bounded`
- `max_page_size`：None
- `max_parallel_per_consumer`：4
- `max_parallel_per_tenant`：32
- `overload_policy`：`reject`

## 输入 Schema

```json
{
  "additionalProperties": false,
  "properties": {
    "device_id": {
      "minLength": 1,
      "type": "string"
    }
  },
  "required": [
    "device_id"
  ],
  "type": "object"
}
```

最小结构示例：

```json
{
  "capability_id": "vismockup.capture",
  "catalog_release": "rel_277fca49891059b565473ae614a948cf",
  "major_version": 1,
  "payload": {
    "device_id": "example"
  }
}
```

## 输出 Schema

首次调用返回 `status=accepted`、`data=null` 和持久化 `operation_ref`；下列输出 Schema 适用于 Operation 完成后的领域结果。

```json
{
  "additionalProperties": false,
  "properties": {
    "command_id": {
      "minLength": 1,
      "type": "string"
    },
    "device_id": {
      "minLength": 1,
      "type": "string"
    },
    "expires_in": {
      "minimum": 1,
      "type": "integer"
    },
    "status": {
      "enum": [
        "queued"
      ],
      "type": "string"
    }
  },
  "required": [
    "command_id",
    "device_id",
    "status",
    "expires_in"
  ],
  "type": "object"
}
```

## 错误

- `catalog_resolution_failed`：目录 release、能力 ID 或主版本无法解析。
- `consumer_not_allowed`：当前消费者类型未获 exposure 授权。
- `authorization_failed`：授权后端不可用或无法形成可信决策。
- `permission_denied`：调用者缺少能力要求的权限。
- `tenant_scope_denied`：身份与授权租户不一致。
- `resource_scope_denied`：目标资源不在授权或 Delegation 范围内。
- `data_scope_denied`：数据分类不在授权范围内。
- `delegation_required`：Agent/委托消费者缺少服务端 Delegation。
- `delegation_expired`：Delegation 已过期。
- `resource_selector_missing`：描述符要求的资源定位字段缺失。
- `resource_selector_invalid`：资源定位字段不是允许的标量标识。
- `invalid_input`：请求不符合该 release 中冻结的输入 Schema。
- `expected_resource_version_required`：该能力要求信封提供预期资源版本。
- `expected_resource_version_payload_missing`：描述符声明的基线版本字段未出现在 payload。
- `expected_resource_version_mismatch`：信封预期版本与 payload 基线版本不一致。
- `confirmation_required`：写操作需要绑定本次请求的一次性审批。
- `confirmation_rejected`：审批无效、已用、已过期或与请求绑定不一致。
- `idempotency_key_required`：描述符要求写请求提供幂等键。
- `idempotency_payload_conflict`：同一幂等范围被用于不同 payload。
- `idempotency_in_progress`：同一幂等请求仍在执行。
- `rate_limit_exceeded`：租户及消费者配额不足，可按 retryable 指示重试。
- `transaction_participant_required`：强一致写 Provider 未加入领域事务。
- `provider_failed`：领域 Provider 执行失败；错误正文不会泄露内部细节。
- `outcome_persistence_failed`：领域可能已提交但 Outcome 未能确认，必须查询 OperationRef。
- `operation_service_unavailable`：能力要求异步 Operation，但持久化 Operation 服务未配置。
- `operation_create_failed`：异步 Operation 无法持久化，领域任务未派发。
- `operation_create_outcome_failed`：异步 Operation 创建后的命令 Outcome 无法持久化，领域任务未派发。

领域错误：

- `device_not_found`：The workstation is unavailable or is not owned by the caller.（retryable=false）
- `device_capability_unavailable`：The workstation does not advertise the requested capability.（retryable=true）
- `local_operation_signing_key_unavailable`：The server cannot sign a local operation.（retryable=true）
- `local_operation_failed`：The workstation returned a sanitized local execution error.（retryable=false）
- `local_operation_outcome_unknown`：Execution may have occurred and must be reconciled before retry.（retryable=true）
- `provider_unavailable`：The Local Runtime application provider is unavailable.（retryable=true）

`domain_errors_complete=true`。为 `false` 时，能力不得扩大插件或 Agent 暴露。

## 版本与迁移

主版本固定为 `1`。同一稳定主版本不得破坏 Schema 或 Agent 投影；升级时并行声明新主版本，调用方显式迁移，不允许“latest”回退。
