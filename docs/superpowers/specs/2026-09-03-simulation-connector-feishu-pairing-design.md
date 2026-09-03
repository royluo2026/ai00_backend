# 数模仿真域 AI00 Connector/VisMockup 迁域与飞书身份配对设计

## 1. 目标与范围

AI00 Connector 不直接登录飞书，也不接收、存储或刷新飞书访问令牌。用户先在 AI00 Web 完成飞书登录，再在网页确认一台 Windows 工作站的短期配对申请。服务端将当前 AI00 `user_gid`、活动租户、Connector 安装实例和运行 VisMockup 的 Windows SID 绑定。

本期只支持一个 AI00 用户绑定一个 Connector。完成后数模页面自动解析该用户唯一的在线 Connector，不再要求手工输入 `device_id`。

AI00 Connector、数模工作站、VisMockup Adapter、心跳、执行计划、回执和配对全都属于 `simulation` 域。`device` 域只表示工厂/物理设备业务，不再承载这些对象、Capability、Provider、运行时表或 HTTP 实现。

本期不包含多用户切换、多个 Connector 选择、无人值守自动升级、通用第三方软件账户授权或飞书 MCP 授权。

## 2. 变更分类

- Type: `new Capability` + `breaking change` + `deprecation/retirement`
- Reason: 现有实现只有管理员创建 enrollment token 和 Connector 命令行激活，没有飞书登录用户可完成的网页确认、领取和自动绑定读取闭环；同时 Connector 与 VisMockup 被错误放入 `device` 域。
- Compatibility: 新增 Simulation 能力和浏览器配对协议；旧 Device/无域前缀能力全部停止新消费并提供有期限的兼容适配。签名执行计划的线协议保持兼容，但 Capability ID、Provider owner、数据库 owner 和 HTTP canonical path 发生迁移。

## 3. 方案选择

采用浏览器设备码授权：Connector 生成临时公私钥与高熵 verifier，创建短期配对申请并打开 AI00 验证页；已通过飞书登录的用户在网页确认；Connector 以 verifier 证明申请所有权并领取只对临时公钥可解密的设备凭证。

不采用以下方案：

- 网页复制长 enrollment token：实现较少，但令牌容易进入剪贴板、工单或录屏，且体验差。
- Connector 内嵌飞书 OAuth：扩大飞书令牌暴露面，形成第二套登录会话和回调维护面。

## 4. 所有权与边界

所有 AI00 Connector 与 VisMockup 原子能力均属于 `simulation` 域，由 Simulation Provider 注册、授权、审计和测试：

| Capability | 原子业务效果 | 调用者 |
|---|---|---|
| `simulation.connector.pairing.request@1` | 为一个 Connector 安装实例创建短期、未绑定用户的数模工作站配对申请 | Connector bootstrap consumer |
| `simulation.connector.pairing.approve@1` | 将一个待确认申请绑定到当前飞书登录对应的 AI00 用户和租户 | AI00 Web 用户 |
| `simulation.connector.pairing.complete@1` | 在已批准申请上向原始安装实例交付一次可重复读取的加密设备凭证包 | 同一 Connector bootstrap consumer |
| `simulation.connector.binding.read@1` | 返回当前用户唯一数模 Connector 的绑定和在线状态 | AI00 Web 用户 |
| `simulation.connector.health.get@1` | 返回当前用户绑定 Connector 的受限健康状态 | AI00 Web/Simulation workflow |
| `simulation.connector.plan.queue@1` | 持久化一份精确、已签名、面向数模 Adapter 的本地执行计划 | Simulation workflow |
| `simulation.vismockup.status.get@1` | 读取 VisMockup 进程和文档状态 | Simulation workflow |
| `simulation.vismockup.application.launch@1` | 在绑定用户会话启动 VisMockup | Simulation workflow |
| `simulation.vismockup.model.open@1` | 在 VisMockup 打开已授权数模制品 | Simulation workflow |
| `simulation.vismockup.tree.get@1` | 有界读取当前 VisMockup 数模结构树 | Simulation workflow |
| `simulation.vismockup.selection.highlight@1` | 高亮指定数模节点集合 | Simulation workflow |
| `simulation.vismockup.visibility.change.apply@1` | 原子改变指定数模节点可见性 | Simulation workflow |
| `simulation.vismockup.capture.create@1` | 使用 VisMockup 内部截图生成受治理截图制品 | Simulation workflow |

