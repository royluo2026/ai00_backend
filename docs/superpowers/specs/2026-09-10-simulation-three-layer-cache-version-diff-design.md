# 数模仿真三层缓存、手动快照与版本差异设计

**日期：** 2026-09-10  
**状态：** 方案方向已确认，等待书面规格复核与 Capability 治理审批
**领域 Owner：** Simulation  
**关联设计：**

- `docs/superpowers/specs/2026-09-08-digital-simulation-environment-redesign.md`
- `docs/superpowers/specs/2026-09-09-simulation-environment-collaboration-versioning-design.md`

## 1. 目标与结论

本设计建设三层彼此独立、可分别失效的读取缓存：

1. Connector 本地 VM 原始结构缓存；
2. AI00 仿真环境结构投影缓存；
3. VM 节点与仿真环境节点之间的绑定缓存。

在三层缓存之上复用同一组不可变 VM Snapshot，提供用户手动快照、自动或单次版本对比、节点级差异提示和不可变差异报告。缓存只优化读取和计算，不成为新的业务权威数据源，不绕过 Capability Gateway、权限、确认、幂等、审计或领域写入规则。

三层缓存共享同一条获取与连接策略：页面先显示最近一次完整、已验证的缓存；Connector 使用 VisMockup 原生 PLMXML 导出取得当前完整结构和稳定 occurrence 身份；当前会话中的 COM NodeKey 只按需解析并只在该进程、文档会话内复用。PLMXML 校验与显隐、高亮等控制命令不能并发争抢 VisMockup COM，必须由单一调度器按优先级和独占规则执行。

本设计明确不包含 BOP 缓存。BOP 只作为既有绑定候选和影响对象被引用，不在本轮增加 BOP 缓存表、BOP 版本规则或 BOP 写链。

## 2. 当前事实与问题

### 2.1 已有实现

- Connector 已有 `VisMockupTreeCache`，使用 SQLite 保存文档和节点，能够在同一来源模型关闭重开后复用结构。
- Connector 当前以 `SourceIdentity + RootNodeKey` 的哈希识别文档，以 VM `NodeKey` 识别节点。
- 2026-09-10 对当前 W10 文档的真实探针确认：完整 Product Structure COM 遍历约 54.48 秒；使用正确 PLMXML 类型导出当前状态约 15.92 秒，文件约 37.2 MB，导出前后 `NumLoadedNodes` 均为 12,753，没有额外打开 JT 几何。
- 当前 Connector 的 `ExportEx` 实现传入 `SaveType=0`，而 VisAutomation 类型库定义 `0=DIRECTMODEL`、`2=PLMXML`。这是此前导出慢、可能拖住 VisMockup 的直接实现错误。
- 当前 VisMockup 14.2 导出的 current-state PLMXML 以 `Occurrence` 和厂商扩展 `PS_API-doc` 为主，而不是为每个节点生成标准 `ProductInstance`。实测包含 14,183 个 `Occurrence`、14,181 条唯一 JT 路径和最大 23 层结构。
- `__PLM_OCC_PDM_UID` 在 14,182 个有效 occurrence 上全部存在且零重复；完整 JT 路径也零重复。单独使用 clone-stable 叶 UID 有 1,950 个重复，不能作为唯一持久身份。
- 同一次 PLMXML 导出期间，另一只读 COM 调用等待约 15.10 秒，证明 VisMockup 服务端会串行化这些调用；把导出放到另一个线程不能消除控制延迟。
- 服务端已有 `workmanship_sim_vm_documents`、`vm_sessions`、`vm_snapshots`、`vm_snapshot_heads`、`vm_occurrences`、`vm_observations` 和 `vm_poses`，持久实体使用后端雪花 GID。
- `project_incremental_vm_snapshot` 与 `diff_snapshots` 已能基于 PLMXML 投影识别实例延续和部分版本变化。
- 仿真环境结构由 `workmanship_sim_workspace_*` 持久化，Workspace 每次受治理写入均推进 `row_version`。
- 前端 `environment_store.js` 当前只在页面内存中保存 Workspace、Nodes 和 Bindings，并在写入成功后应用 patch；刷新页面后仍需重新拉取。
- Workspace Binding 已有雪花 `binding_gid`，但前端未建立跨页面的版本化读取缓存。

### 2.2 必须解决的问题

- 相同来源和根节点并不代表内部零件 Revision 没有变化，现有 VM 缓存可能错误命中旧结构。
- VM 缓存没有节点版本指纹和子树 Hash，无法只刷新变化分支。
- 现有实现误把会话 NodeKey 当成可持久节点身份；VisMockup 重启或文档重载后可能把控制命令发给错误节点。
- 现有规格不能假定在读取当前完整结构之前即可知道哪些子树未变化。子树 Hash 只能减少规范化后的 SQLite 写入和差异计算，不能替代源端完整校验。
- PLMXML 导出是不可抢占的长 COM 操作；若与显隐、高亮共用普通 FIFO 队列，会使直接控制出现十余秒延迟。
- 仿真环境结构每次打开都依赖网络和全量渲染，不能先显示上次已验证数据。
- 绑定缓存没有同时固定 VM Snapshot 与 Workspace Revision，无法确定是否仍有效。
- 用户不能主动创建有名称、有备注、可长期保存的版本快照。
- 自动版本对比无法关闭，也没有关闭自动对比后只执行一次的独立入口。
- 差异结果没有稳定 GID、算法版本、节点证据和受影响绑定清单，不能作为可重复审计的报告。

## 3. 权威数据与缓存边界

