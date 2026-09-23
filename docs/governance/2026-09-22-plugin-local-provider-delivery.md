# App 插件市场与本机 Provider 交付记录（2026-09-22）

## 1. Change classification

兼容扩展和实现修复：Manifest 2.1 增加受治理的本机 Provider，2.0 消费型插件保持原契约；市场 App、管理上传、挂载、调用和保存形成闭环。CAD 两项业务能力仍为候选，本文不构成批准或发布。

## 2. Authoritative context inspected

已核对实际 manifest、市场签名/安装生命周期、mount、SDK host、Gateway policy/reliability、Catalog/Descriptor、SqlGovernanceStore 的 Snapshot/精确业务批准、Artifact、数据库 owner 清单和迁移 runner。

- 候选能力：`huangjing.cad.layout.generate@1`、`huangjing.cad.drawing.export@1`；owner/维护人：黄晶；publisher：`huangjing`；plugin：`huangjing.cad.layout-generator`。
- 公共 capability_version_gid、正式 snapshot_gid、test_run_gid：unverified，未生成冒充正式记录。人的身份 GID 与 Capability GID 不混用。
- CAD 业务定义、输入输出、稳定错误见 `E:/Projects/ai00_v3/plugin/huangjing.cad.layout-generator/contracts.schema.json`、`provider.candidate.json`、`GOVERNANCE.md`。布局为无副作用读取；导出生成租户 Artifact，必须按写能力鉴权及幂等重放。任意线体数量受字节/图像可读性资源限制，拒绝时不截断。
- 本次允许的本地描述符：明确 plugin exposure、authenticated policy、精确 provider/artifact 绑定；不支持借 Provider 权限读取其他资源。BOP 仍由原调用者经已有 Gateway 获取。
- 稳定错误和允许重试来源于可信 Descriptor，不接受插件任意错误文本。敏感范围为调用者租户输入和生成产物，不赋予文件或网络访问能力。

## 3. Reuse, atomicity, and ownership result

复用市场签名、安装 revision、Gateway、Artifact 和既有治理批准；未创建第二套批准系统。Snapshot/批准与 ZIP 分离，避免批准绑定同一 ZIP 哈希产生循环。跨插件调用须显式依赖并保留原 consumer/actor/tenant/mount 权限。

生成在每次调用独立的沙箱 renderer 中执行；Artifact 是服务端单一写效应。写幂等采用原 Gateway reliability 和 projected replay，产物提交重新校验安装及精确批准。保存文件是用户选定目标后 Main 执行的独立动作，不把生成等同于已经保存。

新增 Base owner 迁移 `backend/db/migrations/test_governance/0010_local_provider_runtime_fence.sql`：一个治理提交锁行，由 Snapshot/业务批准写入与本地 Artifact 提交共同持有。迁移可恢复回填，owner/inventory/runner allowlist 已同步。缺表时本地产物提交拒绝，不降级绕过锁。

## 4. Implementation boundary

- 后端：`plugin_platform/{manifest,provider_bindings,local_providers,service,artifacts}.py`、市场 router、Gateway invocation-local resolver；治理 store/runtime_fence 和迁移。
- App：`plugin_provider_runtime.js`、`plugin_mount_client.js`、Main/preload、`desktop_artifacts.js`、可信 host 保存栏。源代码和 job secret 不交给插件 iframe。
- CAD 算法由 CAD 协调任务在 `plugin/huangjing.cad.layout-generator` 维护，平台未修改其业务文件。
- 约束：单 App/设备；无 COM/AutoCAD；无网络/Node/任意宿主 IPC；每次沙箱独立，60 秒上限、并发上限、输入输出限额和采样内存保护。内存采样不是严格堆配额。
- 保留已有 dirty changes，未提交、推送或生产发布。

## 5. Verification evidence

最终后端命令：`python -m pytest backend/tests/test_plugin_provider_bindings.py backend/tests/test_plugin_local_providers.py backend/tests/test_plugin_governance_fence.py backend/tests/test_capability_governance_store.py backend/tests/test_capability_governance_business_store.py backend/tests/test_capability_governance_migrations.py backend/tests/test_plugin_mount_sessions_v2.py backend/tests/test_plugin_router_lifecycle_security.py backend/tests/test_capability_gateway_pipeline.py -q -p no:cacheprovider --basetemp <isolated-temp> --tb=short`：**158 passed**。

此前广泛市场/生命周期/包上传/Gateway 回归 **113 passed**（与最终回归部分重叠，不累加）；旧 ZIP 重复项拒绝测试产生预期警告。前端市场11、mount7、host2、transport/save2和边界脚本通过。真实隐藏 Electron 沙箱测试7场景通过，包括超时、取消、内存压力、网络拒绝和受信错误映射。

