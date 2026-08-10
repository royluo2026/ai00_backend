# ontology.change.proposal.get@1

Read the current immutable proposal revision.

## 使用判断

- 适用：A proposal GID is known.
- 不适用：Searching proposals.
- 生命周期：`experimental`
- 所属领域：`ontology`
- Catalog Release：`rel_9322bdfe651224292d37be91bcb0f647`
- Schema 精度：`legacy_partial`
- 暂未开放原因：`legacy_partial_schema`, `domain_errors_not_declared`, `experimental_lifecycle`

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

- 授权策略：`legacy:authenticated`
- 自动化等级：`A2`
- 数据分类：`internal`
- Delegation：`none`
- 认证新鲜度：0 秒

资源选择器：
- 无资源选择器；仍受租户、身份与权限策略约束。

## 执行与可靠性

- 副作用：`read`
- 执行模式：`cloud_sync`
- 超时：30 秒
- 审批：`none`
- 幂等：`none`
- 并发：`none`
- 一致性：`strong`
- Operation：`none`
- Artifact：`none`
- 审计：`standard`
- Evidence：`optional`
- 配额成本：1

## 输入 Schema

```json
{
  "additionalProperties": false,
  "properties": {
    "proposal_gid": {}
  },
  "required": [
    "proposal_gid"
  ],
  "type": "object"
}
```

最小结构示例：

```json
{
  "capability_id": "ontology.change.proposal.get",
  "catalog_release": "rel_9322bdfe651224292d37be91bcb0f647",
  "major_version": 1,
  "payload": {
    "proposal_gid": "example"
  }
}
```

## 输出 Schema

领域数据必须符合下列 Schema，并封装在完整 `CapabilityResultV2` 中：

```json
{
  "additionalProperties": false,
  "properties": {
    "author_gid": {
      "type": "string"
    },
    "base_ontology_version_ref": {
      "additionalProperties": false,
      "properties": {
        "content_hash": {
          "pattern": "^sha256:[0-9a-f]{64}$",
          "type": "string"
        },
        "release_gid": {
          "type": "string"
        },
        "revision_ref": {
          "additionalProperties": false,
          "properties": {},
          "type": "object"
        }
      },
      "required": [
        "release_gid",
        "content_hash",
        "revision_ref"
      ],
      "type": "object"
    },
    "base_release_gid": {
      "type": "string"
    },
    "changes": {
      "items": {
        "additionalProperties": false,
        "properties": {},
        "type": "object"
      },
      "type": "array"
    },
    "channel": {
      "type": "string"
    },
    "content_sha256": {
      "pattern": "^[0-9a-f]{64}$",
      "type": "string"
    },
    "created_at": {
      "additionalProperties": false,
      "properties": {},
      "type": "object"
    },
    "proposal_gid": {
      "type": "string"
    },
    "proposal_revision_gid": {
      "type": "string"
    },
    "revision_no": {
      "minimum": 1,
      "type": "integer"
    },
    "status": {
      "type": "string"
    }
  },
  "required": [
    "proposal_gid",
    "proposal_revision_gid",
    "revision_no",
    "base_release_gid",
    "content_sha256",
    "changes",
    "status",
    "author_gid",
    "base_ontology_version_ref"
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
- `confirmation_required`：写操作需要绑定本次请求的一次性审批。
- `confirmation_rejected`：审批无效、已用、已过期或与请求绑定不一致。
- `idempotency_key_required`：描述符要求写请求提供幂等键。
- `idempotency_payload_conflict`：同一幂等范围被用于不同 payload。
- `idempotency_in_progress`：同一幂等请求仍在执行。
- `rate_limit_exceeded`：租户及消费者配额不足，可按 retryable 指示重试。
- `transaction_participant_required`：强一致写 Provider 未加入领域事务。
- `provider_failed`：领域 Provider 执行失败；错误正文不会泄露内部细节。
- `outcome_persistence_failed`：领域可能已提交但 Outcome 未能确认，必须查询 OperationRef。

当前 V1 适配描述符尚未完整声明领域业务错误，`catalog.v2.json` 中 `domain_errors_complete=false`。在领域完成 V2 原生迁移前，插件/Agent exposure 必须保持关闭。

## 版本与迁移

主版本固定为 `1`。同一稳定主版本不得破坏 Schema 或 Agent 投影；升级时并行声明新主版本，调用方显式迁移，不允许“latest”回退。