| 数据 | 权威来源 | 本地缓存 | 缓存是否可写回权威数据 |
|---|---|---|---|
| VisMockup 当前原始结构 | 当前 VisMockup 文档及受控 PLMXML/JT 元数据 | Connector SQLite | 否，只能形成 Snapshot 候选 |
| VM 不可变 Snapshot、Occurrence 身份 | Simulation 服务端表 | Connector SQLite、前端只读投影 | 只能经 Simulation Capability 写入 |
| 仿真环境 Workspace、Nodes | Simulation Workspace 表 | 前端 IndexedDB | 否，写入必须经现有 Workspace Capability |
| VM—Workspace Binding | Simulation Workspace Binding 表 | 前端 IndexedDB | 否，写入必须经 Binding Capability |
| 手动快照元数据、差异报告 | Simulation 服务端表 | 前端 IndexedDB 可缓存报告摘要 | 只能经新增的 Simulation Capability 写入 |
| 不可变报告字节 | Base Artifact | 不缓存或按 Artifact 客户端规则缓存 | 只能经 Artifact 能力生成引用 |

任何缓存命中都不能制造授权结果。在线打开 Workspace 时，页面只有在当前登录主体持有未过期缓存读租约时才能先显示缓存，且交互写按钮在本次服务端权限校验完成前保持禁用。离线时只有未过期读租约允许只读显示，并明确标记“离线缓存”；租约过期后只显示骨架。

## 4. 身份与 GID 规则

### 4.1 稳定身份与版本身份分离

- `document_identity_hash`：规范化根 Item/BOM View 身份、来源模型标识和根产品身份后的 SHA-256，用于判断是否为同一逻辑来源模型。VisMockup 进程 ID、文档句柄和 RootKey 不进入持久文档身份。
- `stable_occurrence_key`：优先使用受控 PLMXML 的 `__PLM_OCC_PDM_UID`；缺失时依次使用可证明唯一的 `__PLM_ABSOCC_UID`，或经唯一性校验的 clone-stable 链、产品身份与 occurrence path 组合。它是来源系统身份或其 Hash，不冒充服务端 GID。
- `session_node_key`：VisMockup 当前进程内的 COM NodeKey，只用于控制句柄；它必须绑定 `server_process_id + document_handle + root_key`，不得跨会话作为持久节点身份。
- `revision_fingerprint`：节点当前内容版本摘要，用于判断同一节点是否发生变化。
- `subtree_hash`：节点自身指纹与有序子节点 Hash 的 Merkle Hash，用于跳过整棵未变化子树。
- `document_gid`、`snapshot_gid`、`occurrence_gid`、`binding_gid`、`diff_report_gid`、`diff_item_gid`：服务端雪花 GID。

稳定身份回答“是不是同一个对象”，版本指纹回答“同一个对象是否改变”。两者禁止混为一个字段。

### 4.2 本地 SQLite 主键决定

本地 SQLite 缓存记录不是跨系统业务实体，不允许由 Connector 自行使用未经分配的 `machine_id` 生成看似全局唯一的雪花 GID。原因是多个 Connector 使用相同 10 位 machine ID 时可能产生真实碰撞。

因此：

- 服务端持久业务实体必须使用 `backend.platform_sdk.ids.next_gid()`；
- SQLite 使用本地 `INTEGER PRIMARY KEY` 作为实现行号，并对 `document_identity_hash`、`(cache_document_id, stable_occurrence_key)` 建唯一约束；
- 服务端确认身份后，将真实 `document_gid`、`occurrence_gid` 写入 SQLite 映射列；
- 本地行号永不暴露为 API GID、Snapshot 身份或绑定身份；
- 当前 SHA-256 身份不是 UUID，也不替代服务端雪花 GID。

这项决定满足全局业务实体统一使用雪花 GID，同时避免在离线缓存层制造伪 GID。

## 5. 第一层：Connector VM 原始结构缓存

### 5.1 SQLite 模型

`vm_cache_documents`：

- `local_id INTEGER PRIMARY KEY`
- `document_identity_hash TEXT UNIQUE NOT NULL`
- `document_gid TEXT NULL UNIQUE`
- `source_identity TEXT NOT NULL`
- `root_key TEXT NOT NULL`
- `source_manifest_hash TEXT NOT NULL`
- `root_subtree_hash TEXT NOT NULL`
- `max_cached_depth INTEGER NOT NULL`
- `cache_state TEXT NOT NULL`：`valid | uncertain | rebuilding | stale`
- `captured_at_utc TEXT NOT NULL`

`vm_cache_nodes`：

- `local_id INTEGER PRIMARY KEY`
- `cache_document_id INTEGER NOT NULL`
- `occurrence_gid TEXT NULL`
- `external_node_key TEXT NULL`
- `stable_occurrence_key TEXT NOT NULL`
- `pdm_occurrence_uid TEXT NULL`
- `absolute_occurrence_uid TEXT NULL`
- `clone_stable_chain_json TEXT NOT NULL`
- `occurrence_path_json TEXT NOT NULL`
- `parent_stable_occurrence_key TEXT NULL`
- `child_order INTEGER NOT NULL`
- `depth INTEGER NOT NULL`
- `printable_name TEXT NOT NULL`
- `product_ref TEXT NOT NULL`
- `revision_code TEXT NOT NULL`
- `representation_refs_json TEXT NOT NULL`
- `revision_fingerprint TEXT NOT NULL`
- `subtree_hash TEXT NOT NULL`
- `has_more INTEGER NOT NULL`
- `last_seen_snapshot_gid TEXT NULL`
- `removed_at_utc TEXT NULL`

唯一约束为 `(cache_document_id, stable_occurrence_key)`。`external_node_key` 仅保留为来源/诊断字段，不再承担跨会话唯一约束。节点 GID 映射不是判断同一节点的唯一依据，因为首次本地读取时服务端可能尚未分配 Occurrence GID。

### 5.2 PLMXML 获取与规范化

当前完整结构以 VisMockup 原生 PLMXML 导出为首选来源，不再用逐节点 COM 遍历作为全量采集主路径：

