# Simulation Environment Phase 1 PLMXML Workspace Implementation Plan

> **执行约束：** 本计划由当前任务内的主代理顺序实施。用户明确要求不使用子代理。每个工作包先写失败测试，再做最小实现，再运行有界回归；不得绕过 Capability、Catalog、Provider、权限、审计或证据链。

**目标：** 将“个人仿真环境”落实为 AI00 可持久化、可版本化、可恢复的当前仿真文档；第一阶段通过 PLMXML 文件与 VisMockup 建立稳定闭环，并把 BOP、PLMXML、JT、已有环境版本统一投影为“不可编辑模型文件 + 可编辑备选层次结构”。

**依据规格：** `docs/superpowers/specs/2026-09-11-simulation-environment-phase1-plmxml-workspace-design.md`

**工作树：**

- 后端：`E:/Projects/ai00_v3/.worktrees/orchestration-merge-backend-20260905`
- 前端：`E:/Projects/ai00_v3/.worktrees/orchestration-merge-frontend-20260905`

**实现原则：** 保留现有 environment document、alternate hierarchy、placement、PLMXML codec 和 runtime package 能力；新增能力只覆盖现有合同无法表达的原子业务效果。所有写操作使用 GID、预期行版本、幂等键和事务；所有外部来源必须保留精确版本、内容哈希和来源证据。

---

## 工作包 1：收紧现有环境组合写入边界

**修改文件：**

- `plugins/simulation/tests/test_environment_hierarchy_repository.py`
- `plugins/simulation/simulation_backend/data/workspace_repository.py`
- `plugins/simulation/tests/test_environment_document_capabilities.py`
- `plugins/simulation/simulation_backend/capabilities/environment_documents.py`

**测试先行：**

1. 增加测试：placement 的 `target_node_gid` 和 `parent_placement_gid` 必须同时属于目标 `workspace_gid` 与 `hierarchy_gid`。
2. 增加测试：跨层次节点、已归档层次、已移除节点均返回稳定错误，且事务无部分写入。
3. 增加测试：`model_document` 来源必须由 Owner Capability 返回不可变 Artifact、精确版本和 SHA-256；任一证据缺失时 fail-closed。
4. 增加测试：`craft_resource` 来源必须包含资源 GID、精确版本和内容哈希，不能仅凭前端传入 `source_ref` 落库。

**最小实现：**

1. 将节点归属校验统一为 `workspace_gid + hierarchy_gid + tenant_gid + active` 四条件。
2. 把来源解析移到 capability provider 层；repository 只接收已验证、规范化的 source evidence。
3. 数据库存储 `source_kind`、source GID、source version GID、artifact GID、SHA-256 和稳定 projection identity。
4. 保持现有公开合同兼容；缺少新增证据的旧调用返回稳定错误，不做隐式弱校验。

**验证命令：**

```powershell
pytest -q plugins/simulation/tests/test_environment_hierarchy_repository.py plugins/simulation/tests/test_environment_document_capabilities.py
```

---

## 工作包 2：拆分 PLMXML 检查、恢复和插入原子能力

**新增/修改文件：**

- `plugins/simulation/tests/test_plmxml_environment_capabilities.py`
- `plugins/simulation/tests/test_plmxml_environment_codec.py`
- `plugins/simulation/simulation_backend/capabilities/plmxml_environments.py`
- `plugins/simulation/simulation_backend/domain/plmxml_environment_codec.py`
- `plugins/simulation/simulation_backend/data/workspace_repository.py`
- `plugins/simulation/simulation_backend/capabilities/provider.py`
- 对应 capability descriptor、provider binding、迁移和生成文档

**测试先行：**

