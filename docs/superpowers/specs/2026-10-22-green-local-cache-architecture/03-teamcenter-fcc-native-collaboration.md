# 03 TC、FCC、外置原生文档与双向互动

## 1. 已检查的实现与证据限度

本机安装：`D:/Siemens/Teamcenter14`、`D:/Siemens/Visualization14`；用户最初提供的 `D:/Software` 未找到实际 VisMockup。安装包里包含 PSE 查看／设置版本规则、PCA 加载保存变量规则、内核 RevisionRule／SavedVariantRule／BOMWindow 及 SOA 契约。

FCC 安装库显示 GUID 索引、整文件／分段缓存及自动清理结构，配置模板包含容量和保留时间。此前只读状态查询为 Offline，不能据此判定文件不可用或容量为零，也没有据此启动共享服务。缓存命中率、完整离线及运行中保留尚未验证。

当前绿标来源：`local-runtime/src/Ai00.Connector.Adapters.VisMockup/TeamcenterReadOnlyRuntime.cs`、`teamcenter_readonly_worker.js` 已有 revision rules 查询和配置日期；选择字段未完整携带保存变量规则。`IVisMockupCom.cs` 和 `VisMockupAdapter.cs` 有隐藏原生窗口路径；前端 `packages/core/electron/native/job_object/job_object.cc` 有 SetParent 嵌入逻辑。这些是调查结果，不是已修复证明。

官方交叉依据：[结构配置](https://docs.mendix.com/appstore/industry/teamcenter-extension/integrations/get-structure/)、[服务参考](https://docs.mendix.com/appstore/industry/teamcenter-connector/teamcenter-reference/)。Mendix 文档中的服务输入需要与所装 TC 契约、服务器配置及授权实测核对，不能直接照搬部署。

## 2. 配置解析会话

界面：产品 → 版本规则及详情／日期 → 适用的保存变量规则 → 生效摘要 → 解析／打开。规则使用对象身份，名称仅显示。不能偷偷改变 TC 用户其他 BOM 窗口的当前配置。

变量规则调查必须确认 classic／Product Configurator 等模式、作用于 ItemRevision／ProductContext／ConfiguratorContext 的范围、是否允许多个规则及其覆盖顺序。不能假设所有保存规则都能全局列表查询。

解析固定同一个配置上下文：创建 BOM Window → 应用完整条件 → 读结构／几何／位置 → 验证完整性和可得一致性证据 → 建快照 → 生成对应打开材料 → 原生打开 → 验证目标与结果对应。读结构按 A、原生按默认规则 B 的实现不合格。

失败保留阶段证据和错误，不默默退回 Latest Working、空变量规则或云端重新获取全部 JT。

## 3. 文件接口边界

FCC 访问消费精确 representation/file identity 与受支持的当前文件访问凭据。凭据不入长期日志／版本哈希，过期重新授权。同一配置命中由原生机制证明；不能通过文件名相同或扫 RW 目录猜测。

状态分开：结构解析完成、文件可获取、文档打开、任务所需几何就绪、实例映射可执行。分段读取可能没有完整 JT，不能用单一 exists 判断离线完整。原生已加载也不能断言后续不需读文件。

任务所需文件如何保持可用要实测公开接口；安装类的内部锁方法不是可直接承诺的持久 pin API。若必须临时受控落盘，只能任务范围、明确用途和到期回收，不悄悄变长期数模库。

## 4. 文档会话状态机

`discovered → associating → associated → ready`；异常进入 `stale / disconnected / closed / mapping_rebuild_required`。

DocSession 记录设备、原生 PID＋启动身份、document identity／窗口证明、模型集合、观察 generation、水位、可用能力。PID 重用、窗口复用、文档关闭和集合替换均使对应证据失效。

禁止在正常只读探测中通过 COM activation 随意新建服务器。多实例匹配不明确时展示候选或报不支持，不关闭其他进程、不改操作目标。当前默认 ActiveDocument 路径逐步迁移到显式 DocSession。

外置模式不 SetParent、不隐藏用户主窗口、不全局抢焦点、不随 App 退出关闭用户文档。明确用户请求创建的会话也要区分进程所有权和文档所有权；是否退出由明确用户策略决定。

## 5. 模型集合与映射

集合映射含 `model_set_id + snapshot_occurrence_key → native handle(s)`，允许一个逻辑实例对应多个几何子节点。原生导出辅助节点不计为额外工程实例。相同 CAD ID、重复子装配、多阶段均不靠单键合并。

集合成员范围必须用于显隐、颜色、截图；自动化不能为截 TG1 而全局隐藏同文档 TG0 或用户新插入模型。需要隔离展示时记录范围和恢复策略。

SQLite 可保留业务到原生映射的候选，但使用前通过 PID 启动身份、文档、集合及相关 generation 校验；过期只重建受影响映射，不删绑定或重拉 JT。

## 6. 双向通知协议（内部候选）

通知包含 `session_id, document_generation, observation_sequence, origin, operation_id?, change_kind, affected_model_sets, affected_native_nodes, confidence`，不把未知原生变化冒充可信 TC 更新。

结构变化可靠同步为工作场景差异；选择／视角为短期交互。用户插入无来源模型可浏览、检查及明确保存，但 TC 绑定需补来源确认。用户移动产生场景变换，不自动写 TC 来源矩阵。

命令完成通知与用户事件合并去重，不因自己的高亮再发一次高亮。事件丢失／序号间隙先冻结相关写操作，进行限定范围对账；没有可用原生事件时才启用实测过的低频差异检测，不每次遍历整车。

## 7. 自由交互与自动化

空闲不持续校正视图；联动仅响应明确上下文变化。自动化前记录受影响状态，短期租约内执行，结束后条件恢复。用户同时修改相关状态且无法识别先后时暂停，不用快照强行覆盖。

原生调用仍遵守 STA／UI 线程限制，长调用可能阻塞另一文档。记录每次调用等待／执行时长，优先批量 API、增量数据及有限工作量。不能承诺任意 UI 都无卡顿。

## 8. 原生探测验收

同进程双文档、两个进程、双阶段同文档、关闭后窗口句柄复用、App 重启但原生保活、原生重启但文件保留、用户插入／删除／移动、事件丢失、FCC Offline／恢复、同文件跨配置命中。记录实际支持与不支持，不把模拟测试当原生运行通过。
