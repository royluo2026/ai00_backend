# 06 存储监控与显式保留 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task; subagents only when explicitly selected. Steps use checkbox (`- [ ]`) tracking.

**Goal:** 先独立交付状态栏磁盘用量与分类，再约束显式长期模型保存和安全淘汰。

**Architecture:** Main 管真实目录归属，worker 元数据扫描；FCC 与 AI00 分开，统计结果缓存供 UI 查看，清理不藏在统计接口。

**Tech Stack:** Electron/Node fs、Windows 文件身份／分配大小能力、现有 native addon、SQLite 索引。

**Spec:** [06 存储监控](../../specs/2026-10-22-green-local-cache-architecture/06-storage-monitor-and-statusbar.md)。

## Global Constraints

继承 [总计划](README.md)。普通打开不长期复制数模；FCC 仅受支持管理；未知不当零，后台扫描不阻塞首屏；长期模型和待交付结果不自动淘汰。

## Review Focus

硬链接／目录重叠、跨盘副本、稀疏预分配、无权限及扫描中删除、符号链接越界。T15 要覆盖全部，不能单用目录大小相加冒充精确物理占用。

### T15：目录归属、只读容量计量与调度

**Files:**
- Create F: `packages/core/electron/storage_roots.js`、`storage_usage_worker.js`、`storage_usage.js`、`storage_usage.test.js`。
- Modify F: `packages/core/electron/native/job_object/job_object.cc` 仅在现有依赖无法获得所需 Windows 文件身份／分配大小时增加受控元数据函数；native 源改变必须重建并测试 ABI，不能默认纯 JS 能证明全部物理属性。
- Read: 已确认 app userData、connector state root、T02 提供的实际 FCC 根信息。

**Interfaces:** `createStorageUsageMonitor({roots,metadataReader,clock,workerFactory})` 提供 `read()/refresh({manual})/stop()`；`StorageUsage` 含 scan_id、时间、metric_kind、complete、categories、volumes、errors。roots 只由 Main 确定，Renderer 无路径输入。

- [ ] 写统计 fixture：同文件硬链接只计一次、不同卷相同内容计两次、嵌套根不重算、symlink 不跟随、权限错误返回 partial、已确认空目录为零、未知路径不为零、FCC Offline 仍计元数据。
- [ ] `F> node --test packages/core/electron/storage_usage.test.js`；先看到缺少统计实现的需求失败。
- [ ] worker 单飞、5 分钟周期、手动最短 30 秒、空闲首次；扫描有预算并可取消。无法读取 allocated bytes 时标 logical，不静默混加；不读 JT 内容、不解析凭据。
- [ ] 在 Windows 受控测试目录实建硬链接／稀疏样例验证 metadataReader；真实 FCC 目录只读测量，不全量哈希或清理。扫描期间界面可操作，退出不留 worker。
- [ ] Commit：`feat(storage): measure owned and FCC disk usage separately`。无需等待完整仿真改造即可接 T16。

### T16：状态栏、可访问明细与提醒

**Files:**
- Create F: `packages/core/electron/storage_usage_ipc.js`、`storage_usage_ipc.test.js`；`web/core/statusbar_storage.js`、`statusbar_storage.test.js`、`statusbar_storage.css`。
- Modify F: `packages/core/electron/main.js`、`preload.js`、`web/index.html`。

**Interfaces:** `electronAPI.getLocalStorageUsage()` 无路径参数、可信主窗口检查；status renderer 只接规范 `StorageUsage`。状态栏文本：本地占用／AI00／VisMockup/FCC；明细含分类、口径、时间、水位、卷剩余和错误。

- [ ] 测陌生 frame／caller 参数拒绝、hover 不重新扫描、键盘聚焦／点击可固定明细、窄窗口仍区分两个所有者、部分数据不显示总量已完整、浏览器不显示云端磁盘冒充本地。
- [ ] `F> node --test packages/core/electron/storage_usage_ipc.test.js web/core/statusbar_storage.test.js`，先观察需求失败。
- [ ] 接入 monitor 缓存结果；非阻塞展示，提醒去重。低空间建议阈值 max(10 GiB, 卷容量 5%) 作为可配置初值，面板标出来源；不自动调用 FCC purge。
- [ ] 重跑状态栏既有 build info 测试、IPC 安全相关测试。真实绿标检查 hover／焦点／窄屏／统计失败，截图留证，不能以 DOM 字符串测试代替 UI 验证。
- [ ] Commit：`feat(desktop): show scoped cache storage in statusbar`。

### T17：显式长期模型、缩略图与临时结果生命周期

**Files:**
- Create F: `packages/core/electron/model_retention.js`、`model_retention.test.js`、`cache_reclamation.js`、`cache_reclamation.test.js`。
- Modify F: `desktop_artifacts.js`、`storage_roots.js`、模型文件 UI 的明确“长期保存”动作。
- Modify B: 需要云端归档身份时使用所属 Base Artifact／digital_model 现有公开能力；新动作按 G0 注册，不让只读 IPC 暗含删除。

**Interfaces:** `retainModel(selection,authorizedSource,mutationId)` 返回保留清单；`planReclamation(scope,budget)` 只列可回收项，`applyReclamation(plan,expectedInventory)` 分别核实所有权／在用引用。普通原生打开不能调用 retainModel。

- [ ] 测正常打开不写长期库、用户保存记来源／版本／文件清单、同文件共享与跨盘占用、未完成上传不可淘汰、草稿 SQLite 不当缓存删、回收计划过期不误删。
- [ ] 跑两组新 Node 测试观察需求失败；实现独立元数据和受控文件操作，事务／文件失败保留可恢复状态。FCC 不在 AI00 回收候选中，旧目录先分类不自动搬删。
- [ ] T02 未证明的文件访问不宣称可离线；受控归档需完整依赖校验和明确用户动作。重跑真实目录／断电中断恢复测试，确认未碰生产与原生内部缓存。
- [ ] Commit：`feat(storage): distinguish retained models from disposable caches`。T20 使用同一可靠结果分类和配额信号。