1. `simulation.plmxml.environment.inspect@1` 只读取不可变 Artifact，返回文件哈希、模型文档、Occurrence 数量、备选层次、依赖、manifest 匹配和风险，不写数据库。
2. `simulation.environment.restore_from_plmxml@1` 创建新的个人仿真环境，并恢复所有可识别模型、层次、变换和来源证据。
3. `simulation.environment.plmxml.insert@1` 只修改指定草稿，支持：
   - 插入模型及用户勾选的备选层次；
   - 仅插入模型。
4. 不设置用途或未显式提交层次选择时返回 `invalid_input`，不得默认丢弃或默认保留层次。
5. 同一内容重复插入通过 artifact hash、projection identity 和 idempotency key 去重；恢复或插入都不创建“环境套环境”。
6. 兼容能力 `simulation.plmxml.environment.import@1` 保持原语义，不静默改成创建环境。

**最小实现：**

1. 从现有 codec 提取纯函数 `inspect_environment_plmxml`，复用现有解析和依赖图校验。
2. 恢复时创建 workspace 草稿，再在同一事务内写入模型文档、层次和 placement；任一失败整体回滚。
3. 插入时把外部层次扁平投影为当前环境下的兄弟层次，并为本次投影生成新的 GID；原 projection identity 作为 provenance 保存。
4. 通过 `expected_workspace_version + idempotency_key + inspection_hash` 防止预览后源文件或目标草稿变化。

**验证命令：**

```powershell
pytest -q plugins/simulation/tests/test_plmxml_environment_codec.py plugins/simulation/tests/test_plmxml_environment_capabilities.py
```

---

## 工作包 3：实现带五种复制深度的 BOP 投影插入

**新增/修改文件：**

- `plugins/simulation/tests/test_environment_composition_capabilities.py`
- `plugins/simulation/simulation_backend/capabilities/environment_composition.py`
- `plugins/simulation/simulation_backend/data/workspace_repository.py`
- 对应 capability descriptor、provider binding、迁移和生成文档

**测试先行：**

1. 预览和执行均只通过 `craft.bop.fork_projection.get@1` 获取不可变 BOP 投影，不直接读 Craft 表。
2. 五种复制深度严格对应：`all`、`operation`、`process`、`role`、`station`。
3. BOP 中产品和资源引用不复制成备选层次节点；它们登记到模型文档/资源引用区，BOP 工艺骨架单独成为一个新备选层次。
4. 预览返回来源 repository/version、线体、节点数、模型引用数、资源引用数、冲突、`plan_hash`。
5. 执行必须提交相同 `plan_hash`；来源版本或目标行版本变化时拒绝执行。
6. 同一请求重放返回相同结果；目标环境不得产生第二份重复层次。

**最小实现：**

1. 新增原子能力：
   - `simulation.environment.bop_projection.preview@1`
   - `simulation.environment.bop_projection.apply@1`
2. preview 只产生确定性 projection plan；apply 在单事务内创建一个备选层次、工艺节点和被验证的模型/资源引用。
3. source evidence 固定保存 `source_repository_gid`、`source_version_gid`、`source_content_hash`、`line_gid`、`fork_depth` 和 plan hash。

**验证命令：**

```powershell
pytest -q plugins/simulation/tests/test_environment_composition_capabilities.py plugins/simulation/tests/test_environment_hierarchy_repository.py
```

---

## 工作包 4：修复运行包幂等、依赖闭包和真实语义验证

**修改文件：**

- `plugins/simulation/tests/test_environment_materialization.py`
- `plugins/simulation/tests/test_environment_verification.py`
- `plugins/simulation/tests/test_plmxml_environment_capabilities.py`
- `plugins/simulation/simulation_backend/application/environment_materialization.py`
- `plugins/simulation/simulation_backend/application/environment_verification.py`
- `plugins/simulation/simulation_backend/capabilities/plmxml_environments.py`
- `plugins/simulation/simulation_backend/data/workspace_repository.py`

**测试先行：**

