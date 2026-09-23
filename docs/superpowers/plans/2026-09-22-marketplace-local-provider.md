# App 插件市场与本机 Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 默认本任务顺序实施；只有明确安排独立任务后才并行。

**Goal:** 在 AI00 App 内完成插件打开与受治理调用，使 CAD 插件能够提供可复用能力并生成、保存 DXF/JPG。

**Architecture:** 复用市场签名、安装生命周期、SDK sandbox host、Capability 治理与 Artifact 服务。新增本机 Provider 适配层，限定当前 App/设备会话，执行前验证精确批准与安装 revision；CAD 算法归插件。分三个可验收交付阶段，Provider 隔离技术验证不通过时保留第一阶段成果，不以放宽宿主权限替代隔离。

**Tech Stack:** 现有 Electron、JavaScript/TypeScript SDK、Python 服务、Capability Catalog/Descriptor/Gateway、Artifact；不预先引入第三方执行引擎。

**Spec:** [CAD 接入需求与候选方案](../../governance/2026-09-22-plugin-provider-cad-proposal.md)。本文不是治理审批。

**实施状态（2026-09-22）：** 任务1–5代码及隔离验证完成，已构建并重启当前测试 App；任务6已完成最终 CAD 候选包的实际 Electron/Gateway/Artifact 集成验证。正式注册、数据库迁移、真实批准、签名发布与用户上传验收仍未完成。下方保留原始计划检查项，不将替代测试或部分满足的步骤勾成全通过；以[交付记录](../../governance/2026-09-22-plugin-local-provider-delivery.md)和 SDD ledger 为准。

## Global Constraints

- 仅交付 AI00 App 内插件；不控制 AutoCAD、不引入 COM。
- 本次不做跨设备调度，不恢复任意 Python bridge，不把第三方代码导入官方 DomainProviderLoader。
- CAD owner 负责布局算法/模板和图纸；平台负责通用机制。
- 用户在执行中确认：CAD 首版支持任意数量线体，不采用旧 14 槽限制；资源超限必须明确拒绝，不能截断或静默合并输入。
- 包签名与 Capability 精确业务哈希/Snapshot 批准独立。
- 本机文件写入必须经用户目标选择和受控宿主机制；保持普通插件下载限制。
- 保留已有 dirty changes；不自动提交、发布或覆盖生产资源。阶段验收后才更新当前测试客户端，保留可恢复的上一版构建。
- 所有新增接口名与文件在下文明确标为计划；正式 Capability ID/GID 从实际 owner/治理流程产生，禁止杜撰标识。

## Review Focus

1. 打开插件后账号/tenant 改变，旧窗口不得沿用旧授权（任务1）。
2. 升级或撤销与执行并发，旧 revision 不得继续提交副作用（任务4）。
3. 高权限 Provider 被低权限插件调用，不能借权读取 BOP（任务3、4）。
4. 已批准版本的包或业务定义变化，旧批准不得继续生效（任务2）。
5. 保存取消、磁盘写入失败、同名覆盖，不能报告导出已保存（任务5）。

## 工作区与文件职责

F = `E:/Projects/ai00_v3/.worktrees/orchestration-merge-frontend-20260905`。
B = `E:/Projects/ai00_v3/.worktrees/orchestration-merge-backend-20260905`。

| 路径 | 职责 |
| --- | --- |
| F/web/plugin_marketplace/marketplace.js、model.js | 已安装列表打开动作、状态与错误 |
| F/web/workspace/tab_manager.js | 工作台插件标签生命周期 |
| B/packages/plugin-sdk/src/host.ts、index.ts | sandbox 协议与统一调用；优先复用既有 mountAi00Plugin |
| F/packages/core/electron/main.js、preload.js、capability_client.js | 可信宿主身份与受控调用入口 |
| F/packages/core/electron/desktop_artifacts.js | 用户选择保存与 Artifact 完整性 |
| B/backend/plugin_platform/manifest.py、compatibility.py、service.py、mounts.py | 包契约、兼容、生命周期、挂载授权 |
| B/backend/capability_v2/provider_loader.py | 只作为现有官方边界检查对象，不扩展第三方导入 |
| 计划新增 F/web/plugin_marketplace/plugin_host.js | 挂载/销毁 SDK host，不嵌入 CAD 业务 |
| 计划新增 F/packages/core/electron/plugin_provider_runtime.js | 受限上下文创建、资源与会话回收 |
| 计划新增 F/packages/core/electron/plugin_provider_router.js | 解析精确绑定、调用链与本机会话路由 |
| 计划新增 B/backend/plugin_platform/provider_bindings.py | 插件声明到既有治理身份的绑定与状态检查 |

