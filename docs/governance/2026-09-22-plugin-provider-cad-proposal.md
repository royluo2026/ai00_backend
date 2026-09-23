# CAD 插件接入与市场通用扩展待办

状态：需求记录与候选方案；未实施、未批准。来源：CAD 协调任务 01a0c86f-090e-70a0-bf5a-0e5650e22170 转交的用户需求。仅交付 AI00 App 内插件；不控制 AutoCAD、不引入 COM。

执行中用户确认：CAD 首版支持任意数量线体，不沿用旧 14 槽固定模板。仍遵守明确的执行/内存/产物资源限额；不能静默截断、合并或丢弃线体。

双方已对齐的候选机器标识：publisher_id=`huangjing`，plugin_id=`huangjing.cad.layout-generator`；能力为 `huangjing.cad.layout.generate@1` 与 `huangjing.cad.drawing.export@1`，候选错误/审计前缀为 `huangjing.cad`。维护人已由用户确认，内部个人GID不在本文记录或转交。正式发布者登记、domain/命名授权、Capability GID、Snapshot与批准仍未完成；登记时须对新限定名称重新查重，不能沿用旧短名称的查重结果。业务候选契约由 CAD 任务维护于工作区 `docs/governance/2026-09-22-cad-capability-candidate.md` 及同名 `.schema.json`；机器身份不混入业务 payload。

## 1. Change classification

候选新增插件 Provider 机制及 CAD 业务 Capability；当前只新增本文，不修改运行时代码、Catalog 或权限。目标是生成可由 AutoCAD 打开的 DXF 与同一布局的 JPG，允许其他获授权插件复用业务能力。名称、版本与契约仍待审查。

## 2. Authoritative context inspected

- `backend/plugin_platform/manifest.py`：严格 v2 schema，只有 web runtime；capabilities.required/optional 是消费依赖（ID + major），plugins.required/optional 是精确插件版本依赖，permissions 为消费授权声明。不存在第三方 Provider 声明/执行协议；禁止 python/backend/executable 等声明。
- `backend/capability_v2/provider_loader.py`：官方域 Provider 的冻结模块、artifact hash、owner 校验；不可直接开放为第三方代码加载器。
- `backend/capabilities/plugin_marketplace_next.py`：已有安装、启停、升级健康确认、回滚、撤销、卸载。
- `docs/governance/capability-catalog-release.json`、Craft Provider：可复用 BOP 查询候选已存在；当前未用真实项目账号验证权限、分页与 plugin exposure。
- 前端 `packages/core/electron/desktop_artifacts.js`：已有 Artifact 下载验完整性、用户保存对话框；native_io.save 只允许固定能力。已有 JPG MIME 不等于插件导出全链路已支持，DXF 与插件产物创建/授权桥接需核验。
- `2026-09-22-plugin-marketplace-backend-e2e.md`：后台隔离链路通过；Electron 打开入口与 SDK 宿主接线尚未完成验收。

## 3. Reuse, atomicity, and ownership result

| 需求 | 现状与责任 |
| --- | --- |
| BOP 选择、固定版本读取 | 复用 craft.bop.version.list@1、craft.bop.version.get@1、craft.bop.structure.outline.get@1；明细按需用 craft.bop.work_package.get@2、craft.bop.entry.detail.get@1。Craft owner 维护原业务与权限。 |
| 统计 | CAD owner 完成分页、固定 revision 与来源记录；协调任务已核实 outline.total_lines、lines[].counts.stations。口径为 BOP 工艺节点，不能默认等于物理工位去重数。 |
| 布局生成 | CAD owner 提供业务算法、模板、坐标、尺寸、标注；平台不增加 CAD 专用 Base 取数或排布代码。 |
| DXF/JPG 生成 | CAD owner 用同一布局渲染两种输出，验证格式与可打开性；平台只提供通用受控产物与保存机制。 |
| 发布与生命周期 | 复用发布者签名、平台审核签名、不可变版本、依赖校验、revision 与撤销机制；新增 Provider 可用性联动尚未实现。 |

候选业务边界（不是已注册契约）：

1. 布局生成：输入数量、尺寸、模板版本及可选来源引用，输出带 schema/version 的布局与来源。纯计算、无隐式 BOP 查询或文件写入；校验/矩形/文字函数不分别注册。
2. 图纸导出：输入已确定布局、format=DXF/JPG，输出 artifact_ref、摘要、格式、大小。产物创建是独立授权副作用，幂等键绑定规范输入、格式和模板/实现版本；重试不得产生不受控重复产物。本机保存另由通用宿主动作完成，不暴露任意路径给插件。

## 4. Implementation boundary

最小候选方案与顺序（全部待实现）：

