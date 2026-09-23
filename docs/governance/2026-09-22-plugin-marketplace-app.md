# 桌面 App 插件市场变更记录

## 1. Change classification

- 实现修复：桌面 App 工作台 APP 面板新增一级“插件市场”入口和 SVG 图标；独立页签可重复激活。设置页旧入口复用同一页面。
- 新主要版本：`base.plugin.marketplace.search@2` 提供闭合、分页、租户隔离的市场/安装清单。保留已发布 `@1` 的输入输出，未替换其原合同。
- 生命周期实现修复：复用已有安装/卸载能力，修复启停、更新、回滚、撤销和重新安装的 revision 推进；更新、回滚和启用复用发布签名与依赖验证；拒绝映射到已有 `plugin_state_conflict` 错误。
- 目标为 Windows 桌面 App。`web/` 是 Electron 加载的共享渲染层，非新增独立网页产品。

## 2. Authoritative context inspected

- 活跃前端：`E:/Projects/ai00_v3/.worktrees/orchestration-merge-frontend-20260905`；运行中的 Electron 可执行文件位于该工作树，开发模式由主进程加载 Vite 资源。
- 活跃后端：`E:/Projects/ai00_v3/.worktrees/orchestration-merge-backend-20260905`；本地 App 由 `.runtime/run_current_test_backend.py` 固定使用 `test_` 表前缀及 `127.0.0.1:8080`。
- 已检查：Core manifest、工作台 APP 注册、TabManager、preload、主进程 CapabilityClient、official_capability_manifests、共享业务客户端；Base Provider/Registry、闭合 schema、Gateway 身份/权限/确认规则、生命周期状态机、SQL repository、发布签名和依赖解析器、Catalog 构建及 lineage。
- 新身份：`base.plugin.marketplace.search@2`，GID `cv2_2c7c4de76f7a36822ca1260b`，owner `base`，owner team 为 Base 平台维护团队（具体审批人 unverified），生命周期 `experimental`。
- `business_definition_hash`: `sha256:d4d95bd0947a0d274234b246514ad16c02d94bb91b03dee7b404f0706a9aea04`。
- `schema_hash`: `sha256:fd1184fba52c33703bf3f25753bcbde00bf07f6f07b98c48861a9af98df04615`。
- 源码生成 Catalog：`rel_1ae176126a7ea495a7d2a1f913c0a018`，809 descriptors；本地未发布 App Catalog：`rel_2b849ea923631f8432187a815c0ee445`。Catalog 标识不冒充治理 Snapshot。

## 3. Reuse, atomicity, and ownership result

- 根因：旧设置市场依赖已移除的桌面插件桥接，初始化未接入；已有 search@1 是未绑定的通用 outcome 合同，不能直接改为页面查询。
- 市场查询的单一业务效果：返回已发布且带平台签名的版本及调用者当前租户的安装状态。页面展示不代表完成密码学验证；写操作再次验签。
- 查询输入：`view`、`query`（最多 200 字符）、`limit`（1–200）、`offset`；禁止客户端提交租户/用户身份。输出仅含有界插件摘要、权限、版本、状态、revision 和下一页偏移。
- 不变量：Base 重新读取有效用户及其租户；SQL 只关联该租户安装数据；输出不包含平台签名、私钥或凭据。错误为 `invalid_input`、`permission_denied`、`marketplace_data_invalid`；基础设施错误遵循 Gateway。
- 查询只读、无幂等写入、无迁移，标准 Gateway 审计。事务边界为 Base owner；数据分类 confidential。
- 安装复用 `base.plugin.installation.request.create@1`；卸载复用 `base.plugin.installation.transition.uninstall@1`，携带 expected_revision、保留团队数据。
- 启停、更新和回滚复用 `plugin.enable/disable/upgrade/rollback@1`；权限 `system.plugin.manage`，原 admin confirmation、A0、认证新鲜度、幂等键、资源授权及高风险审计继续生效。内部 `plugin.upgrade.finish` 未对外开放。
- “确认更新可用”为用户显式确认后的 `plugin.enable@1`；不会生成或声称自动健康验收。失败/升级中状态可按状态机回滚。
- 修复 MySQL 回滚授权赋值顺序，使用锁定行的明确新旧 grants；所有现有安装 UPDATE 写入均推进 revision，避免旧页面卸载新状态。
- 无跨域数据库写入，无新增重复生命周期能力。内置官方模块的独立插件设置保留；该市场管理已签名发布及租户安装记录。

## 4. Implementation boundary

- 后端 owner：`backend/base/plugin_marketplace.py`、`official_provider.py`、`backend/plugin_platform/service.py`、`backend/capabilities/plugin_marketplace_next.py`。
- 共享边界：Catalog 构建/consumer refs、Provider artifact manifest、生成 Catalog/lineage；Base 契约测试按 major 1 核对原冻结版本，避免新候选继承旧 stable 结论。
- 桌面消费方：`official.core`、`web/plugin_marketplace/model.js`、`ai00.desktop.windows-x64`。固定 query major 2、生命周期 major 1。`consumer_type=web` 是仓库现有交互传输类型，App 仍有独立的已签名 consumer ID。
- 暴露：交互 App/Web/API；新查询的 plugin、agent、MCP 均关闭。依赖 `base.identity.session.profile.get@1` 读取当前管理权限。
- Electron 调用通过共享 facade → preload → 主进程 Capability IPC → Gateway；渲染层不增加带身份的任意 HTTP 通道。
- 数据：现有 `workmanship_plugin_releases`、`workmanship_plugin_installations`、生命周期事件、幂等记录、mount/namespace 表；仅复用既有 migration，无 DDL。
- Base artifact 摘要按实际源码重算。整库 Registry 校验同时要求同步已有 simulation 未提交源码对应的摘要，未修改其业务实现。保留工作树其他改动。
- 本地 App 的未发布 manifest 同步 Base 摘要，已重启核验过的测试后端；未重启桌面窗口、未修改生产数据库、未推送或发布安装包。