`device` 域不再是依赖方或技术所有者。Connector 控制面从 `plugins/device` 迁入 `plugins/simulation`；Connector 数据使用 Simulation 数据库连接；Canonical HTTP adapter 改为 Simulation 路由。`local-runtime` 目录仍是 Windows 客户端部署物，不代表 Device 领域归属。

受影响消费者是 Simulation workflows、AI00 Web 数模插件与 AI00 Connector Service/Tray。Craft 只消费最终截图附件能力，不依赖 Connector 内部能力。

历史 Device 迁移文件保留以保证迁移链不可变，但其表在切换后只允许迁移/核对工具读取，运行时代码不得继续访问。

## 5. Capability 业务定义

### 5.1 `simulation.connector.pairing.request@1`

- `capability_version_gid`: unverified；注册时由权威治理存储生成，禁止代码内伪造。
- lifecycle status: `experimental`
- `business_effect`: 创建一个可由飞书登录用户确认、且只可由原始 Connector 安装实例完成的短期数模工作站配对申请。
- invariants:
  - `simulation.connector.pairing.request.proof`: 申请必须包含受支持的临时公钥、verifier challenge、安装实例 ID、Windows SID 和防重放 nonce。
  - `simulation.connector.pairing.request.expiry`: 申请最多存活五分钟，重复 nonce 不得创建第二个有效申请。
- inputs: `installation_id`, `windows_sid`, `device_name`, `runtime_version`, `ephemeral_public_key`, `verifier_challenge`, `nonce`。
- outputs: `pairing_id`, 非敏感短码 `user_code`, `verification_uri`, `expires_at`, `poll_interval_seconds`。
- stable errors: `pairing_rate_limited`, `pairing_request_invalid`, `pairing_nonce_reused`, `connector_version_unsupported`。
- permissions and resource scope: 无用户权限；仅允许受限 `LOCAL_RUNTIME` bootstrap consumer，按安装实例、源地址和租户未知态限流。不得授予其他数模能力。
- transaction policy: Simulation 数据库单事务创建申请和审计记录。
- idempotency: `installation_id + nonce`。
- side effects: 创建短期配对申请；不创建设备、不绑定用户。
- audit event: `simulation.connector.pairing.requested`。
- sensitive-data scope: confidential；verifier 仅存哈希，短码仅存服务端 keyed hash。

### 5.2 `simulation.connector.pairing.approve@1`

- `capability_version_gid`: unverified。
- lifecycle status: `experimental`
- `business_effect`: 将用户明确确认的待配对数模工作站绑定到当前飞书身份映射的 AI00 用户及活动租户。
- invariants:
  - `simulation.connector.pairing.approve.current_actor`: `approved_user_gid` 只能来自服务端认证会话，不能由请求体传入。
  - `simulation.connector.pairing.approve.single_user`: 一个用户只能保有一个未吊销的数模 Connector 绑定；已有绑定时返回冲突，不静默替换。
  - `simulation.connector.pairing.approve.pending`: 只有未过期且未被批准、拒绝或完成的申请可批准。
