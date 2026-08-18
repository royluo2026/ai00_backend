# BOP 大版本内存安全与渐进加载设计

## 1. 背景

服务器上一个历史版本在打开工艺流程图大数据版本时出现容器 `OOMKilled`，退出码为 137。用户补充的实际现象是：

- BOP 版本包含数千个工艺、工位、操作和零件节点；
- 图片很少，不是主要载荷；
- 第一次打开通常能够完成；
- 完成首轮加载后，即使只执行一次版本切换或刷新，也可能出现 504；
- 容器随后可能因为整体内存超过 cgroup limit 被操作系统终止。

`OOMKilled/137` 只能证明容器总内存超过限制，不能单独证明存在持续性内存泄漏。本设计同时处理单次峰值、重载叠加、无界读取、资源配置和诊断缺失，并通过压测区分峰值与泄漏。

## 2. 当前代码证据

当前流程图通过 `GET /api/bop/versions/{version_gid}/entries` 一次读取整个版本：

1. Craft 路由执行 `_ENTRY_LIST_SQL`，对 entries、versions、entry links、line、station、process、steps、operator 和 PBOM 执行多表关联；
2. 查询没有分页和字段投影，使用 `fetchall()` 物化整个结果集；
3. SQL 为每个节点拼装 `entity_data`，其中可能包含 `meta`、`ext`、`params`、零件数据和操作数据；
4. Python 将 JSON 字段再次解析为字典和列表，再由 FastAPI 整体序列化；
5. 前端将全量结果保存到 `_rows`，并建立 `_rowByGid`、`_childMap`、`_depthByGid` 和 `_statsMap`；
6. `_reload()` 在新数据完全返回前保留旧数据、旧索引和旧画布 DOM；
7. 版本切换与刷新没有请求取消、单飞互斥或过期响应保护；
8. 现有 `craft.bop.execution_structure.get@1` 也会先全量读取 entries 和 links，不能仅通过替换调用入口解决问题；
9. Gunicorn 配置按 `CPU * 2 + 1` 自动设置 workers，而容器镜像使用单 Uvicorn 进程，部署入口不一致，无法形成可审计的内存预算；
10. `/health` 和 `/ready` 不提供进程 RSS、容器内存、在途大请求或 Capability 资源消耗证据。

一次大请求可能同时存在数据库驱动结果、Python 行字典、解析后的嵌套对象、响应序列化缓冲和框架响应对象。刷新又可能与旧数据或旧请求叠加，因此 504 和 OOM 可以在没有传统泄漏的情况下发生。

## 3. 目标

1. 10,000 节点 BOP 可以安全打开、切换和刷新，不出现 504 或 OOMKilled；
2. 任一同步请求都有确定的输入、输出、行数、并发和内存边界；
3. BOP 页面不再依赖全版本富对象一次返回；
4. 保持 11 个领域独立开发、独立 Provider、独立数据库账号和表所有权；
5. 所有新读取能力进入 Capability Catalog，由相同 Gateway 提供给 Web、插件和 Agent；
6. 资源约束成为 Capability 契约和正式发布门禁的一部分；
7. 通过可观测性区分查询慢、序列化峰值、前端保留、并发叠加和持续泄漏。

## 4. 非目标

- 不合并领域数据库或领域连接模块；
- 不允许 Base、前端、插件或其他领域直接读取 Craft 表；
- 不把画布布局、DOM 组件或页面名称定义成领域 Capability；
- 不改变 `craft.bop.execution_structure.get@1` 的既有业务语义；
- 不以扩大容器内存作为唯一修复；
- 不在没有压测证据时固定生产容器的最终 MiB 数值；
- 不在本次工作中重构整个 Craft 数据模型。

## 5. 原则与领域边界

资源治理采用“平台统一协议、领域独立实现”：

- Craft 拥有 BOP 查询语义、范围 SQL、索引设计、投影模型和业务错误；
- Capability Descriptor 声明资源预算，Catalog 冻结并发布该预算；
- Gateway 统一执行输入大小、并发、内存水位、超时和输出上限；
- Web、插件、Agent 和 API 只能通过 Gateway 调用公开 Capability；
- 每个领域独立配置连接池，但部署校验所有领域连接池的容器总预算；
- 其他领域通过稳定引用消费 Craft 结果，不能跨域 JOIN 或导入 Craft Repository。

## 6. Capability 设计

### 6.1 保留 `craft.bop.version.get@1`

页面首先读取版本状态、项目、生命周期和整数 `revision`。后续读取必须携带该 revision，Craft Provider 在查询开始和返回前验证 revision 未变化。

