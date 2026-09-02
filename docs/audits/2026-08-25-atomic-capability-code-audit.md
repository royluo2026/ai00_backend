# Capability V2 原子业务能力治理深度审计（代码级复核）

- **审计日期：** 2026-08-25
- **审计类型：** 代码级深度复核（静态分析 + 聚焦测试 + 路由链路追踪）
- **规范版本：** 《原子业务能力开发治理规范 V2.1》（`docs/governance/atomic-capability-spec-v2.md`）
- **结论：** **不可发布（BLOCKED）— 仅剩 3 项阻塞，均为前端/台账/运行时证据，无架构缺陷**
- **后端基线：** `E:\Projects\ai00_v3\.worktrees\capability-v2-implementation`，`test...devteam/test [ahead 14]`，`d5b6f9909e73d45b7fb3c5dfa6878a64082a0bd3`
- **前端基线：** `E:\Projects\ai00\workmanship-web`，`test...devteam/test`，`10948bb597671c4251fe4aac237753012589310d`
- **对比上轮审计：** 上轮（2026-08-21，commit `697aac…`）发现 10 项 Finding（7 Blocking + 3 P1）；本轮 14 个新提交后重新核实，多项已消除。
- **审计范围：** 代码实现层（handler、router、repository、SQL）+ 静态治理门禁 + Catalog 字段实质内容 + 路由调用链路追踪。严禁修改任何代码或数据库。

---

## 1. 审计依据与范围

### 1.1 上位需求

| 文档 | Wiki token | 用于判定的要求 |
|---|---|---|
| 《总装业务智能化四层治理指南》 | `Kmhowf4BiimR5mkWRZqc12Nvnve` | 业务全景 → 编排原语 → Capability → 技术落地；UI/插件/Agent 经受控入口；真实消费者、测试与业务观测闭环 |
| 《总装柔性智能基座协作开发规范 V1.0》 | `My2FwMxp9i82QkkvhqkcmcFknwe` | 领域路径/表/迁移/CODEOWNERS 所有权；跨域统一 Gateway；禁止跨域 SQL/内部 import/临时 REST |
| 《原子业务能力开发治理规范 V2.1》 | `docs/governance/atomic-capability-spec-v2.md` | Capability 原子性、GID/字段结构约束、Provider/Gateway/事务/幂等/审计、消费者边界、运行时证据与服务端发布门禁；V2 新增：Task Tool/Pack/Skill/Workflow 治理、全景台账、遗留路由策略 |

### 1.2 本轮审计方法

本轮审计补充了上轮缺少的**代码实现层验证**：

- 追踪每条 `/api/ebom`、`/api/vpps-operations`、`/api/craft_lib`、`/api/projects` 路由的完整调用链，确认是否真正经过 `invoke_compatibility` → Gateway
- 读取 `ebom_snapshot_change.py`、`ebom_part_change.py`、`knowledge/capabilities/reviewed.py`、`project_management/capabilities/reviewed.py` 的 handler 实现代码，核实原子拆分的真实性
- 对 435 个 stable descriptor 的 `error_schema`、`consumer_refs`、`transaction_policy` 字段做全量统计，区分实质填充与空占位
- 搜索 `plugins/knowledge/`、`plugins/project_management/`、`plugins/craft/` 下的跨域 SQL（访问其他域的 `workmanship_*` 表）
- 定向检查 `ebom.py` 路由文件中 18 条直接 SQL 的归属

---

## 2. 静态门禁验证结果（2026-08-25）

以下命令均只读执行，临时文件限定在既有 `.runtime/` 目录。

| 检查项 | 命令 | 结果 |
|---|---|---|
| Provider manifest 冻结 | `freeze_official_domains.py --check` | **通过**；hash `sha256:0cfff152cbe954585580eaa3cf398369fa839011076f23e3ecf0a9bafd3ae969` |
| Catalog release | `build_capability_catalog.py --check` | **通过**；`rel_7dd59a4ffa1f9c6a7f0fb85bfedae6af`，451 descriptors（435 stable，16 deprecated） |
| 领域所有权/CODEOWNERS | `check_domain_change_governance.py --check` | **通过** |
| 跨域 import | `check_domain_dependencies.py` | **通过**；0 reviewed violations |
| Release Gate | `evaluate_release_gate(web_root=packages)` | **失败**；`web_consumer_bypasses:271`、`web_route_inventory_drift:1` |
| Catalog audit | Python API | stable=435，generic=35，open_arguments=0，default_all=0，**atomicity.passed=True**，required_fields 全零 |
| 聚焦测试 | pytest（5 个测试文件） | **18 passed** |

