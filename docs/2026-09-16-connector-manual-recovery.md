# Connector 人工恢复入口

## 变更分类与目的

新增 Simulation 域能力，让设备所属用户处理 VisMockup 文档打开/插入结果不确定的任务。它只记录人工裁定并关闭原任务，不重试原操作、不伪造连接器成功结果、不修改 Teamcenter 产品结构。

## 权威上下文与复用

已检查 Simulation Provider、Connector 合同、设备/任务/审计 Repository、迁移 0008、运行时恢复与执行隔离逻辑、桌面消费者注册以及 SQL/合同测试。复用现有 Capability Gateway、用户确认、幂等机制、runtime audit 和 authenticated obsolete-recovery acknowledgement；没有复用独立安装的 Connector。

## 能力与边界

| 能力 | GID | 效果 |
| --- | --- | --- |
| simulation.connector.recovery.search@1 | cv2_6addb101f6016ed49329e318 | 返回当前用户/租户所属设备的最多 20 个待处理任务 |
| simulation.connector.recovery.resolve@1 | cv2_f5b0af1dbc5778455b56385f | 对精确设备、任务、运行代次及 outcome hash 记录人工裁定 |

生命周期 experimental。Provider 为 Simulation；消费者为已注册的 `ai00.desktop.windows-x64`（web）。仅 web 人工调用，不向 agent/API/MCP 暴露。权限 `simulation.use`，resolve 还要求真实用户确认和幂等键。

输入含 `plan_id`、`device_id`、`expected_generation`、`expected_outcome_hash`、`decision`、`reason`。决定只有 `not_executed` 与 `executed`。输出含 `audit_ref` 和固定 `retry_started:false`。只支持单步、已有签名结果的文档打开/插入；其他任务显示但拒绝处理。

业务不变量：设备及任务 owner/tenant 一致；设备先加锁再锁任务；旧代次/不同结果/冲突决定拒绝；原 `outcome_json` 与 `outcome_hash` 不变；新增 `human_recovery_disposition` 审计后，仅该任务转为 `cancelled`。完全相同的人工决定重放原审计引用。取消处理不会释放其他任务的隔离。

稳定错误包含 `runtime_owner_mismatch`、`recovery_confirmation_required`、`recovery_input_invalid`、`recovery_state_changed`、`recovery_decision_conflict`、`recovery_operation_unsupported`。错误和状态不包含认证材料。

## 数据及运行时

共用现有数据库，仅迁移 `test_` 开头的表。0027 先添加包含 cancelled 的新 CHECK，再确认新约束存在后移除旧 CHECK；适配 OceanBase 3.2.3.3 不支持同条 ADD/DROP 的限制。中间状态仍有旧约束保护，重复执行无变更。历史 0008 不改。

Connector 从认证服务端收到旧任务不可继续核对的结果后，保留签名结果并记录该任务已确认。恢复扫描和后续执行隔离检查均识别这个确认；其他未知结果继续隔离。不会自动调用打开/插入。用户选择“已执行”后再进入现有文档选择/绑定流程，不等同于绑定成功。

## 验证证据

- Python 恢复 SQL、Provider 合同、迁移回归：100 passed / 74 skipped。跳过的是未配置专用原生 MySQL 测试库的用例；SQLite 测试不代表 MySQL 行锁并发验证。
- .NET 恢复及生命周期回归：53 passed / 0 skipped。生产恢复确认边界被测试；RegisterAsync 的生产请求构造仅静态检查，测试传入注册回调。
- 实际共用数据库、test_ 前缀：0027 applied；再次执行返回空列表，未改任务裁定或签名结果。
- 初次单条替换 CHECK 被真实服务器拒绝 1235，随后改为两阶段；不是忽略失败。
- 前端恢复测试 17/17、完整 CAD 测试、桌面参数边界测试、test-governance 构建通过。另补真实 facade→preload→IPC→CapabilityClient 的测试边界；不能代替实际用户会话。
- 用户实际窗口定位到 invalid_invocation:business_facade。2026-09-16 从 Electron HTTP 脚本缓存中只提取代码常量，发现旧 SEARCH 仍包含 `@1`，而磁盘源码已使用无版本后缀 ID。真实 Vite 响应确认 `?v=20260916-manual-recovery` 返回 `max-age=31536000, immutable`，重启客户端不会保证更新此脚本。
- 将恢复入口资源参数改为 `?rev=20260916-manual-recovery-2`，避开 Vite 的 immutable 依赖缓存规则；真实 Vite 回归测试修改前失败（一年 immutable），修改后通过（no-cache）。恢复测试 18/18、business facade 测试及 test-governance 构建通过。未绕过参数校验或手工修改任务状态。实际用户重新加载页面后的恢复列表与裁定仍待验证。

