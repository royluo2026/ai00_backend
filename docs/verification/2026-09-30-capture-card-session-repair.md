# 截图工序卡与实时节点映射修复

## 1. Change classification

2026-09-30，implementation fix。沿用我们自己的前后端 `test` 工作树，不切换分支、不提交、不推送、不部署。

- 前端：`E:/Projects/ai00_v3/.worktrees/orchestration-merge-frontend-20260905`。
- 后端及 Connector：`E:/Projects/ai00_v3/.worktrees/orchestration-merge-backend-20260905`。
- 保留工作区其他任务的既有修改。本报告补充此前逆序截图报告，不能把此前模拟测试解释成真实内嵌窗口验收。

## 2. Authoritative context inspected

已检查 Craft 的 `craft.process_screenshot.attach@1` Provider、封闭输入输出合约、Provider Descriptor 构造器、Artifact Service 校验、`0007_process_screenshots.sql`，以及 `craft.bop.line_operation_catia.read@1` 的实际 Provider 和消费者。读取了 Simulation execution structure → manifest → capture worker → 单工序 Connector plan 链路。

运行端检查了 PLMXML 快照、DocumentSnapshotReader、SessionState、既有 ResolveSessionNodeKey/VisMockupTreeCache 解析器、SceneController、ReverseCaptureRenderer。前端检查了 lineage 图片规范化、认证图片协议入口、关联面板和截图完成回调。

没有获取在线 Catalog Snapshot、持久化 capability_version_gid 或 exact-hash 人工批准；没有调用生产能力或读取用户凭据。

## 3. Reuse, atomicity, and ownership result

确认的断点：

1. PLMXML 快照发布 `pdm:` 稳定键，截图渲染此前把它当原生数字节点键；基线校验此前又使用另一套 COM 树散列。
2. 截图关联保存 ArtifactRef 包装，旧图片规范化和部分页面不能识别该包装。
3. 实际 `line_operation_catia.read` Provider 原先不返回图片，也排除了没有直接零件链接的 process 节点。
4. 完成回调仅刷新关联面板，未更新已经加载的工序卡数据。

本轮复用既有 Connector 节点解析和认证 ArtifactRef 图片展示，不新增旁路上传、localhost Bridge 或跨域 SQL。Simulation 管队列，Connector 管模型，Craft 管工序卡数据。没有新增能力和迁移。

## 4. Implementation boundary

- Snapshot 与首次基线验证统一调用同一 PLMXML 优先、受限回退 COM 的读取方法；错误基线不再污染后续有效请求。
- 场景使用既有稳定键到当前会话节点的解析器，资源附件保留原有专用绑定。每次应用/渲染清除会话键快捷缓存，以重新校验当前节点路径。
- 基线绑定进程 ID/启动时间、文档 ID、来源、根节点及来源修订指纹。渲染、验证和截图均检查该绑定；进程重启不能沿用旧基线。
- 所有渲染目标解析完毕后才改色/显隐；缺失映射失败，不猜节点。
- 新关联同时保留原有 screenshot/run/ArtifactRef 记录并产生已有 `artifact:` 图片路径；读取兼容历史仅有 ArtifactRef 的记录，仍通过 Electron 认证内容协议显示，不生成公开下载地址。
- 线体读取增加 process/operation 图片及父节点字段，保留 500 条上限；递归限定相同 BOP 版本，允许无直接零件链接的工序。它是缩略图读取，不负责截图排序。
- 截图成功关联后更新对应工序 GID 的本地图片字段和卡片；操作级回退会同时刷新所属工序卡。不整树重载，版本切换后的迟到结果不更新新页面。
- 保持原有每次截图替换该条目 `process_flow_pic` 投影的行为；历史截图仍保存在截图关联表。本轮未改为追加手工附图策略。
- 顺序仍由 Craft 的层级顺序生成全局序列，再由 CaptureWorkflow 倒序创建单工序计划。有 process 时子操作合并到所属工序，没有 process 时使用操作条目。

## 5. Verification evidence

最终针对性测试：

- Python：77 passed。包含真实 Repository SQL 调用边界（模拟数据库连接）、旧新图片引用往返、工序/版本精确回填、无直接链接工序读取、队列及结果投影。新增顺序测试把打乱输入的两工位、重复局部工序号传过 `_normalize → compose_manifest → CaptureWorkflow.start_capture`，得到 `process-b-2 → process-b-1 → process-a-2 → process-a-1`。
- C#：113 passed，0 skipped。包含稳定 `pdm:` 快照与 COM 数字节点不同的完整 Adapter 渲染/合成 PNG 截图、不同来源的快照散列、重启后 render/verify/capture 拒绝、映射缺失前无模型副作用、原有生命周期与 Connector 合约测试。
- JavaScript：54 passed。包含 ArtifactRef 和 artifact 路径认证解析、图片缓存不串图、按 GID 局部刷新、版本切换后迟到回调拒绝、空列表清除旧缩略图、已有 viewer interaction 和环境树测试。
- Vite `AI00_WEB_BUILD_PROFILE=test-governance` 构建通过；已有非 module 经典脚本警告仍存在。未构建/替换正式 App，未安装 Connector。
- 新顺序测试开发中曾因 fixture 缺少 content_hash、错误地把多工序传给单工序计划构造器失败；测试已改走实际 CaptureWorkflow，最终通过。未修改生产实现以掩盖这两处测试构造错误。

Python 测试文件：`test_craft_capture_picture_projection.py`、`test_craft_process_screenshot_boundary.py`、`test_craft_bop_line_operation_catia_boundary.py`、`test_simulation_reverse_capture_demo.py`、`test_simulation_capture_workflow.py`、`test_simulation_environment_manifest.py`、`test_simulation_environment_composition_capabilities.py`、`test_simulation_connector_outcome_capabilities.py`、`test_simulation_connector_projection_worker.py`、`test_simulation_process_capture_plan.py`，命令参数 `python -B -m pytest … -q -p no:cacheprovider`。

C# 命令为 `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --no-restore -m:1 -nr:false`，过滤 Capture、Scene、VisMockupSnapshotTests、AdapterManifest、AdapterDispatcher、ServerContractTests、VisMockupDocumentLifecycleTests。

前端 `test:reverse-capture` 已加入工序卡引用测试；最终扩展测试另包含 `viewer_interaction.test.js` 和 `environment_tree.test.js`。

## 6. Governance status

- targeted_tests：passed，证据为上述实际测试输出；COM/数据库/认证内容响应仍含模拟边界。
- machine_passed：unverified，未运行可信在线治理 Snapshot/Release Gate。
- human_approved：unverified，用户要求修复不等于治理 exact-hash 批准。
- runtime_verified：unverified，未用真实线体、数据库上传及当前内嵌窗口跑完。
- advisory：本报告不签署发布、不清除治理 Findings、不授权替换运行端。

## 7. Findings and unresolved risks

实际使用前需要受控更新测试前端、后端和 Connector，并重新构建截图环境。旧签名 Release Report 不因局部测试通过而自动有效。

真实验收应先核对所选线体的工位/工序队列，再确认内嵌窗口的同一文档节点显隐/高亮，最后逐张核对工序 GID、蓝色零件、上传后的卡片图片和刷新后的持久化结果。替换运行端或重新连接后须重新读取快照，不复用旧会话。

本轮不宣称已验证所有 VisMockup 文档结构。沿用解析器的路径/名称校验限制、完整相机/任意材质恢复、交互单步暂停仍未在本轮扩展；500 条缩略图读取上限没有改变。真实模型验证未执行，不能把合成 PNG 或测试通过当作真实截图。
