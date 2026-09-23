# App 插件打开与挂载实施记录

## 1. Change classification

implementation fix / compatible change：补齐市场打开入口、工作台标签与现有 SDK host 接线；为既有 mount/Gateway REST 适配器增加固定 Main 传输。后端 registry 增加权威 mount_expires_at，并直接读取运行 Gateway 已验证的 Catalog 快照。没有新增或重命名业务 Capability。

## 2. Authoritative context inspected

前端隔离工作树 orchestration-merge-frontend-20260905；后端隔离工作树 orchestration-merge-backend-20260905。已读 plugin_marketplace router、MountSessionService、Gateway.catalog、实际 SDK host.ts、市场模型、Electron preload/renderer boundary、实际 Snapshot/业务批准 store/service 与 Descriptor 的 LOCAL 枚举。

当前官方 Provider 加载器仍只加载冻结官方域模块。LOCAL_RUNTIME 是消费身份，不是第三方 Provider 注册机制；用户随后确认维护人，测试环境已解析既有身份，候选 GID/Snapshot 不是可运行批准。

## 3. Reuse, atomicity, and ownership result

沿用现有 SDK mountAi00Plugin 的 opaque-origin sandbox 和 channel token/source 校验；生成浏览器 bundle 带源码 SHA256，构建脚本可指定 SDK 源路径。Main 仅访问固定 plugin-marketplace registry/mount invoke/confirm/assets 路径，不接收任意 HTTP URL。业务调用保留 PLUGIN 身份进入既有 Gateway，不改成普通 desktop 用户能力调用。

插件资源经 ai00-plugin 协议转发：内部随机 handle 绑定 Main owner、当前登录 generation 和后端到期时间；签名资源 token 留在 Main。资源无缓存且限制 25MiB，路径遍历拒绝；脚本不开放网络、Node、文件或普通下载。普通成员可以打开 enabled/rolled_back 插件；管理写权限维持原规则。

## 4. Implementation boundary

前端：plugin_mount_client.js、main/preload/capability_client、市场 host/model/marketplace、tab_manager；新增 SDK 构建脚本与生成产物。后端仅 router 挂载 Catalog 来源与 expires_at 投影，未改审批规则或真实用户身份。新增隔离 Electron 测试和 Provider 技术试验，不载入当前账号数据。

审查修复：取消确认/普通操作失败保留 iframe；只有会话/授权失效销毁。取消错误用结构化 IPC 传输，避免 contextBridge 丢失 Error 自定义字段。到期时间来自服务端，不再用提前的固定 5 分钟。资源协议仅允许插件子 frame 导航，不允许成为顶层 App 或开放远程 renderer 网络。

## 5. Verification evidence

- 新 Main mount 单测7项通过；实际生成 SDK 的 JSDOM host/标签测试2项通过。
- 原市场测试11项通过，Electron生命周期安全脚本、Capability边界与废弃bridge检查通过。
- 后端挂载/生命周期/市场专项38项通过。
- 独立 Electron 41.8.0：真实 host.html → 生成 SDK → 正式 preload → 正式 Main IPC → 模拟后端路径通过；实际 custom protocol 脚本加载、sandbox、网络/Node拒绝通过。没有真实账号或业务数据库。
- Provider 隔离试验：独立隐藏 partition 能运行纯计算、拒绝 Node/网络；无限循环在 watchdog 后终止，证据计时1284ms。仅技术试验，内存/输出配额、批准绑定、跨插件路由、生命周期竞态与产物提交未验证。首次试验协议未在独立 partition 注册而失败，修复后再跑；旧证据覆盖前显式标 running，避免误读。
- 完整 test-governance 前端构建通过。当前测试 App PID336100、后端PID338792已加载本轮功能；health/ready=200，host.html/SDK静态资源=200。

前端原始输出目录 `.superpowers/marketplace-qa/`：mount-marketplace-tests.log、mount-boundary.log、mount-build.log、mount-electron-result.json、provider-isolation-probe.json。PID仅为本轮加载记录，不代表永久身份。

## 6. Governance status

advisory=true；本次专项 machine checks passed，但整库 machine_passed=unverified；human_approved=unverified；runtime_verified=unverified（当前账号实机与真实存储未验收）。未生成或代签正式 Snapshot/TestRun/ReleaseReport，未把模拟后台与用户登录态等同。

## 7. Findings and unresolved risks

当前 App 的真实账号上传/打开验收仍由用户后验；没有伪造登录令牌。第三方 Provider 注册、运行时路由和产物输出能力尚未实施完成，不能把此次 UI 挂载或隔离试验称为 Provider 支持。

用户已确认 CAD 首版支持任意数量线体；已通知 CAD 协调任务修订固定14槽候选契约。维护身份在本任务解析；候选发布者 huangjing、插件 huangjing.cad.layout-generator，尚未通过超管登记或正式注册能力。个人GID不在本共享报告重复记录。CAD算法、动态排布与DXF/JPG格式验收由CAD owner负责。没有将旧模板参数或占位namespace写入正式治理身份。