1. `runtime_package.prepare` 在创建 Artifact 前先查询现有 projection；同一版本和幂等键重放不得产生新 Artifact。
2. imported dependency 缺少 artifact、hash 或 connector binding 时明确返回依赖阻塞，不伪造零哈希或可用状态。
3. 完整环境包固定包含 `environment.plmxml`、`ai00-manifest.json` 和 `dependencies/`，manifest 中每个依赖都有可验证哈希。
4. Connector 同步完成后必须调用生产验证路径，并通过 `save_materialization_verification` 保存文档、层次、Occurrence、变换和显隐语义证据。
5. 无法证明后置状态时保持 `outcome_unknown`；不得自动重复可能已执行的 COM 写操作。

**最小实现：**

1. 把 projection 命中检查前移到 artifact 物化之前。
2. dependency resolver 只接受 artifact-backed 或明确 device-bound 且有 connector/device evidence 的依赖。
3. 在 runtime sync 完成回调中调用 semantic verifier 并持久化验证报告；只有报告通过才把运行包标为 verified。

**验证命令：**

```powershell
pytest -q plugins/simulation/tests/test_environment_materialization.py plugins/simulation/tests/test_environment_verification.py plugins/simulation/tests/test_plmxml_environment_capabilities.py
```

---

## 工作包 5：重构数模仿真两列工作区和操作前置状态

**前端修改文件：**

- `packages/sim-plugin/web/cad_sim/index.html`
- `packages/sim-plugin/web/cad_sim/cad_sim.css`
- `packages/sim-plugin/web/cad_sim/cad_sim.js`
- `packages/sim-plugin/web/cad_sim/environment_workspace.js`
- `packages/sim-plugin/web/cad_sim/environment_workspace.test.js`
- `packages/sim-plugin/web/cad_sim/environment_panel.test.js`
- `scripts/test_simulation_p0_boundary.js`

**测试先行：**

1. 第一列只包含“个人仿真环境”和“资源”，个人仿真环境提供新建、打开、Fork。
2. 第二列上部为“模型文件”，下部为“备选层次结构”，两区使用同一折叠样式。
3. 第二列操作栏固定为：插入、保存仿真环境、同步到 VisMockup、导出、回传 BOP。
4. 未打开个人仿真环境时，插入、保存、同步、导出和回传全部禁用，并给出页内原因。
5. “插入 VisMockup 已打开文档”可见、禁用并标注第二阶段。
6. 不恢复旧“项目空间/个人项目空间作为仿真环境库”的展示；它们只在插入 BOP 对话框中作为来源。

**最小实现：**

1. 仅调整现有 DOM 分区，不引入新 UI 框架或状态库。
2. 在 `environment_workspace.js` 建立单一派生状态 `deriveWorkspaceActions(state)`，所有按钮共用该结果。
3. 复用现有折叠、胶囊、状态栏和错误横幅样式，删除重复标题及旧眼睛/删除线入口。

**验证命令：**

```powershell
node packages/sim-plugin/web/cad_sim/environment_workspace.test.js
node packages/sim-plugin/web/cad_sim/environment_panel.test.js
node scripts/test_simulation_p0_boundary.js
```

---

## 工作包 6：实现 BOP、PLMXML、JT 和已有环境版本插入对话框

**前端新增/修改文件：**

- `packages/sim-plugin/web/cad_sim/environment_workspace.js`
- `packages/sim-plugin/web/cad_sim/environment_workspace.test.js`
- `packages/sim-plugin/web/cad_sim/cad_sim.js`
- `packages/sim-plugin/web/cad_sim/cad_sim.css`
- `packages/sim-plugin/web/cad_sim/plmxml_tree_import.js`
- `packages/sim-plugin/web/cad_sim/plmxml_tree_import.test.js`

**测试先行：**