### 6.2 新增 `craft.bop.structure.outline.get@1`

单一业务效果：读取一个 BOP revision 的可导航结构纲要。

输入：

- `version_gid`：BOP 版本雪花 GID；
- `revision`：由 `craft.bop.version.get@1` 返回的版本 revision；
- `cursor`：可选的不透明游标；
- `page_size`：1 至 100，默认 50。

输出：

- `version_gid`、`revision`；
- 根节点摘要；
- 当前页线体摘要：`gid`、`parent_gid`、`node_type`、`title`、`sort_order`；
- 每条线体的工位、岗位、工序、操作、零件和资源计数；
- `next_cursor` 和总线体数。

该能力不得返回完整 `meta`、图片、操作参数、零件明细或关联实体正文。

### 6.3 新增 `craft.bop.work_package.get@2`

单一业务效果：读取指定线体或工位在一个确定 revision 下的工作包。

输入：

- `version_gid`、`revision`；
- `scope_kind`：`line` 或 `station`；
- `scope_gid`：作用域节点雪花 GID；
- `cursor`：可选的不透明游标；
- `page_size`：1 至 200，默认 100。

输出：

- 作用域与 revision；
- 当前页轻量节点：GID、父 GID、类型、名称、顺序、VPPS 和分类引用；
- 当前页依赖关系；
- 零件、工具、工装、设备、知识和规则的稳定引用；
- `next_cursor` 和作用域总数。

Provider 必须直接执行作用域查询，禁止调用现有全量 `load_bop_aggregate()` 后在内存过滤。游标采用稳定的 `sort_order + gid` 键集分页，不使用随数据规模增长的大 OFFSET。

`@1` 保留给已有消费者，`@2` 作为渐进读取版本并显式迁移消费者。

### 6.4 新增 `craft.bop.entry.detail.get@1`

单一业务效果：读取一个工艺节点的完整详情。

输入为 `version_gid`、`revision` 和 `entry_gid`。输出可以包含该节点的完整业务字段、参数、扩展数据、关联明细和图片引用。图片访问地址只在详情读取时解析，不进入 outline 或工作包列表。

### 6.5 保留完整执行结构能力

`craft.bop.execution_structure.get@1` 继续表示“已发布 BOP 的确定性官方执行结构”，服务于仿真、插件、Agent 和下游系统。它不承担草稿流程图分页职责。后续可以优化其内部生成过程；若正式结构超过同步输出安全线，应新增异步 Operation + Artifact 能力，而不是破坏 `@1` 契约。

## 7. 端到端加载流程

### 7.1 版本选择

1. 页面递增 `load_generation`；
2. 中止上一 generation 的所有请求；
3. 清除旧版本重数据和画布对象；
4. 调用 `craft.bop.version.get@1`；
5. 记录 `version_gid + revision` 作为本轮读取键；
6. 加载过程中禁用重复刷新和重复选择。

每个响应在更新 UI 前必须同时匹配当前 generation、version GID 和 revision。过期响应只能被丢弃。

### 7.2 首屏

页面调用 `craft.bop.structure.outline.get@1`，只渲染根节点、线体框和计数。首屏不等待数千个节点，不创建完整画布 DOM。

### 7.3 线体和工位

默认加载第一条可见或用户选中的线体。`craft.bop.work_package.get@2` 分页返回局部工作包；页面优先渲染当前页，在浏览器空闲且内存水位正常时预取下一页。

同一 `version + revision + scope` 只允许一个在途请求。用户切换线体时取消非必要预取。页面只缓存最近使用的 2 至 3 条线体，并同时设置节点总数和估算字节上限。

### 7.4 节点详情

选中节点后调用 `craft.bop.entry.detail.get@1`。关闭详情或淘汰缓存时释放完整字段和图片 URL，不把富数据合并进全局轻量节点集合。

### 7.5 刷新

刷新保留小型 outline 和用户选择状态，立即销毁：

- 线体分页缓存；
- 节点详情缓存；
- 旧 `_rows` 和派生 Map；
- 画布 DOM、拖拽对象、RAF 和观察器；
- 非当前 generation 的请求。

随后重新读取版本 revision、outline 和当前线体。失败时显示可重试错误并保留 outline，不恢复已经释放的旧富数据。

## 8. Craft Provider 查询设计

### 8.1 Outline 查询

