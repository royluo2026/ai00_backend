# 数模仿真域 AI00 Connector 产品内连接设计

## 1. 决策

AI00 Connector 的正常入口统一放在数模仿真页面，并可在工作台显示同一状态摘要。用户不再手工访问独立配对页，不再抄写配对码，也不再填写 Connector 设备 ID。

首次绑定仍要求当前飞书登录用户明确点击一次“确认绑定”。验证码、设备证明、临时密钥和凭据领取继续存在，但只作为底层安全协议，不暴露为业务操作。

本设计替代 `2026-09-03-simulation-connector-feishu-pairing-design.md` 中关于“Connector 打开独立验证码页面”的用户交互；其身份边界、加密交付、单用户约束、Simulation 领域所有权和 Capability Gateway 要求继续有效。

## 2. 当前问题

当前实现把协议步骤直接交给用户：先运行命令行配对程序、自动打开独立页面、确认后再等待本地写入。页面无法说明 Connector 是否安装、服务是否启动、凭据是否落盘或 VisMockup 是否可用。

更严重的是，服务端当前在 Connector 本地保存凭据之前就把绑定标记为完成。本地写入失败时会留下“服务端已有绑定、客户端没有凭据”的半完成状态；再次配对可能触发唯一约束并被包装为 HTTP 500。这不是用户重复点击能解决的问题。

## 3. 采用方案

采用“产品内发起 + Windows 自定义协议唤起 + 服务端受治理中转”的方案。

不恢复浏览器直连 `127.0.0.1:7654`。生产 Web 不能直接调用工作站 HTTP Bridge；Connector 继续只主动出站，Service 与 SessionHost 继续使用受限 named pipe。这样不会绕过 Capability Gateway，也不要求客户开放本机入站端口。

安装包安装并立即启动轻量 Windows Service，注册 `ai00connector://` 自定义协议，并为当前用户注册轻量托盘启动项。Service 随系统启动并通过一条出站通道保持在线；它不依赖用户进入配对页才运行。

首次绑定时，数模页面创建一个短期、单次、绑定当前用户和租户的启动票据，然后通过自定义协议把票据交给已经运行的 Connector。自定义协议只承担首次绑定或恢复时的本机交接，不负责启动常驻服务，也不负责后续在线。Connector 使用该票据提交设备证明；数模页面在原位置显示设备摘要并要求用户确认。确认后 Connector 领取加密凭据、使用 DPAPI 落盘并回执激活。

独立 `pair.html` 只保留为有期限的兼容和诊断入口，不出现在正常导航、安装引导或 Connector 默认行为中。

## 4. 用户流程

### 4.1 页面初始状态

数模页面调用当前用户范围内的 Connector 绑定与健康能力，并只显示以下一种明确状态：

- **未连接**：没有当前用户的有效绑定，显示“连接本机 Connector”。
- **连接中**：已有未过期启动票据，显示检测进度和取消操作。
- **待确认**：Connector 已提交设备证明，显示设备名、Windows 用户掩码和 Connector 版本，并显示“确认绑定”。
- **已连接但离线**：存在绑定但心跳超时，显示“检查 Connector 服务”和诊断提示；不得自动重新配对。
- **已连接**：显示 Connector、SessionHost 和 VisMockup 的分层状态。
- **需要恢复**：服务端已签发凭据但未收到本机激活回执，显示“恢复连接”。
- **绑定冲突**：当前用户绑定了另一安装实例，显示旧、新设备摘要；替换必须再次明确确认。

页面不得把 `provider_failed`、数据库唯一约束、设备 ID 或 HTTP 500 直接作为用户提示。

### 4.2 首次连接

1. 用户在数模页面点击“连接本机 Connector”。
2. Web 通过 Gateway 创建一个两分钟有效、单次使用的启动票据。
3. 浏览器打开 `ai00connector://pair?...`；URI 只携带网关标识和不透明短期票据，不携带飞书令牌、设备凭据或计划签名密钥。
4. 若 Connector 在限定时间内未领取票据，页面显示“未检测到 Connector”，提供安装包和“已安装，重新交接”两个操作；该提示不等同于服务端已证明本机未安装。
5. Connector 领取票据，持久化受 DPAPI 保护的临时恢复材料，再提交安装实例、临时公钥、verifier challenge、版本和掩码设备摘要。
6. 页面在原位置进入“待确认”，用户核对摘要并点击一次“确认绑定”。
7. Connector 轮询领取只可由临时私钥解密的凭据包，先安全落盘并读回校验，再向服务端发送激活回执。
8. 服务端收到激活回执后才把绑定标记为 `active`。页面自动切换为“已连接”，无需刷新或跳转。

### 4.3 启动 VisMockup

绑定成功后，数模页面通过 Simulation Capability 查询 Connector/SessionHost/Adapter/VisMockup 状态。用户点击“启动并连接 VisMockup”时，Web 只提交受治理的 Simulation 操作；服务端生成签名 ExecutionPlan，Connector 出站领取，SessionHost 在绑定用户会话内串行调用 VisMockup Adapter。