1. 从 `VFFrame.Application` 取得当前 VisAutomation Application、ActiveDocument 和 `PLMXMLSaveOptions`。
2. 临时设置 `AskEveryTime=0`、`CopyParts=0`、`RetainReferences=1`、`ForceRetainRefs=1`、`SaveLateLoadedProperties=0`、`SaveExtendedInPLMXML=0` 和 `SaveInsertedAssemblies=0`。
3. 调用 `ActiveDocument.ExportEx(PLMXML=2, tempPath, "", hierarchyIndex)`；禁止继续使用 `DIRECTMODEL=0`。
4. 在 `finally` 中恢复用户原 PLMXML 保存选项。不得修改用户注册表中的全局导出模式作为运行时方案。
5. 流式解析标准 `ProductInstance/ProductRevisionView` 和 VisMockup 14.2 current-state `Occurrence/ApplicationRef` 两种投影。对 current-state 格式，从 `PS_API-doc/JT_PROP_NAME` 恢复完整父子路径，从 `PS_API-doc/NGID` 与 UserValue 提取 PDM UID、absolute UID 和 clone-stable 链。
6. 校验 XML 安全限制、节点总数、唯一身份覆盖率、父子闭包、根身份和文档来源；任何一项不完整都不得发布为 `valid` generation。
7. 规范化并计算 Snapshot Hash 后删除临时 PLMXML。只有用户手动快照、共享基准或审计流程明确要求 Artifact 时，才通过既有 Artifact 链保存不可变原始文件。

此路径不依赖 AI00 直接访问 Teamcenter。当前文档即使最初来自 Teamcenter，AI00 采集的是 VisMockup 已经持有的产品结构与元数据。

### 5.3 Occurrence 身份与跨版本匹配

同一 Snapshot 内的精确身份优先级固定为：

1. `__PLM_OCC_PDM_UID`；
2. `__PLM_ABSOCC_UID`；
3. 经唯一性校验的完整 clone-stable 链、产品身份和 occurrence path 组合；
4. 以上均不可用时标记 `uncertain_identity`，不得静默生成“稳定身份”。

跨 Snapshot 延续匹配先使用相同 PDM/absolute UID；再使用叶 clone-stable UID、产品 Item 身份和父链上下文联合匹配。叶 clone UID、名称、VPPS 或路径单项均不能自动确认延续。多个候选必须产生 `ambiguous_identity`，交由用户复核。

### 5.4 节点版本指纹

按固定字段顺序 canonical JSON 后计算 SHA-256：

1. 稳定节点键；
2. product/model reference；
3. Revision code 或 Teamcenter Item Revision UID；
4. 规范化 representation location 列表；
5. 能安全读取时的 JT 文件长度与最后修改时间；
6. 用户明确要求几何级校验时的 JT 内容 SHA-256；
7. 父节点稳定键；
8. 同父节点内顺序；
9. 会影响结构或绑定的白名单属性。

显隐、选择、高亮、相机和窗口状态不进入结构指纹。

### 5.5 新鲜度证据优先级

1. 当前完整 PLMXML 的规范化 Snapshot Hash；
2. PLMXML 中的 PDM occurrence UID、Item Revision UID、Revision code 与 representation location；
3. 本地 JT/模型引用文件的路径、长度和修改时间；
4. 当前 VisMockup `server_process_id + document_handle + root_key` 只证明同一活动会话，不证明内部 Revision 未变化；
5. 只能取得 VM NodeKey 与名称时，状态为 `uncertain`，不得静默声称缓存有效。

不得为了读取 `catiaOccurrenceName` 或其他属性触发 JT 几何加载。若 VisMockup COM 某属性会隐式打开 JT，该属性只能进入显式后台深度采集，不进入交互热路径。

### 5.6 完整校验后的增量发布算法

1. 连接当前文档，计算稳定文档身份，并立即返回上一个完整 generation，状态显示为 `verifying`。
2. 按 5.2 导出并规范化当前完整 PLMXML，不加载 JT 几何。
3. 计算节点 `revision_fingerprint`，自底向上计算 `subtree_hash` 和文档 Snapshot Hash。
4. Snapshot Hash 相同：只推进校验时间和当前会话证明，不重写节点、不生成重复技术 Snapshot。
5. Snapshot Hash 不同：比较两棵已完整读取的规范化树；子树 Hash 相同则复用 SQLite 行和已有 diff 结果，只 upsert 新增、变化、移动或顺序变化节点。
6. 在一个 SQLite 事务内写入新 generation、软删除消失节点并原子切换文档 head。
7. 提交后返回新 Snapshot 候选；事务失败继续保留旧的完整 generation，并将本次构建标记失败，不产生半棵树。

Merkle Hash 优化的是完整读取后的比较、写入和报告生成，不得描述为“无需读取当前源子树即可证明其未变化”。

当来源文件被重命名或移动时默认形成新文档身份。用户可通过受治理的“声明为同一模型来源”流程建立 lineage，本地缓存不得只凭文件名猜测继承。

### 5.7 当前会话 NodeKey 映射

NodeKey 映射是易失控制索引，不是第四份业务缓存：

- 映射键固定为 `server_process_id + process_start_time + document_handle + root_key + stable_occurrence_key`；
- Connector 或 VisMockup 重启、ActiveDocument 改变、RootKey 改变时整体丢弃；
- 页面树始终使用 `occurrence_gid/stable_occurrence_key`，不得把 NodeKey 暴露为业务身份；
- 用户第一次控制一个节点时，Connector 根据已验证 occurrence 的子序号路径逐级调用 `GetChildrenKeysPS`，只解析该路径并缓存结果，不遍历整棵树；
- 能安全读取时校验叶节点名称/产品引用；校验不一致立即停止控制并要求重新同步，不使用相邻节点或名称模糊匹配兜底；
- 全显、全隐直接使用视图级 COM；对子树操作只解析子树根 NodeKey；重复操作复用当前会话映射。

### 5.8 COM 调度与连接状态

所有 VisMockup 调用经过一个调度器，但分成两个等级：

- 高优先级控制：显隐、高亮、选择、视角、打开/关闭；
- 低优先级独占采集：PLMXML 导出、完整快照和手动版本采集。

自动采集只有在高优先级队列为空且连续 10 秒没有控制请求时才能开始；开始前有新控制即继续延期。`ExportEx` 开始后视为不可抢占，页面显示“结构校验中”，不得重复提交第二个导出。手动“创建快照/重新同步”允许显式进入独占采集，但必须显示进度。