隔离试验先决定最小运行时结构，避免同时维护两套实现。既有 SDK 源码位于 B，接入 F 时使用可追踪的构建产物，不手抄协议代码。

## 阶段一：插件在当前 App 可打开、可调用（独立交付）

### 任务1：市场打开入口与真实 SDK host

**接口：** 复用 `mountAi00Plugin({container,url,grantedCapabilities,capabilityVersions,catalogRelease,mountSessionId,invoke}) => dispose`。URL/授权由服务端有效 mount 信息提供；不接受插件传来的任意 URL、token、tenant。先核实实际 mount/invoke 路由并记录调用契约；如挂载入口没有合规 Capability，先完成 owner 契约设计，不从页面硬编码旁路。

- [ ] 在 F/scripts/test_plugin_marketplace.js 补用例：启用插件显示打开；停用不可打开；重复打开聚焦已有标签；关闭清理监听。
- [ ] 在 F/scripts/test_desktop_plugin_bridge.js 补真实协议用例：错误 source/channel、过期 session、未授权能力、账号/tenant 切换拒绝；成功调用保持原 CapabilityResult。
- [ ] 运行用例，确认失败源是缺少接线，再实现 plugin_host.js、市场按钮与标签挂载。
- [ ] 每次调用重新验证安装与授权，注销/切换会话销毁 host；SDK 的 mountSessionId 必须真正参与可信验证，不能只传参数。
- [ ] 执行以下现有回归；修复只限本任务引入的问题：

```powershell
# F
npm run test:plugin-marketplace
node scripts/test_desktop_plugin_bridge.js
node scripts/test_electron_capability_boundary.js
# B
python -m pytest backend/tests/test_plugin_mount_sessions_v2.py backend/tests/test_plugin_router_lifecycle_security.py -q
```

- [ ] 构建 `npm run build:web:test-governance`，更新当前测试 App，用已有 Hello 包验证打开与 storage/BOP 调用。无有效登录或无法操作窗口时，记录后台/协议测试通过、实机未验证，不能记本阶段实机通过。用户后验文件选择上传保持原约定。

**退出标准：** App 内可打开 Hello；至少一项真实授权 Capability 成功；停用、关页、换账号后旧通道失效。可单独交付，不等待 Provider 扩展。

## 阶段二：受治理的本机 Provider（先验证，再实现）

### 任务2：冻结最小契约和治理绑定

**文件：** B/backend/plugin_platform/manifest.py、provider_bindings.py（新）、B/packages/plugin-sdk/manifest-v2.schema.json（保持旧版兼容）；计划新增版本化 schema 文件及 B/backend/tests/test_plugin_provider_bindings.py。

- [ ] 从当前 Catalog、Registry、Descriptor、Snapshot/审批存储读取真实字段和 owner 规则；记录 ID、major、GID、business_definition_hash、artifact hash 的权威来源，不另建审批体系。
- [ ] 形成新版本 manifest 契约：提供能力列表与入口映射、消费依赖分离；保留 v2 消费型插件原行为。执行入口只允许已签名包内受控 JS 模块路径，不能是任意模块/URL/本机路径。
- [ ] 用固定 fixture 验证：原 v2 可解析；声明冲突、越 publisher namespace、未知 owner、未批准/哈希不符全部拒绝。先失败再最小实现。
- [ ] 绑定结构明确包含 plugin_id/release version、owner、capability_id/major/GID、business hash、Provider artifact hash、Snapshot 引用；运行态另含 tenant、device session、installation revision，不能混同静态审批身份。
- [ ] 如果需要持久化映射，先核查现有 owner 表；只新增必要 owner migration，验证重复执行和失败恢复，不另存一份批准结论。
- [ ] 输出契约文档与 machine evidence；正式注册与批准经真实治理流程完成。

