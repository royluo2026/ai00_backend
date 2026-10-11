# 装配描述打开大小上限调整

## 1. Change classification

2026-10-08，兼容输入范围增强。用户确认放宽整车装配描述限制。沿用前后端 test 工作树，前端 HEAD 83260f6b、后端 HEAD 488dd7c69，加既有工作区修改。未提交、发布、安装或重启运行端。

## 2. Authoritative context inspected

核对 Simulation 的 TcCacheSourceOpenProvider、TcCacheOpenPayload、Connector 队列/租赁及 HTTP/管道传输源码、缓存准备存储、vismockup.model.open@3 JSON 契约和 C# Adapter，以及前端缓存打开消费者。旧限制对应 UTF-8 PLMXML 文本和完整 JSON 包，不是 JT 文件总量或 VisMockup 原生模型大小。

## 3. Reuse, atomicity, and ownership result

复用既有缓存打开、签名计划和本地 JT 获取路径。Simulation 和 Connector 共同保持大小校验；所有超限请求在原生打开前失败。未添加能力、传输旁路、数据库迁移或匹配规则。

## 4. Implementation boundary

- 后端装配 XML 字段和 UTF-8 字节上限由 7 MiB 调整为 32 MiB（33,554,432 字节）。
- 完整 JSON 请求包上限为 48 MiB（50,331,648 字节），包含 XML、JSON 编码与依赖清单。
- Connector 同步 32 MiB 字节/XML 解析上限，并检查 48 MiB 请求包上限。
- JSON 契约与 Adapter 指纹同步为 sha256:a95c8a80498aecb2166791271d5a0ffd97b2e7e390b117a26af0b973f96fecc1。
- 前端移除写死的“7 MB”提示，以当前运行端的实际拒绝为准。
- 保留既有身份、权限、哈希、取消及 10,000 条依赖数量校验。

## 5. Verification evidence

- Red：旧实现拒绝约 9 MiB 中文 XML，新回归 1 failed、7 passed，失败码 cache_package_result_limit。
- Python 最终 51 passed：test_cache_tc_open.py、test_cache_open_evidence.py、test_cache_document_resume.py。覆盖中文 UTF-8 计数、约 31 MiB 请求入队、超 32 MiB XML 拒绝及超 48 MiB 整包拒绝。数据库/队列为测试夹具，83 条已有 sqlite datetime 弃用警告。
- C# 最终 10 passed、0 skipped：TcCachedDocumentTests、LocalOpenCancellationTests、ServerContractTests。8 MiB 和约 31 MiB XML 经实际 XML 解析打开模拟文档；超限拒绝且无文件获取/模型打开。COM 与 TC 使用模拟对象。
- JavaScript cache_snapshot_viewer.test.js 21 passed；cad_sim.js 语法检查通过。
- Python schema、JSON 契约及 C# Adapter hash 一致；本轮文件 diff whitespace 检查通过。
- pytest 临时目录及 C# 临时目录 ACL 在沙箱内被拒绝，经工具审批在沙箱外重跑。Node --test 被 spawn EPERM 拒绝，直接执行现有测试文件通过。

## 6. Governance status

targeted_tests: passed。machine_passed、human_approved、runtime_verified 在正式 Snapshot/发布层面均为 unverified；AI advisory。本轮源码测试不构成正式治理批准或真实模型运行证据。

## 7. Findings and unresolved risks

未取得此前 W10 整车 XML 的精确大小；32/48 MiB 是有限扩容选择，未宣称所有整车适用。真实数据库 max_allowed_packet、实际 HTTP 传输、大包内存峰值与整车 COM 加载未实测。部署需更新后端和 Connector、重新广告新的 contract hash；旧 Connector 不自动获得更大上限。前端提示也需随测试端更新。BOP 未发布/缺少工序关联属于独立阻塞，不由本次改动解决。

## 本地部署跟进（2026-10-08）

