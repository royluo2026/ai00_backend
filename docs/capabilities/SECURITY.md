# Capability V2 安全模型

目录版本：`rel_86c92a7e6e59a987be6d7ec3d2d4c11b`。

- 身份：仅 Host/Backend 可签发 Web、Plugin Mount、Agent Delegation、MCP、Worker 与 Local Runtime 身份。
- 授权：能力权限、资源范围、数据分类和 delegation 取交集；任一缺失均 fail closed。
- 数据：Agent/MCP 只接收 allowlist 投影；秘密、PII、原始路径和内部异常被移除。
- 可靠性：写操作以消费者维度幂等，强一致写必须加入领域事务；Outcome 与 Audit Outbox 持久化。
- 制品：Host 生成对象键并流式校验 SHA-256/大小；租户和资源授权在下载前再次检查。
- 操作：状态转换使用版本 CAS；终态不可重开，`outcome_unknown` 只能经对账解析。

客户端报送的插件 ID、Agent Run ID、permission、source header 或对象键均不构成可信授权依据。