导出在可回收的 Connector 工作进程中执行并设置一次性超时。超时后终止工作进程、保留上一完整缓存、标记 exporter degraded，且不得自动循环重试或强杀 VisMockup；只有 VisMockup 响应性探针恢复或用户明确重试后才能再次采集。进程隔离保护 Connector 控制面，但不虚假声称能够取消已经进入 VisMockup 服务端的 COM 操作。

## 6. 第二层：AI00 仿真环境结构投影缓存

### 6.1 IndexedDB 作用域

前端建立 `ai00-simulation-cache-v1`：

- `workspace_heads`：`auth_subject_gid + workspace_gid`；
- `workspace_nodes`：`auth_subject_gid + workspace_gid + node_gid`；
- `workspace_bindings`：`auth_subject_gid + workspace_gid + binding_gid`；
- `vm_snapshot_summaries`：当前主体可读的 Snapshot 摘要；
- `diff_report_summaries`：当前主体可读的差异报告摘要；
- `preferences`：当前主体、Workspace 级自动对比偏好和基准快照。

租户、项目可见性或角色不作为客户端自行放宽权限的依据。缓存必须按服务端认证主体隔离；退出登录、切换账号、权限拒绝或主体失效时清除对应作用域。

服务端 Workspace 增加 `cache_revision_hash`。创建时由初始 canonical state 生成；此后每个 Workspace/Node/Binding 受治理写事务使用 `H(previous_cache_revision_hash || canonical_patch || next_row_version)` 推进。它只是廉价缓存失效令牌，不替代冻结版本的语义 `content_hash`，也不能由客户端提交。

### 6.2 读取策略

1. 页面选择 Workspace 后，立即读取当前主体 IndexedDB 中最近一次服务端确认的数据。
2. UI 显示“正在校验”，写操作保持禁用。
3. 调用新的轻量 `simulation.environment.workspace.cache_lease.get@1` 重新校验权限，返回当前 `row_version`、权限版本、`cache_revision_hash` 和最长 5 分钟的签名读租约，不返回完整节点。
4. `row_version` 与 `cache_revision_hash` 相同：保留现有节点 DOM 和展开状态，只更新读租约和校验时间。
5. `row_version` 或 `cache_revision_hash` 不同：调用现有 `simulation.environment.workspace.get@1` 取得完整权威数据并替换缓存；同一页面内的现有受治理 mutation patch 继续即时更新缓存和内存。
6. 请求返回 `permission_denied/not_found`：立即移除该 Workspace 缓存并退出页面，不继续展示旧数据。
7. 网络不可用：仅在缓存读租约未过期时允许只读查看，显著标记离线；租约过期后隐藏业务节点，禁止排队伪写。

第一阶段只新增轻量读租约能力，不新增 Workspace delta Capability。只有 `row_version` 或 `cache_revision_hash` 变化才调用现有 `workspace.get@1` 全量重建；只有真实指标证明变化后的全量重建成为瓶颈时，才设计分页 delta 能力。

## 7. 第三层：VM—仿真结构绑定缓存

### 7.1 缓存记录

绑定权威记录继续使用现有服务端 `binding_gid`。IndexedDB 投影至少保存：

- `binding_gid`
- `workspace_gid`
- `workspace_node_gid`
- `workspace_row_version`：缓存 generation，不作为所有绑定失效的依据
- `workspace_node_row_version`：绑定目标节点版本
- `vm_document_gid`
- `vm_snapshot_gid`
- `vm_occurrence_gid`
- `vm_node_fingerprint`
- `binding_role`
- `source`：`manual | auto | inherited`
- `confidence`：自动候选使用，人工绑定为空
- `review_state`：`candidate | confirmed | rejected`
- `cache_state`：`valid | stale | missing_endpoint | ambiguous`

### 7.2 失效矩阵

| 变化 | 绑定处理 |
|---|---|
| Workspace 目标节点 `row_version` 与绑定时一致，VM 指纹一致 | `valid` |
| VM 节点 Revision 或 representation 指纹变化 | `stale`，等待复核，不自动删除人工确认绑定 |
| VM 节点删除 | `missing_endpoint` |
| Workspace 节点删除 | 清除本地投影；服务端 Binding 由既有事务规则软删除 |
| Workspace 中无关节点变化 | 绑定继续有效，只更新缓存 generation |
| Workspace 目标节点只移动，node GID 不变 | `stale`，保留关系并提示复核上下文 |
| 一个旧节点对应多个新候选 | `ambiguous`，禁止自动推进为 confirmed |
| 自动匹配唯一、双方身份和版本证据完整 | 仅生成 `candidate` 初版 |

绑定缓存命中只允许用于页面定位、显隐选择和提示。任何新增、删除、确认或调整继续调用现有 Binding Capability；前端不得用 IndexedDB 结果伪造写成功。

## 8. Snapshot 类型与手动快照

### 8.1 Snapshot 类型

- `technical_auto`：系统为缓存新鲜度和自动对比形成的不可变技术快照，按滚动策略保留。
- `manual_personal`：用户主动创建的个人快照，长期保留，只有创建者可归档，不允许硬删除。
- `manual_shared_baseline`：项目共享基准，由环境 Owner、项目经理或 super_admin 创建和管理。

所有 Snapshot 使用服务端雪花 `snapshot_gid`、固定 `snapshot_hash`、算法版本、来源文档 GID、创建者 GID、捕获时间和 Artifact 引用。手动快照不是复制一份可变节点表，而是对已完成、已验证 VM Snapshot 的不可变命名引用。

`workmanship_sim_vm_checkpoints` 使用雪花 `gid` 作为主键，保存 `snapshot_gid`、`workspace_gid`、`created_by`、`scope`、`name`、`note`、`row_version`、`created_at` 和可空 `archived_at`。归档只改变 Checkpoint 可见状态，不修改或删除所引用 Snapshot。

### 8.2 创建流程