1. BOP 对话框要求选择来源空间、BOP 版本、线体和五种复制深度之一；先预览，后执行。
2. PLMXML 对话框第一步 inspect，第二步明确选择“恢复新环境 / 插入模型及所选层次 / 仅插入模型”。
3. “插入模型及所选层次”必须显示层次多选框；“仅插入模型”明确提示不会投影备选层次。
4. JT 插入要求不可变 artifact 和 hash；没有可定位 Occurrence 时显示“已登记、尚不可控”。
5. 已有环境版本只允许“插入模型及所选层次”或“仅插入模型”。
6. 所有执行按钮必须消费后端预览返回的 plan/inspection hash，错误在对话框内显示。

**最小实现：**

1. 使用一个轻量 modal controller 和按来源拆分的 payload builder，不复制四套对话框框架。
2. 前端不计算复制深度、冲突或成员集合，只展示后端预览。
3. 文件选择仍通过现有 Electron/Artifact 上传边界，浏览器路径不直接进入 provider。

**验证命令：**

```powershell
node packages/sim-plugin/web/cad_sim/plmxml_tree_import.test.js
node packages/sim-plugin/web/cad_sim/environment_workspace.test.js
node scripts/test_simulation_p0_boundary.js
```

---

## 工作包 7：实现 VisMockup 风格的密集工程树与三态显隐

**前端新增/修改文件：**

- `packages/sim-plugin/web/cad_sim/model_document_collection.js`
- `packages/sim-plugin/web/cad_sim/model_document_collection.test.js`
- `packages/sim-plugin/web/cad_sim/structure_tree.js`
- `packages/sim-plugin/web/cad_sim/cad_sim_visibility.test.js`
- `packages/sim-plugin/web/cad_sim/cad_sim.css`
- `packages/sim-plugin/web/cad_sim/cad_sim.js`

**测试先行：**

1. 每行结构固定为 `[展开控件][显隐复选框][类型图标][名称][状态/数量]`。
2. 模型文件与备选层次使用不同图标；图标不承担显隐含义。
3. 行点击只选择，展开控件只展开，复选框只控制显隐，三个动作互不触发。
4. 复选框支持 checked、unchecked、indeterminate、disabled 四种状态。
5. 父节点状态基于规范化模型中的完整后代集合计算，包括未展开和未渲染节点。
6. 父节点显隐一次提交完整、有界、去重的 leaf occurrence GID 集合；部分失败返回半选与失败数量。
7. 未同步或映射不完整节点复选框禁用，并提供可读原因。
8. 树行高度保持 22–26px、同级使用细连接线、长名称省略但可查看完整文本。

**最小实现：**

1. 新增纯函数 `deriveVisibilityState(node, occurrenceState)` 和 `collectControllableLeaves(node)`，用 Node 测试覆盖。
2. 将现有眼睛/删除线节点动作替换成原生 checkbox；保留右侧命令栏的全显/全隐批量动作。
3. COM 批量调用继续经过既有 Connector Capability，不在浏览器直接请求 7654。

**验证命令：**

```powershell
node packages/sim-plugin/web/cad_sim/model_document_collection.test.js
node packages/sim-plugin/web/cad_sim/cad_sim_visibility.test.js
node packages/sim-plugin/web/cad_sim/cad_sim_vm_tree.test.js
```

---

## 工作包 8：保存版本、同步 VisMockup、导出与 BOP 回传准备

**后端/前端修改文件：**

- `plugins/simulation/tests/test_environment_composition_capabilities.py`
- `plugins/simulation/tests/test_plmxml_environment_capabilities.py`
- `plugins/simulation/simulation_backend/capabilities/environment_composition.py`
- `plugins/simulation/simulation_backend/capabilities/plmxml_environments.py`
- `packages/sim-plugin/web/cad_sim/environment_workspace.js`
- `packages/sim-plugin/web/cad_sim/environment_workspace.test.js`
- `packages/sim-plugin/web/cad_sim/cad_sim.js`

**测试先行：**