## 5. Verification evidence

- `python -m pytest backend/tests/test_plugin_marketplace_search.py backend/tests/test_marketplace_lifecycle_sql.py backend/tests/test_plugin_platform_service.py backend/tests/test_plugin_lifecycle_security.py backend/tests/test_plugin_platform_next.py backend/tests/test_plugin_center_contract.py backend/tests/test_plugin_center_productization.py -q -p no:cacheprovider`：**40 passed**。包含实际 SQL、Ed25519 校验、缺失依赖、租户隔离、回滚授权、revision、Gateway 授权与已声明错误；存储为隔离 SQLite/内存夹具，不是真实团队安装。
- `node scripts/test_plugin_marketplace.js`：**6 passed**。包括实际 DOM 控制器、取消、重复操作阻断、读取失败阻断旧按钮，以及真实 facade/preload/main IPC/manifest 校验链。HTTP 上游为测试替身，无真实安装。
- `node scripts/test_electron_plugin_lifecycle_security.js`、`node scripts/test_electron_capability_boundary.js`、`node scripts/test_electron_runtime_mode.js`：通过。
- 既有 `test_existing_capability_migrations.js` 与 `test_atomic_web_migrations.js`：通过。
- Vite 隔离编译：通过；沿用原多页面入口/转换，仅关闭会覆盖现有 dist 的复制钩子，输出 `.superpowers/marketplace-qa/build`。这不是签名桌面安装包验证。
- `build_capability_catalog.py --write --previous .runtime/marketplace-qa/previous-catalog.json`：兼容性检查通过；`--check`：809 descriptors 一致性通过。
- 本地 App 后端 `/health` 与 `/ready`：HTTP 200，运行时生成 Catalog 包含新 query@2。
- 扩大回归未全绿：设置正确 `AI00_BACKEND_ROOT` 后，`npm test` 在未改动的 `test_simulation_p0_boundary.js:35` 失败；后端扩展检查中角色分配用例 `test_structural_gateway_enforces_admin_boundary_and_write_confirmation` 独立运行仍失败；原 Base 全 stable 假设也与已存在的 experimental desktop 能力冲突。未把这些结果记为通过。
- 浏览器隔离夹具只验证渲染；真实访问没有登录态会进入登录页。本地已有桌面 token 发起只读查询得到 401；未生成新身份/令牌或替用户批准插件权限，真实登录态 App 生命周期验收 **unverified**。
- `code_revision` 与原始输出 `result_hash`：见同目录 `2026-09-22-plugin-marketplace-app-evidence.json`（源码/日志文件 SHA-256，未提交工作树）。
- `snapshot_gid`: unverified；`test_run_gid`: unverified。以上是本地执行证据，未写入可信服务器治理证据服务，不伪造 Snapshot 或 TestRun。

## 6. Governance status

- `machine_passed`: **false**（整库扩展回归存在上述失败；本次插件市场专项与 Catalog 一致性通过）。
- `human_approved`: **unverified**。实现授权不等于对精确业务定义与 Snapshot 的治理审批。
- `runtime_verified`: **unverified**。本地服务加载成功及模拟桌面 IPC 测试，不替代登录后的桌面实机生命周期验收。
- `advisory`: **true**。未批准、豁免、发布、合并，未修改可信 ReleaseReport 或伪造审批结论。

## 7. Findings and unresolved risks

- 已修复的实现问题：旧桥接/初始化缺失、无一级入口、失败状态缺失、错误操作按钮、写后刷新失败仍可操作、revision 未推进、更新/启用/回滚未验签和校验依赖、回滚权限交换及未声明业务错误映射。
- unverified：登录态桌面窗口中的真实安装、启停、升级确认、回滚和保留数据卸载；桌面正式签名包发布。
- blocked：当前会话缺少可用的桌面测试登录凭证，不能完成认证实机验收；没有绕过认证或扩大权限。
- 所需后续人工动作：在桌面 App 使用有效登录态完成上述验收；需要发布时，由可信 super_admin 对精确版本、business_definition_hash 和真实 Snapshot 作治理审批。代码修复本身不以该审批为前置条件。

核对结论：原子性、owner、版本身份、消费声明、暴露及数据边界已核对；机器专项通过、全局失败、模拟运行和未验证项分别记录；人工与服务器审批仍保持独立。

## 本地客户端构建部署补充

用户随后明确授权构建并放入当前客户端，已执行 `npm run build:web:test-governance`，包含完整静态资源复制步骤，产物位于前端工作树的 `dist-test-governance`。原生产目录及其未提交改动未覆盖。

已核验当前 Electron 主进程为 PID 290928，app-path 指向上述前端工作树。其 `http://localhost:5173` 本地资源服务已从 Vite 开发服务切换到完整测试构建的 Vite preview（PID 329044），保留同一地址、后端及用户数据。页面不再包含 `/@vite/client`，提供的是构建产物。首轮 PowerShell 就绪探测超时；随后用 Python HTTP 客户端独立验证服务正常，并逐个比较实际响应与构建文件的 SHA-256。

部署证据：前端 `.superpowers/marketplace-qa/current-client-deployment.json`；完整构建日志 `.superpowers/marketplace-qa/full-app-build.log`。该操作是更新当前本地桌面测试实例的资源，不是发布正式签名安装包。客户端窗口重新加载及登录后的真实生命周期验收仍为 unverified；治理审批状态不变。
