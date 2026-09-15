# Teamcenter 直读产品结构与 VisMockup 投射规格

版本：0.2，2026-09-16。状态：设计方向已确认；Teamcenter 精确搜索、只读结构观测、不可变快照、在线来源绑定、官方 Visualization 启动链和 AI00 UI 已实现并登记 test Catalog。AH 原生写入因 occurrence 映射尚未完成现场读回验证而保持禁用；未获得生产发布批准。

本规格补充并收敛以下既有设计：

- `2026-09-14-online-vismockup-environment-sync-design.md`
- `2026-09-14-large-structure-sync-design.md`
- `2026-09-10-simulation-model-documents-alternate-hierarchy-design.md`

发生冲突时，本规格负责 Teamcenter 登录、产品结构权威来源、AI00 快照以及产品结构到 VisMockup 的投射边界；既有规格继续负责环境、文档、备选层次结构（AH）和大规模调度。

## 1. 决策摘要

所有新增能力属于现有 `simulation` 域，不新增域。

系统分为三层，禁止合成一个万能 Capability：

1. **Teamcenter 本地会话层**：提供 AI00 内登录界面和只存在于本机 ConnectorHost 的会话。
2. **AI00 产品结构层**：直接从 Teamcenter 读取产品实例树，形成不可变、可追溯、可缓存的标准快照。
3. **VisMockup 投射层**：让 VisMockup 打开同一在线来源，再建立 AI00 occurrence 与 VisMockup runtime node 的映射，用于高亮、选择、显示隐藏和 AH 引用。

产品原始结构只读；AH 是独立可编辑引用结构。AI00 不把缓存树逐节点重建为 VisMockup CPS，不用 PLMXML 作为在线结构的日常中转，也不因读取结构加载全部 JT。

## 2. 目标与非目标

### 2.1 目标

- 在 AI00 中提供可用的 Teamcenter 登录、重新认证、切换账号和退出界面。
- 使用 Teamcenter Java SOA/FMS 正常认证，直接批量读取指定装配结构。
- 保留每个装配实例，不能按名称、Item ID 或 ItemRevision 合并重复出现的实例。
- 每个 occurrence 返回层级、父子关系、顺序、零组件类型、版本、版本所有人/组、位置、bbox、扭矩、重量及几何引用。
- 将一次读取固化为带配置和时间语义的 AI00 不可变结构快照，可用于历史对比。
- 支持本地 SQLite 热缓存，重新进入环境时先显示缓存，不默认全量后台重读。
- 将同一在线产品来源打开到 VisMockup，并建立可失效、可重建的实例映射。
- 支持十万级结构异步分块，不阻塞 AI00 或 VisMockup 交互。
- 对 Teamcenter 服务端实施强制零业务写入约束。

### 2.2 非目标

- 不修改 Teamcenter 产品结构、属性、数据集或文件。
- 不用本期替代 Teamcenter 配置规则、权限或审签。
- 不预下载全部 JT，不触发“显示全部数模”。
- 不把 VisMockup 运行时 key 当作跨会话稳定身份。
- 不把 PLMXML 或 VFZ 恢复为在线模型的权威来源。
- 不在本期承诺所有 VisMockup 手工状态均可跨进程恢复；AH 按既有同步规格处理。
- 不宣称直读一定比所有场景更快；必须用同一配置、同一装配和冷热条件实测。

## 3. 已验证事实与仍需验证的门槛

### 3.1 已验证

以 `W10-ENG0001/00;1` 为样本：

- Teamcenter 直读得到 14,416 个 occurrence、4,488 个不同 ItemRevision；结构读取约 42.6 秒。
- 关系与几何引用读取约 19.3 秒；得到 3,359 个 DirectModel Dataset、6,630 个 ImanFile、3,335 个 JT 文件。
- FMS read ticket 和一个真实 JT 下载成功；该 JT 为 Version 10.6。
- 已读取 relative/absolute 4×4 变换矩阵、bbox 原始 double 数组、扭矩、扭矩重要度和重量字段。
- 产品结构读取使用登录、对象加载、修订规则、临时 BOMWindow、全层展开、属性读取、GRM 展开、read ticket、文件下载和关闭临时 BOMWindow；未调用持久化保存。
- FCC 可工作的本机环境为 `FMS_HOME=D:/Siemens/Teamcenter14/tccs`，并需要 `tccs/lib` 位于子进程 PATH 和 `java.library.path`。

