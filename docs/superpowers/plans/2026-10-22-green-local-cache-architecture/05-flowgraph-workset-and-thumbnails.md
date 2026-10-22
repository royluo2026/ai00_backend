# 05 流程图工作集与缩略图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task; subagents only when explicitly selected. Steps use checkbox (`- [ ]`) tracking.

**Goal:** 已同步线体快速可操作，后台增量追平，图片不阻塞首屏；只持久缓存缩略图。

**Architecture:** craft 有版本的只读投影服务＋Main/worker SQLite 工作集＋可视范围渲染；正式附件关系云端权威，缩略图按内容版本和权限范围缓存。

**Tech Stack:** 现有 Python、Node/Electron IPC、SQLite worker、lineage_view 渲染，无新框架。

**Spec:** [02 流程图媒体](../../specs/2026-10-22-green-local-cache-architecture/02-flowgraph-workset-and-media.md)。

## Global Constraints

继承 [总计划](README.md)。旧缓存可以读但明确新鲜度；离线草稿不是云端确认；原图不长期缓存；权限撤回不能因本地存在而继续放行。

## Review Focus

分页期间源改变、cursor 过期／乱序页、草稿被后台覆盖、缩略图 URL 过期、另一账号复用缓存；T12/T13/T14 分别约束。

### T12：云端工作集水位与本地 generation 原子切换

**Files:**
- Create B: `plugins/craft/craft_backend/application/flow_workset.py`、`capabilities/flow_workset.py`、`plugins/craft/tests/test_flow_workset_sync.py`。
- Create F: `packages/core/electron/workset_cache.js`、`workset_cache_worker.js`、`workset_cache_ipc.js`、`workset_cache.test.js`。
- Modify F: `packages/core/electron/main.js`、`preload.js`，复用 `packages/sim-plugin/electron/tree_cache_worker.js` 的已安装 SQLite 承载方式，不重复打包 SQLite 依赖。

**Interfaces:** `read_flow_workset(scope, cursor, limit, context) -> {generation, items, tombstones, next_cursor, watermark, rebuild_required}`；Main `worksetCache.read(scope)`、`stagePage(scope,page)`、`activate(scope,generation)`。Main 根据认证与 origin 派生实际访问 scope，不信 Renderer 的 tenant／actor。

- [ ] 写测试：重复页幂等、乱序不推进、分页固定 generation、未完成新 generation 不覆盖旧可读数据、cursor 过期重建、墓碑消除旧节点、换账号拒绝旧 scope。
- [ ] `B> python -B -m pytest -p no:cacheprovider plugins/craft/tests/test_flow_workset_sync.py -q`；`F> node --test packages/core/electron/workset_cache.test.js`，先观察需求失败。
- [ ] 云端复用 T04 事务变更序号提供增量；未具备可靠变更日志的旧对象只支持固定修订分页，明确 rebuild_required，不用更新时间猜删除。Main 单入口、worker 写事务更新投影和 cursor。
- [ ] 重跑新测试及 `packages/sim-plugin/electron/tree_cache.test.js`；测试库验证一页后他人修改，不混合不同头版本。断电模拟激活前失败，旧 generation 仍可读。
- [ ] Commit B/F：`feat(workset): synchronize versioned flowgraph projections`。

### T13：首屏、布局复用与未提交编辑保护

**Files:**
- Modify F: `packages/craft-plugin/web/lineage_view/lineage_projection_store.js`、`layout_mode.js`、`layout_detail_panel.js`。
- Create F: `lineage_workset_controller.js`、`lineage_viewport_renderer.js`、各自 `.test.js`（同 lineage_view 目录）。
- Extend tests: `lineage_projection_store.test.js`。

**Interfaces:** `createLineageWorksetController({cache,remote,render,readDraft})` 提供 `open(scope)/applyRemote(page)/close()`；`renderViewport({nodes,edges,layout,viewport,overscan})` 只处理当前可视邻域。渲染入口只读既有业务身份，布局不改变执行顺序。

- [ ] 测缓存先于网络显示、无图片也可操作、布局版本命中不调用自动排版、当前线体优先、未提交草稿阻止远端覆盖、切页保留缩放与选择、一次旧请求不能覆盖后来切换的线体。
- [ ] `F> node --test packages/craft-plugin/web/lineage_view/lineage_workset_controller.test.js packages/craft-plugin/web/lineage_view/lineage_viewport_renderer.test.js`；先见预期失败。
- [ ] 接入 Main 工作集并拆开详情／绑定／知识加载；增加结构索引与虚拟呈现，不复制 BOP 业务对象。网页端使用相同云端语义但无桌面磁盘假数据。
- [ ] 重跑 projection store、图片投影和新测试；测三档真实测试数据规模，记录 click→可操作、布局、渲染及总节点／首屏节点数。20 次热态首屏 p95 ≤1 秒目标，未达列分段耗时，不删正确性步骤。
- [ ] Commit：`perf(flowgraph): render cached visible scope before background refresh`。

### T14：正式缩略图与在线原图

**Files:**
- Create B: `backend/base/artifact_thumbnails.py`、`backend/tests/test_artifact_thumbnails.py`；Modify `backend/base/contracts.py` 及 G0 核实的 Base Provider 注册入口。
- Create F: `packages/core/electron/thumbnail_cache.js`、`thumbnail_cache.test.js`；Modify `desktop_artifacts.js`、`main.js`、`preload.js`。
- Modify F: `packages/craft-plugin/web/lineage_view/layout_detail_panel.js`；extend `lineage_browser_picture.test.js`。

**Interfaces:** Base `get_thumbnail(artifact_ref, variant, context) -> {thumbnail_ref, content_version, dimensions, authorized_fetch_ref}`；Main `getThumbnail(ref,variant)` 持久存缩略图，`openOriginal(ref)` 仅在线临时显示。首版 variant 使用最大边 512px、保持原比例、不放大原图；尺寸版本化，可追加受控 variant，不接受任意磁盘路径／URL。

- [ ] 测签名 URL 刷新但内容相同命中同缓存、内容更新换键、媒体类型／大小拒绝、账号变更和权限撤回、原图不写长期缓存、原图失败不阻塞流程图。
- [ ] 跑新 Base pytest、thumbnail Node 测试与 browser picture 测试观察需求失败。
- [ ] 优先复用现有附件服务的缩略图；服务端生成不要求客户端先取完整原图。客户端去重有界请求、临时写校验后原子入索引；原图只用短期显示句柄，关闭释放 App 持有资源，不能承诺操作系统零临时缓存。
- [ ] 重跑并在线／断网查看缩略图、原图；检查真实缓存目录只有缩略图、任务 PNG 另归可靠结果。大图响应丢失不能把另工序图作为兜底。
- [ ] Commit B/F：`feat(media): cache versioned thumbnails and fetch originals on demand`。
