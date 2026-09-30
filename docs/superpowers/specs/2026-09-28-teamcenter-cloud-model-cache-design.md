# Teamcenter 模型文件树云端缓存与工作台应用设计

日期：2026-09-28。状态：待用户审阅的设计草稿；尚未实现、提交或发布。

## 1. 需求与成功标准

将数模仿真的 Teamcenter 模型文件树缓存扩展为云端持久化缓存，提供工作台独立 App“模型缓存”，有独立图标、页签和界面。首版由超管手动触发，预留项目经理授权和自动定时触发的接入位置，本期不启用这两种触发方式。

- 左侧为“项目 → 项目阶段 → 缓存批次”树；阶段内按批次创建时间倒序，新的在上面。
- 每次触发产生独立批次，展示模型名称、版本、配置规则、缓存开始/完成日期、状态及进度；历史批次保留。
- 点击批次后，右侧完整展示本次 TC 返回的业务字段和值，支持字段选择、搜索和筛选；不能仅展示固定的摘要字段。
- TC 查询、云端上传均可断点续作；刷新页面、关闭 App 不应丢失已提交进度。
- 数模仿真读取同一云端缓存，不再依赖某台电脑的缓存才可浏览。
- 复用 test 分支的来源选择器、Connector、子节点分页、属性读取、缓存与发布校验机制。
- 界面优先复用已有 CSS 模板与表格/筛选组件；缓存执行服务支持后续不同触发来源接入。
- 必须满足 Capability 治理要求：逐项核对并优先复用已登记能力，确需新增的业务能力全部归 simulation 数模域；新增页面不新增业务域。

首版只缓存结构与属性、几何引用，不上传或批量下载 JT 几何文件。

## 2. 核对的实际基线

前端 `test`：`048073dbffc2b4724b5f668877edeea50d80f703`。
后端 `test`：`8d3c459a359a92ab1d807aa73b626745452c4889`。

当前主目录为 deploy 分支，不能作为本改动的实现基线。test 的现有检出也包含未提交改动；本草稿以 `git show test:<path>` 核对的提交内容为准，不覆盖已有工作。

已读的权威代码与合同：

| 已有机制 | 位置 / 绑定 | 本次用途 |
| --- | --- | --- |
| TC 来源与分页树 | 前端 `packages/sim-plugin/web/cad_sim/teamcenter_online_source.js` | 复用 selector、occurrence_path、generation 和分页校验 |
| 模型树本地缓存 | 前端 `packages/sim-plugin/electron/tree_cache*.js`、`tree_projection_cache.js` | 保留本地加速层，云端成为共享数据来源 |
| TC 子节点 SQLite 缓存 | 后端仓库 `local-runtime/src/Ai00.Connector.Adapters.VisMockup/TeamcenterChildren.cs` | 复用 children.read；同一来源、路径和 TC 用户优先命中本机缓存 |
| TC 属性白名单与缓存 | `TeamcenterNodeProperties.cs`、`teamcenter.node_properties.read@1.json` | 复用读取和身份隔离；新缓存需完整保留本次读取的业务字段，不能只沿用旧页面的固定字段展示 |
| 云端观察持久化 | `simulation_backend/capabilities/product_structures.py`、`data/product_structure_observation_repository.py` | 复用分块、内容哈希、幂等和完整发布校验的实现模式 |
| 现有结构合同 | `docs/contracts/teamcenter.product_structure.children.read@1.json` | 每页不超过 500、路径深度不超过 128 |
| 现有观察表 | migration `0026_teamcenter_online_structure_observations.sql` | 核对所有者、workspace/source 外键及不可变语义 |
| 工作台 App 面板 | 前端 `web/workbench/workbench.js` | 新增 App 注册；test 的面板需要显式接入 |
| 树列表与布局模板 | 前端 `web/components/tree_list_shell.{js,css}`、`list_shell.css` | 项目树、只读列表、列选择与既有主题 |
| 表格与筛选模板 | 前端 `web/components/grid_editor.{js,css}`、`view_manager.{js,css}` | 只读单元格、列宽、筛选条件、排序和 AND/OR 条件界面 |
| Provider 治理 | `simulation_backend/capabilities/provider.py`、对应 Capability 文档 | 新接口登记消费者、事务、权限和证据 |