1. 用户点击“创建快照”，填写名称和可选备注，选择个人或共享基准作用域。
2. 页面先复用 `simulation.document_snapshot.request@2 → action.get@1 → dispatch@1 → get@1` 获取当前受确认的采集结果，不建立旁路 COM 接口。
3. 采集完成后，调用新的 `simulation.vm_checkpoint.create@1`，输入固定的 `snapshot_request_id`、名称、作用域和请求返回的 exact snapshot hash。
4. Provider 重新读取完成的采集请求，校验所有权/可见性、Workspace 权限、名称长度、共享基准权限、幂等键和 exact hash；随后复用既有 `VmSnapshotRepository` 在同一服务端事务中固化或复用不可变 Snapshot，再创建命名 Checkpoint 引用。
5. 成功后返回 `checkpoint_gid`、`snapshot_gid` 和 `row_version`。

同一 `idempotency_key` 只能对应同一名称、作用域和 Snapshot；请求哈希不同返回幂等冲突。

拥有 Workspace 读取权且绑定当前 Connector 的用户可以创建 `manual_personal`；创建、替换或归档 `manual_shared_baseline` 仅允许环境 Owner、项目经理和 super_admin。归档共享基准前必须先选择新的有效基准或明确关闭该 Workspace 的默认基准，不允许留下悬空引用。

## 9. 自动对比、关闭状态和单次对比

页面固定提供三个互不混淆的控制：

```text
[创建快照]  [立即对比]  自动版本对比 [开关]
```

- “创建快照”始终可用；它产生手动快照，不改变自动对比设置。
- 自动版本对比是当前用户、当前 Workspace 的显示偏好；开启后，每次新鲜度校验发现新 Snapshot 时自动生成或复用差异报告，并显示非阻塞提示。
- 自动版本对比关闭后，缓存仍必须执行轻量新鲜度校验和安全失效，但不自动创建用户可见报告、不弹出差异面板。
- “立即对比”无论开关状态均可执行一次，不改变开关。
- 对比可选择“当前 vs 上一次”“当前 vs 指定手动快照”或任意两个有权读取的 Snapshot。
- 无变化时保持安静；有变化时显示页内状态条，不使用系统弹窗或阻断式 Modal。

自动偏好只保存在按认证主体隔离的 IndexedDB；第一阶段不跨设备同步。共享基准本身保存在服务端并受权限控制。

## 10. 节点级版本差异与报告

### 10.1 差异分类

- `added`
- `removed`
- `revision_upgraded`
- `representation_replaced`
- `geometry_content_changed`
- `moved`
- `reordered`
- `renamed`
- `attributes_changed`
- `ambiguous_identity`

版本号不同但结构和表示内容相同仍记录 `revision_upgraded`。版本号相同但 JT 内容 SHA 不同记录 `geometry_content_changed`，同时产生数据治理警告。只有文件长度/mtime 变化而未计算内容 SHA 时记录 `representation_replaced`，不得声称几何一定变化。

### 10.2 报告持久化

`workmanship_sim_vm_diff_reports`：

- `gid`：雪花 GID
- `workspace_gid`
- `document_gid`
- `before_snapshot_gid`
- `after_snapshot_gid`
- `trigger_kind`：`automatic | manual_once`
- `algorithm_version`
- `before_hash`、`after_hash`
- 各类型计数
- `affected_binding_count`
- `report_hash`
- `artifact_gid`
- `created_by`
- `created_at`

`workmanship_sim_vm_diff_items`：

- `gid`：雪花 GID
- `report_gid`
- `before_occurrence_gid`、`after_occurrence_gid`
- `change_kind`
- `before_parent_gid`、`after_parent_gid`
- `before_fingerprint`、`after_fingerprint`
- `evidence_json`
- `affected_binding_gids_json`

同一 `(before_snapshot_gid, after_snapshot_gid, algorithm_version)` 只有一份确定性报告；自动和手动触发可以复用同一报告。报告一旦完成不可原地修改，算法升级生成新报告。

### 10.3 页面呈现

- 状态条显示总变化数及新增、删除、升级、移动、几何变化数量。
- VM 树使用状态标识，不只依赖颜色；每个变化节点提供文字标签和筛选。
- 点击差异项定位节点并展开祖先路径。
- 受影响绑定独立分组为 `仍有效 / 待复核 / 端点缺失 / 歧义`。
- 自动对比关闭时不主动显示状态条；用户点击“立即对比”后显示本次结果。
- 报告支持导出结构化 JSON；CSV 只导出扁平差异明细，不承载完整证据。

## 11. Capability 复用与新增边界

### 11.1 复用

- `simulation.document_snapshot.request@2`
- `simulation.document_snapshot.action.get@1`
- `simulation.document_snapshot.dispatch@1`
- `simulation.document_snapshot.get@1`
- `simulation.environment.workspace.get@1`
- `simulation.environment.binding.create@1`
- `simulation.environment.binding.remove@1`
- `simulation.environment.bop_vm_binding_draft.preview@1`

### 11.2 新增候选

最终 ID 在实施前仍需 Registry 复用扫描，但业务效果边界固定为：

- `simulation.vm_checkpoint.create@1`：从已完成 Snapshot 创建不可变命名检查点。
- `simulation.vm_checkpoint.search@1`：分页查询当前主体可读的检查点。
- `simulation.vm_checkpoint.archive@1`：归档本人个人检查点，或由授权管理者归档共享基准；不可硬删除 Snapshot。
- `simulation.environment.workspace.cache_lease.get@1`：重新鉴权并返回绑定主体、Workspace、权限版本、`cache_revision_hash`、row version 和最长 5 分钟有效期的签名缓存读租约。
- `simulation.vm_diff_report.generate@1`：对两个固定 Snapshot 生成或复用确定性差异报告。
- `simulation.vm_diff_report.get@1`：读取一份报告及有界摘要。
- `simulation.vm_diff_item.search@1`：分页读取报告节点差异。

`generate` 是持久副作用，要求唯一幂等键；它不修改 VM、Workspace 或 Binding。`get/search` 必须按 Snapshot、Workspace 和项目可见性重新鉴权。缓存设置不定义为业务 Capability，属于本地显示偏好。

## 12. 一致性、并发与失败处理

