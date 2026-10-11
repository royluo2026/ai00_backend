# W10 test2 门线实测记录

## 1. Change classification

Implementation fix。仅修改自身前后端 `test` 工作树；没有修改参考仓库、切换分支、提交或推送，没有发布 BOP 或治理 Catalog。

## 2. Authoritative context inspected

- 实际 App 登录会话，经现有 `AI00Business` / Capability Gateway 调用，不提取认证令牌。
- 环境 `W10 test2 20260928193519`：workspace `230291366528323584`。
- 备选层次 `231001597197586432`，源 BOP `205576954294833152`，revision 2。
- 车门分装线：本地节点 `231001598640427021` → `source_bop_node_gid=205577258981658638`。
- BOP 实际为 `version_type=working`、`lifecycle_phase=init`、`published_at=null`；`craft.bop.execution_structure.get@1` 实际拒绝 `version_not_published`。
- 当前备选层次整树有 8127 个节点、0 个 placement。车门分装线子树仅 1 条线 + 92 个 `station_process`，0 个 process/operation，其 `source_refs.model_references` 中没有门线引用。正式 `craft.bop.line_operation_catia.read@1` 对源线 GID 返回 `ok=true,data=[]`，不是只凭前端树作出结论。
- 缓存模型文档 `230293311259316224`；固定批次 `18f3d11a3e3d41c48ed27102895df821`，generation `284340f0310e4c0e911ecfaadd42e125`，snapshot_hash 为 null（现有合同允许）。
- 已检查 Craft execution-plan 合同、Simulation cache open Provider/Descriptor、Connector queue 合同、相关测试及本机未发布 Provider 清单。

## 3. Reuse, atomicity, and ownership result

- 复用 `craft.bop.execution_structure.get@1` 获取执行 hash，不能把备选层次投影 hash 当作执行结构 hash。
- 复用备选层次 `source_bop_version_gid` / `source_bop_node_gid`，不把工作空间节点 GID 当作工序卡 GID。
- 不使用 draft preview 伪装已发布执行结构，不自动发布用户 BOP。
- 模型打开仍由 `simulation.environment.cache_source.open.request@1` 派发 `vismockup.model.open@3`；未增加旁路。

## 4. Implementation boundary

Simulation 前端：备选层次节点选择及所属线体截图入口；读取并验证正式执行结构；禁止未核验或切换环境后的源进入构建。截图依然由既有受治理工作流执行。

缓存打开前端：每页 500（现有上限），保留累计数量；区分读取引用和提交打开请求。原流程实际读取了 3330 个文件引用，却始终显示“读取固定快照”，不代表原生模型已经打开。

Simulation 后端：保留 Connector/Workspace 拒绝码；未知准备/提交异常只记录类型、字段位置及文件行号，不记录输入、令牌或异常原文。日志定位到 `assembly_xml` 的 `string_too_long`，不是 COM 故障；提前按 UTF-8 字节检查既有 7 MB 上限，使用 `cache_package_result_limit` 明确拒绝。没有扩大限制，也没有实现超大整车的分包打开。

## 5. Verification evidence

- JavaScript：41 passed（截图源解析、正式结构核验、未发布拒绝、工作流、分页进度、卡片图片投影）。含模拟边界。
- Python：最终 27 passed（cache open、TC open、错误码、脱敏诊断、ASCII/UTF-8 大小边界）。数据库和原生队列使用测试夹具，不是实机成功证据。
- 新增超大文本用例初次因 pytest 自动生成了超长参数 ID 导致夹具错误；改用短参数 ID 后全套重跑通过，没有把这次失败算作通过。
- `npm run build:web:test-governance`：passed；`cad_sim.js`、`capture_workflow.js`、`cache_snapshot_viewer.js` 源文件/构建文件 hash parity 均通过。没有构建或安装正式 App。
- Node/pytest 首次在沙箱内遇到 EPERM/临时目录权限错误；经批准在沙箱外重跑通过，不将初始化失败算作通过。
- 实际 UI：选择备选层次车门分装线 → 工序截图，显示正确源线 GID/BOP GID，明确提示 BOP 未发布，构建按钮禁用；snapshotRequest 和 captureRun 均为 null。
- 最终 test 运行端重新部署后复验：打开同一整车缓存，在初次读取阶段即明确显示“所选装配超过单次打开的 7 MB 限制”，文档仍为“未打开模型”；不再遍历全部引用后才返回笼统错误。
- 阻塞界面截图（不是工序图）保存到 `E:\Projects\ai00_v3\.runtime\w10-test2-capture-blocked.png` 并已人工式视觉核对。ConnectorHost 启动成功不等于截图预检、绑定和原生映射已经通过。
- 实际缓存读取：16750 个逻辑节点、3330 个文件引用；原实现逐页读取至 3330/3330 后才报 `cache_materialization_invalid`，脱敏日志已定位为装配 XML 超长。
- 同项目另一 BOP `230862436725592064` 的线体只读查询没有发现名称含“门”的线体；没有擅自更换 test2 的源绑定。
- 草稿 execution_structure 只读预览尝试未获得可用回执（首次缺 envelope expected version，补齐后调试调用超时）；未据此声称源完整或使用其执行截图。
- 实际 `simulation.connector.recovery.search@1`：total=0；未擅自清除或认定未知操作结果。
- 本轮真实工序截图、Artifact 上传、工序卡写入/刷新验证：尚未执行成功。

## 6. Governance status

- targeted_tests：passed，但含模拟边界。
- machine_passed：unverified；未运行可信治理 Snapshot/Release Gate。
- human_approved：unverified；修复请求不是 exact-hash 发布批准。
- runtime_verified：未完成；真实 UI 源解析和拒绝路径已验证，不等于模型控制与卡片上传链路已验证。
- 本机 Provider 清单仅供 test 启动校验，不能替代正式发布证据。AI 为 advisory。
- 最终本机 manifest 校验值：`sha256:ecf0a2a2fbd6835f5ce9f554a324bc0ae901dcdb837c43e833e6129e14196d7f`。

## 7. Findings and unresolved risks

1. 源 BOP 未发布，当前截图合同要求已发布执行结构；需要负责人明确处理，不能靠测试代码绕过。
2. 当前门线没有工序和模型引用；必须先确认正确源数据。不能把工位当工序、伪造零件关系或将空图写入卡片。
3. 全车装配超过现有单次打开限制。当前只修复了提前识别/准确报错，未证明分包或选定子装配能够完成这条门线的全部装配。
4. 尚不能确认该门线的全部零件能在内嵌 VisMockup 中被准确定位、变蓝/隐藏，也不能声称已按工序顺序完成截图并写入工序卡。