浏览器不得恢复 `_bridge()` 或直接调用 COM、本地端口和任意 Connector operation。

## 5. 状态与恢复

配对状态机调整为：

```text
bootstrap_created
  -> device_claimed
  -> user_approved
  -> credential_issued
  -> active

任意非终态 -> expired | cancelled
credential_issued -> recovery_required -> credential_issued | revoked
active -> offline | revoked | replacing
```

`credential_issued` 不等于完成绑定。只有 Connector 完成 DPAPI 写入、读回校验并提交持有证明后才能进入 `active`。

Connector 必须在发起申请前持久化受 DPAPI 保护的临时私钥、verifier、pairing ID 和安装实例 ID。进程退出、系统重启或网络中断后，重新启动时优先恢复同一申请并领取同一密文，不新建第二个绑定。

同一用户、同一 `installation_id` 的再次连接视为恢复或凭据轮换，不是绑定冲突。不同安装实例替换现有绑定时，旧凭据只在新设备成功激活后撤销；失败时保留旧绑定，避免把用户锁死。

所有数据库唯一约束冲突都必须转换为稳定业务错误，并保留审计证据；不得泄漏为 `provider_failed` 或 HTTP 500。

## 6. Capability 变更

所有能力归 `simulation` 域，HTTP 仅为 Gateway 的规范适配器。

| Capability | 业务效果 | 调用者与确认 |
|---|---|---|
| `simulation.connector.binding.get@1` | 返回当前用户绑定、在线和恢复状态，不接受任意用户 ID | Web；只读 |
| `simulation.connector.pairing.bootstrap.create@1` | 为当前登录用户创建短期单次启动票据 | Web；不单独确认 |
| `simulation.connector.pairing.bootstrap.get@1` | 返回当前用户启动票据和安全设备摘要 | Web；只读 |
| `simulation.connector.pairing.request@1` | Connector 使用启动票据提交设备证明和加密领取材料 | Local Runtime bootstrap consumer |
| `simulation.connector.pairing.approve@1` | 当前用户明确批准所见设备或替换设备 | Web；必须用户确认 |
| `simulation.connector.pairing.complete@1` | 原 Connector 证明持有 verifier 后领取可重放的同一加密凭据包 | Local Runtime bootstrap consumer |
| `simulation.connector.pairing.activate@1` | Connector 证明凭据已安全保存，使绑定转为 active | 已签发 Connector 凭据 |
| `simulation.connector.pairing.cancel@1` | 当前用户取消未完成的启动票据或配对 | Web；写操作 |

现有配对能力仍为 `experimental`。实现前必须依据当前 Catalog 的实际生命周期和消费者重新判定是否原地修订；若任何能力已进入 `stable` 或合同被外部消费者采用，则按 major-version 规则新增版本，不原地破坏。

每个 Provider 必须返回结构化 EvidenceRef，审计链至少关联 user request、bootstrap、pairing、installation、binding、credential envelope hash 和 activation。明文 verifier、临时私钥、设备令牌与计划签名密钥不得进入数据库、浏览器、日志或审计详情。

## 7. 组件职责

### Web 数模插件

- 只负责呈现连接状态、发起票据、唤起自定义协议、显示安全摘要和收集一次明确确认。
- 自动选择当前用户唯一 active Connector；不要求输入设备 ID。
- 工作台只复用状态摘要和深链，不复制配对逻辑。

### Simulation 后端

- 拥有配对、绑定、健康、替换和恢复状态机。
- 在事务内执行资源版本、唯一绑定、激活和旧凭据撤销。
- 将数据库异常映射为稳定 Capability 错误。
- 只通过 Gateway 暴露能力；路由不得直接调用领域仓储绕过 Provider。

### AI00 Connector

- MSI 安装并启动 Service、注册 Tray 登录启动项和 `ai00connector://`。Service 随系统启动并轻量常驻；Tray 随交互用户登录启动。
- 自定义协议处理器只接收允许的网关标识和不透明启动票据；拒绝未知 scheme 参数、非 HTTPS 生产网关和非 allowlist 主机。
- 用 DPAPI 保护正式凭据和未完成配对恢复材料。
- 正式凭据验证成功后发送激活回执；失败时保留可恢复状态并在托盘显示明确诊断。
- 托盘只显示状态、诊断、重新连接和解绑，不承载业务操作。
- SessionHost 和业务 Adapter 按任务启动；无任务时不得为了探测软件而常驻或高频轮询。

### Adapter 扩展

Connector 是通用本机能力桥，不是 VisMockup 专用程序。未来的 CATIA、飞书桌面端、内网文件或其他本机 Adapter 共用设备身份、单一出站通道、Capability Gateway 授权、签名 ExecutionPlan 和审计链，但每个 Adapter 仍需独立的白名单操作、权限、Schema、凭据边界和版本合同。

