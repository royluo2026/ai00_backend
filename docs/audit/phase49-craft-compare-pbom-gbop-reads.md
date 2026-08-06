# Phase 49：Craft Compare、PBOM 与活动 GBOP 读取

日期：2026-08-06
实施分支：`codex/capability-wave-a`
前置提交：`2853348`

## 已实施 Capability

- `craft.bop.version.compare`
- `craft.pbom.snapshot.get`
- `craft.pbom.snapshot.compare`
- `craft.pbom.part.search`
- `craft.gbop.item.search`
- `craft.gbop.item.usage.get`
- `craft.gbop.item.knowledge.list`

明确未注册任何 PBOM↔GBOP match、auto-link、confirm 或 staging Capability。

## 边界与语义

1. BOP compare 基于规范化结构返回 comparability、added、removed、moved、changed，不暴露原始数据库 JSON diff。
2. PBOM part search 强制 `snapshot_gid`，禁止脱离版本快照搜索；snapshot compare 使用 component ID、part number、GID 的稳定优先级比较。
3. GBOP 每次先解析唯一 `status='active' AND archived_at IS NULL` 的版本；没有或存在多个活动版本均 fail-closed。
4. GBOP usage 只输出 `exact|modified|outdated|inherited|broken`，未知存量状态会按明确事实降级为受控状态，不原样透传。
5. GBOP knowledge 只从 item meta 返回固定 `document_gid + revision_gid` 引用，不 JOIN Knowledge 表。
6. 所有 SQL 使用 Craft 自有连接与表，无 PostgreSQL qualifier、cast 或 RETURNING。

## TDD 与验证

- 初始红灯：测试收集因 `gbop_read` 不存在而失败。
- 首次实现后有 1 个测试夹具缺失 `version_gid`，产品代码按活动版本边界正确拒绝；修正夹具后 `4 passed`。
- 未连接数据库，未执行 SQL、迁移或部署。

## 待后续治理

当前 GBOP 活动版本由 `status='active'` 表达，且代码会拒绝多活动版本。若未来需要原子切换，应引入唯一 active-ref 治理记录，不能靠“取最新一条”掩盖冲突。

## 远端状态

- 改动仅位于本地隔离 worktree。
- 未推送 Gitea、GitLab 或其他远端。