### 3.2 未验证，不得包装成完成

- 14,416 个直读 occurrence 与现有 PLMXML 的 14,183 个 Occurrence 存在差异；在配置规则、日期、包装根和过滤语义对齐前，不得宣称二者完整等价。
- 尚未证明通过原生接口让 VisMockup 按稳定 Teamcenter 对象选择器打开在线文档，并对所有 occurrence 建立无歧义映射。
- `STU-0000395673/00;1-Tool2025` 的旧网页/jjs 探针失败不等于 Java SOA 直读失败，需用正式本地 Provider 重新验证。
- bbox 和变换存在米/毫米尺度差异，需通过已知几何样本确认单位和坐标系。
- Teamcenter 属性名随部署定制，扭矩、重量、所有人等需支持投影配置和缺失值。

## 4. 总体架构

```text
AI00 登录面板
  │ 本地安全 IPC（含口令，只在此段存在）
  ▼
ConnectorHost / Teamcenter Read-only Provider
  │ local_session_id（设备、进程代次、用户绑定）
  ├── Teamcenter SOA：结构与属性只读
  ├── FMS：JT read ticket / 按需下载
  └── 本地 SQLite：快照块、来源和映射缓存
          │
          ▼
Simulation 产品结构快照（不可变 manifest + chunks）
  ├── AI00 模型文件树 / 历史比较
  └── VisMockup 投射 Provider
          │ 打开同一在线来源，不重建 CPS
          ▼
VisMockup 文档 + occurrence runtime mapping
          └── 高亮 / 选择 / 显隐 / AH 产品引用
```

结构快照是 AI00 的标准读模型；Teamcenter 在线对象仍是来源事实；VisMockup 文档是运行投影。三者身份相关但不能互换。

## 5. Teamcenter 登录界面与会话

### 5.1 UI

入口位于仿真环境的模型来源区域和连接状态菜单，打开 AI00 风格的轻量弹窗：

- 服务器：从管理员配置的端点列表选择；test 默认可包含 `http://192.168.44.150:7001/tc/`。
- 用户名。
- 密码。
- 可选 Group / Role；首次可留空采用服务器默认值。
- “记住服务器和用户名”，默认开启。
- “记住密码”，本期不提供；后续若提供，只能使用 Windows Credential Manager 并单独评审。
- 登录、取消、退出、切换账号、重新认证。
- 状态：未登录、登录中、已登录、会话过期、网络不可达、FCC 未就绪、权限不足。

使用 HTTP 端点时明确显示“当前连接未加密”的提示。生产环境默认要求 HTTPS；继续使用 HTTP 必须有环境级例外决定，不能在设计中声称口令传输安全。

### 5.2 凭据边界

- 密码只从 renderer 的受控 password input 通过 preload 暴露的专用方法进入 Electron main，再通过本地受限 IPC 交给 ConnectorHost。
- renderer 不保留密码到组件状态快照、localStorage、IndexedDB 或错误遥测。
- 密码、cookie、SSO token、FMS credential 不进入云端/服务端 Capability Gateway、业务 API、审计正文、异常堆栈或 SQLite。
- 后端只看到不可作为 bearer token 使用的 `local_session_id` 和脱敏后的 session descriptor。
- `local_session_id` 绑定 `device_id + connector_process_epoch + actor + server_endpoint_id`；跨设备、跨进程或换账号立即无效。
- 登出和会话过期清除内存令牌、SOA session、FMS utility 和运行映射；结构快照仍保留为带时间的只读历史。

## 6. Capability 拆分

以下 ID 是本规格建议的新合同；实施前仍需执行 Catalog/Registry 复用搜索并分配真实 `capability_version_gid`。不能复用旧批准或虚构 GID。