实际集成：运行 `backend.tests.support.plugin_provider_http_fixture`，Electron 执行 `scripts/test_plugin_provider_http_e2e.js`。真实 Main → HTTP Gateway → CAD 沙箱 → Artifact → 原子保存，登录/批准/安装和文件选择均为隔离 fixture，未访问真实用户数据或代登录。

| 场景 | 结果 |
| --- | --- |
| 16 线 DXF | 7608 bytes，通过 |
| 16 线 JPG | 160071 bytes，通过 |
| 1001 线 DXF | 426657 bytes，通过 |

最终 CAD ZIP SHA256：`afc9b22e8503416b2526b81384628dfb9e255e042711703c854de9fcc308d205`。该包是未签名候选 ZIP，不能直接当正式安装外包。

原始证据：前端 `.superpowers/marketplace-qa/provider-http-e2e.json`，SHA256 `1b697c53dd52203410c85392f3494725f588e811b8c3fb46b2bbfb6d56b689ff`；沙箱证据同目录 `provider-runtime.json`。code_revision：后端 HEAD `8d3270084cb786815523acbbcc8c2b9f0e4cccf1` 加未提交工作区变更，不能将 HEAD 单独视为最终补丁身份。

`npm run build:web:test-governance` 成功，旧静态资源已备份到前端 `.superpowers/marketplace-qa/pre-local-provider-dist-*`。已重启当前测试 App PID349244、后端 PID348624；8080 health/ready、5173 市场/host 页面均200。构建保留现有非 module 脚本提示；后端日志有既有 Windows 编码日志错误，但应用启动完成且 readiness 正常。没有操作或确认真实 App 登录后的界面。

独立审查两个 Important 问题均先重现再修复：保存末次 stat 等待期间换账号，新增 rename 前会话检查；治理批准变动与产物提交竞态，新增共同 SQL fence 并在锁内重新读取绑定。共享锁并发测试为模拟数据库连接，真实数据库并发未测。

## 6. Governance status

- `machine_passed`: true，仅指上述代码及隔离自动检查；正式候选发布的机器 Gate 尚未运行。
- `human_approved`: unverified，未注册/制造真实业务批准。
- `runtime_verified`: unverified（真实账号与正式批准部署）；隔离真实 Electron/HTTP 执行通过。
- `advisory`: true。

## 7. Findings and unresolved risks

