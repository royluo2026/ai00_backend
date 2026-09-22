# Local Viewer Interaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for inline execution, or superpowers:subagent-driven-development when independent workers are available and selected. Read the linked spec before implementation. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** TC 来源不变，把已加载数模的人工交互从逐条服务端任务迁移到限定授权下的本地通道，并以真实点击与画面时延验收。

**Architecture:** 服务端签发限定当前模型来源、运行文档和操作集合的短期授权；Electron 主进程持有授权，通过专用命名管道传给 Connector。Connector 持有节点映射、统一执行门和本地审计，复用现有 STA/VisMockup Adapter；业务保存和自动任务仍走签名计划。

**Tech Stack:** 现有 Python/FastAPI/Pydantic、MySQL、Electron/Node、C# .NET 8 Windows、命名管道、VisMockup COM；不增加运行时依赖，不重建 Python Bridge。

**Spec:** `../specs/2026-09-22-local-viewer-interaction-design.md`（用户已确认设计，并回复 go 批准本计划实施；不等于发布或运行验收）。

## Global Constraints

- 不新增 localhost HTTP 服务，不向浏览器或远程网页开放通道，不提供任意 COM/脚本/文件调用。
- 环境历史文档身份不得作为新文档打开成功的前提。
- TTL 60 秒，第 30 秒后台续期；单调时钟限制期限，注销/明确撤销/窗口销毁/进程重启立即失效。
- 请求上限 64KiB、单批最多 256 个 node_ref、每会话最多 32 个待处理请求。
- 先显示、隐藏、高亮、取消高亮，再接入其他已列明的交互；COM 对象仅在同一个 STA 使用。
- 未知结果不重放，不能因本地超时自动退回服务端重发同一控制。
- 不逐点击查 TC、服务端授权、历史执行结果或全树结构。
- 开关默认关闭；不打开整车或其他用户文档；只在获准的诊断小零件上验证，有局部装配权限后再做装配验收。
- 热操作目标：响应 P50 ≤100ms、P95 ≤300ms；实际画面变化 P95 ≤500ms。未测量不能宣称达标。
- 新能力、Provider/Catalog 和消费端例外走现有正式发布检查；普通设计确认不替代发布授权。

## 工作目录、变更保护与基线

`B = E:/Projects/ai00_v3/.worktrees/orchestration-merge-backend-20260905`，`F = E:/Projects/ai00_v3/.worktrees/orchestration-merge-frontend-20260905`，均为现有 test worktree。下文路径相对 B/F。已有大量用户修改和暂存内容，不能清理、整体 git add/commit 或创建空白 worktree后遗漏当前实现。先按 using-git-worktrees 技能确认现有隔离环境，逐文件保存改动前摘要和 diff。

已知基线：上一阶段后端相关测试 25 通过、15 跳过；前端 adapter 25 通过、队列 5 通过；bootstrap 有旧资源版本断言失败。执行前重跑确认，不把旧记录当当前证据。修复版本测试时同时验证实际资源加载，不仅改正则。

本计划不安排自动提交。每个任务完成保存任务级 diff 和测试结果；只有获得提交指示后才按精确文件/改动块提交，不夹带用户暂存内容。

## Review Focus

1. 主窗口允许但子页面/弹窗不可信：不可借父窗口转发调用取得权限（任务 2、5）。
2. 续期乱序与系统时钟回拨：旧授权不能延长或替换新授权，断网到期停止写入（任务 1、2）。
3. 同名零件、多次实例、原生窗口外部结构变动：映射不能误控其他节点（任务 3）。
4. COM 调用后断管道/崩溃/超时：不能报告未执行，也不能跨通道自动补发（任务 4、6）。
5. 本地交互与服务端多步骤任务竞争、磁盘满、审计积压：明确 busy/quarantine/backpressure，不静默继续（任务 4、6）。

## 固定接口与信任边界

以下为本计划要新增的接口，不表示已经存在。

授权业务能力 `simulation.viewer.interaction.authorize@1` 输入仅为 workspace_gid、document_gid、source_association_id、客户端随机 session_nonce 和续期时的 prior_grant_id；请求者不能自行选择 actor、tenant、runtime、任意操作或 TTL。服务端从已鉴权上下文、设备绑定和本次来源关联推导它们。

