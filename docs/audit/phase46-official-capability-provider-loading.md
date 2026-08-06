# Phase 46：官方领域 Capability Provider 加载

日期：2026-08-06
实施分支：`codex/capability-wave-a`
前置提交：`87f3739`

## 目标

落实 Capability 实施计划 Task 2：由官方领域插件拥有并注册自身 Capability，基座 Kernel 不直接导入 Craft 实现模块。此阶段只建立 provider 边界，不注册尚未完成讨论和实现的 Craft 业务能力。

## 已实施内容

1. `PluginLoader.register_capabilities(registry) -> tuple[str, ...]` 读取官方 manifest 的 `backend.capabilities_module`。
2. 仅 `plugin_id` 以 `official.` 开头的 manifest 可执行后端 provider；第三方 manifest 的整个 backend 声明仍在 discovery 阶段被剥离，注册阶段再次检查官方前缀。
3. provider 导入期间仅临时注入对应插件目录到 `sys.path`，完成或失败后均在 `finally` 中移除。
4. 已声明的官方 provider 加载或注册失败时采用 fail-closed：抛出异常中止启动，禁止服务在 Capability 集合残缺时静默上线。
5. Craft manifest 新增 `craft_backend.capabilities`，其入口只允许注册 Craft handler，不挂载 Router、不启动 worker。
6. `backend.main` 在插件 discovery 后、请求服务前，将官方 provider 注册到共享 `capability_registry`。

## 边界结果

- Base Kernel 的 `registry_next.py` 不包含 `craft_backend` 或 `plugins.craft` 导入。
- Craft 依赖 Base 的 Capability 契约；Base 只认识 manifest 和 provider 函数，不认识 Craft 内部模块。
- 第三方网页插件不能通过 manifest 提交 Python provider。
- 官方 provider 声明即启动契约，损坏时不降级成“接口悄悄缺失”。

## TDD 与验证证据

- 初始红灯：`2 failed`，原因均为 `PluginLoader` 尚无 `register_capabilities`。
- fail-closed 红灯：`1 failed, 2 passed`，证明损坏官方 provider 当时被错误吞掉。
- provider、领域治理和 loader 边界回归：`10 passed in 0.41s`。
- 未执行数据库连接、SQL、迁移或部署。

## 文件范围

- `backend/plugin_loader.py`
- `backend/main.py`
- `plugins/craft/manifest.json`
- `plugins/craft/craft_backend/capabilities/__init__.py`
- `backend/tests/test_capability_provider_loading.py`

## 远端状态

- 改动仅位于本地隔离 worktree。
- 未推送 Gitea、GitLab 或其他远端。