## 治理状态

### 事务参与者与批量处理补充（2026-09-16）

实际读取列表后 resolve 被 Gateway 拒绝 `transaction_participant_required`：修复前 handler 未提供事务参与者，仓储还自行提交。现在 resolve 返回真实未提交的 `TransactionalCapabilityOutput`；仓储使用传入事务不自行 commit，Gateway 将状态、人工审计、可靠性 outcome/outbox 一起提交。声明 strong、确认、owner/tenant、generation/hash 及签名不可变约束保持不变。

跨边界涉及 Simulation Provider/连接工厂及平台 Gateway。Gateway 对同步 Provider 迟到的事务返回值增加确定性 rollback/close：请求超时或取消不会再丢弃无人清理的打开事务，不在事件循环线程执行迟到清理。

验证：事务与原 SQL 仓储组合 79 passed / 78 skipped；加超时/取消测试后的平台 Gateway 与恢复 Gateway 组合 35 passed / 6 skipped。跳过为未配置原生测试数据库的用例，SQLite 证据不替代 OceanBase 端到端执行。审查通过；worker 已完成但结果交付前取消的竞争分支经代码审查，尚无确定性调度测试，记录为非阻断测试缺口。

当前 env 的 Base/Simulation 数据库端点、schema 和凭据相同（仅比较布尔，不记录秘密）；经 Simulation 前缀包装连接，只读查询四张 test_ 状态/审计/可靠性表均可见。未改任何业务行。本修复不声称支持 Base/Simulation 独立数据库之间的分布式强事务。

用户批准批量入口：只复用单条 resolve，逐项独立事务、确认和幂等；成功与失败保留逐项结果，不自动重开模型。完成裁定不等于 Connector ready，仍需实际恢复确认、注册及心跳；当前账号待处理总数也不等于本机阻塞数。

最终批量测试 26/26 通过，包含真实 facade 延迟 challenge、关闭取消、重复能力名的 plan/device 区分及实际错误码停止规则。事务补丁和批量补丁复审通过。test-governance 构建完成（保留已有非 module script 警告）；Catalog/文档/验收清单 check 通过，候选 release 为 `rel_3b7251457acb6b7d2c9a6f6d06ab1acd`。2026-09-16 19:30 更新 test 应用，后端健康 200，实际页面批量控件及 no-cache 脚本已核对；两个既有 VisMockup 进程启动时间未变。未代用户提交任何裁定，因此实际解除隔离和 ready 状态仍待用户操作后验证。

当前代码在本地 test 工作树，尚未新建提交。Catalog、Descriptor、Provider 元数据已生成；正式发布未执行。

- machine_passed：完整治理 Snapshot 状态 unverified；上列局部测试结果是真实运行结果。
- human_approved：当前精确 business_definition_hash 的治理批准 unverified；聊天同意实施不替代治理审批。
- runtime_verified：test_ 迁移已验证；用户人工裁定、连接器恢复到 ready 的端到端尚未验证。
- advisory：true。

Snapshot/test-run GID 绑定尚未取得，不能用本地测试数量冒充治理放行证据。正式发布及实际裁定均未代替用户执行。