```json
{
  "protocol": "ai00.viewer.interaction.grant.v1",
  "grant_id": "server-generated-id",
  "grant_generation": 1,
  "session_nonce": "main-generated-random-value",
  "actor_id": "bound-actor", "tenant_id": "bound-tenant",
  "device_id": "bound-device", "runtime_instance_id": "current-runtime",
  "workspace_gid": "10", "document_gid": "20",
  "source_association_id": "current-open-association",
  "document_session": "sha256:<64 hex>",
  "operations": [{"id":"vismockup.node.visibility.change@1","contract_hash":"sha256:<64 hex>"}],
  "policy_version": "registered-policy-version",
  "issued_at": "server UTC timestamp", "expires_at": "issued_at plus 60 seconds",
  "audience": "ai00.connector.viewer-interaction",
  "key_id": "trusted-key-id", "signature": "P256 signature"
}
```

使用现有 canonical JSON/P256 算法和可信公钥配置；签名字节加独立用途前缀 `ai00.viewer.interaction.grant.v1\n`，禁止把 grant 当 execution-plan 或反向使用。授权签名字段不参与被签名内容。增加 grant_generation，续期必须在同一 session_nonce 内严格递增；旧 generation 不再安装。

主进程对页面公开：`viewerInteraction.open({workspace_gid,document_gid})`、`resolve({interaction_id,source_nodes})`、`execute({interaction_id,operation_id,targets,arguments})`、`close({interaction_id})`。open 只打开交互会话，不打开模型文件。页面不能提供 source_association、签名授权、sequence、COM key、PID 或管道名；Main 解析权威关联并生成 request_id/sequence。

管道封闭消息类型：install_grant、resolve_nodes、execute、query_request、close。新请求/结果协议放在 `ViewerInteractionProtocol.cs` 与 JS client，使用共同 JSON fixtures。结果：completed/rejected/busy/outcome_unknown；批量结果按目标逐项返回。query_request 只返回已接受请求的结果，不重新执行。

## Task 1: 服务端授权、来源关联与审计接收合同

**Files (B):**
- Create `backend/contracts/viewer_interaction_v1.py`。
- Create `plugins/simulation/simulation_backend/application/viewer_interaction.py`。
- Create `plugins/simulation/simulation_backend/capabilities/viewer_interaction.py`。
- Create `plugins/simulation/simulation_backend/data/viewer_interaction_repository.py`。
- Create `backend/db/migrations/domains/simulation/0028_viewer_interaction.sql`（执行前检查编号未被其他任务占用）。
- Modify `plugins/simulation/simulation_backend/capabilities/connector_runtime.py` 的注册入口，及 `live_documents.py` 的本次 online bind 集成。
- Test `plugins/simulation/tests/test_viewer_interaction_authorization.py`、`backend/tests/test_viewer_interaction_repository.py`、`backend/tests/fixtures/viewer_interaction_v1.json`。
- Catalog/Provider 由现有治理工具生成评审产物，不手改既有发布快照以伪造新版本。

**Interfaces:** `authorize_interaction(context, request, repository, signer, now) -> SignedGrant`；repository 提供 `authorize_scope(...)`、`append_events(...)`。source association 来自成功的本次来源绑定，持有 workspace/document/source revision/runtime/document_session；旧绑定不完整时明确拒绝，不回查同名旧文档。现有绑定不能表达的字段增量存入新表，不更改旧绑定字段语义。

- [ ] 先增加闭合 Schema、共同签名测试向量和授权测试。测试工具 `grant_case` 放在测试文件内，固定 NOW、60 秒期限，创建两个不同 tenant/workspace 及真实临时 SQL repository；仅签名密钥用测试密钥。

```python
def test_grant_is_limited_to_current_source_and_runtime(grant_case):
    grant = grant_case.authorize()
    assert (grant.expires_at - grant.issued_at).total_seconds() == 60
    assert grant.document_session == grant_case.current_document_session
    assert grant_case.authorize_other_tenant().error_code == 'interaction_scope_denied'
    assert grant_case.authorize_previous_document().error_code == 'interaction_binding_stale'
```

- [ ] 运行 `python -m pytest plugins/simulation/tests/test_viewer_interaction_authorization.py backend/tests/test_viewer_interaction_repository.py -q`，确认缺失行为失败，而非依赖/权限错误。
- [ ] 实现受事务保护的作用域解析和签发；续期重新核验权限/来源关联/当前 runtime，仅增加 generation，不再读取历史 launch 结果。新表按 grant_id、source_association_id、(device_id,request_id) 设置唯一键/查询索引；租户/用户检查与授权数据写入在同一事务。

