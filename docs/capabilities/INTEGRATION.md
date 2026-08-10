# 插件与 AI 接入规范

目录版本：`rel_7263b81c7344960ad9df52f6fb8fdd30`。

1. Host 在安装、挂载或 Agent Run 创建时固定 Catalog Release 与主版本授权。
2. 消费者提交 payload、幂等键、预期资源版本；不得提交权限或伪造消费者身份。
3. 写操作先获取与消费者、资源、策略版本和 payload hash 绑定的一次性审批。
4. `completed` 可消费结果；`accepted` 必须轮询 `OperationRef`；`outcome_unknown` 禁止盲目重试写操作。
5. 大型数模、CAD、仿真结果只通过 `ArtifactRef` 交换，内部对象键不属于公共合同。

最小调用信封可从 `catalog.v2.json` 每项的 `invoke` 字段读取。示例仅用于结构验证，业务标识必须替换为当前租户内已授权资源。