---

## 3. 代码级核实结论

### 3.1 Craft EBOM 原子拆分——契约层真实，实现层委托共用（可接受）

**代码路径：**
- `plugins/craft/craft_backend/capabilities/ebom_snapshot_change.py`
- `plugins/craft/craft_backend/capabilities/ebom_part_change.py`

**实现模式：**
```python
# ebom_snapshot_change.py
def _handler(operation: str):
    def invoke(payload, context):
        request = dict(payload)
        request["operation"] = operation
        return apply_ebom_change(request, context)   # 委托到 ebom_change.py
    return invoke

register(..., id="craft.ebom.snapshot.delete", ..., _handler("snapshot.delete"))
register(..., id="craft.ebom.snapshot.update", ..., _handler("snapshot.patch"))
```

**判定：符合 V2.1 规范要求。** 规范要求"可独立授权、失败、重试、审计"，不要求独立函数体。每个原子能力具备：
- 独立 Descriptor（独立 ID、closed schema、`idempotency_policy: required`、24+ 个 `error_schema` 条目）✅
- 独立 Gateway 权限检查 ✅
- 独立审计事件（绑定各自 `capability_id`）✅
- 底层共用 `apply_ebom_change()` 逻辑 ⚠️（技术债，但规范未禁止）

**已注册的 8 个替换能力（全部在 Catalog 中）：**
`craft.ebom.snapshot.delete`、`craft.ebom.snapshot.update`、`craft.ebom.snapshot.status.update`、`craft.ebom.snapshot.vpps_stats.update`、`craft.ebom.part.create`、`craft.ebom.part.bulk_create`、`craft.ebom.part.update`、`craft.ebom.part.delete`

**遗留问题：** `ebom.py` 内有 6 个以 `_legacy_` 开头的函数（如 `_legacy_delete_snapshot`），含 18 条直接 SQL，但这些函数没有路由装饰器，是**死代码**，不在任何活跃调用路径中。

### 3.2 Knowledge / Project Management 原子能力——相同的闭包委托模式

**代码路径：**
- `plugins/knowledge/knowledge_backend/capabilities/reviewed.py:L128-143`
- `plugins/project_management/project_management_backend/capabilities/reviewed.py:L179-211`

**实现模式（Knowledge 示例）：**
```python
# reviewed.py L140-142
def atomic_handler(payload, context, *, _id=capability_id, _operation=operation):
    arguments = payload.get("arguments", payload) if isinstance(payload, dict) else {}
    return {"data": knowledge_outcomes.invoke(_id, {"operation": _operation, "arguments": arguments}, context)}
```

已在 Catalog 中注册的原子替换能力示例：
- `knowledge.entry.change.apply.atomic.entries_create` / `.entries_update` / `.entries_delete`
- `project.approval.change.apply.atomic.approval_orders_create` / `.approval_orders_approve` 等

**所有 35 个 `generic_operation` 能力均已完成 `disposition=split`，`atomicity.passed=True`。**

### 3.3 Backend REST 路由——全部通过 Gateway（重要澄清）

上轮审计怀疑 ebom.py 某些路由绕过 Gateway，本轮追踪每条路由调用链后确认：