```python
scope = repository.authorize_scope(context, request, now)
claims = scope.claims(session_nonce=request.session_nonce,
                      issued_at=now, expires_at=now + timedelta(seconds=60))
return signer.sign_interaction_grant(claims)
```

`scope.claims` 仅接受已核验字段，按上述封闭 schema 生成 claims；signer 从现有服务端密钥配置注入，缺失时 fail closed，绝不下发私钥。

- [ ] 增加受设备认证的审计批次端点 `/api/v1/simulation/connectors/v2/viewer-interaction/events` 到 `backend/routers/simulation_connector.py`，注册对应传输治理条目。批次带设备签名、grant/request/sequence/outcome 摘要，最大 256 事件/1MiB；过期 grant 的历史结果仍可上传，但不由上传恢复执行权限。相同摘要幂等、不同摘要冲突，事务提交后才返回 ack。
- [ ] 增加跨租户、过期 runtime、注销、源关联变化、乱序续期、篡改签名、重复上传冲突测试，跑新增 tests 及现有 live-document/connector SQL 套件。真实 MySQL 测试未执行时单列，不用 SQLite 代替锁竞争验收。

## Task 2: 限定会话与本地管道

**Files (B):** 新增 `local-runtime/src/Ai00.Connector.Contracts.V2/ViewerInteractionGrant.cs`；AppHost 新增 `ViewerInteractionProtocol.cs`、`ViewerInteractionSession.cs`、`ViewerInteractionPipeHost.cs`；修改 `Program.cs`；测试 `local-runtime/tests/Ai00.Connector.Tests/ViewerInteractionProtocolTests.cs`、`ViewerInteractionSessionTests.cs`。

**Files (F):** 新增 `packages/core/electron/viewer_interaction_client.js`、同目录 `.test.js`；修改 `connector_host_manager.js`、`main.js`、`preload.js`、`capability_client.js`。

**Interfaces:** `ViewerInteractionGrant.ParseAndVerify(json, trustedKeys)`；`ViewerInteractionSession.Install(grant, liveContext, timestamp)`；`Validate(request, liveContext, timestamp)`；`Invalidate(reason)`。JS `ViewerInteractionClient` 方法 open/resolve/execute/close，使用现有 native pipe binding，不新增 socket 服务。

- [ ] 写协议与时间测试，fixture 中一份合法 grant 对照 Python 签名向量。使用可注入单调时间源，不靠真实 sleep 等一分钟。

```csharp
// test rig uses production ParseAndVerify/Install/Validate and a fake clock only.
rig.InstallSignedGrant(ttlSeconds: 60, generation: 1);
rig.AdvanceMonotonic(TimeSpan.FromSeconds(61));
Assert.Equal("authorization_expired", rig.ValidateControl().ErrorCode);
Assert.False(rig.InstallOldGeneration(1));
```

`ViewerInteractionRig` 放在测试目录，负责载入 fixture、签测试 grant、创建固定 liveContext 和可控时间；禁止在产品实现添加测试专用授权入口。

- [ ] 运行 `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter FullyQualifiedName~ViewerInteraction -m:1 /nodeReuse:false`，确认期限、错 scope 和乱序续期测试先红。
- [ ] 实现 `.ViewerInteraction` 管道：当前用户 ACL、拒绝远端、对端 PID 双向校验、64KiB 帧限制、唯一 request_id、closed JSON schema。复用现有安全参数，不将业务消息发送到 DiagnosticPipeHost 或 TeamcenterControlPipeHost。
- [ ] Main 内部通过现有鉴权 capability client 获取授权，不经 Renderer 接收签名结果；将 session_nonce、窗口 webContents/frame 身份与 interaction_id 绑定。校验 trusted sender 后还要核对会话所属窗口；拒绝父窗口代理不可信 iframe 的任意转发。
- [ ] 续期任务在 Main 每 30 秒触发，只保持一个在途续期；Connector 以剩余 wall-clock 时长和本地 monotonic deadline 中较短者限时。明确撤销/登出/窗口关闭立即 invalidate；断管道停止 admission。安装失败不自动重新打开模型。
- [ ] 跑 JS client、ConnectorHost manager 和 C# 管道/会话 tests；负测包含未知字段、伪造 PID、另一个合法窗口盗用会话、任意方法、超大帧、用户注销和重启前授权重放。