用户明确授权更新测试运行环境。启动前未发现本地 Test App 或 8080/5173 监听。测试启动前置检查通过；保留本地 Provider 清单备份，仅更新未发布本地清单中 craft、knowledge、simulation 的实际工作树 artifact hash。没有改正式 Catalog/审批/发布证据。

启动脚本重建并发布 ConnectorHost 到前端 build/connector-debug；部署 DLL 已核对包含新 contract hash，HostSha256 与开发 manifest 一致。前端 cad_sim.js 同步至后端测试 dist，源/目标 SHA256 一致，并备份原运行资源。启动脚本后台辅助进程显式使用 Hidden。

首次启动失败的原因是旧校验强制要求 11 个独立领域账号。该要求现已按用户指令废弃，不再需要独立账号配置。

## 共享数据库账号政策修正与最终状态（2026-10-08）

用户确认同一物理数据库、不同领域表。已移除 runtime readiness、候选部署、授权生成及隔离探针中的用户名唯一性要求；共享账号授权按所绑定领域的表集合取并集，跨前缀探测仅作为可访问性观察，不声称账号提供隔离。旧独立账号运行手册已标记废弃，旧 Gitea RC 作业禁用。没有执行数据库授权或修改真实账号。

本地 test-governance readiness 支持无 managed ENV_FILE 的本机运行模式，保留领域 URL 完整覆盖、显式 MySQL URL、同一物理数据库及前缀检查；正式部署预检仍要求显式 test/production profile。与正在实施的数据环境切换功能兼容。

验证：共享账号、授权生成、领域探针、部署就绪和候选检查共 133 passed、1 skipped；相关修改 diff whitespace 检查通过。最终实际 /ready=200，memory、connector_plan_signing、routes、domain_db_config、domain_db_connectivity、migrations、craft_db 均为 ok。

以下为本轮修复前的状态（已由下文启动验收取代）：后端已运行新的 32/48 MiB 限制，Connector DLL 已部署。桌面启动尚未完成：5173 被另一个前端配置 vite.frontends.config.mjs 占用，该服务没有旧启动器需要的 /web/login/index.html；没有强行终止该前端。重试复用服务仍被该路径检查拒绝，当前尚无新 App/Connector 活跃进程或真实整车截图验收证据。

## Test App 启动修复与验收（2026-10-08）

1. Change classification：implementation fix。修复测试 App 页面服务不匹配，以及 Connector 初始化期间过早超时/只检测进程导致的启动误报。
2. Authoritative context inspected：读取实际 Vite 配置、Electron 渲染来源白名单、运行模式、Connector Host 启动与身份管道、历史日志恢复实现、相关启动/监督/生命周期测试，以及实际端口归属。
3. Reuse, atomicity, and ownership result：复用现有本地 Test App、Vite 服务、Connector Host 和单实例激活机制。5173 原服务确认为本工作树 Browser 配置；先在其标准端口 5175 验证 Browser 页面，再移开旧端口占用。后端监督进程保留。
4. Implementation boundary：App 启动器显式使用 vite.config.js 提供 /web 与 /packages 路径；Connector 初始化预算 60 秒，Host 的身份握手仍为 10 秒。启动器等待 Main 验证身份后记录的 ready，最长 65 秒，不以进程出现代替就绪。增加不含凭据的 Debug 初始化计时。未删除/截断本机历史执行日志，也未执行整车模型操作。
5. Verification evidence：启动器契约、Electron 运行模式、Connector 监督测试全部通过（OS/trust 处为测试替身）；C# AppHostLifecycleTests 34 passed、0 skipped，含真实 Windows 命名管道身份握手。PowerShell/JS 语法与变更 whitespace 检查通过。真实 Test App pid=52368 主窗口可见，Connector pid=54252 持续运行；最新日志 app-test-20261008-110332.err.log 显示 teamcenter=501ms、journal=8850ms、[ConnectorHost] ready。此前一次日志恢复耗时 9569ms，原 10 秒总启动期限可触发超时。/ready=200 全项 ok；5173 登录页、主页、数模页与 5175 Browser 入口均返回 200。部署 HostSha256 与 manifest 一致，Adapter DLL 包含新的 XML contract hash。
6. Governance status：本地启动 runtime_verified=true；相关 targeted tests passed。正式发布的 machine_passed/human_approved/runtime_verified 仍未由本轮建立，AI advisory。
7. Findings and unresolved risks：本机历史日志约 85 MB 主文件 + 811 MB append events，恢复具有内存/时间成本；本轮不处理历史日志压缩。真实整车模型打开、TC 下载、BOP 逆序截图业务验收仍 unverified，需要在已经运行的 App 中使用实际模型验证。

