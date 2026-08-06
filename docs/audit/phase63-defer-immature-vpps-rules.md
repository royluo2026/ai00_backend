# Phase 63 — 暂缓不完善 VPPS 规则

日期：2026-08-06
分支：`codex/capability-wave-a`

## 决策

现有四项 VPPS 检查不够完善，先作为候选规则进入待办，不要求业务 Owner 当前填写和批准，也不把它们升级为发布阻断规则。

候选项：

- `vpps.master_data`
- `vpps.parent`
- `vpps.hierarchy_prefix`
- `vpps.fastener_main_part`

## 对实施计划的影响

原 Task 13 拆分为两个独立批次：

1. 可继续实施的安全写入批次：`version.create`、`version.archive`、`draft.change.preview/apply`、`import.preview`。这些能力依靠类型化变更、预览绑定、乐观并发、幂等、事务、确认和审计保证安全，不声称完成领域规则校验。
2. 暂缓批次：`version.validate`、`version.publish`、`pbom.vpps.validate`。规则成熟、证据齐备并获批后再实施。

不会采取两个危险捷径：

- 不把不完善的现有规则包装成权威 Capability。
- 不在缺少发布 Policy 时实现“无校验发布”。

## 待办状态

- `CRAFT-002/003/006/009`：P2，待完善或暂缓。
- `CRAFT-004/005`：P1，转为待实施，不再依赖 CRAFT-002。
- Policy 技术框架保留；现有候选清单和输入模板保留，供未来重新治理时复用。

本阶段只更新计划和治理记录，没有修改运行时代码、连接数据库、push 或部署。