已有全量 observe 在一次查询结束后才产生完整结果，不具备扫描途中云端检查点。现有观察表绑定个人 workspace 和来源，读取限制 source.owner_gid；不能直接将它当成项目共享缓存，也不能把一份全量 observe 的上传续传称为扫描断点续作。

## 3. 方案选择

推荐：在 simulation 域增加项目缓存批次与任务，复用 TC children/属性读取和现有云端分块校验模式。缓存任务独立于仿真环境，环境可引用完整批次。

其他方案：

1. 仅把 Electron 缓存整体上传：改动较少，但依赖页面存活，不能保证扫描检查点，也无法可靠管理历史批次。
2. 云端重新实现 TC 客户端：需要重新处理凭据、网络和定制字段，重复 test 的 Connector 能力，首版不采用。

“云端缓存”表示数据和任务进度存云端；TC 访问继续由已登录的 Connector 执行。Connector 离线或退出 TC 时，任务保留进度并等待恢复，不宣称此时还能继续查询。

## 4. 应用与交互

App 名称暂定“模型缓存”，使用独立缓存图标；位于工作台 App 面板，可打开独立页签。页面优先复用 TreeListShell、GridEditor 的只读模式和 ViewManager；CSS 复用 list_shell.css、tree_list_shell.css、grid_editor.css、view_manager.css、app-ui.css 的布局、表头、筛选面板和主题变量。只为批次状态和完整字段详情补充少量页面样式。

左侧示例：

```text
项目 A
  阶段 1
    模型甲 / 版本 09 · 09-28 16:20 · 进行中
    模型甲 / 版本 08 · 09-27 10:30 · 完成
  阶段 2
    模型乙 / 版本 02 · 09-26 14:00 · 完成
项目 B
  未分期
    ...
```

右侧顶部显示项目、阶段、根模型版本、修订规则、配置日期、缓存开始/完成时间、TC 数据捕获时间范围、触发者、任务状态，以及已提交节点数/待处理工作项数。总节点数未知时显示已处理计数，不伪造百分比。

右侧以节点表格为主，默认突出层级、名称、Item ID、版本、对象类型、所有者、所属组、重量、单位重量、扭矩、扭矩重要度、实例 UID、数据捕获时间、读取状态；全部返回字段动态进入字段目录，可选作列。默认列只是初始视图，不能作为缓存和显示的字段上限。

点击节点在同一右侧打开“全部字段”详情，使用“中文标签（有映射时）/TC 原始字段名、值、类型”的字段表逐项展示。结构、属性、occurrence_path、变换矩阵、bbox、几何引用和业务来源信息均可查看；未知字段保留原字段名，不丢弃。对象/数组按字段路径展开，并提供完整 JSON 查看/复制；长字段名和值可换行、展开全文，不仅靠省略号或鼠标提示查看。

必须区分字段不存在、null、空字符串、0、false、空数组、空对象与读取失败。重量/扭矩保留原始值，不推断单位；字段中文别名、显示格式和列隐藏不修改原值。不同来源有相同字段名时保留字段路径与来源，禁止同名覆盖。

搜索覆盖字段名、原始字段路径和字段值，可选择全部字段或指定字段。筛选支持名称/编号/版本/类型/所有者/组/缓存状态/时间及动态返回字段，使用含有、等于、不等于、为空/非空等条件；真实数值和日期类型支持比较及区间，原始字符串不擅自转换成数值。条件支持 AND/OR、清除和结果数显示。

节点搜索和筛选覆盖整个选中批次，在云端执行后分页返回，不只过滤已加载的一页；查询切换重置游标并采用稳定排序。字段详情内搜索限定当前节点，界面明确区分两个范围。隐藏列也参与“全部字段”搜索；匹配位于嵌套或隐藏字段时显示匹配字段路径。返回值按纯文本呈现。