| Capability | 单一业务效果 | 执行位置 | 副作用级别 |
| --- | --- | --- | --- |
| `simulation.teamcenter.session.establish@1` | 在当前受控设备建立一个 Teamcenter 本地会话 | ConnectorHost，仅 local IPC | `write`；仅运行会话，无 Teamcenter 业务数据写入 |
| `simulation.teamcenter.session.status.get@1` | 读取当前本地会话状态 | ConnectorHost | `read` |
| `simulation.teamcenter.session.close@1` | 关闭指定本地会话并销毁凭据 | ConnectorHost | `write`；仅运行会话 |
| `simulation.teamcenter.product.search@1` | 按 Item ID、名称及版本条件搜索可读产品 | ConnectorHost → Teamcenter | `read` |
| `simulation.teamcenter.product_structure.observe.request@1` | 从精确来源配置读取并形成一份不可变 AI00 结构观测 | Backend orchestration + ConnectorHost | `write` 到 AI00 快照/操作记录；Teamcenter `read` |
| `simulation.product_structure.snapshot.get@1` | 分页读取既有 AI00 结构快照 | Simulation backend / local cache | `read` |
| `simulation.teamcenter.geometry.fetch.request@1` | 为明确的 Dataset/File 获取 read ticket 并按需缓存 JT | ConnectorHost/FMS | `read`；允许本地 FCC/cache 文件写入 |
| `simulation.vismockup.product_structure.project.request@1` | 在指定 VisMockup 文档打开/命中同一来源并建立运行映射 | ConnectorHost → VisMockup | `write` 到 VisMockup 运行态；Teamcenter `read` |

现有 `simulation.vismockup.node.selection.change.*`、`node.visibility.change.*`、文档身份、AH inventory/adoption/binding 能力继续复用，但消费者必须改为使用新映射，不得仅按名称匹配。

不提供 `executeTeamcenterMethod(name,args)`、任意 SOA endpoint、反射调用、脚本执行或通用 XML 转发能力。

## 7. 产品结构来源选择器

搜索入口支持：

- Item ID 精确/前缀，如 `W10-ENG0001`、`STU-0000395673`。
- 对象名称模糊搜索，如 `Tool2025`。
- Revision ID / sequence。
- 对象类型。
- 修订规则，默认服务器返回的明确规则，例如 `Latest Working`。
- 配置日期，默认“现在”，但必须固化为实际 UTC 时刻。
- 可选顶层对象 UID，供精确重开。

用户选中结果后生成 `source_selector`，至少包含 server identity、top Item/ItemRevision/BOMLine identity、revision rule identity、configuration date、locale 和属性投影版本。仅保存显示名称不能精确重开。

## 8. 标准产品实例树合同

### 8.1 快照 manifest

每次观测生成：

- `snapshot_gid`、`observation_gid`、schema version。
- 来源选择器及来源类型 `teamcenter_online | plmxml_file | jt_file`。
- `captured_at_start/end`、服务器时间（可取得时）、客户端时间偏差。
- revision rule、configuration date、variant/effectivity context。
- 节点数、边数、根集合、最大深度、块数、各块哈希和总体结构哈希。
- `complete | partial | stale | failed` 与缺口列表。
- 属性投影版本、单位与坐标约定版本。
- 读取 Provider、Connector 版本、Teamcenter endpoint identity；不含凭据。

刷新总是创建新 observation；内容相同可复用不可变 chunk，但不得覆盖旧时间记录。

### 8.2 occurrence

每个 occurrence 至少包含：

- `occurrence_gid`：AI00 快照内稳定实例 ID。
- Teamcenter occurrence/absolute occurrence UID（能取得时）。
- `parent_occurrence_gid`、`depth`（业务根为 0）、`sibling_order`、`is_leaf` 与 leaf certainty。
- 实例路径及路径身份构成，不以展示名作为身份。
- Item UID、Item ID、名称、对象类型和类型展示名。
- ItemRevision UID、revision ID、sequence、revision name/status。
- ItemRevision `owning_user` 和 `owning_group`；“版本所有人”默认解释为二者，不能误用当前登录人。
- 相对和绝对 4×4 变换、原始值、单位、坐标系和矩阵约定。
- bbox min/max 原始 double 值、单位、坐标系和有效性。
- 扭矩原值、解析后的 target/min/max/unit/tolerance，以及扭矩重要度；未知字段保留 null，不猜值。
- 单件重量、汇总重量及单位。
- DirectModel Dataset、ImanFile、JT 文件引用、文件大小、版本、是否已缓存；不在结构读取时下载内容。
- 属性读取状态和逐字段 provenance。