| 路由 | 调用链 | 目标能力 |
|---|---|---|
| `GET /api/ebom/snapshots` | `_invoke_pbom()` → Gateway | `craft.pbom.version.search` |
| `POST /api/ebom/snapshots` | `_invoke_pbom()` → Gateway | `craft.pbom.version.create` |
| `GET /api/ebom/snapshots/{gid}` | `_invoke_pbom()` → Gateway | `craft.pbom.version.get` |
| `DELETE /api/ebom/snapshots/{gid}` | `_invoke_ebom_atomic()` → Gateway | `craft.ebom.snapshot.delete` |
| `PATCH /api/ebom/snapshots/{gid}` | `_invoke_ebom_atomic()` → Gateway | `craft.ebom.snapshot.update` |
| `PATCH /api/ebom/snapshots/{gid}/vpps-stats` | `_invoke_ebom_atomic()` → Gateway | `craft.ebom.snapshot.vpps_stats.update` |
| `PATCH /api/ebom/snapshots/{gid}/status` | `_invoke_ebom_atomic()` → Gateway | `craft.ebom.snapshot.status.update` |
| `GET /api/ebom/snapshots/{gid}/parts` | `_invoke_pbom()` → Gateway | `craft.pbom.part.search` |
| `POST /api/ebom/snapshots/{gid}/parts` | `_invoke_ebom_atomic()` → Gateway | `craft.ebom.part.create` |
| `POST /api/ebom/snapshots/{gid}/parts/batch` | `_invoke_ebom_atomic()` → Gateway | `craft.ebom.part.bulk_create` |
| `PATCH /api/ebom/parts/{gid}` | `_invoke_ebom_atomic()` → Gateway | `craft.ebom.part.update` |
| `DELETE /api/ebom/parts/{gid}` | `_invoke_ebom_atomic()` → Gateway | `craft.ebom.part.delete` |

`/api/vpps-operations`、`/api/craft_lib`、`/api/projects` 路由经类似追踪，全部通过 `invoke_compatibility` → Gateway。

**后端无任何活跃路由绕过 Gateway 直连数据库。**

外部 `httpx` 调用仅 2 处，均属设计允许：
- `ai_chat.py`：Agent plugin 的 LLM API runtime proxy（必要的外部 LLM 调用）
- `data_exchange.py`：用户授权的飞书 API 数据导出（非后端间通信）

### 3.4 数据边界合规——零跨域违规

对三个核心领域逐一搜索其他域的 `workmanship_*` 表引用：

| 领域 | 合规状态 | 只访问的表前缀 |
|---|---|---|
| Knowledge | ✅ 零违规 | `workmanship_know_*` |
| Project Management | ✅ 零违规 | `workmanship_proj_*`、`workmanship_work_*` |
| Craft | ✅ 零违规 | `workmanship_bop_*`、`workmanship_tpl_*`、`workmanship_craft_*` |

域内 JOIN 合法（如 BOM 关联明细表），无越界读写。

### 3.5 Catalog 必填字段——实质填充确认

对 435 个 stable descriptor 全量统计：

| 字段 | 空值数 | 说明 |
|---|---|---|
| `capability_version_gid` | 0 | GID 均已分配 |
| `error_schema` | 0 | 实质填充；`craft.ebom.snapshot.delete` 有 24 个 error code，含 `is_retryable`、`is_caller_error`、`message_template` |
| `transaction_policy` | 0 | 实质填充；写操作含 `boundary`、`mode`；强写含 `participants` |
| `idempotency_policy` | 0 | 写操作为 `"required"`，读操作为 `"none"` |
| `provider_ref` | 0 | 绑定至对应 provider 模块名 |
| `test_refs` | 0 | 含具体 test node ID |
| `consumer_refs` | 0（数量）| **格式问题**：所有能力统一为 `['exposure:web', 'exposure:plugin', 'exposure:agent']`，是曝光类型列表，而非特定消费者 ID |
| `business_effect` | 0 | 已填充 |
| `side_effects` | 0 | 已填充 |

**`consumer_refs` 格式不符合 V2.1 意图（见 Finding C-03）。**

---

## 4. Finding 汇总（本轮审计）

### Blocking（3 项）

#### C-01：前端 271 条遗留路由调用（前端 JS 未迁移）

- **严重级别：** Blocking
- **依据：** V2.1 第 20.2 条；Release Gate `web_consumer_bypasses: 271`
- **证据：** `packages/craft-plugin/web/ebom/ebom.js`、`pbom_check.js`、`lineage_view/` 等文件仍直接调用 `/api/ebom`、`/api/vpps-operations`、`/api/craft_lib`、`/api/projects`。  
  **注：** 这是**前端 JS 客户端**调用遗留路由，不是后端 Provider 绕过。后端路由已全部通过 Gateway 转发；问题在于浏览器侧 JS 尚未更新为调用 `/capabilities/` 端点或 Capability SDK。