超管点击“新建缓存”，选择项目、阶段、TC 模型/版本、修订规则与配置日期，然后触发。TC 搜索和登录复用数模仿真的既有流程。支持暂停、继续和新建刷新批次；关闭页面不等于取消任务。

进行中批次可预览已提交节点，明确标记“未完成”；正常缓存消费者只能选择已完成批次。新版缓存期间仍可读取旧的完整批次。

默认阶段处理：优先绑定已有项目阶段；若该项目没有阶段来源，则允许超管填写阶段名称，未填归入“未分期”。阶段不是仿真 review_type，也不是项目 status；不能用这两种字段冒充项目阶段。阶段来源是本草稿需确认的业务默认。

## 5. 数据、身份与时间

所有缓存记录归 simulation 域，使用其领域连接与迁移，不直接查询 craft 项目表。项目存在性和可读范围通过项目域已登记合同确认；若阶段尚无合同，新增显式阶段字段与后续绑定接口，而非跨域 SQL。

建议增加批次、工作项、节点和分页回执四类持久化记录：

- 批次：租户/项目/阶段引用及名称快照、selector、source hash、TC principal 的受控身份引用、投影版本、根模型版本、触发来源、触发者、设备绑定、状态、检查点版本、各时间字段与最终 manifest hash。
- 工作项：批次、工作类型（结构/属性）、occurrence_path、generation、cursor、状态、尝试次数、租约与错误码。
- 节点：批次、稳定 occurrence 身份、父身份、顺序、版本、结构字段、完整原始业务字段及类型、属性和各自 captured_at、字段读取状态。标准化展示字段与原始业务字段分别保存，不能在 productNode 或 Provider 字段映射时丢失本次 TC 读取返回的字段。
- 回执：批次/工作项/generation/cursor、页哈希及已提交结果。唯一键处理上传成功但响应丢失的重试。

键与查询同时限制租户、项目、来源选择器、配置、投影和批次。不同实例不按名称或 ItemRevision 去重。新批次与旧批次不合并。

selector 复用 endpoint_id、object_uid、item_revision_uid、bom_view_uid、revision_rule、configuration_date。根版本和配置绑定后不可在续作时偷偷切成 Latest。

批次创建时间负责排序，completed_at 表示缓存完成时间，captured_at 表示实际 TC 读取时间；本机热缓存命中不得把旧 captured_at 改成当前时间。阶段或项目改名不改写历史快照名称。

字段目录从同批次所有已提交结构/属性页的字段并集生成，而非仅从第一页推断；保存原字段路径、类型和展示标签。后续页面出现新字段时自动补入目录。筛选字段必须从该目录解析，采用参数化查询，限制查询长度、条件数和结果页大小；不接受调用方提供 SQL 或任意 JSON 表达式。复用现有索引列处理常用字段，动态字段的查询由领域仓储负责；不得一次将整份大树送进浏览器搜索。

“全部字段”指本次 TC 模型业务读取实际返回的全部字段和值，不是任意查询 TC 系统所有对象属性。现有 node_properties.read@1 是固定投影；若 worker 已读到的业务字段被固定映射裁剪，新缓存合同需增加有类型、有大小界限的原始字段集合，并配套新合同版本、Connector 校验和云端存储。保留原 @1 消费者行为，不能仅修改前端就宣称完整展示。

## 6. 持久化任务与断点续作

云端保存队列并调度短工作项，继续使用受控 Connector 请求/结果通道。执行者为领域后台 worker；网页仅创建任务、读取状态和发出显式暂停/继续命令。

状态包括 queued、running、paused、waiting_connector、waiting_auth、needs_refresh、failed、completed。工作租约到期可重新领取；旧租约回传不得修改已被新执行者接管的状态。

每个结构工作项执行：

1. 从云端领取精确来源、parent_path、cursor、generation 的工作项。
2. 调用现有 children.read，复用本地 SQLite 热缓存和 TC warm worker；逐页获取，禁止为缓存任务打开或操作 VisMockup。
3. 校验响应的来源、路径、generation、cursor、节点身份与字段边界。
4. 在一个领域事务中写入页回执、节点、子节点工作项，并推进检查点。只有事务成功后才完成本工作项。
5. 对 has_children=true 或未知的子节点创建展开工作；未知需实际读取后才能确认为叶子。
6. 对已发现节点创建属性读取工作，复用现有读取机制与缓存，并完整保存当前投影返回的原始业务字段；结构与属性完成状态分别记录。