同一 ItemRevision 在不同 occurrence 中出现多次时生成多个 `occurrence_gid`，共享产品引用但保留各自父、顺序和变换。一个 VisMockup 文档中同名 PLMXML、在线文档或不同插入时间的内容也不得合并。

## 9. 缓存与时间语义

### 9.1 两级保存

- Simulation 数据库存不可变 manifest、结构 chunks、环境与 snapshot 绑定及历史观测。
- ConnectorHost SQLite 保存当前设备的热副本、来源解析索引和 VisMockup runtime mapping；它是可淘汰加速层，不是唯一事实库。

缓存键包含 endpoint、顶层对象 UID、修订规则、配置日期、variant/effectivity、属性投影版本和 schema version。名称相同不是同一缓存键。

### 9.2 命中行为

- 进入环境或切回文档时立即显示最近一次完整/部分缓存，并标注采集时间、配置和完整性。
- 默认不在命中后全量后台重读；否则缓存不能缩短用户等待时间。
- UI 显示“结构缓存：时间 · 未自动重读”，刷新入口放在模型文件树和 AH 区域的右键菜单。
- 用户显式刷新、来源配置变化、服务器明确推送变化或映射操作需要新证据时才读取。
- 可选的轻量 freshness probe 必须证明明显低于全量读取成本，且不得因此将缓存树隐藏或阻塞使用。

如果 VisMockup 关闭，再打开同名模型：AI00 快照仍可展示；所有旧 runtime key 立即失效。重新投射时按来源选择器和新 document session 重建映射，绝不因同名自动继承旧 key。

## 10. VisMockup 投射与通信

### 10.1 正确投射方式

在线来源的默认流程：

1. 捕获明确的目标 VisMockup document session，不在后台重新取任意 ActiveDocument。
2. 如果该文档已经打开同一精确 Teamcenter 来源，复用该模型插入实例。
3. 否则命令 VisMockup 通过其 Teamcenter 在线入口打开/插入同一来源选择器。
4. 枚举 VisMockup CPS occurrence，使用 Teamcenter occurrence identity、实例路径、产品版本及父链建立映射。
5. 映射完整后才能启用高亮、选择、显隐和 AH 引用操作。

禁止从 AI00 缓存节点逐节点新建 VisMockup 产品树；禁止将在线来源静默导出为 PLMXML 后再打开。二者都会丢失或弱化 Teamcenter 在线关联。

本地 PLMXML/JT 来源继续按文件插入实例处理，并保留文件绝对受控链接、内容哈希和 `inserted_at/first_seen_at`。它不能冒充在线来源。

### 10.2 产品结构与 AH 的汇流语义

产品结构和 AH 是两条独立的数据流，但必须汇入**同一个目标 VisMockup 文档会话**，不是分别导入两个互不关联的文件：

1. AI00 直读 Teamcenter，保存产品 occurrence、属性和 JT/FMS 引用；这些数据用于模型树、缓存、比较和身份映射。
2. AI00 以同一 `source_selector` 请求 Teamcenter `createLaunchInfo`，由官方 VVI/runner 让 VisMockup 打开在线 CPS；AI00 不逐节点重建 CPS。
3. 文档身份回读确认 `visDocUid + document_session + model_insertion_instance` 后，建立 AI00 occurrence 到当前 CPS runtime key 的映射。
4. BOP 经现有 `craft.bop.fork_projection.get@1` 和 `simulation.environment.alternate_hierarchy.bootstrap_from_bop_fork@1` 形成 AI00 AH 事实。
5. AH 投影器在该文档的 `AltHierMgr` 上创建/命中 AH：工艺组织节点投成虚拟 AH 节点，产品用 occurrence 映射得到 CPS key 后以“复制链接”加入；绝不移动或修改原 CPS。
6. VisMockup 关闭后，CPS/AH runtime key 全部作废；AI00 的在线来源、结构快照和 AH 事实仍保留。重开同一来源后重新映射，再按差异恢复 AH。