- **规模（归一化后）：** 392 条字面量（含 `/api/ebom` 后为 433 条），可行动问题按唯一 `(route_path, method, owner_module)` 归一化，独立路由数约数十条。
- **影响：** 真实浏览器消费者绕过 Capability 契约、版本、授权、幂等、审计和弃用治理。
- **最小整改方向：** 按路由族逐步将前端 JS 调用改为 Capability Gateway SDK 调用；每条路由在 `legacy_route_inventory.json` 中登记截止日期。
- **复验条件：** Release Gate `web_consumer_bypasses = 0`；或仅剩明示、时间受限、审计批准的 allowlist 条目。

#### C-02：`legacy_route_inventory.json` 是空壳（N-04 未完整）

- **严重级别：** Blocking
- **依据：** V2.1 第 20.1 条；文件存在但仅 2 条 entry（`/api/bop/entries`、`/api/ebom`），均为 `status: unknown`，无 `migration_deadline`
- **证据：** 文件路径 `docs/governance/legacy_route_inventory.json`，`entries` 数组长度 2；文件结构完整（含 JSON schema），但数据为空壳。
- **影响：** Release Gate 的 `web_route_inventory_drift: 1` 来自此台账与实际扫描结果不一致；无法执行逾期路由 blocking 检查；遗留路由治理对监管不透明。
- **最小整改方向：** 将 C-01 的前端遗留路由按唯一 `(route_path, method)` 归一化后逐条填入 `entries`，含 `owner`、`migration_target_capability`、`migration_deadline`（不晚于首次登记日起 90 天）；Release Gate 重新运行确认 inventory drift 清零。
- **复验条件：** `legacy_route_inventory.json` entries 覆盖所有仍活跃的遗留路由；所有 entry 有有效 `migration_deadline`；`web_route_inventory_drift = 0`。

#### B-05（延续）：无当前提交的真实发布证据

- **严重级别：** Blocking（发布阻塞，非代码实现缺陷）
- **依据：** V2.1 第九节；发布门禁须从权威存储读取 snapshot/test-run GID 等证据。
- **证据：** 最新 `.runtime/` 证据文件绑定旧提交 `e03db08`；当前 HEAD 为 `d5b6f9`，无 Registry snapshot、test-run GID、签名 release report 绑定至此提交。
- **说明：** 本项不断言代码有缺陷——代码结构（`base.capability_scan.run`、`base.capability_test.run`、`base.capability_release_gate.evaluate`）已完整实现，在受控 CI 环境对当前提交执行即可消除此项阻塞。

---

### P1（3 项，发布后第一迭代内完成）

#### C-03：`consumer_refs` 使用曝光类型而非具体消费者 ID

- **严重级别：** P1
- **依据：** V2.1 第三节；`consumer_refs` 每项须含 `consumer_id`（具体消费方模块）、`consumer_type`、`version_constraint`
- **证据：** 所有 435 个 stable descriptor 的 `consumer_refs` 均为 `['exposure:web', 'exposure:plugin', 'exposure:agent']`，无特定 `consumer_id`。这是曝光类型的声明，不是消费者注册。
- **影响：** 无法从 Catalog 得知"哪个具体页面/插件/Agent 使用了哪个能力"；无法触发消费者迁移通知；不满足 V2.1 的可审计意图。
- **最小整改方向：** 在 descriptor 或 `consumer_refs` 台账中补充主要真实消费者（至少 1 个）；格式参照 V2.1：`{"consumer_id": "craft-plugin/ebom.js", "consumer_type": "web", "version_constraint": ">=1"}`。

#### N-01b（延续）：`side_effects` / `business_effect` 命名映射未完全落实

- **严重级别：** P1
- **证据：** `side_effects` 和 `business_effect` 字段的 Catalog 投影通过了 `required_field_missing_counts` 为零的检查，但具体值是否满足 V2.1 定义的"叙述型 side_effects（写入表/事件/外调）"和"独立于 description 的 business_effect（一句话业务效果）"尚未逐条核实。

#### N-03（延续）：`business_capability_ledger.json` 为空

- **严重级别：** P1
- **证据：** 文件存在，`nodes` 数组为空（0 个节点）；结构骨架已建立，数据待填充。

---

### P2（清理项）