幂等键来自批次、工作项及精确页身份。同一身份同一哈希重复提交返回既有结果；同一身份不同哈希拒绝，不覆盖。

恢复时：已提交页不重传、已完成节点不重扫，只继续未提交结构页和未完成属性。需要重新登录时暂停依赖任务，认证恢复后按原批次继续；换 TC principal 不允许继续合并原批次。

generation 过期、历史 parent_path 消失或 revision 不一致时停止相关批次，显示 needs_refresh。用户可保留旧批次并新建刷新批次；禁止自动替换祖先或把新版本拼进旧快照。缓存未命中导致第一页面代次变化时也必须做同样检查。

“强制刷新”创建新批次，并使用受控的新鲜读取策略。现有 children 支持 refresh，但属性 read 合同没有明确强制刷新输入；如产品要求重新抓取全部属性，应新增兼容版本合同与实现，不能只刷新结构却宣称属性也已更新。

所有必要结构和属性工作结束、父子关系/节点计数/页连续性/哈希校验通过后，原子发布 completed。属性单项失败保留错误和重试入口；不可作为全部成功发布。超过既有节点/深度限制明确失败，不截断成“完整”。

逐项采集跨多个 TC 请求，不能声称它是 TC 服务端同一事务的全局快照；页面展示捕获时间范围并标记 pinned configuration 的观测语义。

## 7. 数模仿真接入与兼容

TC 模型加入环境时，按精确 selector 与授权范围查找匹配的完整云端批次，可指定历史批次。命中后使用云端结构页和已缓存属性，本地 SQLite 作为可丢弃加速层。

无完整匹配缓存时保留 test 现有的 TC 按需读取能力，不把普通浏览变成完整缓存构建。完整云端构建仍暂由超管触发。

缓存节点的 TC 身份与 VisMockup 运行时控制身份保持分离；历史缓存仅用于读取，不凭缓存数据自动建立原生控制映射。切换云端批次不得混用旧环境的 live document 控制状态。

现有个人观察快照保持原合同。共享批次使用新增关联与权限，复用已有校验代码，不创建虚假的个人 workspace 绕过外键，也不放宽旧观察接口的所有者限制。

## 8. Capability 与权限边界

变更分类：新增项目模型缓存能力；兼容接入现有数模仿真；如果改变既有 I/O 或缓存执行语义，建立新合同版本，不静默改变 @1。

Owner：simulation。跨域协作者：project（项目身份/可见范围）、platform（认证/Gateway/工作台外壳），保持各自数据所有权。

### 能力复用与新增边界

先按业务效果、资源范围、合同版本、权限、执行位置和消费者逐项检查复用，不能因页面不同就另建同义能力。已有能力满足需求且消费者合法时，通过 Gateway/SDK 调用原能力；同域内部函数和仓储也优先复用。内部辅助函数、页面格式化和每一步实现细节不自动注册成 Capability。

基于 test 提交的静态 Catalog 核对结果：

| 现有 Capability | 已登记 version GID | 本次复用结论 |
| --- | --- | --- |
| simulation.teamcenter.product.search.request@1 | cv2_ccadbdc99fce9d5435cc7198 | 复用 TC 模型搜索，不新建缓存专用搜索能力 |
| simulation.teamcenter.revision_rule.search.request@1 | cv2_2e923180fa9472155d406af0 | 复用修订规则查询 |
| simulation.teamcenter.product_structure.children.read.request@1 | cv2_53f6e195c5bd8407768cc80d | 复用结构读取、来源/路径/generation 合同及本地缓存；后台消费者接入必须补治理绑定 |
| simulation.teamcenter.node_properties.read.request@1 | cv2_c967f8e668c81ebf49434542 | 原字段需求直接复用；完整原始字段/强刷若超出现合同，评估版本演进，避免建立同义能力 |
| simulation.product_structure.observation.begin@1 | cv2_4faee1f7e4ccafb0dd0dc407 | 个人环境观察场景复用；项目共享任务不能假冒个人 workspace |
| simulation.product_structure.observation.page.append@1 | cv2_7641cf066421fb004d55aff2 | 复用幂等分块及校验代码；只有原资源/所有者语义吻合时才直接复用该能力 |
| simulation.product_structure.observation.publish@1 | cv2_9c9b9989687c91cba8d9e0fe | 复用完整性验证及发布不变量；不放宽原权限换取共享 |
| simulation.product_structure.snapshot.page.get@1 | cv2_59def8d66fe68b5abe3f9217 | 复用已发布个人观察读取；项目共享批次需匹配明确的资源授权合同 |