## Task 3: 本地来源实例映射

**Files (B):** 新增 `local-runtime/src/Ai00.Connector.Adapters.VisMockup/ViewerNodeRegistry.cs`；修改 `VisMockupAdapter.cs`、`IVisMockupCom.cs` 的局部解析/事件边界；测试 `ViewerNodeRegistryTests.cs`、`VisMockupCadLocatorTests.cs`、`VisMockupDocumentLifecycleTests.cs`。

**Interfaces:** `ResolveNodes(sourceAssociationId, documentSession, structureEpoch, sourceNodes)` 返回逐项 node_ref/status；`ResolveTarget(nodeRef, liveContext)` 返回当前数值 key；`InvalidateStructure(reason)` 提升 epoch 并清映射。sourceNodes 只含已关联来源下的完整 occurrence path/单零件根标识，不接受页面任意数值 key。

- [ ] 用现有 FakeVisMockupCom 建立同名不同路径两个节点；增加运行文档切换、删除再插入复用 key、结构事件缺失时的局部标识不符测试。

```csharp
var left = rig.ResolveOccurrence("/assembly/left/bolt");
var right = rig.ResolveOccurrence("/assembly/right/bolt");
Assert.NotEqual(left.NodeRef, right.NodeRef);
rig.Hide(left.NodeRef);
Assert.False(rig.LeftVisible);
Assert.True(rig.RightVisible);
rig.ChangeDocument();
Assert.Equal("document_session_changed", rig.TryHide(left.NodeRef).ErrorCode);
```

此 rig 使用生产 registry/adapter 与现有 COM fake；增加精确路径固定节点，不使用名称猜测。先跑新增和现有 locator/lifecycle 测试得到预期失败。

- [ ] 实现 session + epoch + occurrence path 缓存，复用 `_sessionNodeKeys` 而非增加并行权威缓存。opaque node_ref 随机生成且仅当前 registry 可解释；容量沿用现有 4096 映射上限，淘汰返回映射过期，不自动全树扫描。
- [ ] 所有打开/插入/关闭/切换/刷新入口集中提升代次；续期不清除映射。首次 resolve 单独有界处理；控制目标未映射时明确返回 unmapped，不在 execute 内递归全树。
- [ ] 以安装类型库/现有代码验证外部结构事件，先只读探测。在无法可靠监听的情形，使用节点存在性与缓存的 CADID/实例路径作本地局部检查；不能可靠辨认的场景拒绝快路径。测试局部检查不会调用 JT metadata 或加载几何。
- [ ] 热重复控制测试断言一次 resolve 后 100 次操作不重复调用树遍历/TC。使用计数器记录真实 registry 对 Fake COM 的边界调用；检查最终节点状态，不只检查 mock 是否存在。

## Task 4: 共享调度、去重和本地审计

**Files (B):** AppHost 新增 `ViewerExecutionGate.cs`、`ViewerInteractionExecutor.cs`、`ViewerInteractionJournal.cs`、`ViewerInteractionAuditWorker.cs`；修改 `PlanExecutionWorker.cs`、`Program.cs`；测试 `ViewerInteractionExecutionTests.cs`、`ViewerInteractionJournalTests.cs`、`OutcomeUnknownRecoveryTests.cs`。

**Interfaces:** gate `TryEnterInteractive()` / `EnterPlanAsync(ct)` / `Quarantine(reason)`；executor `ExecuteAsync(request, ct)` 与 `QueryRequest(requestId)`；journal `Admit` / `Complete` / `ReadPendingUpload` / `AcknowledgeBatch`。同一 gate 实例注入计划执行器和交互执行器，覆盖整个多步骤计划，而不只某一个 COM 调用。

- [ ] 先写计划持锁期间交互 busy、COM 结果未知后仍拒绝新写、重复 request 不重复写、同 request 不同内容拒绝、记录失败不执行测试。

```csharp
using var plan = await rig.Gate.EnterPlanAsync(CancellationToken.None);
Assert.Equal("busy", (await rig.ExecuteHide()).Status);
Assert.Equal(0, rig.ComWrites);
```