使用按版本和节点类型过滤的聚合查询，只选择纲要字段。计数可以通过按线体祖先映射的预聚合查询获得。必须具备支持 `version_gid`、`parent_gid`、`node_type`、`sort_order` 和 `gid` 的索引，并通过 `EXPLAIN` 验证未退化成全表扫描。

### 8.2 工作包查询

先验证 scope 属于目标版本，再通过层级路径、祖先映射或受控递归查询取得当前范围。只查询当前页轻量 entries；然后用当前页 GID 批量查询 links 和引用摘要，避免一个巨大多表 JOIN 产生宽行和重复字段。

### 8.3 详情查询

详情只处理一个 entry。完整实体和图片解析在此路径执行。所有关联查询仍在 Craft Provider 内完成。

### 8.4 一致性

每次调用在查询前读取当前 revision，完成组装后再次验证。revision 改变时返回不可伪装为普通空数据的 `revision_conflict`。前端收到后终止当前 generation，并从版本读取重新开始。

## 9. Capability 执行预算

`CapabilityDescriptorV2` 增加冻结的 `execution_budget`：

- `memory_class`：`small`、`medium`、`large`；
- `max_input_bytes`；
- `max_output_bytes`；
- `collection_policy`：`bounded`、`paged`、`artifact`；
- `max_page_size`；
- `max_parallel_per_consumer`；
- `max_parallel_per_tenant`；
- `overload_policy`：`reject`、`degrade`、`async_artifact`。

首版预算：

| Capability | memory class | output 上限 | page 上限 | consumer 并发 | tenant 并发 |
|---|---:|---:|---:|---:|---:|
| `craft.bop.structure.outline.get@1` | small | 512 KiB | 100 | 1 | 8 |
| `craft.bop.work_package.get@2` | medium | 1 MiB | 200 | 1 | 4 |
| `craft.bop.entry.detail.get@1` | small | 512 KiB | 不适用 | 4 | 16 |

这些是契约安全上限，不是期望响应大小。压测可以降低 page 默认值，但提升冻结上限必须通过 Catalog 兼容性和资源评审。

Gateway 在 Provider 调用前检查输入、并发名额和内存水位；在输出进入传输层前检查结果估算与实际序列化字节。超限返回平台错误：

- `capacity_unavailable`：并发名额不足，可重试；
- `resource_pressure`：容器处于高内存水位，可重试；
- `capability_output_limit_exceeded`：Provider 违反 Descriptor，默认不可自动重试；
- `dataset_too_large_use_paged_capability`：旧全量入口拒绝大数据集。

任何返回集合的稳定 Capability 必须具备 `maxItems`、分页或 Artifact 策略，否则 Catalog 发布检查失败。

## 10. 容器与进程预算

1. Gunicorn worker 数由显式 `AI00_WEB_WORKERS` 配置，默认 1；删除 `CPU * 2 + 1` 自动推导；
2. Docker、运行手册和实际部署使用同一入口；
3. worker 数依据 `基础 RSS + 允许的在途 Capability 峰值` 计算；
4. 容器为 Python 运行时、数据库驱动、SDK、序列化和系统开销保留 20% 至 30%余量；
5. `max_requests + jitter` 仅作为未知碎片或长期泄漏的保险丝；
6. 各领域连接池保持独立，但 max/min cached 必须可配置，并由部署检查汇总连接总预算；
7. 未完成压测前使用单 worker 和保守并发；
8. 压测后设置生产 `resources.requests.memory` 和 `resources.limits.memory`，验收峰值不得超过 limit 的 75%。

运行水位策略：

- 60%：记录预警；
- 75%：停止预取和非关键后台大任务；
- 85%：拒绝新的 large Capability；
- 90%：readiness 转为不接收新流量，等待已有请求结束。

## 11. 可观测性

Capability Gateway 和 Craft Provider 对每次调用记录结构化指标：

- Capability ID、major version、owner domain；
- consumer type 和匿名化 consumer key；
- version、revision、scope 类型；
- SQL 耗时、读取行数；
- Provider 组装耗时；
- 序列化耗时和响应字节；
- 调用前后进程 RSS；
- cgroup current、limit 和水位；
- 同类在途调用数；
- 结果状态、错误码和是否取消。

日志不得包含业务正文、零件名称、图片 URL 中的签名、数据库 URL、JWT 或凭据。

`/health` 保持便宜且不执行大查询。`/ready` 增加内存接纳状态。新增管理员保护的诊断接口，返回当前进程、容器水位和最近高消耗 Capability 摘要；不要求生产治理 UI。

## 12. 旧接口兼容

新 Capability 和前端加载器上线前不删除 `/api/bop/versions/{gid}/entries`。迁移后：