以上是静态 Catalog 中实际存在的身份，不是运行时调用许可或发布批准。新增候选与能力版本调整在实施前还要查可信 Registry Snapshot、依赖图和消费者，记录重复/冲突结果。

只为现有能力未覆盖的独立业务效果新增：项目缓存批次构建与管理、受授权的共享批次查询、持久化续作等。新增 ID 使用 simulation.*，Provider、业务规则、领域仓储和 migration 位于 simulation 域；是否分为独立暂停/恢复/提交能力取决于独立授权、失败、重试和审计需求，实施计划不得机械地将每个函数变成能力。

改变既有副作用、身份、执行位置或消费者预期时评估兼容性；合同不兼容则演进版本，兼容改动仍更新 Descriptor revision 与 Provider artifact 绑定。不能通过新增壳能力绕开既有权限，不能把缓存写入包装成无副作用 BFF。

### 治理登记与验收约束

每个新增或变更能力必须完整声明并绑定：业务效果与验收标准、业务不变量及规则 ID、enforcement/error/test 引用（确实无不变量时写明理由）、capability_id/major version/真实持久化 GID、领域 Owner、生命周期、关闭的输入/输出合同、稳定错误、资源选择器、服务端权限、事务参与者、幂等/并发、重试边界、审计/证据、数据敏感范围与预算。

同步核对 Catalog/Registry、Descriptor、Provider、Gateway/API、Connector operation_id@major_version 与 contract_hash、App/worker 消费者、依赖、领域表和迁移、文档与测试映射。复用现有能力的消费者引用也要登记，不能只登记新增能力。服务实现通过现有 simulation Provider 注册入口接入，不新增平行 Registry 或绕过 Gateway 的写路由。

关键业务不变量至少包括：项目/租户授权不越界，源版本与配置在续作期间不漂移，检查点与页写入原子提交，重复提交相同内容幂等/不同内容拒绝，过期租约不得覆盖新执行，未完整验证不得发布，新批次不覆盖历史批次。每条约束必须绑定实际 enforcement、稳定错误码和可执行测试。

worker 只执行精确登记和授权的资源范围；Connector 只接受签名计划及其支持的版本/合同哈希。验证旧、新合同兼容，拒绝未知版本、重复 operation ID、哈希漂移及越权资源，覆盖重启和重新连接。

实施验证覆盖合同边界、Provider 实际存储与事务、权限拒绝、幂等冲突、断点恢复、领域/消费者/迁移绑定、前端调用和真实 Connector 读回。测试与运行证据绑定当前能力版本、business_definition_hash、Snapshot、代码 revision 和 test run；旧测试报告或离线模拟不算当前运行验证。

机器检查、可信超管对精确业务定义哈希的批准、受控运行验证分别记录 machine_passed、human_approved、runtime_verified。AI 仅 advisory，不代替批准、签署或 Release Gate。设计确认不等于治理批准，test 已登记不等于允许生产发布。

### 已发现的治理缺口