- 2026-09-23 test-plugin result-envelope follow-up — classification: backward-compatible SDK host fix. The visible `Error: storage update failed` was not intended product behavior and did not mean the package was empty. The immutable `acme.ai00.hello@1.0.20260922` test package used the earlier example convention `result.success`, while the governed Gateway and current host return the canonical `CapabilityResult.ok`; a successful storage response was therefore interpreted as failure inside the example before the BOP list call. The host now preserves the complete canonical envelope and adds a derived `success = ok` compatibility field only on the sandbox message boundary, so already-published example packages work without changing their signed bytes or bypassing Gateway policy. Canonical SDK examples/templates now consume `ok`. The regression was observed failing before the change and passing afterward; host tests passed 2, mount-client tests passed 7, the Electron sandbox test exited successfully, the test-governance Web build succeeded, and the served host contains the compatibility bridge. The local App was restarted with backend, frontend, and ConnectorHost healthy. `machine_passed=true`; the compatibility behavior is runtime-verified at the host boundary; the final visible button result remains a user-visible App check because native App accessibility is unavailable to this task.
- 2026-09-23 plugin-open follow-up — classification: local test-environment configuration fix. The uploaded `acme.ai00.hello@1.0.20260922` package is not empty: its signed envelope contains `plugin.zip`, and the inner archive contains `index.html`, `app.js`, `style.css`, `ai00-plugin-sdk.js`, and `plugin.json`. Authoritative marketplace state shows the release is `published` and its installation is `enabled` with no recorded installation error. The host's generic “请确认已登录且插件已启用” message masked a `plugin_mount_unavailable` response: the running local backend had no `AI00_PLUGIN_MOUNT_SECRET`, so registry issuance returned 503 before package content could load. A persistent local-test-only mount secret is now validated and loaded by `.runtime/run_current_test_backend.py`; no capability policy, installation state, approval, or package was changed. After restart, health/readiness returned 200, direct Electron mount returned a governed handle with the three declared capability versions, the host reopened an `ai00-plugin://.../index.html` frame, and all four Web assets returned 200. The shared signing/mount configuration regression passed. `machine_passed=true`; local mount and asset delivery `runtime_verified=true`; interactive invocation of the test button remains a separate user-visible check.
- 2026-09-23 install authentication follow-up — classification: compatible App implementation fix. Authoritative test marketplace state shows `acme.ai00.hello@1.0.20260922` is `published`, while the installation table remains empty. The install request was rejected by Gateway before Provider dispatch because `base.plugin.installation.request.create@1` requires authentication within 300 seconds; access-token refresh intentionally preserves the original authentication time. The 300-second policy remains unchanged. On `authentication_stale`, the App now starts the existing desktop Feishu authorization-code flow, refreshes marketplace state after success, and requires the user to click and confirm installation again; it does not replay the high-risk write automatically. The new regression first failed against the old generic error path, then passed; `npm run test:plugin-marketplace` passed 13 marketplace tests plus lifecycle security, the production Web build succeeded, and the current Electron App was reloaded with the marketplace iframe present. No installation was created by this remediation. `machine_passed=true`; release review `human_approved=true` for this test package; install `runtime_verified=unverified` until the authenticated super administrator completes reauthentication and retries.
- 2026-09-23 authorization-window follow-up — the live Electron target showed the Feishu authorization page existed with an enabled authorization button while the user observed no response from the launch link. The OAuth BrowserWindow now calls `focus()` immediately after `show()` so the authorization surface is brought to the foreground. The regression was observed failing before the change and passing afterward; desktop auth security, embedded OAuth, 13 marketplace tests, and lifecycle security passed. The Electron main process was restarted and the marketplace tab reopened. This changes presentation only; it does not grant consent or replay installation.
- 2026-09-23 review follow-up — classification: test-environment configuration fix. Authoritative `test_` state showed `acme.ai00.hello@1.0.20260922` remained `submitted`, publisher `acme` was active, and no platform signature/reviewer write occurred. The failure was the local backend's missing `AI00_PLUGIN_PLATFORM_ED25519_PRIVATE_KEY` and matching public key. A persistent local-test-only Ed25519 pair is now validated and loaded by `.runtime/run_current_test_backend.py`; the backend was restarted without executing the review. The current release envelope passed platform sign/verify, focused marketplace/lifecycle tests passed 21 with one expected duplicate-ZIP warning, and health/readiness returned 200. `machine_passed=true` for this configuration fix; `human_approved=unverified` and real review `runtime_verified=unverified` until the authenticated super administrator retries the pending review.
- 2026-09-23 upload follow-up — classification: compatible implementation fix. The selected `acme.ai00.hello@1.0.20260922` package reached governed submission, but the current `test_` publisher and release tables were both empty; submission therefore failed because publisher `acme` was not registered. The package signature was reverified against `publisher-public.pem`. The App now expands and enables the publisher form, focuses `publisher_id`, and explains the registration/key/version checks on `marketplace_state_conflict`. `npm run test:plugin-marketplace` passed 12 marketplace tests plus lifecycle security; mount7, host2 and capability-boundary checks passed; test-governance build succeeded and App PID461144 was restarted. This does not register or approve the publisher: `machine_passed=true` for the UI fix, `human_approved=unverified`, and real upload `runtime_verified=unverified` until the authenticated super administrator registers `acme` and retries.

- **blocked**：本机缺少专用 `AI00_BASE_DDL_DB_URL` 配置，0010 未执行。已请求现有配置路径；没有把 runtime USERS_DB_URL 作为 DDL 凭据。拿到专用配置后须使用现有迁移 runner 检查/应用，并补真实数据库并发验证。
- **blocked**：正式 CAD 发布者注册、公共 Capability GID、精确 Snapshot/业务批准、签名外包尚无真实流程记录。应由登录的授权超管完成；AI 不替代批准。当前不会把候选包置为可执行的正式插件。
- **unverified**：用户实际超管上传文件选择、登录后打开/管理/保存验收，按用户约定后验。
- **deferred / Minor**：local-job complete 当前仅接受对象 JSON，尚不支持通用标量/数组结果；CAD 两项输出都是对象，不受影响。
- **deferred / Minor**：现有审计保留原 consumer、capability/major、request/payload hash 和状态，但未完整落库 producer 的 GID/revision 绑定链，正式发布前需补齐完整审计证据。
- 审查范围不替代 CAD 算法正确性、严格堆配额、真实数据库并发或生产部署证明。CAD owner 的文件解析/图像验证为该任务证据，不冒充平台独立验收。

用户可先在当前测试 App 验证工作台“插件市场”和超管管理入口；候选 CAD 正式安装要等上述迁移、治理与签名完成。
