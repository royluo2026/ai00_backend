# base.plugin.installation.request.create@1

Execute exact Base outcome base.plugin.installation.request.create.

## 使用判断

- 适用：A browser consumer needs exactly this Base-owned outcome.
- 不适用：The request selects another operation or domain.
- 生命周期：`stable`
- 所属领域：`base`
- Catalog Release：`rel_2a6666b7b028b0ac07b3f5dd1b2108a3`
- Schema 精度：`typed`
- 暂未开放原因：无

## 消费者可用性

| 消费者 | 状态 |
|---|---|
| web | 可用 |
| plugin | 可用 |
| agent | 可用 |
| api | 可用 |
| mcp | 可用 |
| worker | 不可用 |
| local_runtime | 不可用 |

插件和 Agent 只有在上表对应值为“可用”，且安装/Mount 或 Delegation 明确授权时才可调用。

## 授权与数据边界

- 授权策略：`base.v2:system.plugin.manage`
- 自动化等级：`A0`
- 数据分类：`restricted`
- Delegation：`scoped`
- 认证新鲜度：300 秒

资源选择器：
- `plugin-installation` ← `plugin_id`（必填）

## 执行与可靠性

- 副作用：`write`
- 执行模式：`cloud_sync`
- 超时：30 秒
- 审批：`user`
- 幂等：`required`
- 并发：`none`
- 无预期版本信封要求。
- 一致性：`strong`
- Operation：`optional`
- Artifact：`none`
- 审计：`high_risk`
- Evidence：`optional`
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
    "idempotency_key": {
      "maxLength": 512,
      "minLength": 1,
      "type": "string"
    },
    "plugin_id": {
      "maxLength": 255,
      "minLength": 1,
      "type": "string"
    },
    "release_sha256": {
      "pattern": "^sha256:[0-9a-f]{64}$",
      "type": "string"
    },
    "release_version": {
      "maxLength": 64,
      "minLength": 1,
      "type": "string"
    },
    "requested_grants": {
      "items": {
        "maxLength": 512,
        "minLength": 1,
        "type": "string"
      },
      "maxItems": 200,
      "type": "array",
      "uniqueItems": true
    }
  },
  "required": [
    "plugin_id",
    "release_version",
    "release_sha256",
    "requested_grants",
    "idempotency_key"
  ],
  "type": "object"
}
```

最小结构示例：

```json
{
  "capability_id": "base.plugin.installation.request.create",
  "catalog_release": "rel_2a6666b7b028b0ac07b3f5dd1b2108a3",
  "major_version": 1,
  "payload": {
    "idempotency_key": "example",
    "plugin_id": "example",
    "release_sha256": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
    "release_version": "example",
    "requested_grants": []
  }
}
```

## 输出 Schema

领域数据必须符合下列 Schema，并封装在完整 `CapabilityResultV2` 中：

```json
{
  "additionalProperties": false,
  "properties": {
    "installation": {
      "additionalProperties": false,
      "properties": {
        "granted_capabilities": {
          "items": {
            "maxLength": 512,
            "minLength": 1,
            "type": "string"
          },
          "maxItems": 200,
          "type": "array"
        },
        "plugin_id": {
          "maxLength": 512,
          "minLength": 1,
          "type": "string"
        },
        "release_version": {
          "maxLength": 64,
          "minLength": 1,
          "type": "string"
        },
        "revision": {
          "minimum": 1,
          "type": "integer"
        },
        "state": {
          "enum": [
            "disabled",
            "enabled",
            "rolled_back",
            "uninstalled"
          ],
          "type": "string"
        },
        "tenant_gid": {
          "maxLength": 512,
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [
        "plugin_id",
        "release_version",
        "state",
        "revision",
        "granted_capabilities",
        "tenant_gid"
      ],
      "type": "object"
    }
  },
  "required": [
    "installation"
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

- `already_installed`：base.plugin.installation.request.create can return already_installed.（retryable=false）
- `idempotency_conflict`：base.plugin.installation.request.create can return idempotency_conflict.（retryable=false）
- `invalid_input`：base.plugin.installation.request.create can return invalid_input.（retryable=false）
- `release_not_verified`：base.plugin.installation.request.create can return release_not_verified.（retryable=false）

`domain_errors_complete=true`。为 `false` 时，能力不得扩大插件或 Agent 暴露。

## 版本与迁移

主版本固定为 `1`。同一稳定主版本不得破坏 Schema 或 Agent 投影；升级时并行声明新主版本，调用方显式迁移，不允许“latest”回退。
