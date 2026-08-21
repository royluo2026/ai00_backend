# Capability V2 治理审计整体整改设计

**日期：** 2026-08-21  
**目标分支：** 后端 `test`（`697aac18`）、前端 `test`（`10948bb`）  
**依据：** `docs/audits/2026-08-21-atomic-capability-test-branch-audit.md`、`docs/governance/atomic-capability-spec-v2.md`

## 1. 目标与范围

本设计一次性处理审计中的 7 个 Blocking 和 3 个 P1 Finding，建立一条可重复运行的治理整改流水线，而不是为每条 Finding 编写一次性补丁。范围包括：

- 后端 Capability V2 契约、Catalog 投影、原子性审计、Release Gate、路由扫描和发布证据；
- 后端 Craft、Knowledge、Project Management 中已确认的合并 Capability；
- 前端 `test` 工作树中的 Web/插件 REST 消费者；
- Task Tool/Pack/Skill/Workflow 登记骨架和业务全景节点台账；
- 不访问生产环境、不修改生产数据库、不改变 `deploy` 分支。

## 2. 设计原则

1. **单一事实源。** Capability descriptor、原子性处置清单、遗留路由台账、BFF 台账和发布证据均生成稳定 JSON，并由 Catalog/Gate 读取，不在多个脚本中复制判断。
2. **批量治理。** 对 34 个 `operation + arguments` descriptor 统一生成处置报告；对路由按唯一 `(route_path, method)` 和路由族迁移，不按静态字面量逐条派工。
3. **Fail closed。** 字段缺失、处置未分类、路由未登记、测试证据 `not_run/skipped`、快照与代码 revision 不一致时，Gate 必须阻断。
4. **兼容迁移。** 旧 REST 只作为有明确 owner、目标 Capability 和截止日期的迁移适配器；新代码不得增加旧入口。
5. **最小权限和原子语义。** 一个 Capability 只承载一个主要业务效果；确需参数化时必须有可审计的 operation 处置证据。

## 3. 目标架构

```text
领域 Provider / 原子 Capability
        │  descriptor + operation_disposition
        ▼
Registry snapshot ──► Catalog projection ──► Catalog audit
        │                                      │
        ├── consumer_refs / api_refs           ├── atomicity gate
        ├── provider_ref / test_refs           ├── field completeness gate
        └── snapshot_gid / code_revision       └── release gate

Web/Plugin source ──► source-only route inventory ──► Gateway/BFF adapter
                                                   └── legacy expiry gate
```

正式发布只接受同一个 `code_revision` 绑定的 Registry snapshot、Catalog release、测试运行、结果 hash 和签名 release report。

## 4. 主要组件和职责

### 4.1 契约与 Catalog 投影

扩展 `backend/capability_v2/contracts.py` 的 `CapabilityDescriptorV2`，正式增加并校验：

- `capability_version_gid`；
- `error_schema`（由 `DomainErrorContract` 映射，明确 `error_code`、`message_template`、`is_retryable`、`is_caller_error`）；
- `transaction_policy`；
- `consumer_refs`、`provider_ref`、`api_refs`、`test_refs`；
- `business_effect`、`side_effects`，并保持 `side_effect_level` 为枚举分类。

`backend/capability_v2/catalog.py`、`descriptor_adapter.py`、Catalog 构建脚本和 `docs/capabilities/catalog.v2.json` 使用同一字段模型。历史 `deprecated/retired` descriptor 保留不可变投影，但不能作为新 release 证据。

### 4.2 原子性处置

新增 `docs/governance/capability-atomicity-dispositions.json` 及 schema。每个使用 `operation + arguments` 的 stable descriptor 必须有：

- `disposition`: `split`、`justified` 或 `retire`；
- `business_effects`、`owner_domain`、`evidence_refs`；
- `replacement_capabilities`（split/retire 时必填）；
- `approval` 和 `expires_at`（justified 时必填）。

`catalog_audit.py` 汇总未处置项和过期例外，`release_gate.py` 将其作为 blocking 条件。

已确认的合并能力按领域批量拆分：

- Craft EBOM/PBOM：快照删除、快照更新、状态更新、VPPS 统计、零件创建/批量创建/更新/删除；
- Knowledge：entry/hub 的 create、update、delete、list、get、history；
- Project Management：审批决定、状态转移、项目/车型、task/dependency、批处理动作。

旧 Capability 仅保留为带到期时间的兼容 Facade；Facade 不得作为新的 stable 原子能力或前端新入口。