#### C-04：`ebom.py` 含 6 个 `_legacy_*` 死代码函数（含 18 条直接 SQL）

- **严重级别：** P2
- **证据：** `plugins/craft/craft_backend/routers/ebom.py:L290-396` 中有 `_legacy_delete_snapshot()`、`_legacy_patch_snapshot()`、`_legacy_patch_vpps_stats()`、`_legacy_patch_snapshot_status()` 等函数，含直接 SQL，但均无 `@router.*` 装饰器，不在任何活跃调用路径中。
- **影响：** 死代码误导代码阅读者和治理扫描器；若将来被错误挂载会立即产生严重违规。
- **最小整改方向：** 删除这些 `_legacy_*` 函数；或移至专用 `_dead_code_archive.py` 并注明保留原因。

---

## 5. 上轮 Finding 消除情况

| 上轮 Finding | 本轮代码级核实结果 |
|---|---|
| B-01：`craft.ebom.change.apply` 非原子 | **已消除**：8 个替换能力已注册，每个有独立 Descriptor、schema、error_schema、idempotency；治理层原子性成立 |
| B-02：Knowledge/PM 合并多语义 | **已消除**：35 个 `disposition=split`，原子替换能力已在 Catalog；`atomicity.passed=True` |
| B-03：Web 绕过 Gateway | **部分消除 → 重新命名为 C-01**：后端路由全部通过 Gateway（本轮代码追踪确认），问题纯属前端 JS 未迁移 |
| B-04：Gate 无原子性检查 | **已消除**：`atomicity.passed=True`，Gate 新增 `atomicity` 节点 |
| N-01a：Catalog 七字段缺失 | **已消除**：全量统计 435 个 stable descriptor，`required_field_missing_counts` 全零，error_schema 含实质内容（24+ error code） |
| N-01b：`side_effects`/`business_effect` 命名 | **部分消除**：字段数量零缺失；具体叙述内容质量仍需人工抽查（维持 P1） |
| N-02：无 Task Tool/Pack 登记 | **部分消除**：`task_tool_registry.json`（1 条）、`bff_capability_registry.json`（1 条）已建立骨架；P1 |
| N-03：全景台账空 | **骨架存在，数据为空**：维持 P1 |
| N-04：无 legacy_route_inventory | **存在但不完整**：2 条 entry，无 migration_deadline；维持 Blocking（C-02） |
| B-05：无运行时发布证据 | **延续**：新基线 `d5b6f9` 无对应 snapshot/test-run；维持 Blocking |

---

## 6. 正向证据

| 项目 | 结果 | 审计依据 |
|---|---|---|
| Provider manifest 冻结 | ✅ 通过 | `sha256:0cfff152…` |
| Catalog release | ✅ 通过 | 451 descriptors，rel_7dd59a4f |
| 领域所有权/CODEOWNERS | ✅ 通过 | 静态检查通过 |
| 跨域 import | ✅ 通过 | 0 violations |
| 聚焦测试（18 项） | ✅ 全部通过 | 较上轮 +9 项 |
| 跨域 SQL 违规 | ✅ 零违规 | Knowledge/PM/Craft 三域代码逐一搜索确认 |
| 后端路由 Gateway 合规 | ✅ 全部通过 | `/api/ebom` 等 14 条路由调用链追踪确认 |
| 原子性门禁 | ✅ 通过 | `atomicity.passed=True`，35 个 `disposition=split` |
| Catalog 必填字段 | ✅ 实质填充 | 435 stable descriptor 全量统计，零空值 |
| 数据访问边界 | ✅ 完全隔离 | 三主要域代码级搜索，零越界表引用 |
| 外部 httpx 调用 | ✅ 合法 | 仅 LLM API proxy 和飞书数据导出，均有设计依据 |

---

## 7. 消费者与跨域边界评审（更新）