- inputs: `user_code`, `expected_resource_version`, confirmation token；设备摘要由服务端从申请读取。
- outputs: `pairing_id`, `status=approved`, `approved_at`, 安全展示用设备摘要。
- stable errors: `pairing_not_found`, `pairing_expired`, `pairing_already_decided`, `connector_binding_conflict`, `confirmation_required`, `resource_version_conflict`。
- permissions and resource scope: `simulation.use`；资源为当前用户和待确认 pairing；必须进行用户确认。
- transaction policy: Simulation 数据库强事务，锁定 pairing 与当前用户绑定索引；Connector 凭证尚不在本步骤创建。
- idempotency: Gateway idempotency key 加 `pairing_id`；相同用户对同一申请重复确认返回同一结果。
- side effects: 记录批准主体与租户；不向浏览器返回设备密钥。
- audit event: `simulation.connector.pairing.approved`。
- sensitive-data scope: confidential。

### 5.3 `simulation.connector.pairing.complete@1`

- `capability_version_gid`: unverified。
- lifecycle status: `experimental`
- `business_effect`: 向已获用户批准且持有原始 verifier 的 Connector 安装实例交付其单用户数模设备绑定凭证。
- invariants:
  - `simulation.connector.pairing.complete.proof`: verifier、安装实例 ID 与临时公钥必须匹配原申请。
  - `simulation.connector.pairing.complete.approved`: 未批准、过期、拒绝或主体冲突的申请不得创建设备凭证。
  - `simulation.connector.pairing.complete.encrypted`: 浏览器、日志和 Simulation 数据库不得出现明文设备令牌或计划签名密钥；交付包只可由申请中的临时私钥解密。
- inputs: `pairing_id`, `installation_id`, `verifier`。
- outputs: `status=completed`, `connector_id`, `encrypted_credential_envelope`, `envelope_hash`, `expires_at`。execution-plan v1 线协议中的旧字段 `device_id` 仅作为兼容序列化别名。
- stable errors: `pairing_not_found`, `pairing_expired`, `pairing_not_approved`, `pairing_proof_invalid`, `credential_issuance_failed`, `credential_envelope_unavailable`。
- permissions and resource scope: 仅受限 `LOCAL_RUNTIME` bootstrap consumer；proof-of-possession 绑定 pairing。
- transaction policy: Simulation 数据库强事务。以唯一 `pairing_id` 创建 Connector 绑定、令牌哈希和加密回执；明文凭证只在内存中生成并立即加密，中断进入 reconciliation，不盲目重建凭证。
- idempotency: `pairing_id`；在领取窗口内相同证明重复读取同一密文和哈希。
- side effects: 创建设备凭证并完成数模 Connector 绑定。
- audit event: `simulation.connector.pairing.completed`；审计只记录哈希和标识符。
- sensitive-data scope: restricted secret envelope。

### 5.4 `simulation.connector.binding.read@1`

- `capability_version_gid`: unverified。
- lifecycle status: `experimental`
- `business_effect`: 返回当前用户唯一数模 Connector 的绑定身份、在线状态和可用 Adapter 摘要，供数模页面自动选择执行目标。
- invariants: 无业务决策；只读取当前认证用户的唯一绑定，不能按请求体查询其他用户。
- inputs: 空对象。
- outputs: `binding` 可空；存在时含 `connector_id`, `device_name`, `installation_id`, `status`, `last_seen_at`, `connector_version`, `adapter_ids`。
- stable errors: `connector_health_unavailable`, `provider_unavailable`。
- permissions and resource scope: `simulation.use`；主体来自认证会话。
- transaction policy: Simulation read-only；绑定与健康投影标明各自观察时间。
- idempotency: read-only，不需要幂等键。
- side effects: none。
- audit event: `simulation.connector.binding.read`。
- sensitive-data scope: confidential；不返回 Windows SID、设备令牌或密钥。

### 5.5 既有 Connector 能力迁域

#### `simulation.connector.health.get@1`

