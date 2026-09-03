# simulation.environment.compose@2

Compose an immutable Connector environment from a pinned whole BOP or one exact line scope.

## 使用判断

- 适用：Compose an immutable Connector environment from a pinned whole BOP or one exact line scope.
- 不适用：Use the owning domain's governed Capability.
- 生命周期：`experimental`
- 所属领域：`simulation`
- Catalog Release：`rel_6aa108ced57d29b4cb35d05266369c04`
- Schema 精度：`typed`
- 暂未开放原因：`experimental_lifecycle`

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

- 授权策略：`simulation.v2:simulation.use`
- 自动化等级：`A1`
- 数据分类：`confidential`
- Delegation：`scoped`
- 认证新鲜度：0 秒

资源选择器：
- `craft-bop-version` ← `execution_plan_ref.version_gid`（必填）
- `simulation-connector` ← `device_id`（必填）

## 执行与可靠性

- 副作用：`write`
- 执行模式：`cloud_sync`
- 超时：30 秒
- 审批：`user`
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
    "capture_profile": {
      "additionalProperties": false,
      "properties": {
        "background": {
          "enum": [
            "current"
          ],
          "type": "string"
        },
        "format": {
          "enum": [
            "png"
          ],
          "type": "string"
        },
        "height": {
          "enum": [
            1080
          ],
          "type": "integer"
        },
        "width": {
          "enum": [
            1920
          ],
          "type": "integer"
        }
      },
      "required": [
        "format",
        "width",
        "height",
        "background"
      ],
      "type": "object"
    },
    "device_id": {
      "type": "string"
    },
    "execution_plan_ref": {
      "additionalProperties": false,
      "properties": {
        "content_hash": {
          "example": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
          "pattern": "^sha256:[0-9a-f]{64}$",
          "type": "string"
        },
        "revision": {
          "minimum": 1,
          "type": "integer"
        },
        "version_gid": {
          "type": "string"
        }
      },
      "required": [
        "version_gid",
        "revision",
        "content_hash"
      ],
      "type": "object"
    },
    "name": {
      "type": "string"
    },
    "scope": {
      "additionalProperties": false,
      "properties": {
        "gid": {
          "type": "string"
        },
        "kind": {
          "enum": [
            "line"
          ],
          "type": "string"
        }
      },
      "required": [
        "kind",
        "gid"
      ],
      "type": "object"
    },
    "snapshot_request_id": {
      "type": "string"
    }
  },
  "required": [
    "name",
    "device_id",
    "execution_plan_ref",
    "snapshot_request_id",
    "capture_profile"
  ],
  "type": "object"
}
```

最小结构示例：

```json
{
  "capability_id": "simulation.environment.compose",
  "catalog_release": "rel_6aa108ced57d29b4cb35d05266369c04",
  "major_version": 2,
  "payload": {
    "capture_profile": {
      "background": "current",
      "format": "png",
      "height": 1080,
      "width": 1920
    },
    "device_id": "example",
    "execution_plan_ref": {
      "content_hash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
      "revision": 1,
      "version_gid": "example"
    },
    "name": "example",
    "snapshot_request_id": "example"
  }
}
```

## 输出 Schema

领域数据必须符合下列 Schema，并封装在完整 `CapabilityResultV2` 中：

```json
{
  "additionalProperties": false,
  "properties": {
    "capture_profile": {
      "additionalProperties": false,
      "properties": {
        "background": {
          "enum": [
            "current"
          ],
          "type": "string"
        },
        "format": {
          "enum": [
            "png"
          ],
          "type": "string"
        },
        "height": {
          "enum": [
            1080
          ],
          "type": "integer"
        },
        "width": {
          "enum": [
            1920
          ],
          "type": "integer"
        }
      },
      "required": [
        "format",
        "width",
        "height",
        "background"
      ],
      "type": "object"
    },
    "connector_requirement": {
      "additionalProperties": false,
      "properties": {
        "adapter_id": {
          "enum": [
            "ai00.vismockup"
          ],
          "type": "string"
        },
        "adapter_major": {
          "enum": [
            1
          ],
          "type": "integer"
        },
        "maximum_product_version_exclusive": {
          "type": "string"
        },
        "minimum_product_version": {
          "type": "string"
        },
        "operations": {
          "items": {
            "additionalProperties": false,
            "properties": {
              "contract_hash": {
                "example": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
                "pattern": "^sha256:[0-9a-f]{64}$",
                "type": "string"
              },
              "operation_id": {
                "type": "string"
              }
            },
            "required": [
              "operation_id",
              "contract_hash"
            ],
            "type": "object"
          },
          "maxItems": 64,
          "type": "array"
        },
        "product_id": {
          "enum": [
            "siemens.vismockup"
          ],
          "type": "string"
        },
        "protocol": {
          "enum": [
            "ai00.connector.execution-plan.v1"
          ],
          "type": "string"
        }
      },
      "required": [
        "protocol",
        "adapter_id",
        "adapter_major",
        "product_id",
        "minimum_product_version",
        "maximum_product_version_exclusive",
        "operations"
      ],
      "type": "object"
    },
    "document_source": {
      "additionalProperties": false,
      "properties": {
        "document_id": {
          "type": "string"
        },
        "root_node_key": {
          "type": "string"
        },
        "snapshot_hash": {
          "example": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
          "pattern": "^sha256:[0-9a-f]{64}$",
          "type": "string"
        },
        "source_identity": {
          "type": "string"
        }
      },
      "required": [
        "document_id",
        "root_node_key",
        "source_identity",
        "snapshot_hash"
      ],
      "type": "object"
    },
    "environment_id": {
      "type": "string"
    },
    "environment_version": {
      "minimum": 1,
      "type": "integer"
    },
    "execution_source": {
      "additionalProperties": false,
      "properties": {
        "bop_version_gid": {
          "type": "string"
        },
        "content_hash": {
          "example": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
          "pattern": "^sha256:[0-9a-f]{64}$",
          "type": "string"
        },
        "execution_plan_uri": {
          "type": "string"
        },
        "project_gid": {
          "type": "string"
        },
        "revision": {
          "minimum": 1,
          "type": "integer"
        }
      },
      "required": [
        "bop_version_gid",
        "revision",
        "project_gid",
        "content_hash",
        "execution_plan_uri"
      ],
      "type": "object"
    },
    "manifest_hash": {
      "example": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
      "pattern": "^sha256:[0-9a-f]{64}$",
      "type": "string"
    },
    "mapping_snapshot_hash": {
      "example": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
      "pattern": "^sha256:[0-9a-f]{64}$",
      "type": "string"
    },
    "operations": {
      "items": {
        "additionalProperties": false,
        "properties": {
          "operation_id": {
            "type": "string"
          },
          "predecessor_ids": {
            "items": {
              "type": "string"
            },
            "maxItems": 10000,
            "type": "array"
          },
          "product_node_keys": {
            "items": {
              "type": "string"
            },
            "maxItems": 10000,
            "type": "array"
          },
          "resource_node_keys": {
            "items": {
              "type": "string"
            },
            "maxItems": 500,
            "type": "array"
          },
          "scene": {
            "additionalProperties": false,
            "properties": {
              "capture_profile": {
                "additionalProperties": false,
                "properties": {
                  "background": {
                    "enum": [
                      "current"
                    ],
                    "type": "string"
                  },
                  "format": {
                    "enum": [
                      "png"
                    ],
                    "type": "string"
                  },
                  "height": {
                    "enum": [
                      1080
                    ],
                    "type": "integer"
                  },
                  "width": {
                    "enum": [
                      1920
                    ],
                    "type": "integer"
                  }
                },
                "required": [
                  "format",
                  "width",
                  "height",
                  "background"
                ],
                "type": "object"
              },
              "operation_id": {
                "type": "string"
              },
              "scene_hash": {
                "example": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
                "pattern": "^sha256:[0-9a-f]{64}$",
                "type": "string"
              },
              "visible_products": {
                "items": {
                  "type": "string"
                },
                "maxItems": 10000,
                "type": "array"
              },
              "visible_resources": {
                "items": {
                  "type": "string"
                },
                "maxItems": 500,
                "type": "array"
              }
            },
            "required": [
              "operation_id",
              "visible_products",
              "visible_resources",
              "capture_profile",
              "scene_hash"
            ],
            "type": "object"
          },
          "sequence": {
            "minimum": 0,
            "type": "integer"
          }
        },
        "required": [
          "operation_id",
          "sequence",
          "predecessor_ids",
          "product_node_keys",
          "resource_node_keys",
          "scene"
        ],
        "type": "object"
      },
      "maxItems": 10000,
      "type": "array"
    },
    "problems": {
      "items": {
        "additionalProperties": false,
        "properties": {
          "candidates": {
            "items": {
              "type": "string"
            },
            "maxItems": 10000,
            "type": "array"
          },
          "kind": {
            "enum": [
              "not_found",
              "ambiguous"
            ],
            "type": "string"
          },
          "source_code": {
            "type": "string"
          },
          "source_type": {
            "enum": [
              "product",
              "tool",
              "equipment",
              "fixture"
            ],
            "type": "string"
          }
        },
        "required": [
          "kind",
          "source_type",
          "source_code",
          "candidates"
        ],
        "type": "object"
      },
      "maxItems": 10500,
      "type": "array"
    },
    "product_bindings": {
      "items": {
        "additionalProperties": false,
        "properties": {
          "node_key": {
            "type": "string"
          },
          "product_ref": {
            "type": "string"
          }
        },
        "required": [
          "product_ref",
          "node_key"
        ],
        "type": "object"
      },
      "maxItems": 10000,
      "type": "array"
    },
    "resource_bindings": {
      "items": {
        "additionalProperties": false,
        "properties": {
          "code": {
            "type": "string"
          },
          "model_ref": {
            "additionalProperties": false,
            "properties": {
              "artifact_ref": {
                "additionalProperties": false,
                "properties": {
                  "artifact_id": {
                    "type": "string"
                  },
                  "byte_size": {
                    "minimum": 0,
                    "type": "integer"
                  },
                  "media_type": {
                    "type": "string"
                  },
                  "sha256": {
                    "example": "0000000000000000000000000000000000000000000000000000000000000000",
                    "pattern": "^[0-9a-f]{64}$",
                    "type": "string"
                  },
                  "version": {
                    "minimum": 1,
                    "type": "integer"
                  }
                },
                "required": [
                  "artifact_id",
                  "media_type",
                  "sha256",
                  "byte_size",
                  "version"
                ],
                "type": "object"
              },
              "model_id": {
                "type": "string"
              },
              "snapshot_hash": {
                "example": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
                "pattern": "^sha256:[0-9a-f]{64}$",
                "type": "string"
              },
              "version_id": {
                "type": "string"
              }
            },
            "required": [
              "model_id",
              "version_id",
              "snapshot_hash",
              "artifact_ref"
            ],
            "type": "object"
          },
          "node_key": {
            "type": "string"
          },
          "normalized_code": {
            "type": "string"
          },
          "resource_type": {
            "enum": [
              "tool",
              "equipment",
              "fixture"
            ],
            "type": "string"
          }
        },
        "required": [
          "resource_type",
          "code",
          "normalized_code",
          "node_key",
          "model_ref"
        ],
        "type": "object"
      },
      "maxItems": 500,
      "type": "array"
    },
    "status": {
      "enum": [
        "composed",
        "unresolved"
      ],
      "type": "string"
    }
  },
  "required": [
    "status",
    "problems"
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

- `source_resolver_unavailable`：A required owning-domain resolver is unavailable.（retryable=true）
- `source_version_mismatch`：A referenced source no longer matches its immutable hash or version.（retryable=false）
- `parameter_set_not_found`：The immutable parameter set is unavailable or not visible.（retryable=false）
- `simulation_profile_not_found`：The immutable Simulation profile is unavailable or not visible.（retryable=false）
- `solver_not_allowed`：The requested solver coordinate is not in the governed allowlist.（retryable=false）
- `simulation_environment_not_found`：The Simulation environment is unavailable or not visible.（retryable=false）
- `simulation_run_not_found`：The Simulation run is unavailable or not visible.（retryable=false）
- `simulation_result_not_ready`：The Simulation run has no completed result artifacts.（retryable=true）
- `idempotency_conflict`：The idempotency key is bound to a different Simulation request.（retryable=false）
- `execution_plan_unavailable`：The pinned Craft execution plan is unavailable.（retryable=true）
- `active_document_unavailable`：The Connector has no readable active document.（retryable=true）
- `active_document_snapshot_required`：A confirmed asynchronous active-document snapshot is required.（retryable=false）
- `document_snapshot_not_found`：The document snapshot request is unavailable or not visible.（retryable=false）
- `document_snapshot_action_not_ready`：The prepared document snapshot action is not ready to dispatch.（retryable=false）
- `bom_snapshot_invalid`：The Connector returned an invalid active BOM snapshot.（retryable=false）
- `bom_identity_mismatch`：The active BOM identity does not match the requested source.（retryable=false）
- `bom_snapshot_limit_exceeded`：The active BOM exceeds the governed snapshot limit.（retryable=false）
- `product_binding_not_found`：A process product reference has no active BOM node.（retryable=false）
- `product_binding_ambiguous`：A process product reference resolves to multiple BOM nodes.（retryable=false）
- `resource_model_not_found`：A typed resource code has no model mapping.（retryable=false）
- `resource_model_ambiguous`：A typed resource code has multiple active model mappings.（retryable=false）
- `environment_source_changed`：A pinned environment source changed before composition.（retryable=false）
- `connector_offline`：The bound Connector is offline or stale.（retryable=true）
- `connector_version_incompatible`：The Connector protocol or target product version is incompatible.（retryable=false）
- `adapter_unavailable`：The required Connector Adapter is unavailable.（retryable=false）
- `adapter_contract_mismatch`：An Adapter operation contract hash does not match.（retryable=false）
- `interactive_session_missing`：The bound user's interactive SessionHost is unavailable.（retryable=true）
- `interactive_session_conflict`：More than one fresh SessionHost claims the bound user.（retryable=false）
- `bound_user_mismatch`：The Connector is bound to a different AI00 user.（retryable=false）
- `vismockup_unavailable`：VisMockup is unavailable to the bound SessionHost.（retryable=true）
- `vismockup_document_changed`：The active VisMockup document changed during execution.（retryable=false）
- `scene_verification_failed`：The actual VisMockup scene does not match the manifest.（retryable=false）
- `capture_failed`：VisMockup internal view capture failed.（retryable=true）
- `artifact_upload_unconfirmed`：A captured Artifact upload has not been reconciled.（retryable=true）
- `craft_screenshot_attach_failed`：Craft rejected or failed the screenshot association.（retryable=true）
- `local_execution_outcome_unknown`：The local side effect outcome requires reconciliation.（retryable=false）
- `downstream_confirmation_required`：The exact downstream action requires a separately issued user confirmation.（retryable=false）
- `capture_action_not_ready`：No capture action is currently ready to dispatch.（retryable=false）
- `materialization_run_not_found`：The materialization run is unavailable or not visible.（retryable=false）
- `materialization_action_not_ready`：The materialization action is not ready to dispatch.（retryable=false）
- `plan_outcome_invalid`：The Connector outcome does not match the immutable execution plan.（retryable=false）
- `capability_migration_required`：This deprecated immediate-dispatch version must migrate to the @2 two-phase workflow.（retryable=false）
- `pairing_not_found`：The Connector pairing request does not exist.（retryable=false）
- `pairing_expired`：The five-minute Connector pairing request expired.（retryable=false）
- `pairing_proof_invalid`：The Connector did not prove the original verifier and installation identity.（retryable=false）
- `pairing_not_approved`：The signed-in AI00 user has not approved this pairing.（retryable=false）
- `pairing_version_conflict`：The pairing changed after it was displayed.（retryable=false）
- `connector_binding_conflict`：The AI00 user already has a different Connector binding.（retryable=false）
- `feishu_login_required`：Pairing approval requires an AI00 Web session established through Feishu login.（retryable=false）

`domain_errors_complete=true`。为 `false` 时，能力不得扩大插件或 Agent 暴露。

## 版本与迁移

主版本固定为 `2`。同一稳定主版本不得破坏 Schema 或 Agent 投影；升级时并行声明新主版本，调用方显式迁移，不允许“latest”回退。