- VM 树读取状态固定为 `verified | verifying | stale | unavailable`。`verified` 才能用于自动绑定、版本报告或需要当前结构证据的写入；`verifying` 可显示最近完整缓存并允许通过当前会话路径校验的查看/控制；`stale` 只读且显著提示；`unavailable` 不显示业务节点。
- 自动 PLMXML 校验触发条件固定为：首次连接无缓存、VisMockup 进程/活动文档/RootKey 改变、用户重新同步、用户创建手动快照，或业务写入要求当前 Snapshot。不得因页面重渲染、轮询或重复连接事件反复导出。
- 同一活动会话且 Snapshot 已验证时，重开页面、前端刷新和 Connector 心跳不得重新扫描 VM 树。
- 自动校验可以延后但不能被省略为“已验证”；自动绑定、Checkpoint、Diff Report 和依赖当前结构的提交在校验完成前 fail closed。
- SQLite 增量替换必须是单事务；进程崩溃后保留上一个完整 head。
- 服务端 Snapshot 与报告不可变；Head 推进使用 expected row version。
- 同一文档并发采集只允许一个构建者推进 head，失败方重新读取 head，不覆盖胜者。
- 对比必须固定 before/after Snapshot GID 与 hash；运行期间 Head 变化不改变本次报告输入。
- IndexedDB 写入先写临时 generation，再原子切换 head；不允许 Nodes 更新成功而 Head 仍指向旧 generation。
- 服务端返回 schema 不兼容、hash 不一致或分页缺页时丢弃新 generation，继续保留上次完整缓存并显示错误。
- 权限拒绝优先于缓存可用性；不得以“正在显示上次成功数据”为理由继续展示已经无权访问的数据。
- 自动任务失败只显示页内可重试状态，不循环弹窗、不无限重试、不阻塞显隐等无关控制。

## 13. 安全与隐私

- 缓存不得保存 access token、cookie、confirmation token、API key 或 Connector 私钥。
- IndexedDB 按认证主体分区，退出和换号清理；共享电脑不能跨用户读取旧缓存。
- 服务端 `workspace.cache_lease.get@1` 返回短期 `cache_read_lease`，固定主体、Workspace、权限版本、`cache_revision_hash` 和不超过 5 分钟的过期时间。只有未过期租约允许在网络校验完成前先显示缓存；租约过期时先显示骨架并完成在线鉴权。离线查看同样不得超过租约期限。
- 私人仿真环境缓存不能被其他用户命名空间读取。
- 项目共享 Snapshot 的可见性每次在线打开都由服务端重新判定。
- 差异证据中的绝对本地文件路径默认脱敏，只保存来源 hash 和允许显示的模型标识。
- 报告 Artifact 不包含用户无权读取的节点属性或跨域数据。

## 14. 迁移与回滚

### 14.1 Connector SQLite

- 数据库使用显式 `schema_version`。
- 从现有 `document_cache/document_nodes` 迁移时读取旧记录，能形成新文档身份和节点指纹的写入新 generation。
- 缺少 Revision/representation 信息的旧记录标记 `uncertain`，首次打开执行有界重建；禁止直接标记 `valid`。
- 迁移成功后保留旧表一个应用版本，只读回退；下一版本再清理。
- 新代码失败时可切回旧表读取，但不能把新格式部分数据反写旧表。

### 14.2 前端 IndexedDB

- 数据库名带版本号，升级失败时删除未启用的新库，不删除旧版本。
- IndexedDB 不做服务端数据迁移；任何缺失都可以通过 Capability 重新构建。
- 紧急回滚可关闭缓存读取特性开关，恢复现有在线全量读取，不影响服务端权威表。

### 14.3 服务端

- 新增 Checkpoint、Diff Report、Diff Item 表，不修改既有 Snapshot 历史。
- 回滚只停止新报告生成；已生成报告保留只读，不删除审计证据。

### 14.4 容量、保留与淘汰

缓存容量必须有硬上限，不能依赖用户手工清理：

| 存储 | 默认上限 | 自动淘汰策略 | 永不由缓存清理删除 |
|---|---:|---|---|
| Connector SQLite | 2 GiB | 超过 80% 先清旧 generation，再按 LRU 清理已关闭文档；每次清理到 60% 以下 | 当前打开文档、未同步 generation |
| 前端 IndexedDB | 200 MiB 或浏览器可用配额的 20%，取较小者 | 按 Workspace 最后访问时间整 generation 淘汰；Diff Item 分页优先淘汰 | 当前打开 Workspace、未过期读租约所引用 generation |
| 自动技术 Snapshot | 每文档最多 20 份未被引用的不同内容 Snapshot，最长 30 天 | 超过数量或时间上限且无强引用时清理 | Checkpoint、未压缩 Diff Report、发布证据或审计引用的 Snapshot |
| 自动差异报告 | 每文档最多 100 份未固定报告，最长 90 天 | 超过数量或时间上限、未固定且无外部证据引用时压缩为摘要 | 用户手动对比报告、共享基准报告、审批/发布/审计引用报告 |

补充规则：

- SQLite 只保存结构元数据、指纹和映射，不复制 JT 几何文件或 PLMXML 原始大文件。
- 相同 `(document_gid, snapshot_hash, algorithm_version)` 的技术采集复用同一 Snapshot，不因重复打开模型生成重复历史。
- 用户手动快照和共享基准不参与普通 LRU；用户只能归档，服务端保留其引用完整性。
- 清理顺序固定为：先压缩符合条件的自动报告，再清理无强引用的自动 Snapshot。不得反向执行。
- 自动报告压缩会删除 Diff Item 和明细 Artifact，写入 `compacted_at`，保留雪花 GID、before/after Snapshot GID 与 hash、算法版本、report hash、统计摘要和清理审计。压缩后的自动报告只保留摘要引用，不再强制保留完整技术 Snapshot。
- 清理 Snapshot 前必须在同一事务中确认没有 Checkpoint、未压缩 Diff Report、Binding review、发布或审计强引用；有强引用即跳过。
- Connector 在启动后和每次成功写缓存后检查容量；清理在空闲线程执行，不阻塞 COM 显隐、高亮和树读取。
- 2 GiB 是硬上限。清理旧 generation 后仍超限时，允许删除最久未使用的已关闭文档最后一个 valid generation；未同步数据或当前文档单独导致超限时停止写入新缓存并提示容量不足，不能突破上限。
- SQLite 使用 WAL checkpoint 和 incremental vacuum；不得每次写入执行全库 `VACUUM`。
- IndexedDB 使用 `navigator.storage.estimate()` 读取真实配额；写入出现 quota error 时淘汰最旧完整 generation 后重试一次，仍失败则关闭本次本地写入并继续在线读取。
- 页面提供“缓存占用”和“清除此模型缓存/清除全部本地缓存”。手工清理只删除本机 SQLite/IndexedDB 副本，不删除服务端 Snapshot、Checkpoint、Binding 或报告。
- 淘汰必须以完整 generation 或完整 Workspace 为单位，禁止只删一部分节点形成看似完整的残缺树。