第二组独立测试对同一 request 执行两次，断言实际 COM 写次数为 1 且两个结果相同；第一次已调用 COM 后模拟断管道，query_request 返回 completed 或 outcome_unknown，绝不再次调用 COM。

- [ ] 红测后实现固定 allowlist 到现有 Adapter 方法的分派；show/hide、highlight/unhighlight 使用绝对值。重用 STA，不创建第二条 COM 执行线程。支持 256 目标的逐项结果；遇到未知停止后续项并标记 not_started。

```text
校验授权/epoch → 非阻塞尝试共享 gate → 检查重复与序列
→ 持久化 admission → STA 内复核会话并执行
→ 持久化 outcome → 返回结果 → 后台上传
```

- [ ] 本地日志为独立追加流，唯一键 interaction_id/request_id；恢复时只有 admission 的写请求标为 unknown，不重放。初始磁盘积压上限 64MiB 或 10000 个未确认请求，任一达到即拒绝新写；每 2 秒或满 128 条上传一批，最大不超过服务端 256 条/1MiB，ack 后才回收已确认段。
- [ ] 去重保留完整会话内已接受 request 的结果；会话关闭后以日志回收策略处理。Main 分配严格递增 sequence，Connector 拒绝未见过但小于已接受水位的请求，防止去重条目清理后重放。续期不重置水位。
- [ ] 超时前未派发返回 rejected；COM 已派发后超时 quarantine，并保留 gate 隔离状态，即使底层 Task 后来完成也不能自动恢复写权限。只有有界结果核对证明完成/未发生才恢复，否则要求恢复或新进程。
- [ ] 故障注入测试覆盖磁盘满、半条日志、上传重复/冲突、长时间断网、日志上限、COM 永不返回以及计划多步骤互斥。运行整个 .NET 套件；需要真实 Windows ACL/DPAPI 时请求相应运行权限，不把沙箱失败当产品回归。

## Task 5: 页面接入与生命周期

**Files (F):** 新增 `packages/sim-plugin/web/cad_sim/viewer_interaction.js`、`.test.js`；修改 `live_document_adoption.js`、`live_document_bootstrap.js`、`cad_sim.js`、`index.html` 及相应 tests；修改 `scripts/desktop_runtime_allowlist.json` 和 `scripts/test_no_desktop_business_bypass.js` 的受控例外测试。

**Interfaces:** `createViewerInteraction({api,onState})` 返回 open/resolve/execute/close；api 是 Task 2 的固定 preload 接口。四种动作映射到已注册 operation_id + action，禁止 Renderer 自建任意 HTTP/pipe 路由。

- [ ] 行为测试先证明：本地会话就绪后 show/hide/highlight/unhighlight 只调用 local execute，不再调用 `_requestVisMockupCommand`/`command.get`/binding.get；失败时图标不伪造成功。

```javascript
await rig.openBoundViewer();
await rig.resolveSelectedNode();
for (const action of ['show','hide','highlight','unhighlight']) await rig.act(action);
assert.equal(rig.cloudCommandCount, 0);
assert.deepEqual(rig.completedActions, ['show','hide','highlight','unhighlight']);
```

`rig` 在测试文件内实例化生产 controller，使用本地 API fake 返回封闭协议结果；cloud capability stub 一旦被调用即失败。分别检查终态 UI、目标 node_ref 和四种 action。

- [ ] 在本次打开/内嵌/运行关联完成后建立交互会话，不再添加历史文档绑定前置条件。映射准备作为独立状态，loading/mapping_pending 与控制完成分开。关闭环境、切换文档、窗口导航立即 close。
- [ ] 移除前端对快路径的临时权威映射和每次 binding.get，保留旧路径兼容代码但由固定会话模式选择。执行中切换开关不能重发已接受命令；unknown 显式阻止新写并显示恢复入口。
- [ ] `AI00_LOCAL_VIEWER_INTERACTION` 仅 Main 读取，默认关闭，页面不能通过参数启用。打包 HTML 更新资源版本；自动测试实际加载的模块与版本一致，修复已知 bootstrap 版本断言不一致。
- [ ] 新本地入口登记成窄范围、明确 owner/理由的消费契约。扫描器仍拒绝 localhost fetch、任意 COM、未授权本地业务调用；新授权通道有独立运行测试，不能只靠 allowlist 字符串通过。
- [ ] 运行新增页面 tests、live-document/队列/布局 tests、`npm test` 和桌面绕过扫描；逐项记录原有失败，不因目标 tests 通过宣称整个前端通过。