**退出标准：** 所有字段有权威来源，旧包兼容；治理批准与包审核分别可验证。未获批准绑定保持不可执行。

### 任务3：受限执行技术验证

**文件：** 计划新增 F/scripts/test_plugin_provider_isolation.js；候选运行时 plugin_provider_runtime.js。试验不进入默认启用路径。

- [ ] 比较三种路径：受限 Electron renderer/worker（优先验证，复用现有依赖）；嵌入 JS 引擎（只有前者不满足隔离时评估）；服务端执行（不满足当前本机最小范围，本轮不选）。
- [ ] 用 dummy pure-compute Provider 验证关闭页面后仍可被授权宿主调度；不允许 DOM 页面函数直接成为 Provider。
- [ ] 探测 Node/process/require、任意 IPC、文件读写、fetch/WebSocket、动态远端脚本与窗口逃逸；预期全部拒绝。宿主只放行精确受治理 broker。
- [ ] 测试无限循环、超大输出、取消、崩溃；宿主能终止独立执行上下文并返回稳定失败，不拖死 App。
- [ ] 定义可配置的执行时间、输入/输出与并发限额；基于 dummy 和 CAD 样本测量确定默认值，写入契约和边界测试，不凭空扩大整个 App 限额。
- [ ] 保存隔离证据。任何权限绕过未解决时停止该候选进入产品代码，保留阶段一成果；不通过开启 Node 或关闭 sandbox 达成运行。

**退出标准：** 选定一个可验证运行时，隔离与终止有效；仅具备 JS 执行不算通过。

### 任务4：统一路由与生命周期绑定

**文件：** F/plugin_provider_router.js 对应上表完整路径；B/backend/plugin_platform/provider_bindings.py、service.py；计划新增 F/scripts/test_plugin_provider_router.js、B/backend/tests/test_plugin_provider_lifecycle.py。

**接口草案：** `invoke({capability_id, major, payload, request_id, idempotency_key?}, trustedContext) -> CapabilityResult`；trustedContext 只能由宿主生成。路由解析 GID、批准身份、Provider artifact 与 revision，不信任调用方自行填写。复用现有 result/error schema，新增稳定错误先写入契约。

- [ ] 用两款 dummy 插件测试 A 调用 B 成功与无权限失败；测试伪造 caller、跨 tenant、低权限调用高权限 Provider 不得借权。
- [ ] 用实际 Gateway/治理策略检查精确绑定；App 内只做执行适配，不建立可绕过服务端授权的第二条普通执行入口。
- [ ] 实现本机注册：安装停用态不可调用；启用检查审批、依赖和健康；页面关闭不改变安装态；App/设备离线无可用路由。
- [ ] 升级健康通过后切换绑定，旧 revision 失效；失败恢复旧绑定前重新检查批准与依赖；回滚执行同样校验。
- [ ] 停用/撤销/卸载拒绝新调用并取消旧执行；副作用提交前再次检查 revision。测试检查与提交的竞态，不仅测试静态状态。
- [ ] Agent 仅能通过同一宿主授权路由调用；无本机会话返回稳定不可用，不在全平台广告本机 Provider。
- [ ] 记录审计：调用方与被调用方、精确版本/GID、设备会话、revision、结果与 correlation；默认不记录完整敏感 BOP payload。

**退出标准：** 两插件跨调用和完整生命周期通过；篡改批准、断线、重启、并发撤销均有可重复证据。

## 阶段三：产物保存与 CAD 首个真实接入

### 任务5：通用 Artifact 与本机保存

