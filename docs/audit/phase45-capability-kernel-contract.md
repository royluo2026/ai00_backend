# Phase 45：Capability 内核契约加固

日期：2026-08-06
实施分支：`codex/capability-wave-a`
基线提交：`b0473c33d92718b0bbfce1ba4b4a7a95b72ae0d9`

## 目标

落实已确认 Capability 实施计划的 Task 1，为后续 Craft、本体、系统与插件能力提供不可绕过的统一边界。本阶段不新增业务 Capability，不修改数据库结构，不执行数据库 SQL，也不连接生产数据库。

## 已实施内容

1. `CapabilitySpec` 新增强制 `owner`，以及 `use_when`、`do_not_use_when`、`subject_concepts`、`effects` 治理元数据。
2. 所有现有 Next Kernel 注册项已标注真实 owner：
   - `system.*`：`base`
   - `knowledge.*`：`knowledge`
   - `plugin.*`：`plugin`
   - `local.*`：`runtime`
   - `vismockup.*`：`vismockup`
3. 新增 `CapabilityBusinessError`。领域处理器只拥有稳定 `code`、`message`、`retryable` 与 `details`，不得选择 HTTP 状态码。
4. REST 适配层使用基座维护的受限映射表，将业务错误转换为既有 `CapabilityError` 信封；未知业务错误统一返回 HTTP 422。
5. Registry 在解包 `CapabilityOutput.data` 后强制校验 `output_schema`。失败会进入既有失败审计和失败用量统计，不会被记录成成功调用。
6. 输入、输出复用同一轻量 Schema 校验器，通过 `label` 明确错误来自 `payload` 还是 `output`。

## 关键边界决策

- `owner` 是注册时强制字段，禁止使用无责任主体的默认值掩盖遗漏。
- HTTP 是传输层语义，领域 Capability 不得携带任意 HTTP 状态。
- 输出 Schema 与输入 Schema 同为运行时契约；仅在文档中声明而不执行校验不算完成治理。
- `CapabilityOutput.evidence` 先与业务数据分离，再仅对业务数据执行输出 Schema 校验。
- 本阶段未引入任何跨领域 SQL、JOIN 或数据库迁移，因此不新增 OceanBase MySQL 兼容风险。

## 测试证据

TDD 红灯：

- 首轮内核契约：4 个预期失败，分别证明治理字段、真实 owner、稳定业务错误、输出校验尚未存在。
- REST 传输契约：补齐项目声明的隔离环境依赖后，测试因 `_business_error_http_exception` 尚不存在而按预期失败。

转绿结果：

- Task 1 聚焦测试：`7 passed in 1.29s`。
- Capability 相关回归：`40 passed, 1 deselected in 1.60s`。
- Python 编译检查：通过。
- `git diff --check`：通过。

未运行项说明：

- `test_web_bridge_sends_plugin_identity_to_capability_kernel` 在隔离后端 worktree 中按既有路径推导到不存在的相邻前端目录 `E:/Projects/ai00_v3/.worktrees/workmanship-web/...`。这是跨仓测试对目录布局的既有假设，不是本阶段产品代码失败；其余同文件测试均通过。后续消费者迁移阶段应改为显式配置前端仓库路径，或在包含前后端的集成工作区运行。

## 文件范围

- 内核模型、Registry、Schema 校验与公开导出：`backend/capabilities/*_next.py`、`backend/capabilities/__init__.py`
- 现有注册项 owner：知识、插件市场、插件存储、本地运行时、VisMockup、worker 相关注册模块
- REST 适配：`backend/routers/capabilities.py`
- 契约测试：
  - `backend/tests/test_capability_kernel_contract.py`
  - `backend/tests/test_capability_business_error_transport.py`
  - `backend/tests/test_capability_evidence_contract.py`

## 部署与远端状态

- 改动仅位于隔离 worktree 和本地功能分支。
- 未启动服务、未部署、未推送任何远端。
- 未对 GitLab 或生产仓库执行任何操作。