## Task 6: 其余交互、部署和真实性能验收

**Files:** F 新增 `scripts/measure_viewer_interaction.js`；B 新增 `docs/verification/2026-09-22-local-viewer-interaction.md`。扩展仍修改 Task 1/2 的白名单合同与 Task 4 的既有分派器，不新增第二条通道。

- [ ] 核对全部既有改动与测试结果，将新通道授权合同/测试向量、功能开关和版本作为一个兼容发布单元。先备份当前实际运行文件、manifest 与哈希，构建后核验差异，不复制整个脏目录。
- [ ] 首先验证四种动作端到端。之后按全显/全隐、隔离、视图复位/适配顺序逐项增加失败测试、固定分派和合同登记。每新增操作都测试未授权拒绝/正确效果/无任意参数；不把所有 Adapter 方法自动加入授权。
- [ ] 实施工具脚本必须限定诊断 workspace/document/source，并在操作前打印非敏感名称供核对；若目标不一致直接停止。保存并恢复可见/选中状态；不运行整车加载、保存文件或 TC 写入。
- [ ] 测量流程：打开和几何就绪计入冷启动；resolve 计入冷映射；分别测 100 次显隐和 100 次选中类热操作。授权续期保持开启，统计样本是否跨越续期，不能关闭安全机制跑出更好数字。

```javascript
const percentile = (samples, p) => {
  const sorted = [...samples].sort((a,b)=>a-b);
  return sorted[Math.ceil(sorted.length*p)-1];
};
// Each sample is a completed real UI action, not a mocked timer.
const report = {count: samples.length, p50: percentile(samples,.50),
  p95: percentile(samples,.95), max: Math.max(...samples)};
```

- [ ] 每样本记录 click_to_response、ipc、queue、mapping、com、journal、result；画面变化独立采样原生视图截图/观察，不能把响应时间当画面时间。若截图无法稳定捕捉真实像素变化，标记画面指标未验证，保留响应指标。
- [ ] 网络抓取仅记录方法/路径/时间不记录令牌，证明热请求没有逐次 TC、读树、command.get、lease 流程；后台续期与审计单独列出。
- [ ] 小零件达到响应 P50≤100ms/P95≤300ms 和画面 P95≤500ms 后，在获准的已有局部装配重复。任何性能失败按分段数据继续定位，不能删掉授权或审计以达标。
- [ ] 验证断网至 60 秒过期、撤销、快速切换、未知 COM 结果和回退。回退先冻结 admission、核对未决操作、撤销交互会话，再让新的用户操作走旧路径；不自动重播失败操作。
- [ ] 核验当前运行进程路径、模块哈希、前端资源版本、连接器 ready 与登录状态。重启若清掉 TC 会话，只在此时请用户登录，不反复提前重启。
- [ ] 验收文档包含真实样本数/分位数/错误、协议测试通过与跳过清单、已知失败、准确部署版本、回退位置。没有实际样本不得写“瞬显瞬隐已解决”。

## 执行顺序与停止条件

顺序 1 → 2 → 3 → 4 → 5 → 6。Task 1 的后端协议与 Task 2 的解析实现可在合同冻结后分工，但不让两个实现自行决定字段。建议本会话原生执行以保持跨语言合同一致，任务 1–5 自动测试可连续推进，不需要每小步用户确认；部署、登录或超出诊断文档的现场操作按实际需要说明。

停止条件：来源关联不具备所需实例证据、Catalog/发布审批缺失、原生外部结构变化无法安全识别、身份/窗口隔离测试失败。停止对应阶段，不以 UI 可显示模型替代正确性证明。

## 计划自检

- 来源/运行身份分离：任务 1、3、5；低频业务路径保留：任务 1、5。
- 授权 TTL/续期/撤销/防重放：任务 1、2、4；同实例映射与外部变化：任务 3。
- 本地管道可信端点：任务 2；自动任务互斥/unknown/日志背压：任务 4。
- 四种操作与扩展：任务 5、6；冷/热分开、画面与响应分开：任务 6。
- 用户已批准实施。任务 1 的授权合同、签名和 SQL 基础已实现并有针对性测试；来源关联集成、审计端点及后续任务未完成，未提交、未部署。执行时每项按真实结果勾选。