1. “保存仿真环境”只冻结 AI00 当前草稿为不可变版本，不触发 VisMockup 或 BOP 写入。
2. “同步到 VisMockup”生成完整运行包并一次性更新指定运行文档；轻量层次编辑只对已加载 Occurrence 批量执行，无法增量表达时标记 `full_sync_required`。
3. “导出 PLMXML”与“导出完整环境包”是两个明确选项，均来自已保存版本或明确快照。
4. “回传 BOP”先产生差异预览；无 Craft 写权限、来源版本变化或冲突未解决时禁止写入。
5. 回传只通过 Craft Owner Capability；Simulation 不直接更新 Craft 表。

**最小实现：**

1. 保存、同步、导出、回传保持四个独立 action 和 capability 调用链。
2. 第一阶段若 Craft 尚无满足精确写回合同的能力，只实现可审计差异预览并将回传按钮置为“存在阻塞原因”的禁用态，不用直连数据库补洞。
3. UI 状态栏显示当前环境、草稿/版本、是否有未保存更改、VisMockup 绑定、最后同步时间和 `full_sync_required`。

**验证命令：**

```powershell
pytest -q plugins/simulation/tests/test_environment_composition_capabilities.py plugins/simulation/tests/test_plmxml_environment_capabilities.py
node packages/sim-plugin/web/cad_sim/environment_workspace.test.js
node scripts/test_simulation_p0_boundary.js
```

---

## 工作包 9：Capability 治理、生成物和有界验收

**修改/生成文件：**

- `docs/capabilities/catalog.v2.json`
- 新增 capability 文档页
- `docs/capabilities/openapi-fragment.v2.json`
- `docs/capabilities/mcp-tools.v2.json`
- `docs/capabilities/agent-tools.v2.json`
- `docs/governance/capability-catalog-release.json`
- Provider 绑定与必要迁移

**治理步骤：**

1. 重新生成 Catalog、Descriptor、Provider binding 和文档，不手工伪造生成结果。
2. 校验新能力定义哈希、版本、owner、risk、confirmation、idempotency、consistency、transaction、evidence 和 audit 字段。
3. 校验发布 Provider artifact 与运行时实际绑定 artifact 完全一致。
4. 运行离线治理扫描并确认新增 blocker 为零；已有 blocker 单独列出，不把“测试通过”冒充 `human_approved`。

**后端有界回归：**

```powershell
pytest -q plugins/simulation/tests/test_environment_document_repository.py plugins/simulation/tests/test_environment_document_capabilities.py plugins/simulation/tests/test_environment_hierarchy_repository.py plugins/simulation/tests/test_plmxml_environment_codec.py plugins/simulation/tests/test_plmxml_environment_capabilities.py plugins/simulation/tests/test_environment_materialization.py plugins/simulation/tests/test_environment_verification.py plugins/simulation/tests/test_environment_composition_capabilities.py
```

**前端有界回归与构建：**

```powershell
npm run test:simulation-p0-boundary
npm run build:web:test-governance
```

**最终人工试运行：**

1. 使用测试 `.env` 和 `test_` 表启动后端、前端和 Electron App。
2. 新建个人仿真环境，插入一份 PLMXML，检查模型区和备选层次区。
3. 用五种深度各预览一次 BOP，并至少执行一种深度。
4. 在层次 A 下新增 E，确认 AI00 选择 A 时 leaf set 包含 B、C、D、E。
5. 保存版本、同步 VisMockup、重开 App、再次打开环境并验证结构与显隐语义。
6. 导出 `environment.plmxml` 和完整目录包，再恢复为新环境；比较文档、层次、Occurrence、变换、显隐和依赖哈希。

**完成条件：**

- 规格第 18 节第一阶段验收场景全部有自动测试或明确人工证据。
- 后端、前端工作树均通过 `git diff --check`，没有意外生产表或无前缀表写入。
- 未经用户明确要求，不提交、不合并、不推送；达到提交阶段时先报告测试证据与剩余治理状态。