1. 小版本暂时保持兼容；
2. 路由在执行富查询前先读取轻量条目计数；
3. 超过配置上限时返回 `dataset_too_large_use_paged_capability`；
4. 审计所有消费者并迁移到 Capability；
5. 无消费者后按正式弃用流程退役。

旧接口不得通过增加反向代理超时来掩盖问题。

## 13. 测试与验收

### 13.1 测试数据

在 Craft 测试数据库生成 1,000、5,000 和 10,000 节点 BOP，覆盖工厂、线体、工位、岗位、工序、操作、零件和工具引用。图片保持少量。测试夹具只写 Craft 测试表，并按精确 GID 清理。

### 13.2 契约测试

- 三个新 Capability 的 closed input/output schema；
- owner domain、资源选择器、暴露范围和执行预算；
- page size、游标、revision conflict 和稳定排序；
- Provider 不调用全量 `load_bop_aggregate()`；
- Web、插件和 Agent 通过同一 Gateway 获得一致边界；
- 其他领域不能导入 Craft Repository 或查询 Craft 表。

### 13.3 前端测试

- 版本切换取消旧请求；
- 过期 generation 和 revision 响应被丢弃；
- 刷新单飞，重复操作不产生第二组请求；
- 刷新释放画布和重缓存；
- outline、线体分页、详情按需加载；
- LRU 达到节点或字节上限时淘汰；
- `revision_conflict` 和资源压力错误提供可重试提示。

### 13.4 性能与稳定性

依次验证：

- 第一次打开；
- 单次刷新；
- 连续刷新 20 次；
- 大版本快速切换；
- 请求未完成时切换；
- 展开多条线体后返回；
- 5 个用户并发查看同一大版本；
- Craft 压力期间调用其他领域 Capability。

通过标准：

- 10,000 节点首屏不产生全量富响应；
- outline 和每个工作包页面符合 Descriptor 上限；
- 不出现 504、OOMKilled 或 worker 非预期重启；
- 峰值不超过容器 limit 的 75%；
- 20 次刷新后内存进入稳定平台，最后 10 次不能呈持续线性增长；
- 其他领域 Capability 错误率不增加；
- 浏览器只保留预算内的线体和详情数据；
- 数据库查询计划使用预期索引。

## 14. 实施顺序

1. 增加只读诊断和可复现的大 BOP 压测，记录当前基线；
2. 统一容器入口、固定单 worker、增加前端请求取消和刷新互斥；
3. 扩展 Descriptor、Gateway 执行预算和 Catalog 发布检查；
4. 实现 Craft outline、范围工作包和 entry detail Provider；
5. 为范围查询补充索引和查询计划测试；
6. 将流程图迁移到渐进 Capability 加载；
7. 给旧全量接口增加预检上限并审计消费者；
8. 执行 1k、5k、10k 及跨领域压测；
9. 按实测确定 worker、连接池和容器 request/limit；
10. 将资源预算和大数据压测加入正式发布前门禁。

## 15. 风险与应对

- **层级分页导致孤儿节点**：每页返回必要祖先摘要，或以 line/station 作用域为分页边界；
- **编辑中 revision 改变**：返回 `revision_conflict`，整轮 generation 重启；
- **缓存造成再次增长**：同时按版本数、线体数、节点数和估算字节执行 LRU；
- **索引增加写成本**：仅增加被范围查询和稳定游标使用的复合索引，并用写入压测验证；
- **旧消费者依赖全量接口**：先审计、兼容小版本、提供明确迁移错误，不静默截断数据；
- **分页让插件调用复杂**：SDK 提供有上限的分页迭代器，但插件仍受 Manifest 授权和 Capability 预算约束；
- **只降低 worker 掩盖根因**：worker 调整仅是容器保险，渐进读取和有界契约必须完成；
- **单次峰值被误判为泄漏**：用 RSS、cgroup、请求字节和重复周期趋势共同判断。

## 16. 完成定义

只有同时满足以下条件才视为完成：

- 新 Capability 进入正式 Catalog，并有 Provider、契约、权限和资源预算测试；
- 工艺流程图不再调用大版本全量 entries 接口；
- 10,000 节点版本通过首次加载、切换、20 次刷新和 5 用户并发验收；
- 容器实际 worker、连接池和 memory request/limit 有压测证据；
- 运行日志能够定位 SQL、Provider、序列化、并发和内存水位；
- 其他领域仍保持代码、数据库访问和 Capability 边界独立；
- 正式发布前检查能够阻止新的无界集合 Capability。