## 15. 性能目标

- Connector SQLite 已命中且无需重建时，本地缓存查询 P95 小于 100 ms，不含 Gateway 调度时延。
- 仿真环境 IndexedDB 缓存命中时，页面骨架和上次确认结构在 300 ms 内可见。
- 当前会话 NodeKey 已解析时，单节点显隐/高亮的 Connector 内部控制 P95 小于 100 ms；首次按路径解析一个节点的 P95 小于 300 ms，不含 VisMockup 自身重绘时间。
- 对约 15,000 个 occurrence 的 current-state PLMXML，试点机结构导出目标 P95 小于 30 秒、规范化解析 P95 小于 2 秒，且导出前后 `NumLoadedNodes` 不增加。
- 只有一个节点分支变化时，完整 PLMXML 仍允许读取全部当前结构，但不得重写 Hash 相同的兄弟子树或重新生成等价差异明细。
- 5000 节点报告分页首屏不读取超过 200 条 Diff Item。
- 自动对比关闭时，不执行报告持久化和明细加载；新鲜度检查仍执行。
- `technical_auto` 先按内容 Hash 去重；每文档最多保留 20 份未被引用且不超过 30 天的不同内容 Snapshot。手动 Checkpoint 引用的 Snapshot 不自动删除。
- 自动导出不得在控制活跃期开始。不可抢占导出开始后的固有等待必须被页面明确显示并计入 `plmxml_export_blocked_control_ms`，不得隐藏在普通控制耗时中。

性能验收同时记录本地缓存耗时、Gateway 排队耗时、Connector COM 耗时和页面渲染耗时，不能只报告总时间掩盖瓶颈。

## 16. 测试与验收

### 16.1 VM 缓存

- `ExportEx` 必须使用 `SaveType=2`；回归测试应证明 `0` 被拒绝为 PLMXML 导出参数。
- 导出临时关闭交互、零件复制和 late-loaded 属性，结束后恢复原设置；失败路径同样恢复。
- 真实 VisMockup current-state PLMXML 能从 `Occurrence/ApplicationRef` 还原完整父子结构、PDM UID、stable clone 链、产品身份和最大层级。
- 真实约 14,000 节点采集前后 `NumLoadedNodes` 不增加，导出目录不产生 JT 副本。
- 同一来源模型使用不同会话 Document ID 时命中同一文档缓存。
- 内部一个零件 Revision 改变，只更新该节点及祖先 Hash。
- 完整 PLMXML 读取后，子树 Hash 相同时不重写其后代、不生成重复差异明细。
- 节点新增、删除、移动、重排分别得到正确增量。
- 文件时间变化但无内容 SHA 时不误报几何变化。
- 无可靠版本字段时缓存状态为 `uncertain` 并重建。
- SQLite 中途失败后仍能读取上一完整 generation。
- SQLite 达到 80% 上限后按 LRU 清理到 60% 以下；达到 2 GiB 硬上限时允许淘汰已关闭旧文档的最后 valid generation，但保留当前文档和未同步 generation。
- 清理期间显隐、高亮和缓存读取不等待全库 vacuum。
- VisMockup/Connector 重启后旧 NodeKey 全部失效；首次控制只解析目标路径，不能批量预热完整 NodeKey 树。
- PLMXML 导出期间并发只读探针被 VisMockup 排队时，调度器记录阻塞且不会启动第二个导出。
- 导出超时后保留上一完整 generation、停止自动重试且不强杀 VisMockup。

### 16.2 仿真结构缓存

- 同一用户重开页面且缓存读租约未过期时先显示 IndexedDB，再由服务端相同 row version 确认。
- 缓存读租约过期时不能先显示业务节点，必须先完成服务端鉴权。
- 轻量读租约返回相同 row version 但不同 `cache_revision_hash` 时仍必须丢弃缓存并全量重建，同时记录写链不变量违规。
- row version 变化后替换为完整新 generation。
- 写 Capability 成功的 patch 同时更新内存和 IndexedDB。
- 权限撤销后立即清理缓存且不能继续查看。
- 切换账号不能读取上一账号缓存。
- 离线时只读，所有写按钮禁用。
- IndexedDB 配额不足时只淘汰完整 Workspace generation，不能留下半棵树。

### 16.3 绑定缓存

- 双方版本一致时复用。
- VM 单节点升级只使相关绑定 stale。
- Workspace 无关节点变化不使绑定失效；目标节点移动只使该节点绑定进入 stale。
- 任意端点删除正确标记或清除。
- 歧义候选不能自动确认为人工绑定。

### 16.4 快照和对比

- 手动个人快照、共享基准权限和幂等均正确。
- 自动对比关闭后仍校验缓存，但不生成可见报告。
- 关闭状态下“立即对比”只执行一次且不开启自动对比。
- 任意两个可读 Snapshot 可重现同一 report hash。
- 不可读 Snapshot、相同 Snapshot、算法版本非法和分页越界返回稳定业务错误。
- 节点版本号不变但 JT SHA 改变时记录几何内容变化。
- 报告能够列出受影响绑定且不自动删除人工确认关系。
- 自动 Snapshot/报告清理不删除任何 Checkpoint、发布、审批或审计引用的证据；手动本地清理不触碰服务端数据。