- 静态 Catalog 中上列能力均为 experimental；TC request 能力 exposure.web=true、worker=false，个人观察能力亦 worker=false。后台复用需要显式消费者/执行合同及新 Release 绑定，不能直接从后台以 web 身份调用。
- `docs/capabilities/catalog.v2.json` 的 release_id 为 rel_78e6844b2238e075052eea7810e820d5，catalog_hash 为 sha256:78e6844b2238e075052eea7810e820d522978c43929ad332d7cb3a89af5c2663；`docs/governance/capability-catalog-release.json` 的 release_id 为 rel_1f857e1e265864513910f1469df58a71，catalog_hash 为 sha256:1f857e1e265864513910f1469df58a71a0f8b7966544e13f2cc526d6a11d2799。两份仓库投影不一致，需读取实际可信 Registry/固定 Release 再确定实施和发布绑定，不能任选一份当权威。
- 已有个人观察的资源/Owner 范围与项目共享不同；完整字段和属性强刷需求也可能超出现合同。记录为复用边界，不静默扩大旧能力语义。
- 当前可信运行 Snapshot、精确哈希批准与新增测试证据均为 unverified；本草稿只完成静态复用核对，不报告治理通过。

新增能力候选按独立效果拆分：创建批次、读取批次列表/详情/节点页、暂停任务、恢复任务，以及 worker 的领取和幂等页提交。候选尚未分配正式 Capability ID/GID，不把草稿标成已登记能力。

业务效果：形成可追溯、可恢复、可按项目共享的指定 TC 模型结构与属性缓存。

服务器使用可信认证身份强制 super_admin 才可触发/暂停/恢复完整缓存。按钮隐藏不能替代后端权限。已发布缓存读取按租户和项目访问权限；权限映射尚未具备时默认限制超管，不能默认全员可读。

TC 密码、cookie、token、FMS ticket 不进入云端缓存、任务或审计正文。Connector 仅用本地当前登录身份访问 TC。数据共享按明确项目范围，不把采集账号可读范围直接当作其他用户的授权。

业务写接口通过 Gateway 与 simulation Provider；worker 消费者需要显式登记与授权。现有 observation 能力文档不开放 worker，不能直接假定可复用其消费者授权。分页读接口设置 page_size、max_nodes、max_depth 边界。

审计记录批次、项目、来源哈希、触发者、动作、租约/检查点、结果与稳定错误码，不记录凭据或完整敏感属性。

### 后续项目经理与定时缓存的预留

缓存创建入口只做授权和输入校验，统一调用 simulation 域的缓存任务服务；执行、断点、分页存储和发布逻辑不按超管/项目经理/定时任务复制。

首版授权策略只放行可信 super_admin。策略预留“当前用户是否为目标项目有效经理、是否有该项目缓存触发权限”的判断位置；后续开放时接入项目域可信成员与授权合同，并在触发/恢复时检查。项目经理只能操作获授权项目，不能将项目经理权限升级为系统超管权限。

任务上下文预留 trigger_kind（manual/scheduled）、trigger_actor_gid 和可选 schedule_ref/scheduled_for；首版仅接受 manual，后续 scheduled 由可信后台调度器写入，不能由页面自报定时来源绕过授权。每次定时执行仍创建独立历史批次，并复用相同来源绑定、审计、恢复和完整发布流程。

后续计划配置可携带项目/阶段、selector、执行时间规则、时区、启停状态和执行授权；首版不建调度管理页面、不启动 cron、不引入调度依赖、不自动新增计划。未来优先接入平台已有调度设施，同一计划时刻幂等且同一来源运行中的任务不重叠。计划权限失效或 Connector 不可用时按统一任务状态等待/拒绝，不换用其他 TC 登录身份。

## 9. 验证与验收

实现后的必要验证：