- `capability_version_gid`: unverified；lifecycle status: `experimental`。
- `business_effect`: 返回调用者唯一绑定数模工作站的 Connector、用户会话、Adapter 与目标应用健康投影。
- invariants: `simulation.connector.health.bound_user` 要求绑定用户与认证主体一致；读取不得创建执行计划。
- inputs: 可选 `binding_id`，缺省解析当前用户唯一绑定；不接受任意用户 ID。
- outputs: 绑定 ID、Connector/SessionHost/Adapter/VisMockup 状态、版本、心跳时间。
- stable errors: `connector_binding_not_found`, `connector_offline`, `provider_unavailable`。
- permissions/resource: `simulation.use` + 当前用户绑定；read-only，无幂等键、无外部副作用。
- transaction/audit/sensitivity: Simulation 只读；`simulation.connector.health.read`；confidential。

#### `simulation.connector.plan.queue@1`

- `capability_version_gid`: unverified；lifecycle status: `experimental`。
- `business_effect`: 验证并持久化一份精确签名的数模本地执行计划，供绑定用户的 AI00 Connector 领取一次。
- invariants: `simulation.connector.plan.bound_identity` 约束用户、租户、绑定和安装实例；`simulation.connector.plan.exact_contract` 约束协议、Adapter、操作、schema hash、payload hash 和 idempotency；拒绝不得创建本地工作。
- inputs/outputs: 沿用 Connector execution-plan v1 与 `OperationRef`，但目标字段使用 Simulation binding identity。
- stable errors: `connector_binding_not_found`, `connector_offline`, `connector_contract_mismatch`, `connector_plan_conflict`, `provider_unavailable`。
- permissions/resource: 仅 Simulation workflow/internal Gateway；资源为 simulation binding 与上游 Simulation run。
- transaction/idempotency: external consistency；以 `plan_id + plan_hash` 幂等，Device 域不参与。
- side effects/audit/sensitivity: 写入 Simulation plan/outbox，供 Connector 出站领取；`simulation.connector.plan.queued`；confidential。

### 5.6 VisMockup 原子能力迁域

所有 VisMockup Capability 的 owner 为 `simulation`、lifecycle 为 `experimental`、execution mode 为 `LOCAL`、local-runtime exposure 为 true，Web/API/plugin/agent/MCP 默认 false。它们只供已治理的 Simulation workflow 编排，不能绕过环境搭建或截图运行直接从 Web 调用。

| Capability | `business_effect` | 主要输入/输出 | 稳定错误与原子性 |
|---|---|---|---|
| `simulation.vismockup.status.get@1` | 返回绑定会话中 VisMockup 与当前文档状态 | binding；进程/文档摘要 | `connector_offline`, `vismockup_unavailable`; read-only |
| `simulation.vismockup.application.launch@1` | 在绑定用户交互会话启动一个 VisMockup 实例 | binding；进程结果 | `interactive_session_unavailable`, `vismockup_launch_failed`; plan ID 幂等 |
| `simulation.vismockup.model.open@1` | 在 VisMockup 打开一个已授权且哈希匹配的数模制品 | artifact ref；document ref | `artifact_not_authorized`, `model_open_failed`; artifact hash 幂等 |
| `simulation.vismockup.tree.get@1` | 有界读取当前文档结构树 | document ref, max depth/nodes；tree | `document_not_open`, `tree_limit_exceeded`; read-only |
| `simulation.vismockup.selection.highlight@1` | 将精确节点集合设为高亮选择 | document ref, node refs；selection summary | `node_not_found`, `selection_failed`; plan step 幂等 |
| `simulation.vismockup.visibility.change.apply@1` | 对精确节点集合执行一种可见性改变 | document ref, node refs, action；visibility summary | `node_not_found`, `visibility_change_failed`; plan step 幂等 |
| `simulation.vismockup.capture.create@1` | 使用 VisMockup 内部渲染生成与操作步骤绑定的截图制品 | document/run/step refs, capture settings；artifact ref/hash | `document_not_open`, `capture_failed`, `artifact_upload_failed`; outcome_unknown 禁止自动重拍 |

共同规则：

