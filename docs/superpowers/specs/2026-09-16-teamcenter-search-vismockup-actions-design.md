# Teamcenter 搜索与 VisMockup 显式打开设计

## 目标

在 AI00 仿真模型文件区域提供独立的 Teamcenter 登录、选项目和模糊搜索入口，并把在线模型读取与 VisMockup 打开解耦。用户选择并保存在线模型后，可以明确选择“新 VisMockup 文档打开”或“插入当前 VisMockup 文档”。

## 既有事实

- Teamcenter 14 安装位于 `D:\Siemens\Teamcenter14`，Visualization 14 位于 `D:\Siemens\Visualization14`。
- Teamcenter 搜索沿用保存查询语义，目标字段为 Item ID、名称和精确 Revision ID；不提供错别字纠正或语义搜索。
- `D:\Siemens\Visualization14\Program\VisAutomation.tlb` 声明了 `Documents.Open`、`ActiveDocument` 和 `Document.InsertDocument`。现有 Connector 已有对应 COM 包装和本地文件生命周期测试。
- Teamcenter `Visualization-2013-05-DataManagement.createLaunchInfo` 能生成保持在线身份的 VVI；VVI 含短期会话材料，不能进入网页、普通日志或持久化业务数据。

## 交互设计

### 登录

Teamcenter 登录使用独立弹窗。模型选择弹窗不再包含账号和密码。

页面显示三种本机状态：未登录、已登录（显示账号）、会话失效。登录成功后状态保持到用户主动退出或 Connector/App 进程退出。密码只存在本机 Connector 受控内存中，不使用 localStorage、sessionStorage、浏览器 cookie、后端数据库或日志；应用重启后重新登录。

登录控制通道增加 `status` 和 `logout`。状态响应只返回状态、脱敏账号和错误码，不返回凭据。退出时清零账号密码字符缓冲。

### 两个入口

在线模型选择弹窗包含两个页签：

1. **选项目**：只输入项目号。规范化后形成 `项目号-ENG0001`，Revision 固定为 `00;1`。如果用户误输入后缀或版本，界面不做二次拼接，而是明确提示只输入项目号。
2. **搜索**：输入框 placeholder 固定为“输入要搜索的零组件 ID”。支持 Item ID 和名称的精确、前缀、包含匹配；Revision ID 若填写则精确匹配。无错别字、拼音或语义扩展。

搜索排序稳定为：精确 Item ID、Item ID 前缀、Item ID 包含、名称匹配；同等级按 Item ID、Revision ID 排序。返回最多 20 条，界面必须由用户选择唯一结果。

### 修订规则和日期

登录成功后由 Connector 调用 Teamcenter `getRevisionRules()` 返回服务器真实规则名称。界面使用下拉框，优先默认 `Latest Working`；服务器没有该规则时选择第一项并明确显示。配置日期继续使用可编辑的 `datetime-local`，传输为带时区 ISO 8601 字符串。

### 保存与 VisMockup 动作

选定来源后先执行只读结构观察并加入当前 AI00 仿真环境，不自动调用 Visualization。

每个 Teamcenter 在线模型显示两个按钮：

- **新 VisMockup 文档打开**：生成一次性 VVI，在 VisMockup 应用中调用 `Documents.Open(vviPath)`；没有运行实例时由既有连接层启动 VisMockup，再打开新文档。
- **插入当前 VisMockup 文档**：要求已有活动文档，调用 `ActiveDocument.InsertDocument(vviPath)`。没有活动文档时失败关闭，返回 `vismockup_active_document_required`，界面给出可行动提示。

现有 `simulation.teamcenter.visualization.launch.request@1` 保持兼容，但其实现收紧为显式新文档打开。新增 `simulation.teamcenter.visualization.insert.request@1` 和 Connector 操作 `teamcenter.visualization.insert@1`。两条操作均需用户确认，且必须绑定当前用户的 Connector。

## 在线 VVI 安全边界

Teamcenter worker 生成 VVI 后通过受控 stdin/stdout 协议只发送随机受限临时文件路径和非敏感身份摘要，并继续保持 SOA 会话。临时文件位于 Connector 状态根下的专用目录，ACL 仅允许当前 Windows 用户，文件名不可预测。C# Connector 在同一受控操作内将该路径交给 COM，随后回传一次 `consumed` 或 `failed` 确认；Java 收到确认后才删除 VVI、退出 Teamcenter 并结束进程。超时、取消、COM 失败和进程异常均由两侧 `finally` 尝试删除材料。这样避免先 logout 导致短期在线票据在 VisMockup 读取前失效。

VVI 正文、SessionID、CredToken 不得进入 stdout JSON、诊断管道、执行计划结果、审计事件或异常文本。日志只允许记录 operation id、来源身份哈希、耗时和分类错误码。

## 能力与合同

- `simulation.teamcenter.revision_rule.search.request@1`：只读，返回本机 Teamcenter 规则列表。
- `teamcenter.revision_rule.search@1`：Connector 原子操作。
- `simulation.teamcenter.product.search.request@1`：兼容扩展为显式 `query`、可选精确 `revision_id`、`match_mode=exact_prefix_contains`；底层原子合同相应升级为 `teamcenter.product.search@2`，旧 v1 保留。
- `simulation.teamcenter.visualization.launch.request@1`：兼容的新文档动作。
- `simulation.teamcenter.visualization.insert.request@1`：新增写操作，用户确认。
- `teamcenter.visualization.insert@1`：新增 Connector 原子操作。

生成的 Catalog、能力文档和 release lineage 由仓库脚本重建，不手工编辑生成产物。`machine_passed`、`human_approved` 和 `runtime_verified` 独立记录；没有真实 Teamcenter/VisMockup 联调证据时不得把 `runtime_verified` 标为真。

## 错误行为

- 未登录：`teamcenter_login_required`。
- 会话验证失败：清除内存凭据并返回 `teamcenter_session_expired`。
- 规则列表为空：`teamcenter_revision_rules_unavailable`。
- 搜索词为空、过长或含控制字符：`teamcenter_search_input_invalid`。
- 搜索无结果不自动降级为语义搜索。
- 插入时无活动文档：`vismockup_active_document_required`。
- VVI 创建、消费或清理失败使用分类错误码，任何错误文本不得包含 VVI 内容。

## 验证

自动化测试覆盖：控制协议闭集、凭据清零、登录状态生命周期、项目号拼接、匹配排序、规则默认值、日期序列化、保存后不自动启动、两个按钮路由、无活动文档失败关闭、VVI 临时文件清理、能力合同和治理生成检查。

真实环境验证分开执行：登录一次后连续规则读取和搜索、精确项目选择、模糊搜索、新文档打开、插入当前文档、退出后拒绝访问，以及进程退出后不保留登录。