- P0：市场提供“打开插件”，接通当前 App sandbox 挂载与 SDK bridge；校验来源窗口、mount session、tenant、installation revision，过期/停用立即拒绝。先用 Hello 验证平台消费能力。
- P1：在版本化扩展契约中声明提供的能力；服务端绑定 publisher/plugin/owner、Capability ID、major、GID、精确业务哈希、Provider artifact hash 与批准 Snapshot。包签名仅证明包来源/完整性，不替代 Capability 治理审批。现有 v2 拒绝未知字段，需明确新 schema 兼容方案，不能直接追加字段假定生效。
- P1：候选采用独立受限 JS 执行上下文，不依赖页面是否打开；无 Node、任意文件/网络或 Python bridge。统一调度执行 schema、授权、依赖、资源配额、超时、取消、输出校验和审计。Worker 本身不足以证明安全隔离；隔离技术与绕过测试需先完成技术验证。
- P1：调用经 SDK → 受治理宿主路由 → 授权/策略检查 → 受限 Provider。调用上下文由可信宿主绑定调用方、用户、tenant、设备会话、安装版本/revision；不接受插件自报身份。被调用 Provider 再调用平台能力时必须传递并收窄调用链权限，禁止借用 Provider owner 的高权限。批准状态由可信服务端判定，不由本地 JS 判定。
- P1：本机 Provider 只注册为当前 App/设备会话可用，不广告为全平台服务。其他插件与 Agent 只有通过同一授权宿主路由且设备在线时可用；远端 Agent 无该路由返回不可用。本次不做跨设备调度。
- P2：复用 Artifact 服务与保存对话框；核验/补齐受控二进制产物创建、DXF/JPG MIME/扩展名及大小限制、摘要验证、目标选择、覆盖确认与取消/失败结果。具体限额待契约评审。不得通过 iframe 普通下载或任意路径 IPC 绕过机制。

Provider 生命周期契约要求：安装后停用不注册；启用需精确审批、依赖与隔离健康检查通过；升级准备态不暴露新绑定，成功后切换并令旧 revision 路由失效；回滚仅恢复仍获准且兼容的旧绑定；停用/撤销/卸载立即阻断新调用并取消旧会话执行，副作用边界重新检查 revision。已提交产物按保留策略处理，不承诺撤销已完成写入。

调用契约至少包含 capability_id、major、payload、request_id、必要幂等键；GID/Provider artifact/安装 revision 由受信路由解析绑定。候选稳定错误类别：未安装/停用/撤销、版本不兼容、依赖缺失、未批准或哈希不匹配、调用方无权限、设备不可用、超时/取消、输出无效、保存取消/失败。具体错误字符串待审查冻结，不作为现有 API。

owner 分工：市场/backend owner 负责声明、签名、安装态与治理绑定；桌面宿主 owner 负责执行隔离、设备作用域路由、挂载桥与本机保存；Capability 治理 owner 负责 Descriptor/Snapshot/审批和策略契约；CAD owner 负责业务定义、实现、模板与格式验收。数据库迁移与新增表本轮未设计；禁止直接跨 owner 写入。

## 5. Verification evidence

本次实际执行：只读 Get-Content/rg 检查上述源码和既有验收报告；新增文档后读回。未执行新运行时测试。既有后台 50 项回归与 SDK 2 项仅覆盖原链路，不能证明此扩展可用。

验收待办：

- [ ] App 内 Hello 打开、真实 SDK 调用、过期 mount/伪造窗口拒绝。
- [ ] CAD 固定 BOP revision、多页完整性、跨项目/租户越权与统计口径。
- [ ] 两个插件通过统一路由复用布局能力；无直接 import 或任意脚本入口；Agent 范围明确。
- [ ] 精确业务哈希/Snapshot/Provider artifact 绑定，未审批、篡改、旧批准复用均拒绝。
- [ ] 安装→启用→升级/失败恢复→回滚→停用/撤销→卸载的路由状态、并发调用与稳定错误。
- [ ] 网络/文件/Node 隔离、资源耗尽、超时、取消、权限传递与输出 schema 拒绝测试。
- [ ] 同一布局 DXF/JPG 内容一致；DXF 由目标软件实际打开，JPG 尺寸/标注可读；CAD owner 提供证据。
- [ ] 保存选择/取消/覆盖/失败/过大文件/摘要不符；插件无法自行指定本机任意位置。
- [ ] 当前 App 实机构建验收，真实数据库/存储验证，与受控后台替身测试分别记录。

code_revision：当前脏工作树，非冻结实现；snapshot_gid/test_run_gid/result_hash：unverified，不生成占位证据。候选 capability_id、capability_version_gid、owner team 精确标识、审计事件名、大小限额与事务参与者均待契约审查；来源数据按项目授权限制，敏感等级由 owner 确认。

## 6. Governance status

machine_passed=unverified；human_approved=unverified；runtime_verified=unverified；advisory=true。需求转交授权不等于实现方案、发布或治理审批。没有注册候选 Capability 或批准任何 Snapshot。

## 7. Findings and unresolved risks

现有能力消费契约不等于 Provider 支持；当前 Electron 实际打开仍缺验收。受控 JS 执行、安全策略可信来源和本机路由是必须实装验证的缺口。跨设备不在本轮范围。正式 Capability 名称/GID、owner 及契约需 CAD 与平台 owner 联审；当前仅记录方案，不改变既有官方 Provider 信任边界。