## 真实 W10 数据与扩大上限（2026-10-08，后续记录）

本节取代上文 32/48 MiB 当前限制及“未取得真实 XML 大小”的结论；上文保留为历史过程。

- 对实际 W10-2026 v2 缓存批次 18f3d11a3e3d41c48ed27102895df821 执行只读预检：16,750 节点、3,330 个依赖。XML 为 41,054,140 字节（约 39.15 MiB），实际重建请求包为 43,576,405 字节（约 41.56 MiB）。既有缓存有 16 个排除项、准备状态 partial，不能据此声称全量几何完整。
- 32 MiB 上限实际拒绝该 XML。按用户已授权的扩容范围，Simulation 与 Connector 当前同步调整至 XML 64 MiB、请求包 96 MiB；保留身份、授权、哈希和依赖数量检查。新契约指纹 sha256:ed3b82d97c619831446e32110d7ca40f8cce6eac32f223a6fd8db1b7202f6399。
- 更新后的真实缓存预检 schema/大小通过；Python 51 passed，C# TcCachedDocumentTests、LocalOpenCancellationTests、ServerContractTests 共 11 passed、0 skipped。覆盖 40/63 MiB XML 接受、64 MiB + 1 字节拒绝和 96 MiB 整包限制。C# COM 与 TC 为测试替身；不等同于真实原生整车打开。
- 用户明确授权本机 CDP 测试。启动脚本添加默认关闭的 EnableLocalDebugging 开关，本轮显式启用 127.0.0.1:9222，用 DOM 与既有公开 preload API 操作 Test App。
- 暂停后恢复实际测试时，当前数据前缀为 pp_，后端有实际请求响应，Connector 公共状态为 ready；旧平台会话调用能力接口及 desktop token 接口返回 401，环境库显示 invocation_unavailable，Teamcenter 公共会话为 logged_out。已打开正常平台登录流程，等待用户完成平台和 Teamcenter 登录。
- 原生 W10 整车打开、JT 下载、BOP 倒序截图及截图写入工步仍 unverified。当前记录不构成正式发布或 Catalog 批准。

## 恢复登录后的实际测试结果（2026-10-08）

- 正常平台登录后能力请求恢复 200；用户完成 Teamcenter 登录，公开会话 state=ready。恢复时最新数据环境状态文件已为 test_（2026-10-08T06:06:28Z 从 pp_ 切回），本次任务确实存于 test_ 表；上节 pp_ 为暂停前历史状态，不是本次任务所在库前缀。
- 实际选择已有 W10 test2 20260928193519 环境，点击“打开缓存模型”。真实整车范围 16,750 节点、3,330 依赖读取完成，16 个既有空间证据缺失节点被排除。open.request 返回成功、耗时约 61 秒，operation_id=vismockup-command-6a8057189eb3244913c27000e020adb08010183010bdf12a7e23012f7cd66220。
- 原生打开失败，未进入 VisMockup 载入。Connector 日志在本次长请求期间出现 HttpClient.Timeout=30 秒的 TaskCanceledException，导致 BackgroundService/Host 退出、自动重启。只读任务审计为 plan_queued（06:11:01.867749Z）→ plan_failed_without_effect（06:11:44.400167Z），reason=runtime_session_replaced_before_lease，outcome_json=null。该任务没有租约执行，不能声称 TC 文件下载或原生加载已验证。后端长请求与本机请求超时重叠；导致后端请求耗时的细分瓶颈尚需专项定位，不能仅凭此断言具体 CPU/数据库根因。
- 同时发现较早运行日志有 wake_type_invalid 导致 Host 退出：V2 wake 客户端把 WebSocket Close 帧作为非法非文本帧抛错。该历史问题不是本次 30 秒请求超时的替代解释。
- 实际选中“前内饰一线”并打开逆序截图预检。界面返回：BOP 205576954294833152 尚未发布，仅接受已发布执行结构；尚未截图或回写工序卡。未擅自发布该 BOP。
- 结论：大小限制已允许该实际整车任务入队；整车打开及逆序截图验收未通过。当前阻塞为 Connector 请求超时恢复和 BOP 发布状态，测试结果已明确记录。

