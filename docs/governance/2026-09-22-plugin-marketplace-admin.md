# 插件市场 App 超管管理补充（advisory）

## 1. Change classification
新增 4 个原子 Capability，publisher.register 新增 major 2，保留旧 major 1；桌面管理消费迁移。旧 REST 平台管理角色收紧、审核/撤销强制摘要属于安全边界修复及兼容性变更，旧调用方必须传 release_sha256。未进行实际业务发布、撤销或人工治理审批。

## 2. Authoritative context inspected
已核对 Base official_provider、Catalog/Registry、plugin_platform owner 服务、签名 Manifest、Gateway 事务/确认策略、桌面共享 Capability client、官方 App manifest、旧 REST 管理入口及测试。旧 publisher.register@1/release.change.apply@1 为泛化未绑定接口，不用于新 UI。真实运行入口为当前两个 orchestration-merge 工作树。

## 3. Reuse, atomicity, and ownership result
复用 register_publisher、review_release、revoke_release owner 服务，不复制签名或跨租户撤销规则。每个写 Capability 一个主效果；release.review 的批准/拒绝为同一提交版本的审核决定。新读为有界 release.search 及当前用户 access flag。平台管理每次重读 Base 当前用户并校验 super_admin，不依赖页面角色。审核/撤销在 owner 行锁内核验 plugin_id、version、artifact SHA-256。旧 REST 旁路也收紧为超管。

## 4. Implementation boundary
Base owner 与已有 plugin_platform 服务、兼容 REST 和桌面消费者；未新增表或迁移。只向 web/api 暴露新能力，plugin/agent/mcp=false。服务自己提交 SQL 事务，按现有 desktop_actions 声明 external consistency，写入必须有幂等键及 admin 确认；不虚称 Gateway 强事务参与。桌面没有任意 HTTP 业务旁路。UI 入口：工作台 APP → 插件市场 → 右上角“超管管理”。支持待审核/已发布/已拒绝/已撤销列表、审核发布/拒绝、全租户指定版本撤销、发布者公钥登记。此补充不包含插件包上传向导、动态 Provider/Python 运行或正式签名安装包。

## 5. Verification evidence
后端 46 项专项通过（6 项新增管理测试），含真实 Gateway、SQLite SQL、缺确认拒绝、错误摘要拒绝、缺平台签名密钥拒绝、实际测试密钥签名、跨租户撤销且保留其他版本、发布者重复登记拒绝和旧 REST 角色边界。前端 8 项通过，含超管入口显隐、确认取消无写、摘要与版本 pin、失败禁用旧状态；Electron 生命周期安全和 IPC 边界通过。独立只读审查发现并修复事务声明与旧 REST 权限两项问题。Catalog --check 通过。
完整 test-governance 构建通过；8 个实际 HTTP 资源与 dist-test-governance 字节一致；当前 App 原资源地址 localhost:5173 已提供新版。后端 PID 308272 运行既有本地测试 launcher，health/ready 200，新管理能力在本地 Catalog 中。登录态桌面点击/真实业务写未验证，未伪造用户令牌。后端日志出现既有 Windows GBK 对 emoji 的日志编码错误，应用启动完成、健康探测正常；这不是业务写成功证据。

## 6. Governance status
machine_passed=false：此前报告记录的整库无关回归失败仍未消除，本次专项通过。
human_approved=unverified；runtime_verified=unverified；advisory=true。
源码、各 Capability GID/业务哈希、日志摘要见同日 admin-evidence.json；这些本地证据不是受信任 Snapshot/TestRun，也不是发布批准。不修改签名 ReleaseReport。

## 7. Findings and unresolved risks
真实登录 App 的界面重新加载及平台审核、跨租户撤销验收仍 unverified。实际发布依赖已配置的平台签名密钥，未配置时明确拒绝。当前 owner 自提交与 Gateway outcome 持久化并非同一强事务；发生结果未知时必须刷新权威状态再操作，不宣称 exactly-once。旧 REST 因强制超管和摘要而拒绝旧弱调用者，这是有意的边界收紧。正式签名发布仍需要精确版本/业务哈希/Snapshot 的可信人工审批。