因此 UI 可以把“模型”和“备选层次结构”分栏显示，但运行时绑定必须共同指向同一 `document_session`。若产品在线文档尚未打开或 occurrence 映射不完整，AH 可以保存在 AI00，却不能把未解析的产品引用猜测写入 VisMockup。

### 10.3 AH 增量投影与回收

- AI00 是由 BOP 创建或在 AI00 编辑的 AH 的权威事实；VisMockup 是运行时投影。
- 首次绑定只创建缺失 AH/节点/引用；后续按稳定 `projection_identity + insertion_instance_id` 计算增删改，不重载产品文档。
- 同一产品多次插入必须保留多个 insertion instance；不得按名称、ItemRevision 或 CPS key 去重。
- 每批原生写入限制节点数和时间片，批间让出 VisMockup UI 线程；万级 AH 使用游标、幂等键、fencing 和读回校验。
- AI00 拥有节点可自动增量更新；VisMockup 手工新增/修改节点先作为 observed 分支回收，三方合并冲突时停止该 AH 的自动写入，不能静默覆盖。
- 已实测边界仅包括整份 AH 创建/枚举/重命名/删除和单个 CPS 引用添加。任意虚拟子节点创建、移动、删除在 live 验证通过前保持 feature gate 关闭；初版不得把静态定位到的 vtable slot 当作已验证能力。

### 10.4 映射状态

每个文档会话的映射状态：`unmapped → mapping → complete | partial | ambiguous | stale`。

映射记录包含 snapshot occurrence、document session、VisMockup model insertion instance、runtime key、建立时间和证据等级。以下事件令相关映射失效：

- VisMockup 进程或文档 session 变化。
- 文档关闭、在线模型重新插入、来源配置变化。
- 产品结构刷新到新 snapshot。
- VisMockup 返回节点已不存在或父链不一致。

`partial/ambiguous/stale` 节点禁止执行写入运行态的显示、隐藏、高亮或 AH 引用；UI 给出明确原因和“重新映射”，不能出现无解释的禁止符号。

### 10.5 文档和环境联动

- 选择仿真环境：显示缓存结构；命中绑定的存活 VisMockup 文档则激活并内嵌，否则按来源恢复。
- 选择 VisMockup 文档：有唯一环境绑定则切换环境；无绑定则显示“未绑定环境”；多个绑定属于数据冲突，禁止任选。
- 切换请求用 generation 保证最后一次意图胜出，迟到映射不能抢回 UI。
- 离开数模仿真页、窗口隐藏或切到工艺规划时，原生 3D 子窗口必须隐藏；不能继续悬浮覆盖其他页面或系统弹窗。

## 11. Teamcenter 强制只读

只读不是 UI 文案，而是 Provider 的不可绕过边界。

### 11.1 允许列表

仅允许已审计的强类型操作：登录/登出、对象加载、revision rule 读取、临时 BOMWindow 创建/展开/关闭、属性读取、GRM 关系读取、FMS read ticket 和文件读取。

临时 `createBOMWindows` 只用于会话内配置展开；不得调用 `saveBOMWindows`。FCC 在本地写缓存不等于修改 Teamcenter 业务数据。

### 11.2 明确禁止

- `setProperties`、`saveBOMWindows`。
- BOM add/remove/reparent、revision/create/delete/release。
- Dataset/File upload、replace、delete、write ticket。
- 任意命令名、反射、脚本或原始 SOA/REST 透传。
- 通过 VisMockup 修改 CPS；只允许显示状态、选择、高亮及已治理 AH 操作。

Provider 使用封闭的 `TeamcenterReadOperation` 枚举和强类型接口。denylist 仅作防御性补充，不是主防线。自动测试必须使用 recording transport，断言一次完整流程调用集合严格属于 allowlist；出现未知调用立即失败并审计。

