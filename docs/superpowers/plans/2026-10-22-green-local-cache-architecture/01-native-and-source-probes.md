# 01 原生与来源验证门 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task; subagents only when explicitly selected. Steps use checkbox (`- [ ]`) tracking.

**Goal:** 先用可复核证据确定 TC 配置、FCC 和 VisMockup 的真实支持边界。

**Architecture:** 在现有受支持适配器外围增加有范围的诊断与脱敏证据，不修改工程数据或用默认实例冒充指定实例。

**Tech Stack:** 当前 TC SOA worker、.NET、Windows、现有 Node 测试。

**Spec:** [03 原生规格](../../specs/2026-10-22-green-local-cache-architecture/03-teamcenter-fcc-native-collaboration.md)。

## Global Constraints

继承 [总计划](README.md) 全部约束。普通 JT 采用 FCC；不重写 TC 规则，不关闭未知进程、不反复下载完整模型，不把探测结果写入生产业务。

## Review Focus

不同规则模式、日期的真实语义、默认 COM 接错实例、事件覆盖缺口、分段缓存不等于完整文件。T01/T02 分别覆盖并给出不支持结论。

### T01：验证 TC 两类规则与解析／打开的一致性

**Files:**
- Modify B: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/teamcenter_readonly_worker.js`、`TeamcenterReadOnlyRuntime.cs`（只增加范围受控的配置诊断入口，真实新增操作需注册）。
- Test B: create `local-runtime/tests/teamcenter_configuration_probe.test.cjs`；extend `local-runtime/tests/Ai00.Connector.Tests/TeamcenterReadOnlyRuntimeTests.cs`。
- Evidence B: create `docs/superpowers/reports/2026-10-22-green-tc-configuration-probe.json`。

**Interfaces:** 输入当前已授权 endpoint、精确根 revision 和用户选定规则；产出 `configuration_probe.v1` 证据：规则 UID／模式／scope、日期字段语义、展开结果摘要、打开结果来源证明、支持／不支持状态。诊断 schema 为闭合对象，不返回密码或票据。

- [ ] 写失败测试：`configuration_probe_rejects_name_only_rule`、`configuration_probe_keeps_rule_order`、`configuration_probe_rejects_unknown_fields_and_secrets`。断言名称不替代 UID、多变量覆盖顺序不被擅自排序、未知字段拒绝、证据无凭据。
- [ ] `B> node --test local-runtime/tests/teamcenter_configuration_probe.test.cjs`；预期新入口不存在／schema 不满足而失败，不能以语法错误代替需求失败。
- [ ] 加入最小只读配置诊断，保持已有 worker 命令兼容；如需新受治理操作先完成真实登记。解析与打开使用同一配置会话，缺失规则不回退默认。
- [ ] 重跑 Node 与 `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter FullyQualifiedName~TeamcenterReadOnlyRuntimeTests`；再对一个授权测试产品，选同一 TC UI 条件比较所选版本、实例数、位置及打开身份。记录配置前后变化和长解析一致性能力，不能只比总数。
- [ ] 证据含 `supported/unsupported/unverified`、输入来源版本和逐段耗时；不能证明一致时停止 T05 的原生打开集成部分，保留纯数据工作。
- [ ] Commit：`test(tc): establish configuration and source-consistency evidence`，只列本任务文件。

### T02：验证精确文档、多集合、事件与 FCC

**Files:**
- Modify B: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/IVisMockupCom.cs`、`NativeDocumentWindow.cs`（诊断／读取路径）。
- Test B: create `local-runtime/tests/Ai00.Connector.Tests/NativeCapabilityProbeTests.cs`。
- Evidence B: create `docs/superpowers/reports/2026-10-22-green-native-capability-matrix.json`。
- Read F: `packages/core/electron/native/job_object/job_object.cc`、`packages/sim-plugin/electron/document_session_coordinator.js`。

**Interfaces:** `ProbeNativeCapabilities(expectedPid, expectedStarted, expectedDocument)` 只连接明确目标并返回文档、集合、事件、文件访问、线程影响的能力项；不自动关闭程序、不启动共享 FCC。

- [ ] 写失败测试：错误 PID／启动身份返回 target mismatch；同快照双集合不合并；未知事件能力不能标 supported；FCC Offline 不推导目录容量为零；缺少公开 pin 接口不报告长期保留支持。
- [ ] `B> dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter FullyQualifiedName~NativeCapabilityProbeTests`；验证预期失败。
- [ ] 加入最小诊断接口与有界日志；通过安装契约核查受支持的 FCC 获取／定位，不从内部 RW 文件名反推版本。
- [ ] 单进程双文档、双进程、同文档两阶段各做一次指定目标验证；插入／删除／移动／选择各记录通知覆盖；测事件丢失后恢复方式与长 COM 调用阻塞。任何需要关闭／重启共享程序的步骤先确认现场范围。
- [ ] 用同一精确文件身份做冷／热获取，记录真实原生缓存命中依据、几何就绪及任务使用期间文件可用性。若证据不足标 unverified，不要求重复下载整车验证。
- [ ] 追加V7保存能力清单：当前COM保存/Export接口及枚举、服务级别、应用级偏好作用域、静态结构、插入集合与派生依赖。真实写入往返在T24/T25的授权隔离副本执行，当前只读探测不顺带保存用户文档。
- [ ] Commit：`test(native): document exact-session and FCC capabilities`。只有支持的路径允许进入 T09/T17；不支持项要求缩小功能边界或修订设计，不引入错误兜底。
