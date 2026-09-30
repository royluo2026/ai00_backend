# TC JT 本地打开实施计划

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. 按用户要求由当前实例执行，不委派。用户已用 `go` 授权实施；当前进展及真实测试以 [实施记录](../../verification/2026-09-30-tc-local-open-execution.md) 为准。用户随后明确回复“你可以测试了”，已恢复真实测试并部署暂存取消改动。当前验收仍未通过，详见实施记录末尾的 2026-09-30 复测结果。

**Goal:** 缓存模块提前准备装配依据，仿真点击后仅按需从 TC/FMS 下载 JT 到本机，全程不上传 JT。

**Architecture:** 固定快照派生出共用装配产物和文件依赖索引；仿真服务签发精确范围任务，Connector 用临时本地缓存解析 TC 文件依赖，再复用单环境文档和批量显隐。结构准备与 JT 字节传输分离。

**Tech Stack:** 现有 Python/MySQL 后端、JavaScript 页面、.NET Connector、Teamcenter SOA/FMS、VisMockup COM；不新增基础设施。

**Spec:** [2026-09-30-tc-jt-local-open-design.md](../specs/2026-09-30-tc-jt-local-open-design.md)

## Global Constraints

- 禁止 JT 上传 OIS；禁止把 OIS JT 下载作为新打开流程的依赖。
- 固定批次与装配依据供所有有权限用户共用；JT、下载进度、缓存命中与原生文档状态属于各客户端。相同账号的两台电脑也不得共享“本机已下载”判断。
- 缓存准备不下载 JT；点击时仅下载选中范围、本地缺失或失效的 JT。
- 保留固定快照、准确实例坐标、单环境单文档/单根、逐节点范围、批量显隐与直接 TC 入口。
- 不持久化临时 FMS ticket，不伪造预期文件 hash，不复用越权文件，不以最新 TC 树替换旧树。
- 保留工作区此前未提交改动和已签名的历史执行记录；不批量提交或回滚他人修改。
- 新接口使用独立版本和 contract hash，不改写旧契约含义；新客户端/服务端不支持时明确升级提示，不回退到上传 JT。

## Review Focus

1. 同一个 JT 出现在多个装配实例：文件去重，occurrence 和变换不去重（任务 1、4）。
2. FMS 元数据缺失或历史文件内容变化：不能用引用冒充字节完整性证据（任务 2、3）。
3. 用户切环境或取消后旧下载完成：不能插入错误环境（任务 3、4）。
4. 清理本地缓存时文档仍引用文件：引用保护，关闭后可清理（任务 3）。
5. 另一项目授权用户或同账号第二台电脑使用同一批次：共用准备产物，但本地状态独立，TC 下载仍遵守当前身份权限（任务 1、2、3、5）。

## 路径和初始状态

后端根：`E:/Projects/ai00_v3/.worktrees/orchestration-merge-backend-20260905`。
前端根：`E:/Projects/ai00_v3/.worktrees/orchestration-merge-frontend-20260905`。
下面文件相对其对应根目录。重用这两个现有工作区，不新建工作区，不触碰 Siemens 安装文件。

此前暂停时仅新增 `application/cache_preparation.py` 空实现及 `tests/test_cache_preparation.py`（旧上传方案的失败测试），未接入正式流程、未部署。执行任务 1 时先确认文件仍是本实例新增内容，再改写为“元数据准备、不传 JT”的实现与测试；不能沿用旧测试里的 acquire/upload 前提。

## Task 1: 缓存派生装配产物，零 JT 传输

**Files:**
- Modify: `plugins/simulation/simulation_backend/application/cache_preparation.py`
- Modify: `plugins/simulation/simulation_backend/application/cloud_model_cache_worker.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/cloud_model_cache.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/cloud_model_cache_pinned.py`
- Modify: `plugins/simulation/simulation_backend/data/cloud_model_cache_repository.py`
- Reuse: `data/cache_assembly_reader.py`, `data/cached_assembly_projection.py`, `application/cache_source_materialization.py`（上述相同 simulation_backend 根）。
- Create: `plugins/simulation/simulation_backend/data/cache_assembly_preparation.py`
- Create: `backend/db/migrations/domains/simulation/0036_cache_assembly_preparation.sql`（实施前确认编号未占用）。
- Test: `plugins/simulation/tests/test_cache_preparation.py`，扩展 `test_cloud_model_cache_pinned.py`。