### 4.3 Web/Plugin 路由治理

重构 `backend/capability_v2/consumer_routes.py`：

- 只扫描配置的版本控制源目录；
- 按目录模式排除 `dist`、`dist-*`、缓存和生成目录；
- `/api/ebom` 等治理 prefix 进入统一 legacy 规则；
- 输出唯一 `(route_path, method, owner_module, migration_target)` 记录；
- 记录 source file、line、consumer type 和 allowlist reason。

新增：

- `docs/governance/legacy_route_inventory.json`：每条 legacy 路由的 owner、迁移目标、绝对截止日期、允许消费者、状态和证据；
- `docs/governance/bff_route_inventory.json`：正式 BFF 路由、Gateway 绑定、允许的数据聚合范围和测试引用。

前端按路由族迁移到 Gateway/SDK/BFF，不再直接调用领域 REST。迁移完成前的旧路由只能命中台账 allowlist，且不得过期。

### 4.4 Release Gate 和发布证据

`backend/capability_v2/release_gate.py` 统一阻断以下情况：

- completion 未通过或 Web source-only bypass 非零；
- Catalog 必填字段缺失；
- generic operation 未有有效处置；
- 默认全开放 exposure；
- legacy route 未登记或已逾期；
- Task Tool/Pack 消费未绑定 stable Capability；
- release evidence 缺失、`not_run/skipped`、hash/revision/snapshot 不一致。

`backend/capability_governance_test` 的 authority port 继续作为证据唯一读取入口；离线 acceptance 不能替代正式 release evidence。

### 4.5 四层编排与业务全景

新增治理登记：

- `docs/governance/task-tool-registry.json`；
- `docs/governance/capability-pack-registry.json`；
- `docs/governance/skill-registry.json`；
- `docs/governance/workflow-registry.json`；
- `docs/governance/business_panorama_ledger.json`。

首批至少登记 3 个 Task Tool，并为每个登记 `consumed_capabilities`、owner、major version、lifecycle、Gateway/SDK route 和测试引用。全景台账首批覆盖至少 5 个核心业务节点，每个 green 节点必须有 stable Capability 和生产观测指标。

## 5. 实施顺序

1. **契约基础层：** 先扩展模型、JSON schema、Catalog 生成和审计输出，确保后续拆分有承载结构。
2. **治理清单层：** 生成 34 项原子性处置清单和 source-only 路由台账，建立 Gate 的 fail-closed 检查。
3. **领域原子化层：** 按 Craft → Knowledge → Project Management 批量拆分 Provider、兼容 Facade、consumer refs 和测试。
4. **前端入口层：** 在前端 `test` 分支按路由族替换 Gateway/BFF 调用，保留短期 allowlist 并绑定到后端新 Capability。
5. **编排与全景层：** 登记 Task Tool/Pack/Skill/Workflow 和业务节点台账。
6. **证据与发布层：** 绑定当前两个 `test` revision 生成 snapshot、真实测试、签名报告，执行最终 Gate。

每个阶段都必须有独立测试和可审阅的 JSON 产物；任何阶段失败都不进入下一阶段发布。

## 6. 验收标准

- 所有 stable Catalog descriptor 都具备 9 个新增治理字段，且 `error_schema` 与 `DomainErrorContract` 映射一致；
- 34 个 generic operation descriptor 无未处置项，无过期 `justified` 例外；
- Craft/Knowledge/Project Management 已确认的合并 Capability 不再作为新的原子能力暴露；
- source-only Web/Plugin inventory 与 Gate 使用同一数据集，未授权 legacy route 为 0；
- legacy route 和 BFF inventory 完整、无逾期项；
- 至少 3 个 Task Tool、1 个 Capability Pack、1 个 Skill、1 个 Workflow 和至少 5 个业务节点登记有效；
- release evidence 绑定后端 `697aac18` 与前端 `10948bb` 对应构建，组件结果不含 `not_run`/`skipped`；
- `python -m pytest` 治理聚焦集、Catalog audit、consumer route、release gate 和迁移后的领域测试全部通过；
- 最终 Release Gate 输出 `passed: true`，并可从权威存储重读全部输入。

## 7. 非目标

- 不在本设计中修改生产数据库或生产部署；
- 不删除历史 Capability descriptor、历史路由或历史证据；
- 不把所有业务逻辑搬到 Gateway；Gateway 只负责路由、身份、授权、版本、证据和必要的 BFF 投影；
- 不用静态计数直接代表独立修复任务，所有数量以唯一键归一化后为准。