纯云端飞书及其他 SaaS 集成默认由 AI00 服务端完成。只有确实依赖本机桌面客户端、Windows 登录态、客户内网出口或本机文件时，才允许新增 Connector Adapter；不得为了统一形式把云能力搬到工作站。

## 8. 安装和兼容

开发环境允许显式配置 `http://127.0.0.1:8080`，生产安装包只接受受信任的 HTTPS 网关。安装完成后 Service 立即启动，当前用户 Tray 启动；首次进入数模页面即可绑定。绑定完成后 Service 使用设备凭据持续心跳和领取任务，用户日常进入页面不再执行配对。

未注册自定义协议时，浏览器无法可靠区分“未安装”和“未启动”。因此页面通过启动票据是否被 Connector 领取来判断：超时后给出安装/启动指引，不声称已经检测到本机程序。

旧命令行 `pair --gateway ...` 和独立配对页保留一个迁移期，只用于支持人员诊断。它们必须使用同一 Capability 状态机，不能形成第二套绑定逻辑。

## 9. 资源预算

常驻部分必须保持轻量，资源预算作为发布门禁而不是建议值：

- 空闲状态下 Connector Service 加 Tray 的总私有工作集目标不超过 `100 MB`；超出时必须形成性能 Finding 并说明原因。
- 连续十分钟空闲状态下平均 CPU 低于 `1%`，不得使用忙等或高频空轮询。
- 无任务时不启动 SessionHost、VisMockup Adapter 或其他业务 Adapter；任务结束并超过有界空闲期后释放 COM、进程、文件和网络句柄。
- Service 使用一条共享长轮询或长连接接收任务；断线采用带抖动的指数退避，Adapter 不得各自建立后台轮询。
- 心跳周期和离线判定由服务端合同统一配置；页面不得通过提高轮询频率制造“实时”假象。
- 日志按大小轮转并设置总量上限；临时配对材料、下载制品和任务临时文件必须有有界保留期和受控清理。
- 活跃任务允许短时超过空闲预算，但必须记录 Adapter 级 CPU、内存、执行时长和释放结果，防止任务结束后资源不回落。

## 10. 验证

### 自动化

- Capability 合同、权限、confirmation、幂等、资源版本、EvidenceRef 和稳定错误测试。
- 同一安装恢复、不同安装替换、重复确认、票据重放、过期、篡改和并发唯一约束测试。
- 在“签发凭据后、本地写入前”注入失败，验证服务端不会误报 active，Connector 重启后可恢复同一申请。
- Connector DPAPI 写入、读回、临时材料清理和 URI 参数 allowlist 测试。
- 数模页面每个状态的渲染、按钮可用性、轮询停止条件和错误文案测试。
- Service/Tray 十分钟空闲 CPU、私有工作集、句柄、线程和网络请求频率预算测试。
- 验证无任务时 SessionHost 和业务 Adapter 不存在，完成任务后在有界时间内退出并释放资源。
- Catalog、Descriptor、Provider hash、consumer ref、路由和前端治理扫描通过。

### 真实运行

- 使用签名安装包安装，验证 Service、Tray、自定义协议和卸载。
- 从数模页面完成首次连接，全程不输入验证码和设备 ID。
- 人为结束 Connector、断网和重启 Windows，验证自动恢复和状态一致性。
- 制造一次本地凭据写入失败，验证“恢复连接”能够闭环且不会产生重复绑定。
- 启动真实 VisMockup，验证 Connector、SessionHost、Adapter、COM 和页面状态逐层一致。
- 空闲、执行任务和任务结束后三个阶段采集资源数据，确认常驻预算与资源回落。

自动化通过只能设置 `machine_passed`。真实 Windows/VisMockup 链路完成前 `runtime_verified=false`；正式业务描述和版本仍需超管在治理中心批准，不能用本次页面确认替代 `human_approved`。

## 11. 非目标

- 不恢复网页直连 7654。
- 不让 Connector 持有飞书 OAuth token。
- 不在一期支持一个用户同时选择多台 Connector。
- 不把任意 COM 方法或本地命令暴露给 Web。
- 不在本改造中实现飞书桌面 Adapter、自动升级、通用 MCP Adapter 或新的数模业务编排；本设计只固定未来扩展必须复用的边界。

## 12. 完成标准

- 新用户只需安装一次，并在数模页面点击“连接本机 Connector”和一次“确认绑定”。
- 正常流程不出现独立配对页、验证码、设备 ID、命令行或原始 HTTP/Provider 错误。
- 服务端 active、Connector 本地凭据和在线心跳不存在半完成假成功。
- 同一设备可安全恢复，不新增重复绑定；更换设备必须明确确认且失败可回退。
- 数模页面能从未安装/未连接一直引导到 Connector 在线和 VisMockup 可操作。
- 安装后 Service 随系统轻量常驻；无任务时不运行 SessionHost 和业务 Adapter，且通过空闲资源预算。
- 后续本机 Adapter 复用同一设备连接与治理链，纯云能力默认不经 Connector 绕行。
- Capability 治理、审计和发布门禁保持 fail closed。
