# Teamcenter 在线模型、VisMockup 与备选层次结构运行手册

本手册覆盖 AI00 `simulation` 域中的在线产品结构读取、缓存、VisMockup 官方在线打开和备选层次结构边界。它不会把机器测试结果视为人工批准或真实运行验证。

## 数据流与边界

1. AI00 App 的本地运行时使用当前 Windows 用户专属 IPC 接收 Teamcenter 登录信息，建立只读 SOA/FMS 会话。
2. Teamcenter 产品结构按页读取；AI00 保存不可变 observation 与分页结构缓存。相同名称、相同产品的多次出现仍以 occurrence 身份区分。
3. AI00 通过 Teamcenter 官方 `createLaunchInfo` 产生的 VVI 调用 runner，让 VisMockup 打开同一个在线来源。禁止从缓存节点逐个重建 VisMockup 产品树。
4. VisMockup 文档打开后，AI00 按 `__PLM_INST_UID`、`bl_occurrence_uid`、最后才是唯一 `catiaOccurrenceName` 建立运行时实例映射。重复或歧义必须停止控制。
5. BOP 形成的备选层次结构是产品 occurrence 的复制链接，不改变原产品结构。原生 AH 写入在真实安全验收前保持关闭。

## 测试环境启用

本地测试环境读取现有后端 `.env` 的 `USERS_DB_URL`，使用共享数据库中的 `test_` 表投影，不使用独立测试数据库。执行迁移时必须在当前进程显式设置 `TABLE_PREFIX=test_`；不得对这个共享数据库使用空前缀。当前迁移账本已有 `0001`–`0025`，`0026` 会新增三张 `test_` 在线结构表。

当前 `.env` 账号具备 schema 权限，但 `run_domain_migrations.py` 的正式接口仍将 DDL 地址建模为 `AI00_SIMULATION_DDL_DB_URL`。若测试环境明确授权复用该账号，只能在单次迁移进程中把现有 URL 映射到该变量；不得写回 `.env`、打印连接信息或改变生产配置。迁移完成后立即重放一次，必须显示零项新增。

迁移后依次确认：

- Catalog release 与 Provider artifact 校验通过；
- 新增六张 Simulation 表均归属 `simulation`；
- 前端官方 manifest 和 business facade 只允许精确 capability；
- App 本地 runtime 能启动 Teamcenter 只读 worker，且未依赖独立安装的旧 connector；
- 登录、搜索、观察、翻页、缓存命中、官方打开、文档绑定和实例映射分别可观测。

## 真实验收

先使用 `STU-0000395673/00;1-Tool2025`：

1. 在 AI00 登录 Teamcenter，使用精确 Item/revision 搜索，确认 source selector 包含对象、版本、BOM view、revision rule 和配置日期。
2. 冷读取完整结构，只展开结构，不加载全部几何。记录节点数、页数、耗时、峰值内存和错误。
3. 重新进入同一仿真环境，确认先命中缓存，不自动完整重读；手工刷新才创建新的 immutable observation。
4. 触发官方 VisMockup 打开，确认在线模型仍保持 Teamcenter/FCC 关联。
5. 抽样映射根、叶、同名重复 occurrence；只有唯一匹配才允许高亮或显示隐藏。

再使用 W10 大装配重复测试，记录冷读、热缓存、手工刷新、VVI 打开和映射耗时。禁止“显示全部数模”。若直接读取与 PLMXML 节点数不同，先按配置日期、revision rule、packed line 与 suppression 状态解释，不能按名称合并节点。

## AH 验收与开关

原生 AH 写入默认关闭。启用前只能在 AI00 自有测试 AH 上验证：新建、重命名、复制产品链接、删除链接和读回；每次都要证明原 CPS 的 parent、name、在线 source identity 未改变。任何未验证操作返回 `native_ah_operation_unverified`，保留 AI00 事实，不向 VisMockup 猜测写入。

## 故障与回退

- Teamcenter 会话失效：保留最后一次 observation，标记过期；要求重新登录，不重放密码。
- VisMockup 关闭或换文档：立即使 runtime mapping 失效；同名文档不能自动继承旧 session mapping。
- 同名在线模型与 PLMXML 同时存在：以 source identity、insertion timestamp 和 occurrence identity 区分。
- 映射歧义或缺失：禁用高亮/显示隐藏写操作，允许用户刷新映射。
- 官方打开失败：保留 AI00 的只读树，不降级为缓存树重建。
- 迁移或治理门禁失败：保持 capability 不可用，不修改 Catalog 证据；测试环境只能操作 `test_` 命名空间。

## 敏感信息检查

真实验收后检查本地日志、SQLite、后端数据库与上传证据，不得包含 Teamcenter 密码、完整 VVI body、SessionID 或 CredToken。发现任一命中即停止发布、撤销会话并清理受影响的测试证据。