权限分开声明：`simulation.teamcenter.session.use`、`simulation.product_structure.read`、`simulation.geometry.read`、`simulation.vismockup.project`。会话所有者和环境访问者不一致时不得借用他人的本机会话。

## 12. 大结构性能设计

- 产品结构观测作为异步 operation；UI 先显示缓存和已接收块，不等待整树完成。
- 优先使用 Teamcenter 批量展开；如果服务端只提供层级/分页入口，按固定 snapshot context 分页，禁止逐节点网络往返。
- 节点块初始上限 1,000 项或 1 MiB；Connector 内存队列初始上限 2,000 项或 8 MiB，先到者背压。
- 遍历使用显式队列，不递归；必须限制节点数、边数、深度、截止时间并报告 partial。
- 属性按投影批量取，不为每个字段、每个节点单独请求。
- 几何引用和 JT 内容分离；只有用户打开/显示对应节点时按需获得 read ticket。
- 前端树虚拟化，DOM 常驻行目标不超过 300；父级展开只取结构，不加载几何。
- VisMockup 原生执行每进程串行、短片调度；AI00 结构解析、哈希、SQLite 和网络落库不占用 VisMockup UI 线程。
- 万级 AH 同步沿用专项规格的 manifest、差异块、持久化游标、fencing 和 outcome-unknown 读回，不与 CPS 观测队列混为一个无界队列。

## 13. 错误与恢复合同

稳定错误至少包括：

- `teamcenter_endpoint_unavailable`
- `teamcenter_authentication_failed`
- `teamcenter_session_expired`
- `teamcenter_insecure_transport_not_approved`
- `teamcenter_fcc_unavailable`
- `teamcenter_object_not_found`
- `teamcenter_configuration_unavailable`
- `product_structure_partial`
- `product_structure_limit_exceeded`
- `product_structure_snapshot_stale`
- `vismockup_document_unavailable`
- `vismockup_online_source_open_failed`
- `vismockup_mapping_partial`
- `vismockup_mapping_ambiguous`
- `vismockup_mapping_stale`
- `teamcenter_write_operation_forbidden`

认证失败不自动无限重试；会话过期回到登录面板。结构读取失败保留上次快照，不将空结果提交为删除。原生调用 `invocation_outcome_unknown` 时先读回文档与映射状态，不盲目重放打开/插入。

## 14. 数据迁移与兼容

- 现有 PLMXML 环境保持 `plmxml_file` 来源，不按名称自动改成在线来源。
- 用户可显式“关联 Teamcenter 在线来源”；匹配必须比较顶层对象、配置和实例证据，歧义时人工选择。
- 现有只含顶层壳的模型缓存标记为 legacy/partial，不能作为完整删除或同步基线。
- 现有 VisMockup 映射全部视为 session-only；上线新 identity schema 后重新建立，不迁移旧 runtime key。
- 新 Capability、Descriptor、Provider、API、Electron IPC 和消费者绑定必须成套发布；不能只加前端按钮或 Provider 私有入口。

## 15. 验收计划

### 15.1 登录和安全

- 正确/错误密码、会话过期、切换账号、退出、网络断开、FCC 缺失分别验证。
- 自动扫描 renderer、main、Connector 日志、SQLite、backend request 和审计记录，确认无密码/token。
- recording transport 覆盖搜索、结构、属性和 JT 下载，断言 Teamcenter 持久化写调用为 0。
- 尝试调用未知方法、`saveBOMWindows`、文件 upload，必须在本地 Provider 边界拒绝且未到达网络层。

### 15.2 结构正确性

- 小装配 `STU-0000395673/00;1-Tool2025`：记录配置、节点/边、深度、重复实例、属性缺失和耗时。
- 大装配 `W10-ENG0001/00;1`：在相同 revision rule/date 下与 VisMockup、PLMXML 对比。
- 对数量差异逐项归因：包装根、配置、过滤、权限、未驻留、重复实例；未归因前状态不得为 complete-equivalent。
- 抽样核对层级、类型、版本、所有人/组、矩阵、bbox、扭矩、重量和 JT 文件。
- 同一 ItemRevision 至少两次插入的测试必须保留两个 occurrence 和各自变换。