- `capability_version_gid`: 均为 unverified，注册时从权威治理存储取得。
- permissions/resource: `simulation.use`，且 plan、binding、document、run/step 必须属于同一用户和租户。
- transaction: COM 外部效果使用 external consistency、租约、回执和 outbox；读操作为 read-only。
- side effects: 仅表中明确的本地应用效果；不得执行任意 COM 方法名。
- audit: 使用对应 `simulation.vismockup.*` 事件，记录标识符与哈希，不记录密钥或完整敏感 payload。
- sensitive-data scope: confidential；截图制品按既有 Simulation/Craft artifact policy 管理。

### 5.7 旧能力关闭映射

| 旧 Capability | 处理 | 替代 Capability |
|---|---|---|
| `device.connector.health.get@1` | deprecated，所有 exposure 关闭，Provider fail-closed | `simulation.connector.health.get@1` |
| `device.connector.plan.queue@1` | 保持 deprecated/fail-closed | 不再提供兼容替代 |
| `device.connector.plan.queue@2` | deprecated，所有 exposure 关闭，Provider fail-closed | `simulation.connector.plan.queue@1` |
| `vismockup.status@1` | deprecated，所有 exposure 关闭 | `simulation.vismockup.status.get@1` |
| `vismockup.launch@1` | deprecated，所有 exposure 关闭 | `simulation.vismockup.application.launch@1` |
| `vismockup.model.open@1` | deprecated，所有 exposure 关闭 | `simulation.vismockup.model.open@1` |
| `vismockup.tree@1` | deprecated，所有 exposure 关闭 | `simulation.vismockup.tree.get@1` |
| `vismockup.highlight@1` | deprecated，所有 exposure 关闭 | `simulation.vismockup.selection.highlight@1` |
| `vismockup.visibility@1` | deprecated，所有 exposure 关闭 | `simulation.vismockup.visibility.change.apply@1` |
| `vismockup.capture@1` | deprecated，所有 exposure 关闭 | `simulation.vismockup.capture.create@1` |
| `local.command.get@1`, `local.device.*@1` | 若只被 Connector 消费则 deprecated/fail-closed；若 Device 域另有物理设备用途，必须由 Device owner 重新定义后才能保留 | 不作为 Connector 兼容入口 |

## 6. 数据与状态机

Simulation 新增领域迁移，拥有：

- `workmanship_sim_connector_pairings`：申请、challenge/keyed-code hash、临时公钥、安装实例、Windows SID 摘要、状态、版本、批准主体、租户、过期时间、加密回执及哈希。
- `workmanship_sim_connector_bindings`：`user_gid` 唯一的有效数模 Connector、安装实例、设备令牌哈希、状态与审计时间。
- `workmanship_sim_connector_health` 与 `workmanship_sim_connector_heartbeat_audit`：当前健康投影和追加式心跳审计。
- `workmanship_sim_connector_plans` 与 `workmanship_sim_connector_projection_outbox`：签名执行计划、租约、结果与跨步骤投影 outbox。
- 如旧 command 协议仍需迁移期兼容，则使用 `workmanship_sim_connector_legacy_commands`；新业务不得继续写 `workmanship_runtime_commands`。

配对状态机：`pending → approved → completing → completed`。终态还有 `rejected`、`expired`、`reconciliation_required`。只有 `pending` 可被批准；只有 `approved` 或可恢复的 `completing` 可完成；完成失败但外部效果未知时不得退回 `approved`。

所有新表由 `AI00_SIMULATION_DDL_DB_URL` 迁移并通过 Simulation 数据库连接访问。不得通过 `AI00_DEVICE_DB_URL` 运行 Connector、VisMockup 或配对逻辑。

短码不是授权凭证，只用于定位申请。授权由飞书会话对应 AI00 身份的确认产生；领取权由 verifier 与临时私钥证明。

## 7. Web 与 Connector 交互