- 普通用户拒绝触发/续作；租户、项目、来源和采集身份隔离；恢复前重新验证权限。
- 上传前断网、上传提交后响应丢失、worker/Connector/服务重启、关页面与重复点击，均从最后云端提交点恢复。
- 源 generation 漂移、版本变化、历史路径不存在时不混合批次，并保留旧完整缓存。
- 重复页同哈希幂等、不同哈希冲突；租约竞争拒绝旧回传；完成节点不重扫。
- 大树按页扫描、表格按页读取，未知子节点正确展开，达到上限明确失败。
- 本机热缓存保留原始捕获日期；属性强刷合同与普通读合同分别验证。
- 任务发布完整性和旧批次可读性；数模仿真云端命中、无缓存回退和原生控制身份隔离。
- 工作台 App 图标/入口、项目阶段分组、批次倒序、详情列与状态的 UI 验证。
- 完整字段验证包含未知字段、后续页才出现的字段、长字段名/值、嵌套对象/数组、0/false/null/空值、同名不同路径；保存与详情展示不丢字段、不改类型、不覆盖来源。
- 全批次搜索/筛选验证包含未加载页、隐藏列和嵌套字段；字段详情搜索明确只针对当前节点；组合条件、结果数和分页一致。
- CSS/组件复用验证包含明暗主题、列宽、横向滚动、全文查看、只读行为和既有筛选面板。
- 预留接口验证：首版仍拒绝项目经理触发和调用方伪造 scheduled 来源；不同触发方式后续接入同一任务服务，不改变批次/检查点语义。
- migration、合同/Provider/consumer/领域边界检查，以及 test 分支相关现有测试回归。
- 按复用清单逐项核对 Registry/Descriptor/Provider/消费者真实绑定；新增能力全部属于 simulation，权限/事务/幂等/业务不变量具有执行与测试证据；Catalog Release 不一致必须在发布绑定前解决。

当前只进行了代码/合同/迁移/调用链检查，未执行实现测试或 TC 实时读写。

Governance：machine_passed=unverified；human_approved=unverified；runtime_verified=unverified；AI 建议 advisory=true。

## 10. 需在审阅时确认的默认

1. 项目阶段采用既有阶段优先、缺失时手动填写的方式。
2. 已发布批次按项目权限共享；触发、暂停、恢复暂仅超管。
3. TC 仍由现有 Connector 查询；云端保存数据并调度任务，Connector 离线时等待恢复。

用户于本轮追加的明确约束已纳入：右侧查看全部 TC 返回字段和值，支持筛选/搜索，复用现有 CSS 模板，预留后续项目经理和定时缓存能力。本轮仍为设计修订，不表示业务代码已实现。

用户进一步明确：必须满足 capabilities 治理，能复用现有能力的直接复用，新增能力仍放数模域。该约束已写入能力复用清单、新增边界和治理验收要求。

设计确认后再编写实施计划；实施基于 test 的独立隔离分支，并保留现有检出中的未提交改动。

## 11. 实施补充（2026-09-28）

用户已授权完成设计后直接执行。实施结果与验证证据见实施计划。本节 supersedes 上述“本轮仍为设计修订”的阶段说明。

已有节点属性合同返回固定展示投影，会合并 BOMLine 名称和 ItemRevision 名称、把空字符串变为 null。云端缓存新增数模域原生读取合同 `teamcenter.model_cache.read@1`，复用已有 children 遍历和 TC worker，只读取既有业务属性 allowlist，同时返回原始字段的对象 UID、属性名、JSON 值和读取状态。既有 children/property @1 合同保持兼容。页面表格与完整值详情展示结构字段、原始属性字段及来源元数据。

批次固定 Connector device 与 TC principal hash；重登录为其他 TC 账号或换设备须新建批次。任务用 operation_id/attempt 拒绝过期回传，终页检查 child_count、连续 cursor、路径及重复节点，发布前流式校验唯一根、父子路径、属性齐备及直接子节点数量。列表分页覆盖历史批次，查询使用实际游标和字节预算，完整单值不截断。项目创建通过项目域已有 projects_get 验证真实租户与权威名称。

新能力保持 experimental，机器验证、正式人审与真实 TC 联调分别记录；本地 test App 可通过现有未发布测试 Catalog 运行，未代表生产审批。


### User-confirmed creation form corrections
Phase is chosen independently from a fixed dropdown with the BOP data-stage labels; no linkage to BOP records or workflow is introduced. Batch names are cloud-allocated v1, v2, ... scoped to tenant/project/phase, with a transactional version counter (0031) and idempotent replays. Project selection uses the authoritative project_code and reuses Simulation projectSearchInput for <project>-ENG00001 / 00, followed by exact result filtering. Component ID/name and manual batch-name fields are removed.