### 15.3 缓存和历史

- 冷读、热缓存命中、手工刷新分别计时；热命中不得自动启动全量重读。
- 相同内容的两次刷新保留两个 observation，允许复用 chunk。
- revision rule/date 或在线版本变化生成新 snapshot，可比较新增、删除、移动和属性变化。
- VisMockup 被关闭后，缓存仍显示；重开同名模型不继承旧 runtime key，重新映射成功后才恢复操作。

### 15.4 VisMockup 投射

- 在线模型投射后，VisMockup 中仍能通过 Teamcenter/FCC 按需加载零件，无大面积红叉。
- AI00 与 VisMockup 抽样 occurrence 一一对应；歧义节点拒绝自动操作。
- 高亮、显示隐藏、父级级联和 AH 复制链接读回一致，原 CPS 父子关系不变。
- 文档/环境 A-B-A 切换 100 轮无串文档、无旧窗口悬浮、无过期响应抢回。

### 15.5 性能

- 同一机器、网络、账号、配置分别测 Teamcenter 直读、VisMockup 读取和 PLMXML 解析，记录冷/热总耗时、节点/秒、网络调用数和峰值内存。
- 14k、100k occurrence 测试不加载全部 JT；AI00 UI 输入响应 p95 目标不超过 100ms。
- 大结构分块可暂停/继续，磁盘满、网络断开、会话过期不丢已完成 chunk，不提交伪完整快照。

## 16. Capability 治理提案记录

### 16.1 Change classification

- Type: new Capabilities plus compatible consumer migration; exact major compatibility remains unverified until Registry comparison.
- Reason: introduce local Teamcenter authentication, immutable product-structure observations, and source-preserving VisMockup projection without widening existing generic native operations.

### 16.2 Capability identity

- capability IDs: listed in section 6; provisional until Catalog/Registry reuse search.
- capability_version_gid: unverified; must be allocated by governance system.
- domain: `simulation`.
- owner team: `simulation`.
- lifecycle status: proposed/experimental until machine, human and runtime gates pass.

### 16.3 Business definition

- business effects: each capability has exactly one effect listed in section 6.
- business invariants: Teamcenter business data is immutable; occurrence identity is instance-scoped; snapshot history is append-only; VisMockup projection never replaces online CPS with cached nodes.
- inputs/outputs: sections 5–10; exact JSON Schema to be generated during implementation.
- stable errors: section 13.
- permissions and resource scope: section 11.
- transaction policy: Teamcenter read-only; AI00 snapshot publishes manifest only after all accepted chunks are durable; Connector and backend have no distributed transaction.
- idempotency: reads are naturally repeatable against a fixed selector; session establish/close and observe/project requests require unique keys and readback on unknown outcomes.
- side effects: explicit in section 6.
- audit events: session established/closed without secrets; search; observation requested/completed/partial; geometry fetched; projection requested/completed/ambiguous; forbidden operation blocked.
- sensitive-data scope: passwords/tokens secret local-only; usernames personal/internal; product structure, file names, geometry and attributes internal restricted data.

### 16.4 Bindings and impact

- Provider: new Teamcenter read-only provider in ConnectorHost; existing VisMockup provider extended with stable projection/mapping, not arbitrary method execution.
- exposure: session establish/close are local UI IPC only and excluded from public REST/MCP/agent advertisements; structure reads exposed only through governed Simulation contracts.
- consumers: simulation workspace UI, model tree, environment/document coordinator, VisMockup selection/visibility/AH flows.
- tables/migrations: immutable observation manifest/chunks/source selectors and mapping metadata; local SQLite cache schema versioned separately.
- compatibility: existing PLMXML flows retained; online environments migrate only by explicit user action.

### 16.5 Verification and authority