1. Connector Tray 首次启动生成临时密钥、verifier 和 nonce，调用 request Capability 的协议适配 API。
2. Connector 打开 `https://<ai00>/simulation/connector/pair?code=<非敏感短码>`。URL 不包含 token、verifier 或凭证。
3. 未登录用户走现有飞书登录，登录成功后返回原配对页。
4. Web 读取申请安全摘要，显示设备名、Connector 版本和掩码后的 Windows 用户信息；用户点击确认。
5. Web 经 Capability Gateway 对 approve 获取 confirmation token 后执行写入。
6. Connector 按服务端 `poll_interval_seconds` 领取；成功后解密并使用 DPAPI 保存设备凭证，删除临时私钥和 verifier。
7. 数模页面调用 binding.read；一个在线绑定自动选择，无绑定时显示“绑定 Connector”，离线时显示最后心跳与排障入口。

浏览器不得直接访问 localhost，Connector 不开放入站 HTTP 端口。Service 继续主动出站，SessionHost 继续在绑定 Windows 用户会话中运行 VisMockup COM。

## 8. 错误处理与恢复

- 用户拒绝或超时：Connector 删除临时材料并允许重新申请。
- 浏览器重复确认：相同用户幂等返回；不同用户或已有绑定返回冲突。
- 完成响应丢失：相同 verifier 可在短领取窗口内重新取得相同密文，不创建第二个 Connector 绑定。
- Connector 凭证密文已创建但状态未完成：记录 `reconciliation_required`，后台只读取/对账同一 pairing 的既有密文和哈希，不重放凭证创建。
- Windows 提权：配对必须记录安装后实际运行 SessionHost 的 SID；若安装程序使用不同管理员账号，不得把管理员 SID 当作目标用户 SID。
- 用户退出飞书或 AI00：不立即吊销设备；解绑/吊销属于后续独立 Capability。调度仍要求当前 AI00 用户与绑定一致。

## 9. 兼容与迁移

- Provider 迁移：`connector_runtime.py`、Connector contracts/descriptor policy、控制面仓储及公开端口从 `plugins/device/device_backend` 移入 `plugins/simulation/simulation_backend`。Device Provider 停止注册 Connector/VisMockup；Simulation Provider 注册所有新能力。
- 数据迁移：用受控、幂等、可复跑的部署脚本从旧 `workmanship_runtime_devices/enrollments/commands` 和 `workmanship_device_connector_*` 读取 Connector 行，写入 `workmanship_sim_connector_*`。脚本按主键保存源/目标行数和规范化内容哈希；目标冲突必须 fail-closed，不覆盖。
- 切换顺序：停止新计划入队 → 等待已租赁计划完成或转 reconciliation → 迁移与核对 → 切换 API/Provider/Connector client → 恢复入队。禁止跨库双写；回滚只切回旧只读快照前的应用版本，不反向覆盖已发生的新结果。
- 零数据环境也必须产生迁移报告，明确源行数为 0；不能据代码推测“尚未生产”而跳过核对。
- 现有 `/api/v1/devices/enrollments`、`/api/v1/device-runtime/*`、`/api/v1/connector/*` 与 `AI00.Connector.Service.exe pair --token-stdin` 暂时保留为兼容适配；其实现改为调用 Simulation Provider，不得再引用 Device Provider 或 Device 数据库。完成一次发布迁移后返回明确 deprecation headers，再按审核期限关闭。
- Canonical HTTP path 使用 `/api/v1/simulation/connector/*`；Connector 新版本只调用 canonical path。
- 新 Web 不展示旧长令牌，不依赖旧入口。
- 数模截图页删除手工 `device_id` prompt，改为 binding.read；没有唯一有效绑定时拒绝创建执行计划。
- `device.connector.plan.queue@2` 被关闭并迁移到 `simulation.connector.plan.queue@1`；Connector execution-plan v1 的签名线协议暂时不变，旧 `device_id` JSON 字段只表示 `connector_id` 的兼容别名，下一线协议版本再更名。

## 10. 验证策略

必须按 TDD 顺序先看到失败，再实现：

