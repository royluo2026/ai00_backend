# Capability Governance Center Completion Design

## Goal

把治理中心从“能力清单可用、其余页面部分占位”补齐为一个只读优先、证据驱动、可审计的测试环境治理控制台。六个页面都必须连接真实 Gateway/Service 数据；任何依赖缺失、权限不足或证据过期都必须显式显示，不能用空数据伪装成功。

## Scope and constraints

- 只改测试环境 `test-governance`；不修改生产配置、不推送远端、不修改旧服务。
- 继续使用 Vanilla JavaScript、现有设置页样式和 Capability Gateway；不引入前端框架。
- 不增加跨领域业务 SQL、插件业务表或特殊读取 API。治理数据只来自 Capability Governance Store、workflow/release ports 和审计投影。
- 所有列表查询有明确 `limit`（默认 50，最大 200），错误返回结构化 `code/message/retryable/details`。
- 所有管理写操作继续受 `system.plugin.manage`/现有治理权限约束；普通成员只能读取授权范围内的数据。
- 不读取 Cookie、密码、Token 明文或数据库凭据；前端只使用现有认证状态和 Gateway。

## Product surfaces

### 1. Overview

展示真实 Catalog Release、当前快照、Finding 总数/严重级别、11 个领域健康汇总、最近发布闸门结论。每个指标携带 `source`、`checked_at` 和 `snapshot_gid`，缺失时显示 `unverified`。

### 2. Inventory

保留当前已经可用的能力清单，并补充跨域搜索、状态/消费者筛选、关系摘要和详情抽屉。清除筛选必须恢复全量查询；切换筛选不能生成重复请求。

### 3. Findings

按领域、严重级别、状态和文本筛选问题；详情中显示规则、证据、快照、影响能力和建议。管理员可生成修复 Prompt；生成失败时保留上一次成功数据并展示可读错误。

### 4. Changes

显示提案、目标能力、基线/候选版本、代码和 Catalog 哈希、评审阶段、冲突/过期原因。管理员可提交评审、批准、拒绝、撤回；每个写操作使用确认对话框、幂等键和按钮忙碌态。

### 5. Health

展示 11 个领域的 `healthy/attention/blocked/unverified` 卡片、快照时间、检查时间、Finding 数量、依赖错误和重新扫描/重新分析入口。健康结论由后端根据快照和 Finding 计算，前端不得自行推断。

### 6. Release and Audit

发布页展示候选版本、快照、测试、Finding、审批、签名和证据状态；执行发布闸门时只读取服务端固定证据，证据不完整或过期必须 fail-closed。审计页支持按时间、操作者、能力、事件类型和结果检索脱敏事件，并显示关联 report/proposal GID。

## Capability contracts

新增只读契约：

| Capability | Purpose | Input | Output |
| --- | --- | --- | --- |
| `base.capability_proposal.search@1` | 查询变更提案 | `query`, `domain`, `stage`, `limit`, `cursor` | `items`, `next_cursor`, `checked_at` |
| `base.capability_health.get@1` | 查询领域健康 | `domains`, `snapshot_gid` | `items[]` with status, counts, evidence |
| `base.capability_audit.search@1` | 检索治理审计 | `from`, `to`, `actor`, `capability`, `event_type`, `result`, `limit`, `cursor` | redacted `items`, `next_cursor` |

现有契约继续使用：

- `base.capability_registry.search/get@1`
- `base.capability_graph.get@1`
- `base.capability_finding.search@1`
- `base.capability_analysis.run/get@1`
- `base.capability_scan.run@1`
- `base.capability_repair_prompt.generate@1`
- `base.capability_proposal.submit@1`
- `base.capability_review.decide@1`
- `base.capability_waiver.grant/revoke@1`
- `base.capability_release_gate.evaluate@1`

新增契约必须进入 Catalog、Provider、Gateway closed schema、Service handler 和前后端测试；权限矩阵默认只读，写权限不自动扩大。

## Backend design

- `contracts.py`：声明新增 READ capability、严格输入/输出字段和上限。
- `provider.py`：注册 handler，并把模型投影为稳定的闭合 JSON；禁止把内部 store、异常堆栈或凭据返回给 UI。
- `service.py`：
  - proposal search 从持久 workflow port 读取；没有持久端时返回 `governance_dependency_unavailable`，不返回伪造空列表。
  - health summary 从同一 snapshot/finding 查询计算，并保留证据 GID。
  - audit search 使用 bounded audit port；只输出白名单字段。
  - release gate 从服务端证据装载器读取固定输入，忽略调用方自带的通过状态、Finding、审批和哈希。
- `store.py`：仅补充治理快照/提案/审计所需的查询适配，沿用已有 OceanBase 兼容写法和显式列限定。
- `bootstrap.py`：test-governance profile 注入可用的 workflow/audit/release evidence adapters；缺失时服务仍可启动，但相关页面显示依赖不可用。

## Frontend design

- `governance_api.js`：为六个页面提供独立加载函数；统一 unwrap Gateway response、超时、重试和 stale-data 处理。
- `governance_model.js`：扩展页面状态、筛选状态、健康状态和 release/audit DTO；保留权限矩阵。
- `governance_controller.js`：每个 section 有独立 render/load；支持骨架、空态、错误态、上次成功数据和应用内对话框。
- `governance.css/index.html`：补充卡片、表格、抽屉、筛选条和错误提示样式；保持现有深色视觉，不使用白底灰字。

## Failure and security rules

- `403` 显示权限不足；`governance_dependency_unavailable` 显示依赖不可用；业务 Finding 只能由后端返回 `blocked/attention`。
- stale data 必须带上次成功时间和来源，不能显示为最新结果。
- 任何旧请求完成后，如果 request generation 已变化，禁止覆盖新结果。
- 管理写操作在 UI 和 Gateway 双重校验，重复点击只产生一次幂等请求。

## Acceptance

- 前端治理测试覆盖六个页面的加载、筛选、错误保留、权限矩阵、重复点击和原生弹窗禁用。
- 后端测试覆盖新增契约 closed schema、Provider 投影、Service 依赖不可用、health 计算、audit 脱敏和 release fail-closed。
- `npm test`、`npm run build:web`、治理后端定向 pytest、`python -m pytest -q` 和 `check_frontend_deployment.py` 通过。
- 浏览器中管理员和普通成员分别验证：清单、Finding、健康、变更、发布、审计；普通成员看不到管理动作。
