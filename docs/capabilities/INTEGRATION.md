# 插件与 AI 接入规范

目录版本：`rel_d407979e8fe9737980e72058e3384b37`。

1. Host 在安装、挂载或 Agent Run 创建时固定 Catalog Release 与主版本授权。
2. 消费者提交 payload、幂等键、预期资源版本；不得提交权限或伪造消费者身份。
3. 写操作先获取与消费者、资源、策略版本和 payload hash 绑定的一次性审批。
4. `completed` 可消费结果；`accepted` 必须轮询 `OperationRef`；`outcome_unknown` 禁止盲目重试写操作。
5. 大型数模、CAD、仿真结果只通过 `ArtifactRef` 交换，内部对象键不属于公共合同。

完整调用信封至少包含 `catalog_release`、`capability_id`、`major_version`、`payload`、可信 `identity`、`request_id` 和 `trace_id`。`idempotency_policy=required` 时必须增加 `idempotency_key`；`concurrency_policy=expected_version` 时必须增加 `expected_resource_version`，并令其与描述符 `expected_version_payload_path` 指向的 payload 值完全一致；需要确认时再传服务端签发的 `approval_reference`。

`catalog.v2.json` 每项的 `invoke` 只给出能力定位与 payload 最小结构，不包含可信身份、幂等、并发和审批字段。示例仅用于结构验证，业务标识必须替换为当前租户内已授权资源。