## 草稿 BOP 支持与本轮实际验证（2026-10-08）

用户已明确批准：未发布 BOP 使用现有预览快照仿真和逆序截图，绑定 revision 与内容指纹，回填保留版本冲突检查。本节取代上节“必须发布 BOP”的阻塞结论。

- 前端仅在 execution_structure.get 返回未发布错误时读取版本 revision，再调用现有 execution_structure.preview，同时传 expected_revision 和 expected_resource_version。拒绝权限错误、revision 不一致、来源/线体不一致及缺失内容指纹。草稿仍标记 official=false。
- 后端 GovernedSimulationRuntimeClient 同样只对未发布错误使用固定 revision 的预览；既有仿真组合和工步截图回填冲突校验保留。没有发布 BOP，也没有修改 Craft 正式执行结构发布规则。
- 实际 W10 revision 2 预览快照为 7,629,684 字节（只读测量约 3.94 秒），超过 Electron 默认 4 MiB 响应上限；后端这两个读取契约已有 32 MiB 上限。Electron 仅将这两个 major 1 读取接口对齐为 32 MiB，其他接口保留原限制。新回归先失败后通过。
- 重启正常 Test App 后，真实“前内饰一线”逆序截图入口成功显示 BOP 205576954294833152、revision 2、sha256:d22f166fbdf59162f1a6af0a83d0d1241b6ecda702c67f0a37ed85f51d0b1bd3。当前环境仍未关联活动模型文档；这里只验证草稿来源读取，不能据此声称截图已执行。
- 最新前端 capability_client、reverse_capture_scope、capture_workflow 共 33 passed；后端 governed_domain_client、environment_composition、capture_workflow、craft_process_screenshot_boundary 共 39 passed。相关代码 diff whitespace 检查通过。

Connector 前一轮超时修复及实际打开重试：

- HttpClient 自身超时归类为可重试 transport timeout；调用方取消保持取消语义。plans/lease 可接收 100 MiB 响应（96 MiB 原生请求包及信封余量），其他控制响应仍限制 4 MiB；正常 WebSocket Close 帧回到轮询并完成关闭握手。AppHostLifecycle、TcCachedDocument、OutcomeUnknownRecovery 共 78 passed、0 skipped（已运行记录）。
- 重试打开任务 vismockup-command-63221bdc146bf63abeed1debe308a4b0e39a8649cae16680d4b2a4d4b7716d51 已收到真实整车请求并开始 TC/FMS 下载。记录为 48/3330 个依赖完成、4 个缓存命中、约 280 秒；随后 300 秒执行租约到期取消。未记录 native_open_started，原生整车打开未通过。
- 该操作后续对账结果为 manual_review_required（探测 inconclusive）；未绕过正常恢复流程或直接修改数据库状态。当前业务阻塞为首次大规模下载与执行租约不匹配及未完成操作人工核对，已不是 BOP 未发布。
- 原生整车完整载入、逆序截图图像、工步回填仍 unverified。本记录不是正式发布、人工批准或完整业务 runtime_verified 的证明；上文 runtime_verified=true 仅指本地服务启动，不代表业务验收。