- Simulation Capability 合同：正常、无效/null、过期、重复 nonce、版本冲突、用户冲突、幂等与闭合输出。
- Provider：真实状态机、唯一用户约束、权限拒绝、确认令牌、过期、并发批准、外部效果未知与对账。
- 迁域合同：旧 Capability 全部 fail-closed，新 Simulation ID 解析到 Simulation Provider；旧 ID 不得通过任何 exposure 或 Local Runtime 身份执行。
- 数据迁移：空库、正常数据、部分已迁移、目标冲突、租约中计划和 outbox reconciliation；逐表行数与规范化哈希核对。
- 安全：短码不能领取、错误 verifier 被拒绝、密钥不进入 URL/日志/Simulation 明文字段、跨用户读取被拒绝。
- 领域边界：Simulation Connector 代码、路由和运行时测试不得导入 `device_backend`、`get_device_conn` 或 `AI00_DEVICE_*`；Device 领域依赖图中不得再出现 Connector/VisMockup。
- Connector .NET：临时密钥生成、浏览器 URL、轮询节流、密文解密、DPAPI 保存、SID 匹配、响应丢失重试。
- Web：飞书登录返回、确认前摘要、确认动作、无绑定/在线/离线状态、自动设备选择、无 localhost 请求。
- 端到端：Web 飞书会话 → 配对确认 → Connector 凭证 → 心跳 → binding.read → 数模执行计划。

实机 VisMockup COM 验收仍单独记录，不由离线配对测试替代。

## 11. Governance 状态

- `machine_passed`: unverified；尚未实现或运行本规格测试。
- `human_approved`: unverified；用户对产品设计的确认不等同于受信 `super_admin` 对精确 `business_definition_hash` 的治理审批。
- `runtime_verified`: unverified；尚未在试点 Windows/VisMockup 机器完成配对与 COM 链路验收。
- `advisory`: true。
- `code_revision`: 规格起草基线 `065868ce`；实现提交后重新记录。
- `snapshot_gid`, `test_run_gid`, `result_hash`: unverified。

## 12. Findings 与未决风险

- finding: 现有配对 HTTP 路由没有对应的数模域原子 Capability，Web 也没有消费者入口。
- finding: 现有 enrollment 创建要求 `system.tech_config`，不适合作为普通数模用户日常绑定流程。
- finding: 当前数模 Web 仍通过 prompt 接收 `device_id`，无法证明设备属于当前飞书用户。
- finding: `device.connector.*`、`vismockup.*`、Connector Provider/路由以及七组运行时表的现有 owner 与业务归属冲突，必须整体迁移，不能只增加 Simulation facade。
- unverified: Gateway 是否已有可表达无用户 bootstrap consumer 与 proof-of-possession 的认证策略；实现前必须读取并复用，不能伪造用户 actor。
- unverified: 旧 Device 数据库是否已有生产 Connector 数据；若存在，部署前必须生成迁移清单、行数/哈希核对和可恢复切换证据。
- blocked: stable 发布、治理审批与 runtime_verified；不阻塞 experimental 实现和机器验证。
- required human decisions: 本规格由业务所有者确认后进入计划；实现完成后仍需受信 super_admin 审核精确版本和定义哈希。

## 13. Pre-submission checklist

- [x] Atomicity: 申请、确认、领取、读取可独立授权、失败、重试、审计和测试。
- [x] Identity: 新 Capability ID、Simulation owner 和消费者已明确；GID 等待权威注册。
- [x] Security and data: 身份、proof、确认、幂等、事务、密钥和敏感数据边界已声明。
- [x] Relationships: Connector/VisMockup 的 Simulation 单一所有权与旧 Device 能力关闭映射已明确。
- [ ] Verification: 实现与真实测试尚未运行。
- [ ] Evidence: Snapshot、测试运行与结果哈希尚不可用。
- [x] Authority: 产品设计确认、机器验证、治理审批和实机验证保持独立。