**文件：** F/packages/core/electron/desktop_artifacts.js、capability_client.js、B Artifact owner 既有接口；F/scripts/test_desktop_round5_artifacts.js，计划新增 F/scripts/test_plugin_artifact_save.js。

- [ ] 核对已有二进制 Artifact 创建能力是否向插件开放；缺失时按 owner 新增最小通用契约，不用 CAD 专用上传接口。
- [ ] 插件 Provider 返回受控 artifact_ref、摘要、名称、media_type、byte_size；输出内容与扩展名匹配，DXF/JPG 两种格式均做校验。
- [ ] 保存由用户手势触发可信宿主对话框；插件不能传目标绝对路径。复用完整性校验与权限，明确覆盖确认、取消、写入失败语义。
- [ ] 测试正常保存、无权限引用、大小超限、摘要不符、用户取消、磁盘失败、同名覆盖；失败不得报告已保存或留下被当成成功的截断文件。
- [ ] 执行既有 Artifact 与宿主边界回归，保持非插件消费路径兼容。

**退出标准：** dummy Provider 产物可受控保存，取消与失败准确显示；不依赖普通浏览器下载。

### 任务6：CAD owner 接入与联合验收

**源码参考：** `E:/Projects/ai00_v3/plugin/CAD生成器备份/CAD生成器备份`。由 CAD owner 审核源代码后确定修改文件；市场任务不改其业务源码。

- [ ] 冻结两个业务契约：布局生成（纯计算）；布局导出（format=DXF/JPG，生成 Artifact）。字段、错误、幂等、权限与精确 owner/GID 按治理流程确定后发双方共享契约。
- [ ] 复用 craft.bop.version.list@1、version.get@1、structure.outline.get@1；版本固定、正确分页；需要明细才消费 work_package.get@2、entry.detail.get@1。
- [ ] CAD 提供最小/多线/空工位/长文字/非法尺寸样本，验证统计口径、布局确定性、相同布局两种输出一致性。
- [ ] 用第二款消费插件调用 CAD 布局能力，证明不是页面私有函数。验证缺依赖、停用、升级与回滚的稳定结果。
- [ ] 构建签名 CAD 包，在当前测试 App 完成安装、打开、真实数据授权调用、生成、保存、升级、回滚和卸载；用户验证此前约定的文件选择上传。
- [ ] CAD owner 验证 DXF 在目标软件可打开、JPG 标注可读，保存样本与证据；平台测试不操控 AutoCAD。

**退出标准：** 当前 App 内真实 CAD 链路和跨插件复用通过；不增加独立 Web 版交付。

## 交付、治理与恢复

每阶段交付源码差异、测试命令/结果、当前构建身份及未验证清单。测试结果区分单元、协议、隔离后台、真实存储、Electron 实机；历史 50 项通过不作为新增 Provider 通过证据。

治理报告保持顺序：Change classification → Authoritative context inspected → Reuse/atomicity/ownership → Implementation boundary → Verification evidence → Governance status → Findings/risks。当前规划 `machine_passed=unverified, human_approved=unverified, runtime_verified=unverified, advisory=true`；正式批准只由可信 super_admin 对精确对象执行。

先交付阶段一，再完成任务2/3后实施任务4；任务5可在契约稳定后独立完成；最后联合任务6。默认本任务顺序推进，CAD owner 在契约冻结后负责业务改造。本轮不承诺工期：任务3隔离试验和真实 App 登录验收是主要不确定项。

恢复策略：第一阶段失败恢复上一版测试构建；Provider 功能独立默认关闭，只有治理有效、安装启用且健康通过才激活；回滚代码不得恢复已撤销的治理授权。已有用户数据按当前保留策略处理，不为测试清空业务库。

## 规划自查

- [x] 用户需求已映射到任务1—6，CAD 与平台责任分离。
- [x] 现有事实与计划新增文件/接口分开，未声称 Provider 已支持。
- [x] 关键失败条件均对应具体任务验收；没有把修改 manifest 当成生命周期完成。
- [x] 未产生虚构 GID/Snapshot/批准；未执行实现、发布或数据库变更。