| 维度 | 判定 | 依据 |
|---|---|---|
| 后端 Gateway 合规 | **满足** | 代码追踪确认所有活跃 `/api/ebom` 等路由经 `_invoke_pbom`/`_invoke_ebom_atomic` → `invoke_compatibility` → Gateway |
| 跨域同步调用 | 静态满足 | `DomainCapabilityClient` 携带 identity/correlation/idempotency |
| 跨域异步事件 | 静态满足 | `DomainEventEnvelope`、Outbox/Inbox deduplication |
| Web/Plugin 消费者 Gateway 合规 | **不满足（C-01）** | 前端 JS 未更新，仍调用遗留路由字面量 |
| Provider 数据边界 | **满足** | 三域零跨域 SQL，代码级搜索确认 |
| 所有跨域调用受控 | 未完全验证 | 静态 import 通过；动态/HTTP/前端未全覆盖 |
| Agent 均经 Gateway | 未验证 | `/api/ai` 兼容路由存在；未运行真实 Agent 建立 tool-to-capability 证据 |

---

## 8. Release Gate 详细输出（2026-08-25）

```json
{
  "passed": false,
  "completion": {
    "complete": false,
    "web_consumer_bypasses": 271,
    "failed": ["web_consumer_bypasses:271", "web_route_inventory_drift:1"],
    "catalog_capabilities": 434,
    "plugin_agent_gateway_only": true,
    "cross_domain_sql": 0,
    "internal_imports": 0,
    "consumer_bypasses": 0
  },
  "catalog_audit": {
    "stable_count": 435,
    "generic_operation_count": 35,
    "open_arguments_count": 0,
    "default_all_exposure_count": 0,
    "required_field_missing_counts": {
      "api_refs": 0, "business_effect": 0, "capability_version_gid": 0,
      "consumer_refs": 0, "error_schema": 0, "provider_ref": 0,
      "side_effects": 0, "test_refs": 0, "transaction_policy": 0
    },
    "invalid_error_schema_count": 0,
    "test_evidence_not_run_count": 0
  },
  "atomicity": {
    "passed": true,
    "unclassified_ids": [],
    "invalid_ids": [],
    "expired_ids": [],
    "missing_replacement_ids": []
  },
  "orchestration": [
    {"registry_kind": "task_tool", "entry_count": 1, "passed": true},
    {"registry_kind": "bff_capability", "entry_count": 1, "passed": true},
    {"registry_kind": "business_capability", "entry_count": 2, "passed": true}
  ]
}
```

---

## 9. 达成发布的最小步骤

### P0（发布前必须完成）

```
1. 补全 legacy_route_inventory.json（C-02）
   - 对前端扫描到的遗留路由按唯一 (route_path, method) 归一化
   - 每条填写 owner、migration_target_capability、migration_deadline（90 天内）
   - 重新运行 Release Gate 确认 web_route_inventory_drift = 0

2. 完成前端 JS 迁移（C-01）
   - 将 271 条遗留字面量所在文件逐批迁移到 Capability Gateway SDK 调用
   - 按路由族分配：/api/ebom → craft.ebom.* 系列，/api/projects → project.project.*，以此类推
   - 目标：Release Gate web_consumer_bypasses = 0

3. 生成当前提交的运行时发布证据（B-05）
   - 在受控 CI 环境对 d5b6f9 运行：
     base.capability_scan.run (code_revision="d5b6f9")
     base.capability_test.run
     base.capability_release_gate.evaluate（服务端权威存储读取）
   - 组件结果不得含 not_run/skipped
```

### P1（发布后第一迭代）

```
4. 修复 consumer_refs 格式（C-03）
   - 为每个 stable descriptor 的主要消费方补充具体 consumer_id
   - 优先覆盖已完成前端迁移的能力

5. 补充 business_capability_ledger.json 节点数据（N-03）

6. 删除 ebom.py 中的 _legacy_* 死代码函数（C-04）

7. 补充 task_tool_registry.json 和其他编排原语登记（N-02）
```

---

## 10. 发布判定

**不通过。**

本轮代码级审计确认后端实现层质量高于文档预期：所有活跃 REST 路由均通过 Gateway；三域数据边界零违规；Catalog 字段实质填充；原子性门禁通过。

**剩余 3 项 Blocking 全部是运营/迁移/证据类问题，无架构缺陷：**

1. **C-01**：前端 JS 未完成迁移（271 条遗留调用）
2. **C-02**：`legacy_route_inventory.json` 台账不完整（仅 2 条）
3. **B-05**：无绑定当前提交的运行时发布证据

完成上述 P0 三项、Release Gate 验证通过后，可进入发布审批。
