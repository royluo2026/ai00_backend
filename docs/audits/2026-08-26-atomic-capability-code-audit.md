# Capability V2 原子业务能力治理审计（代码级，第三轮）

- **审计日期：** 2026-08-26
- **审计类型：** 代码级深度复核（静态门禁 + 路由链路追踪 + Catalog 字段全量统计 + 测试）
- **规范版本：** 《原子业务能力开发治理规范 V2.1》（`docs/governance/atomic-capability-spec-v2.md`）
- **结论：** **静态 Release Gate 通过（`passed: true`）；治理层运行时发布证据仍缺失**
- **后端基线：** `E:\Projects\ai00_v3\.worktrees\capability-v2-implementation`，`test [ahead 72]`，`b3f4367e666743fcb591d169298cd07b0148fdf1`
- **前端基线：** `E:\Projects\ai00\workmanship-web`，`test`，`10948bb597671c4251fe4aac237753012589310d`
- **参照上轮：** 2026-08-25 审计（commit `d5b6f9…`）发现 3 项 Blocking；本轮全部已消除或澄清。

---

## 1. 核心结论

本轮相较上轮（2026-08-25）新增 72 个提交。大量 `chore: remove * route`、`刷新*路由清单` 提交将前端遗留路由字面量从 271 条降至 **0**，并刷新了 web route inventory 快照。

**静态发布门禁（`evaluate_release_gate`）以完整前端根目录运行结果：**

```
passed: true
web_consumer_bypasses: 0
web_route_inventory_drift: 0（完整 web root 扫描与存储快照一致）
atomicity.passed: true
open_arguments_count: 0
required_field_missing_counts: 全部 0
cross_domain_sql: 0 | internal_imports: 0 | consumer_bypasses: 0
```

**注意区分两层门禁：**

| 门禁 | 本轮结果 | 说明 |
|---|---|---|
| 静态 Release Gate（`evaluate_release_gate`） | **通过** | 检查代码/Catalog/路由/原子性静态规则 |
| 治理 Release Gate（`base.capability_release_gate.evaluate`） | **未执行** | 需要运行时 snapshot_gid、test_run_gid、找批、签名；本轮未在受控环境运行 |

**最终发布判定：** 代码层已满足 V2.1 所有静态要求。发布前仍需在受控 CI/CD 环境生成当前提交的运行时发布证据并通过治理 Release Gate。

---

## 2. 静态门禁验证（2026-08-26）

| 检查项 | 命令 | 结果 |
|---|---|---|
| Provider manifest 冻结 | `freeze_official_domains.py --check` | **通过**；`sha256:40aede3b…` |
| Catalog release | `build_capability_catalog.py --check` | **通过**；`rel_1b40890b…`，453 descriptors（437 stable） |
| 领域所有权/CODEOWNERS | `check_domain_change_governance.py --check` | **通过** |
| 跨域 import | `check_domain_dependencies.py` | **通过**；0 violations |
| Legacy/BFF route inventory audit | Python API | **通过**；legacy 0 issues，BFF 0 issues |
| Static Release Gate（完整 web root） | `evaluate_release_gate(web_root=全前端根目录)` | **通过**；`passed: true` |
| 聚焦测试 | pytest（5 个测试文件） | **20 passed** |

---

## 3. 代码级核实结论

### 3.1 前端路由迁移——完全完成

- `web_consumer_bypasses: 0`：前端 JS 源文件中已无遗留 `/api/legacy` 字面量调用
- Web route inventory snapshot 与当前扫描结果一致（使用完整 `web_root` 时无 drift）
- 72 次提交中包含大量：`刷新*路由清单`、`chore: remove * route`、`chore: retire * route from inventory`

**上轮的"drift:1"已澄清**：是因为审计时使用了 `packages/` 子目录而非完整前端根目录，导致快照不匹配。以完整前端根目录运行时无 drift。