- commands actually run for this design: repository/catalog inspection and prior direct-probe execution recorded in the exploration notes.
- raw outcomes: section 3; no new runtime implementation test was run for this document.
- code_revision: unverified because the target worktree contains unrelated in-progress changes.
- snapshot_gid/test_run_gid/result_hash: unverified; must be generated after implementation.
- machine_passed: unverified.
- human_approved: direction approved; exact business-definition hash unverified and not yet signed.
- runtime_verified: unverified.
- advisory: true.

## 17. 严格自审

### 17.1 已发现并在规格中修正的风险

1. **把登录密码放进 Capability 请求**：已改为 local-only IPC，远端只见不可远用的 session reference。
2. **把认证会话当成纯 read**：建立/关闭运行会话有副作用，按 `write` 治理，但明确 Teamcenter 业务数据写入为零。
3. **一个 Capability 包办认证、读取和投射**：已拆成可独立授权、失败、重试和审计的原子能力。
4. **按名称合并零件**：已改为 occurrence 实例身份；同 ItemRevision 多次出现保留多实例。
5. **缓存命中后又全量校验**：已取消默认后台全量重读，改为显式刷新和可选轻探针。
6. **用缓存树重建 VisMockup CPS**：已禁止；在线来源必须由 VisMockup 打开同一 Teamcenter 来源并映射。
7. **结构读取顺带加载全部几何**：已分离 geometry reference 与按需 fetch。
8. **把客户端采集时间当产品版本时间**：已分离配置日期、服务器时间、采集区间和首次观察时间。
9. **单位误读**：matrix/bbox 均携带原始值、单位、坐标和约定版本，未确认前不静默换算。
10. **旧 runtime key 跨会话复用**：已规定进程/文档变化立即失效并重新映射。
11. **只靠 denylist 保证只读**：已改为封闭 allowlist、强类型接口和 recording transport 断言。
12. **HTTP 口令安全被忽略**：已明确不加密警告和生产例外门槛。
13. **直读/PLMXML 数量不同仍宣称完整**：已设差异归因验收门槛。
14. **只加前端按钮不补治理链**：已要求 Catalog、Descriptor、Provider、API/IPC、消费者和证据成套变更。

### 17.2 仍然开放的风险

- VisMockup 是否提供足够稳定的在线来源打开和 occurrence identity，仍需原生探测；若只有歧义映射，相关操作必须降级为人工选择，不能猜测。
- Teamcenter 服务器定制属性与权限可能使部分字段为空；空值不是读取失败，需按 projection coverage 报告。
- 当前 HTTP Teamcenter 端点使口令在链路上缺少 TLS；本地不落盘不能消除网络风险。
- 超大 `expandPSAllLevels` 的服务端调用本身可能不可取消；异步壳只能避免阻塞 AI00，不能虚称底层可抢占。
- AI00 数据库和本地 SQLite 之间没有分布式事务；以 immutable chunk + manifest publish + 幂等重试恢复。

### 17.3 提交前检查

- [x] Atomicity：设计已拆分为单一业务效果。
- [ ] Identity：真实 Capability GID、Descriptor revision 和 Provider artifact hash 待实施。
- [x] Security/data：权限、只读允许列表、敏感数据和 HTTP 风险已声明。
- [x] Relationships：环境、快照、文档、来源、映射和 AH 边界已声明。
- [ ] Verification：合同、Provider、权限、边界、迁移、构建和端到端测试待实施。
- [ ] Evidence：当前 revision、Snapshot、test run 和 result hash 待实施后生成。
- [x] Authority：设计同意不等于治理人签署或运行时通过。

## 18. 实施顺序

用户复核本规格后再编写逐文件实施计划。建议顺序：

1. Teamcenter local-only session 与登录 UI，先完成凭据泄漏和只读边界测试。
2. 小装配正式 SOA 搜索/直读及标准 occurrence schema。
3. 不可变 snapshot/chunk 和 SQLite 热缓存。
4. W10 完整性差异归因及性能基线。
5. VisMockup 在线来源投射与 runtime mapping。
6. 接入现有选择、显隐、文档切换和 AH 引用。
7. Catalog/Descriptor/Provider/consumer 生成、治理检查及 test 运行验收。