**Interfaces:** `prepare_cached_assembly(projection) -> dict` 返回 `identity`、`preparation_version`、`preparation_hash`、`nodes`、`files`、`node_dependencies`、`excluded`。不接受 JT 字节、OIS JT ref 或下载凭据。文件用 TC 来源与准确 UID 派生稳定 dependency_key；存储的准备产物可由原快照重建。

- [ ] 测试先行：准备期间任何 FMS 文件下载/JT 上传调用都使测试失败；重复文件只产生一条依赖、多个 occurrence 保留各自坐标；无坐标节点可定位排除；跨用户/跨租户权限；旧快照 hash 不变。
- [ ] 运行 `python -m pytest plugins/simulation/tests/test_cache_preparation.py -q -p no:cacheprovider`，确认业务断言失败后实现。
- [ ] 从已验证快照生成相对依赖路径基础装配描述和范围索引，持久化准备状态；新批次自动准备，旧批次可显式准备。缺原始字段标明原因，不隐式重采。
- [ ] 测试通过后运行相邻 cloud cache、projection 和 materialization 测试，检查迁移可重复部署和原批次兼容。

## Task 2: 版本化“TC 缓存打开”契约

**Files:**
- Modify: `plugins/simulation/simulation_backend/capabilities/cache_source_open.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/connector_runtime.py`
- Modify: `plugins/simulation/simulation_backend/application/cache_open_evidence.py`
- Modify: `backend/contracts/connector_execution_plan_v2.py`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupAdapter.cs`
- Create: `docs/contracts/vismockup.model.open@3.json`（确认未占用后）。
- Test: `plugins/simulation/tests/test_cache_source_open.py`，`backend/tests/test_connector_execution_plan_v2.py`。

**Interfaces:** 新打开输入绑定 `cache_binding`、`preparation_hash`、`environment`、`root_node_key`、`assembly_manifest`/所选描述以及 `tc_dependencies`；每个依赖含 dependency_key、endpoint、dataset/file UID、可用版本/大小依据。hash 覆盖描述和依赖，任务授权精确范围。结果为新的本地缓存打开回执协议，含输入绑定、实际文件校验摘要和 native document identity，不含 JT 字节。

- [ ] 先测：输入 JT 云端 artifact 不能进入新接口；越界节点、伪造依赖、快照不符、无项目权限和未知版本被拒绝；只选父/子节点时依赖范围准确。
- [ ] 运行相关 Python 测试确认失败，再实现从已准备产物读取、范围筛选、版本化任务和新回执校验。
- [ ] 移除新路径对 `cache_file_receipt_index` 的上传者记录依赖，保留当前用户授权；同步真正的 provider/descriptor/catalog 和运行时 operation advertisement。
- [ ] 相邻契约、admission、打开证据与恢复测试通过；新客户端检测旧 Connector 时明确升级错误。
- [ ] 回执/任务绑定 device_id、runtime_generation/instance 和当前文档；测试 A 设备回执不能绑定 B 的本地文件或原生窗口。共用元数据查询不依赖原创建者在线。

## Task 3: Connector 直接下载到受控本地缓存

**Files:**
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/TeamcenterModelFile.cs`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/TeamcenterReadOnlySession.cs`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/teamcenter_readonly_worker.js`
- Modify: `local-runtime/src/Ai00.Connector.AppHost/PlanExecutionWorker.cs`
- Modify: `local-runtime/src/Ai00.Connector.AppHost/AppArtifactMaterializer.cs`（明确新版本走独立本地解析，不走 JT Artifact 下载）。
- Create: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/LocalTeamcenterModelCache.cs`
- Test: `local-runtime/tests/Ai00.Connector.Tests/TeamcenterModelFileTests.cs`、新增 `LocalTeamcenterModelCacheTests.cs`。

**Interfaces:** `ResolveAsync(binding, dependencies, ct)` 返回受控本地路径及实际 SHA256/大小/获取时间。路径只在 Connector 内流转，不由前端指定。复用 TC 会话及 FMS 工具；按已有线程安全约束批量下载，不能盲目对同一 SOA 会话并发调用。

- [ ] 先测：未命中文件只下载一次；同名不同 UID 不串文件；命中不重复下载；损坏/清理后可重新下载；取消不提交半文件；大小未知不伪造；上传器被调用则测试立即失败。
- [ ] 运行 `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter "FullyQualifiedName~TeamcenterModelFileTests|FullyQualifiedName~LocalTeamcenterModelCacheTests" -m:1 -nr:false -p:UseSharedCompilation=false`，确认失败后实现。
- [ ] 原子落盘并记录来源、可用版本依据和实际内容 hash；受控目录/路径检查不弱化；新下载不调用 UploadModelAsync、不删除后再下载。
- [ ] 使用本地磁盘缓存清理策略和活动文档引用保护；测试关闭后清理、重启后的保守引用处理。大任务用分阶段进度和合理超时，不能仅延长一个不透明 600 秒等待。
- [ ] 下载回执只上传执行元数据；按原身份、计划和恢复机制持久化，不把本地副作用标为不存在。
- [ ] 用两个独立临时目录和设备上下文测试：A 命中不使 B 命中；同账号 B 无文件仍下载；A 清理不影响 B；两端下载后各自校验。同机账号切换遵守当前授权和本地缓存访问策略。

## Task 4: 当前环境打开、树同步与两处 UI

**Files:**
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/ManagedCacheOpen.cs`
- Reuse/Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/CacheEnvironmentDocument.cs`
- Modify: `plugins/simulation/simulation_backend/capabilities/live_documents.py`（现有 cache_source.live_document.bind 所在文件，不新增第二套绑定）。
- Modify frontend: `packages/sim-plugin/web/cad_sim/cache_snapshot_viewer.js`, `cache_snapshot_source.js`, `cache_snapshot_picker.js`
- Modify frontend: `packages/sim-plugin/web/model_cache/model_cache.js`, `cache_model.js`, `index.html`
- Tests: `CacheEnvironmentDocumentTests.cs`, `ManagedCacheOpenTests.cs`；页面对应 `cache_snapshot_viewer.test.js`, `cache_snapshot_picker.test.js`, `model_cache.test.js`。

**Interfaces:** 前端只检查准备状态并请求新打开能力；缺准备产物时提示在缓存模块准备，不自行调用 file.fetch.batch.request。UI 分清“装配依据就绪，JT 按需下载”与“本地下载/打开中”。日志采用 spec 的独立阶段名和关联字段。

- [ ] 先测页面打开从不调用旧获取/上传能力；待准备和部分可用提示准确；取消/切环境后不再插入；显示选中范围及下载命中数量。
- [ ] 扩展 native 测试：一个环境连续装置加载只有一个根；紧固件重复实例变换独立；已有几何显隐与坐标保留；父/零件批量显隐回读。
- [ ] 实现新本地文件证明到既有文档装配器的适配，不伪造 ArtifactRef；保留同环境单文档、10 文档上限、环境切换绑定规则和未知问号。
- [ ] 共用批次 UI 显示装配依据状态；仿真页面显示“本机待下载/下载中/已缓存/已加载”。其他设备的任务进度只可作为显式标注设备的审计，不混入当前本机状态。
- [ ] 运行 `node --test packages/sim-plugin/web/cad_sim/cache_snapshot_viewer.test.js packages/sim-plugin/web/cad_sim/cache_snapshot_picker.test.js packages/sim-plugin/web/model_cache/model_cache.test.js` 及相关 .NET 测试。

## Task 5: 切换旧路径、真实验收和部署

- [ ] 清查旧 `simulation.model_cache.file.fetch.*`、`teamcenter.model_file.fetch@1` 的调用者。新缓存/仿真路径禁用其 JT 上传链；旧入口不能继续默默排入上传任务。保留历史证据，不改写已完成回执，不影响无关图片/报告上传。
- [ ] 同步后端、前端、Connector 契约及产物，执行迁移和兼容检查；先记录当前环境与文档状态，按既有重启授权部署，不丢模型状态。
- [ ] 用 W10 test2 中此前未由 AI00 打开的装置验证：缓存准备无 JT 字节传输；实际点击才从 TC/FMS 下载；网络/执行日志证明 JT 上传与 OIS JT 下载均为零。
- [ ] 分别记录下载前准备、FMS 校验、下载字节耗时、本地文件验证、原生加载、映射和树回读；注明 FCC/本地命中，不以暖缓存结果冒充首次下载。
- [ ] 对整装置、单零件、已有父节点显隐、本地缓存失效、登录失效、下载取消、连续环境切换执行验收；核对紧固件世界坐标与单根文档。
- [ ] 两台可用客户端真实验证同一共用批次的独立下载、清理和显隐；若仅有一台机器，报告中明确双客户端只有隔离目录/设备上下文测试，不声称通过双机实测。
- [ ] 写入实测报告：已通过、未验证与残留瓶颈分别列出。失败时停用新入口并报告，不以回退 JT 上传作为修复。

执行顺序：1 → 2 → 3 → 4 → 5。当前仅完成重新规划，以上任务均未执行。