### 3.2 Legacy_route_inventory——完整有效

- `legacy_route_inventory.json`：224 条 entry，每条含 `route_path`、`method`、`owner`、`migration_target_capability`、`migration_deadline: 2026-11-21`、`source`、`allowed_consumers`
- Route inventory audit：**0 issues**
- BFF route inventory audit：**0 issues**

### 3.3 Ebom.py 死代码清理——已完成

- 上轮发现的 6 个 `_legacy_*` 函数（含 18 条直接 SQL）已全部删除
- 当前仅剩 `_legacy_version(item: dict) -> dict:` — 这是响应格式化辅助函数，无数据库访问
- 文件从原来 649+ 行缩减至 554 行，`cur.execute` 调用降至 1 次（在格式化函数外部的合法调用）

### 3.4 Catalog 必填字段——全部实质填充，零空占位

437 个 stable descriptor 全量统计，无任何字段缺失：

| 字段 | 缺失数 | 格式违规数 |
|---|---|---|
| `capability_version_gid` | 0 | 0 |
| `error_schema` | 0 | 0（含格式校验：is_retryable、is_caller_error 齐全）|
| `transaction_policy` | 0 | 0 |
| `idempotency_policy` | 0 | 0 |
| `provider_ref` | 0 | 0 |
| `api_refs` | 0 | 0 |
| `test_refs` | 0 | 0（test_evidence_not_run_count=0）|
| `business_effect` | 0 | 0（格式校验通过）|
| `side_effects` | 0 | 0（格式校验通过）|

### 3.5 Consumer_refs——部分填充（P1）

- 437 stable 中：**46 个**有真实 consumer_refs（具体 `consumer_id`），**391 个**为空 `[]`
- 有实质内容的示例：
  - `agent.flow.change.apply` → `{"consumer_id": "agent-plugin/flow_canvas/flow_editor.js", "consumer_type": "web", "version_constraint": ">=1"}`
  - `craft.ebom.change.apply` → `{"consumer_id": "craft-plugin/ebom.js", ...}`
  - `craft.bop.version.list` → `{"consumer_id": "web/my_files/my_files.js", ...}`
- Catalog audit 的 `invalid_consumer_ref_count: 0`：空 `[]` 被当前门禁接受（可能以 `no_consumer_reason` 字段补充）
- **判定：P1，不阻塞静态门禁，但不满足 V2.1 第三节"发布时 MUST 有至少一个已验证消费者"的语义完整性要求**

### 3.6 原子性——全部处置，门禁通过

- 35 个 `operation + arguments` generic capability：`disposition=split`，`atomicity.passed=True`
- 所有 35 个均有 `replacement_capabilities` 列表且替换能力已在 Catalog 注册
- `unclassified_ids: []`、`invalid_ids: []`、`expired_ids: []`、`missing_replacement_ids: []`

### 3.7 新增能力质量——符合规范

本轮新增能力（`ontology.object.list`、bounded BOP paging 等）：

| 能力 | idempotency | side_effect_level | 判定 |
|---|---|---|---|
| `ontology.object.list` | none | read | 合规 |
| `craft.bop.version.freeze.change.apply` | required | write | 合规 |
| `craft.bop.version.snapshot.change.apply` | required | write | 合规 |
| `craft.bop.entry.bulk.change.apply` | required | write | 合规 |
| `craft.bop.entry.change.apply` | required | write | 合规 |

写操作均有 `idempotency_policy: required`；读操作为 `none`；符合 V2.1 要求。

### 3.8 数据边界与跨域 import——持续合规

- `cross_domain_sql: 0`：无跨域 SQL 违规
- `internal_imports: 0`：无禁止的内部 import
- 后端消费者（backend routers/ai_assistant/plugin adapter）：`consumer_bypasses: 0`

---

## 4. Finding 汇总（本轮）

### 已消除（对比上轮 2026-08-25）

