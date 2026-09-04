# 编排中心治理闭环验收标准

本文件是编排中心 MVP 在 Capability Governance V2.5 下的实现与验收基线。编排中心只拥有业务全景、分解关系、运行事件和指标快照；Capability、数据源、规则源、知识源、本体与代码的权威定义仍由各自域维护。

## 变更边界

- Agent 域拥有 14 张 `workmanship_agent_orch_*` 表及其迁移；跨域对象只保存经过 Resolver 验证的引用，不建立跨域外键。
- 所有写入必须同时绑定 `tenant_gid`、资源 owner 和 project/resource scope；越权、租户缺失、资源不存在均 fail closed。
- 运行状态与审计事件在同一数据库事务中提交；任一写入失败必须整体回滚。
- 发布时只接受服务端 Catalog/Descriptor/Provider Resolver 派生的 Capability 元数据，拒绝客户端提交的 provider、gateway、catalog 或 hash。
- 前端只调用统一 Capability Gateway；没有已批准的 read Capability 时显示 governed unavailable，不回退到猜测性 REST 或本地伪数据。
- 演示数据必须由测试功能开关显式启用并标注 `demo=true`；默认生产 profile 不加载演示状态。
- 有效智能作业率只计入安全授权、授权比例、业务验收通过率和可信证据均齐全的任务；缺任一项按 0 计入。
- 图模型必须通过有界节点/边/深度、唯一 ID、引用完整性、DAG 无环和正交连线校验。

## 验收证据

1. schema/migration/ownership 静态门禁通过，迁移编号与当前统一线不冲突。
2. provider/repository 单元测试覆盖租户、owner、project scope、并发版本和事务回滚。
3. resolver 测试覆盖过期 Catalog、错误 Provider/Gateway/hash、非 stable 成员及客户端篡改。
4. 前端测试证明 demo 来源显式、governed 缺少 loader 时 fail closed、写请求包含版本/幂等键/确认令牌并只走 Gateway。
5. 运行态 E2E 需绑定真实 `capability_version_gid`、business-definition hash、代码提交、测试运行和结果摘要；未执行或无可信审批时分别记为 `unverified`。

本轮隔离复核证据：

- 后端提交 `39092086`（包含 `f8d024e8`）基于最新 `test@655418f8`；Catalog Release 为 `rel_b29ec309ee7aaa692bd89420063c443e`，552 descriptors / 495 stable。
- `141 passed, 5 skipped`：编排、schema/migration、Catalog/release-gate、Provider integration 与 HTTP harness；HTTP harness 使用每测试独立 fake connection，客户端关闭后连接对象即丢弃，不写共享数据库。
- Catalog、Capability docs、acceptance manifest 的 `--check` 均通过；Provider integration `9 passed, 5 skipped`。
- HTTP harness 验证 `POST /api/orchestration/runs` → `POST /api/orchestration/runs/{run_gid}/transition`，状态更新和审计事件分别在单事务中提交，且租户/项目作用域写入 guard 生效。

治理状态始终独立记录：`machine_passed`、`human_approved`、`runtime_verified`；AI 输出只作为 advisory，不能代替审批、发布或清除阻断。