### 16.5 治理与运行证据

- 新 Capability 的 closed schema、权限、幂等、审计、Provider、consumer 和测试引用完整。
- Catalog/Descriptor/Provider Artifact hash 一致。
- Connector 单元测试、Simulation Provider 测试、前端缓存测试和真实 VisMockup 有界联调分别记录，不互相替代。
- `machine_passed`、`human_approved`、`runtime_verified` 独立报告。

## 17. 分阶段交付

### 阶段 A：VM 缓存正确性

先修复 `ExportEx SaveType` 和保存选项，增加 VisMockup 14.2 current-state PLMXML 规范化，再补齐稳定 occurrence 身份、节点指纹、子树 Hash、SQLite generation、跨会话命中、NodeKey 按需映射和 COM 调度。该阶段完成前不得启用自动差异报告。

### 阶段 B：仿真结构与绑定读取缓存

增加 IndexedDB generation、认证主体隔离、stale-while-revalidate 和绑定失效状态。继续复用现有 Workspace 全量 Get，不提前建设 delta API。

### 阶段 C：手动快照与差异报告

新增 Checkpoint/Diff 表与原子 Capability，完成自动开关、单次对比、树定位、报告分页和绑定影响清单。

各阶段均可独立关闭读取特性开关并回退到现有在线全量读取；任何阶段都不修改 BOP 缓存。

## 18. AI 严格自审记录

### 18.1 已发现并修正的设计问题

1. **不能把三个缓存合为一份。** VM 原始结构、Workspace 业务结构和 Binding 的权威来源、权限与失效条件不同，已拆成三层。
2. **不能只用 SourceIdentity 命中。** 内部 Revision 可变化，已增加节点指纹、子树 Hash 和 `uncertain` 降级。
3. **不能用本地未分配 machine ID 伪造雪花 GID。** 已限定服务端业务实体使用真实雪花 GID，本地实现行号不对外暴露，并保存服务端 GID 映射。
4. **关闭版本对比不能关闭缓存校验。** 已将“新鲜度校验”和“用户可见报告”拆开。
5. **手动快照不能旁路现有确认采集链。** 已明确复用 `document_snapshot.request@2` 工作流，再创建命名 Checkpoint。
6. **mtime 不能证明几何变化。** 已把 mtime/长度变化与 JT 内容 SHA 的结论分级。
7. **缓存先显示可能泄漏已撤销权限的数据。** 已要求按认证主体隔离，并在权限拒绝时立即清除；共享设备退出必须清理。
8. **Workspace 增量 API 可能过度设计。** 第一阶段复用现有 Get 与 patch，只有指标证明必要才新增 delta 能力。
9. **自动绑定不能因为缓存命中升级为确认绑定。** 已固定 candidate/confirmed 状态边界。
10. **差异报告不能跟随活动 Head 漂移。** 已要求固定两个 Snapshot GID、hash 和算法版本。
11. **不可变历史不能等于无限保留。** 已区分可重建本地缓存、滚动技术历史和人工/审计证据，并增加硬容量、LRU、水位线、引用保护与清理审计。
12. **Diff Report 对 Snapshot 的引用会阻止所有清理。** 已增加自动报告摘要压缩和强/弱引用语义，并固定“先压缩报告、再清理 Snapshot”的顺序。
13. **轻量校验不能为了算 Hash 重新读取完整结构。** 已增加写事务内推进的 `cache_revision_hash`；它只用于失效检测，不冒充语义内容 Hash。
14. **Merkle Hash 不能让 Connector 在未读取当前结构时跳过源端子树。** 已改为完整轻量 PLMXML 后做增量比较和 SQLite 发布，不再承诺无法证明的源端局部扫描。
15. **会话 NodeKey 不能作为持久 occurrence 身份。** 已将 PDM occurrence UID 作为首选身份，并把 NodeKey 限定为按需解析、会话失效的控制索引。
16. **单独 clone UID 不唯一。** 真实 W10 样本出现 1,950 个重复叶 UID；已要求 PDM/absolute UID 优先，clone UID 必须与产品身份及父链联合且通过唯一性检查。
17. **把 PLMXML 导出放到后台线程不能避免控制延迟。** 真实并发探针显示只读 COM 调用仍等待约 15 秒；已增加控制优先、空闲启动、独占导出和禁止重复导出规则。
18. **当前 Connector 传错导出类型。** 类型库确认 `0=DIRECTMODEL`、`2=PLMXML`；阶段 A 首先修复参数并验证不复制/不加载 JT。
19. **不能要求 Teamcenter 作为缓存新鲜度依赖。** 当前方案只读取 VisMockup 已持有结构，Teamcenter 来源仅作为不可变引用证据；无法访问 Teamcenter 不阻塞本地快照。

### 18.2 仍需人工评审的业务决策

- 项目经理、环境 Owner 与 super_admin 是否是共享基准的完整授权集合。
- `geometry_content_changed` 默认只产生高可见度证据和受影响绑定复核项，不自动阻塞项目发布；若未来需要阻塞，必须由业务 Owner 另行审批规则变更。

### 18.3 自审结论

本设计覆盖缓存身份、PLMXML 获取、会话 NodeKey、版本失效、三层所有权、用户手动快照、自动对比开关、关闭状态下单次对比、节点差异报告、权限、并发、迁移、回滚和验收。最快路径固定为“缓存立即显示、当前节点按需解析”；准确路径固定为“完整轻量 PLMXML、不可变 Snapshot、业务写前强校验”；稳定路径固定为“控制优先、导出独占、失败保留上一完整 generation”。共享基准授权固定为环境 Owner、项目经理和 super_admin；个人快照只能由创建者归档。未发现未声明的跨域写入；新增写能力仅属于 Simulation，Artifact 仅保存不可变报告字节。AI 自审不构成人工批准，实施前必须由用户确认本规格，并在 Capability 治理中心完成业务描述和新增能力审批。
