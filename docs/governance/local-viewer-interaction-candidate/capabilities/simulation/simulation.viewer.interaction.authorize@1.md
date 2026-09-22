# simulation.viewer.interaction.authorize@1

Resolve or authorize an owned current-open viewer source association.

## 使用判断

- 适用：The authenticated owner opens or renews a local interactive session.
- 不适用：There is no verified current-open binding or the caller is automated.
- 生命周期：`experimental`
- 所属领域：`simulation`
- Catalog Release：`<catalog_release>`（调用时使用 Host 当前固定的目录版本）
- Schema 精度：`typed`
- 暂未开放原因：`domain_errors_not_declared`, `experimental_lifecycle`

## 消费者可用性

| 消费者 | 状态 |
|---|---|
| web | 可用 |
| plugin | 不可用 |
| agent | 不可用 |
| api | 不可用 |
| mcp | 不可用 |
| worker | 不可用 |
| local_runtime | 不可用 |

插件和 Agent 只有在上表对应值为“可用”，且安装/Mount 或 Delegation 明确授权时才可调用。

## 授权与数据边界

- 授权策略：`simulation.v2:simulation.use`
- 自动化等级：`A1`
- 数据分类：`confidential`
- Delegation：`scoped`
- 认证新鲜度：0 秒

资源选择器：
- 无资源选择器；仍受租户、身份与权限策略约束。

## 执行与可靠性

- 副作用：`write`
- 执行模式：`cloud_sync`
- 超时：30 秒
- 审批：`none`
- 幂等：`required`
- 并发：`none`
- 无预期版本信封要求。
- 一致性：`external`
- Operation：`optional`
- Artifact：`none`
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
    "document_gid": {
      "pattern": "^[1-9][0-9]{0,19}$",
      "title": "Document Gid",
      "type": "string"
    },
    "prior_grant_id": {
      "anyOf": [
        {
          "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$",
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Prior Grant Id"
    },
    "session_nonce": {
      "pattern": "^[0-9a-f]{64}$",
      "title": "Session Nonce",
      "type": "string"
    },
    "source_association_id": {
      "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$",
      "title": "Source Association Id",
      "type": "string"
    },
    "workspace_gid": {
      "pattern": "^[1-9][0-9]{0,19}$",
      "title": "Workspace Gid",
      "type": "string"
    }
  },
  "required": [
    "workspace_gid",
    "document_gid",
    "source_association_id",
    "session_nonce"
  ],
  "title": "AuthorizeRequest",
  "type": "object"
}
```

最小结构示例：

```json
{
  "capability_id": "simulation.viewer.interaction.authorize",
  "catalog_release": "<catalog_release>",
  "major_version": 1,
  "payload": {
    "document_gid": "example",
    "session_nonce": "0000000000000000000000000000000000000000000000000000000000000000",
    "source_association_id": "example",
    "workspace_gid": "example"
  }
}
```

## 输出 Schema

领域数据必须符合下列 Schema，并封装在完整 `CapabilityResultV2` 中：

```json
{
  "$defs": {
    "GrantedOperation": {
      "additionalProperties": false,
      "properties": {
        "contract_hash": {
          "pattern": "^sha256:[0-9a-f]{64}$",
          "title": "Contract Hash",
          "type": "string"
        },
        "id": {
          "enum": [
            "vismockup.node.visibility.change@1",
            "vismockup.node.selection.change@1"
          ],
          "title": "Id",
          "type": "string"
        }
      },
      "required": [
        "id",
        "contract_hash"
      ],
      "title": "GrantedOperation",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "actor_id": {
      "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$",
      "title": "Actor Id",
      "type": "string"
    },
    "audience": {
      "const": "ai00.connector.viewer-interaction",
      "title": "Audience",
      "type": "string"
    },
    "device_id": {
      "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$",
      "title": "Device Id",
      "type": "string"
    },
    "document_gid": {
      "pattern": "^[1-9][0-9]{0,19}$",
      "title": "Document Gid",
      "type": "string"
    },
    "document_session": {
      "pattern": "^sha256:[0-9a-f]{64}$",
      "title": "Document Session",
      "type": "string"
    },
    "expires_at": {
      "title": "Expires At",
      "type": "string"
    },
    "grant_generation": {
      "maximum": 9007199254740991,
      "minimum": 1,
      "title": "Grant Generation",
      "type": "integer"
    },
    "grant_id": {
      "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$",
      "title": "Grant Id",
      "type": "string"
    },
    "issued_at": {
      "title": "Issued At",
      "type": "string"
    },
    "key_id": {
      "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$",
      "title": "Key Id",
      "type": "string"
    },
    "operations": {
      "items": {
        "$ref": "#/$defs/GrantedOperation"
      },
      "maxItems": 2,
      "minItems": 1,
      "title": "Operations",
      "type": "array"
    },
    "policy_version": {
      "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$",
      "title": "Policy Version",
      "type": "string"
    },
    "protocol": {
      "const": "ai00.viewer.interaction.grant.v1",
      "title": "Protocol",
      "type": "string"
    },
    "runtime_instance_id": {
      "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$",
      "title": "Runtime Instance Id",
      "type": "string"
    },
    "session_nonce": {
      "pattern": "^[0-9a-f]{64}$",
      "title": "Session Nonce",
      "type": "string"
    },
    "signature": {
      "pattern": "^[A-Za-z0-9_-]+$",
      "title": "Signature",
      "type": "string"
    },
    "source_association_id": {
      "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$",
      "title": "Source Association Id",
      "type": "string"
    },
    "tenant_id": {
      "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$",
      "title": "Tenant Id",
      "type": "string"
    },
    "workspace_gid": {
      "pattern": "^[1-9][0-9]{0,19}$",
      "title": "Workspace Gid",
      "type": "string"
    }
  },
  "required": [
    "protocol",
    "grant_id",
    "grant_generation",
    "session_nonce",
    "actor_id",
    "tenant_id",
    "device_id",
    "runtime_instance_id",
    "workspace_gid",
    "document_gid",
    "source_association_id",
    "document_session",
    "operations",
    "policy_version",
    "issued_at",
    "expires_at",
    "audience",
    "key_id",
    "signature"
  ],
  "title": "SignedGrant",
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

- `interaction_scope_denied`：The caller does not own a current permitted source scope.（retryable=false）
- `interaction_binding_stale`：The source, document binding or current runtime changed.（retryable=false）
- `interaction_renewal_stale`：The prior grant is not the latest grant for this session.（retryable=false）
- `interaction_signer_unavailable`：Trusted grant signing material is unavailable.（retryable=false）
- `interaction_catalog_binding_unavailable`：Exact trusted authorization or operation Catalog binding is unavailable.（retryable=false）
- `interaction_authorization_rejected`：The closed request or trusted signer rejected the grant.（retryable=false）

`domain_errors_complete=false`。为 `false` 时，能力不得扩大插件或 Agent 暴露。

## 版本与迁移

主版本固定为 `1`。同一稳定主版本不得破坏 Schema 或 Agent 投影；升级时并行声明新主版本，调用方显式迁移，不允许“latest”回退。
