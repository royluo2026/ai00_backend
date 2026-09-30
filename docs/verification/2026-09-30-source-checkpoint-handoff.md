# 2026-09-30 前后端源码检查点交接

用户要求整理当前前后端分支，并提交到本地、Gitea 和 GitHub。本次保存当前源码进展，供其他实例继续修复；不是生产发布或全部验收通过。

## 分支与提交范围

- 两个仓库均保留 `test` 分支；开始整理时本地、`devteam/test`（Gitea）、`github/test`（GitHub）一致，无远端分叉。
- 本地 `checkpoint/test-before-cache-20260930` 指向整理前 HEAD，保留回溯入口。
- 每仓库分两组提交：工艺 / BOP / 项目相关；数模共用缓存 / 仿真 / Connector / 配套平台与桌面接线。
- 纳入源代码、测试、SQL 迁移、契约、catalog 及设计 / 验证文档。旧接口及历史设计保留用于兼容与追溯，当前 JT 路径以 2026-09-30 TC 本机打开设计和实施记录为准。
- 不纳入 `.runtime`、本机 Connector manifest、临时 pytest 数据、`bin-*`、TestResults，以及已过期的 `dist` / `dist-production` 构建目录。磁盘文件保留；已有受 Git 跟踪的构建目录仍可能显示变更，不代表源码漏提交。正式部署前需按现有流程重新构建。
- 不合并到 deploy，不强推，不删除正在使用的其他分支或工作树。

## 本次提交前验证

| 范围 | 结果 |
| --- | --- |
| 数模仿真前端目录全部 Node 测试，独立进程 | 403 通过，2 失败 |
| 前端缓存 / Electron / 工艺谱系 / 登录 / 侧栏相关 | 171 通过 |
| Python 共用准备 / 缓存打开 / 绑定 / 装配相关 | 81 通过 |
| Connector 本地 JT / 单环境装配 / 取消 / 清理相关 | 18 通过 |
| Python 平台 / BOP / 项目 / Connector 契约相关 | 288 通过，149 跳过，1 失败 |

未声称仓库所有测试均通过。三项失败：

1. `packages/sim-plugin/web/cad_sim/connector_recovery.test.js:396`：旧 CSS / script 资源版本断言与当前页面不一致。
2. `packages/sim-plugin/web/cad_sim/teamcenter_entry_assets.test.js:10`：旧资源版本断言与当前页面不一致。
3. `backend/tests/test_resource_requirement_boundary.py::test_resource_requirement_compatibility_invokes_the_atomic_capability`：测试中 SimpleNamespace principal 缺少 `desktop_consumer`，在 `backend/capability_v2/identity.py:79` 报 AttributeError。接手时应核对测试夹具与身份边界，不能据此声称该路径已验证通过。

完整输出保存在本机工作区 `.runtime/checkpoint-front-cad.log`、`checkpoint-front-related.log`、`checkpoint-backend-pytest.log`、`checkpoint-backend-related.log` 和 `checkpoint-connector-tests.log`，不上传运行日志。

## 数模仍需修复

1. 切回环境能恢复原生窗口，但 `_cacheViewer` 被清除，树映射 / 控制关联 / 显隐没有恢复，已有装置保留问号。应核对会话和来源后恢复已加载范围并回读；禁止通过整文档打开扩大范围。
2. 温缓存打开仍约 25～28 秒；后悬架本次约 64 秒。需分别分析重复来源核对、请求提交、原生替换、绑定与回读，不应把所有耗时归因于 JT 下载。
3. 原生首次启动 `vismockup_document_limit_unverifiable` 及 Connector 重启后保留文档的恢复仍不稳定；保留 10 文档上限，不放宽身份检查，不自动重试 outcome_unknown。
4. 尚未做两台物理客户端验证。测试启动时需先等待后端就绪，避免登录恢复失败。

已验证：取消后明确重试不再消费旧 cancelled 错误；只有 failed_without_effect / cancelled 才开启新请求。三个装置共 233 个几何实例，1 文档 / 1 根；新增后悬架 116 个矩阵匹配准备文件，原有 117 个位置保持。装置和紧固件显隐已回读验证。

## 必须保持的产品约束

共用缓存只保存固定 TC 元数据、文件引用和装配依据。JT 由各客户端从 TC/FMS 下载到自己的电脑，可定期清理，不上传 OIS。父节点控制其子树，零件控制自身；未知状态显示问号；不得扩大加载范围或改变实例坐标。

更完整的运行证据在后端 `docs/verification/2026-09-30-tc-local-open-execution.md`。本轮没有继续修复以上遗留问题，只整理提交供接手。