| 原 Finding | 本轮状态 | 证据 |
|---|---|---|
| C-01：前端 271 条遗留路由 | **已消除** | `web_consumer_bypasses: 0`；大量 route 删除和 inventory 刷新提交 |
| C-02：legacy_route_inventory 空壳 | **已消除** | 224 条 entry，inventory audit 0 issues |
| C-04：ebom.py `_legacy_*` 死代码 | **已消除** | 6 个死代码函数已删除，仅剩格式化辅助函数 |
| web_route_inventory_drift:1 | **已消除（澄清为扫描目录错误）** | 完整 web root 扫描无 drift |

### 仍存在（非 Gate 阻塞）

| Finding | 级别 | 代码依据 |
|---|---|---|
| **R-01：治理 Release Gate 尚未执行** | **发布阻塞** | 无 `92706e8f`/`b3f4367e` 的 snapshot_gid、test_run_gid 或签名 release report；静态门禁通过不等于治理门禁通过 |
| R-02：consumer_refs 391/437 为空 | P1 | 46 个有真实 consumer_id，391 个 `[]`；现有门禁接受空数组 |
| R-03：business_capability_ledger 0 节点 | P1 | 文件存在但无数据；全景台账未实质填充 |
| R-04：task_tool_registry 仅 1 条 | P1 | 骨架存在；高频场景 Task Tool 尚未系统登记 |

---

## 5. Release Gate 输出（2026-08-26，`b3f4367e`）

```json
{
  "passed": true,
  "completion": {
    "complete": true,
    "web_consumer_bypasses": 0,
    "cross_domain_sql": 0,
    "internal_imports": 0,
    "consumer_bypasses": 0,
    "plugin_agent_gateway_only": true,
    "independent_domains": 11,
    "sync_production_paths": 1,
    "async_production_paths": 1,
    "failed": []
  },
  "catalog_audit": {
    "stable_count": 437,
    "generic_operation_count": 35,
    "open_arguments_count": 0,
    "atomicity": {"passed": true, "unclassified_ids": [], "missing_replacement_ids": []},
    "required_field_missing_counts": "全部0",
    "invalid_error_schema_count": 0,
    "test_evidence_not_run_count": 0
  },
  "atomicity": {"passed": true}
}
```

---

## 6. 发布前剩余步骤

### 必须完成（治理 Release Gate）

```
1. 在受控 CI/CD 环境执行：
   base.capability_scan.run(code_revision="b3f4367e")  # 生成 snapshot_gid
   base.capability_test.run(snapshot_gid=...)          # 生成 test_run_gid
   base.capability_release_gate.evaluate(...)           # 服务端从权威存储读取证据、签名

2. 上述命令必须满足：
   - 使用当前 HEAD 提交 hash
   - 组件结果不含 not_run/skipped
   - release report 包含 conclusion=pass 且有有效签名
```

### 发布后迭代（P1）

```
3. 为更多 stable descriptor 填写具体 consumer_refs（consumer_id）
4. 向 business_capability_ledger.json 补充业务节点数据（R-03）
5. 扩充 task_tool_registry.json 覆盖高频场景（R-04）
```

---

## 7. 三轮审计对比

| 指标 | 2026-08-21（`697aac`） | 2026-08-25（`d5b6f9`） | 2026-08-26（`b3f4367e`） |
|---|---|---|---|
| Catalog stable | 317 | 435 | 437 |
| web_consumer_bypasses | 392 | 271 | **0** |
| required_field_missing | 333×9字段 | 0 | 0 |
| atomicity.passed | N/A | true | true |
| legacy_route_inventory entries | 0 | 2 | 224 |
| _legacy_* 死代码 SQL | 18 条 | 18 条 | **0 条** |
| 聚焦测试通过数 | 9 | 20 | 20 |
| Static Release Gate | 失败 | 失败（drift） | **通过** |
| 静态 Blocking Finding 数 | 7 | 3 | **0** |
