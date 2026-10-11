# craft.bop.demo.relation.change.apply@1

Connect or reset demo station/process/operation/part relations by hidden codes inside a demo-marked BOP version（W10 工艺关系演示）。

## 使用判断

- 适用：超级管理员在 `bop_versions.meta.demo.relation_demo=true` 的专用演示版本上，执行工艺关系演示的「连接」（connect）、「恢复待连接」（reset）或查询各线体连接状态（status，供前端状态指示与刷新后恢复播放数据）。
- 不适用：任何正式生产版本；非超管调用；常规工艺编辑。
- 生命周期：`experimental`
- 所属领域：`craft`
- Schema 精度：`typed`

## 业务效果（business_effect）

在专用演示版本内，按隐藏编码（`bop_process.process_code` ↔ `bop_station.ext.demo_process_codes`）把工序从「待连接工序区」移入目标工位（操作随工序），并按隐藏零件编码（`bop_steps.ext.demo_part_codes` ↔ `pbom.meta.demo_code`）建立操作到 PBOM 零件的「装配零件」直接关系；reset 时把工序移回待连接区并软删带 demo 标记的装配零件链接。只影响演示版本数据。

## 授权与数据边界

- 服务端强制 `super_admin`（`context.active_roles`），前端按钮同样仅超管可见。
- 权限：`craft.write`；副作用：`write`；幂等：是（已连接/已恢复时跳过）。
- 资源范围：单个演示 BOP 版本；可选 `line_gid` 限定单条线体。

## 输入 Schema

见 `plugins/craft/craft_backend/capabilities/contracts.py`：`operation ∈ {connect, reset, status}`、`bop_gid`（必填）、`line_gid`（可空）。

## 输出 Schema

`data` 为闭合对象：`connect` 返回 `line_gid/line_title/stations/processes_moved/operations/part_links/steps`（steps 为按工位有序的 工位→工序→操作→零件 结构，供前端逐步展示；幂等重连时仍返回该线体当前完整 steps）；`reset` 返回 `processes_moved/part_links_removed`；`status` 返回 `lines[]`（每条线体含 `line_gid/line_title/connected/processes_connected/steps`，steps 仅在已连接时非空）。

## 错误

领域错误：

- `demo_super_admin_required`：调用方不是超管（retryable=false）
- `demo_version_not_found`：BOP 版本不存在（retryable=false）
- `demo_version_frozen`：版本已冻结（retryable=false）
- `demo_version_required`：版本未标记演示（retryable=false）
- `demo_holding_line_missing`：缺少「待连接工序区」线体（retryable=false）
- `demo_line_not_found`：指定线体不在演示版本或无演示编码（retryable=false）

## 测试

- `backend/tests/test_craft_demo_relation_change_boundary.py`：注册/契约存在性、operation 先于 IO 校验、非超管拒绝、缺参拒绝。
- 运行时实测：本地 test 环境 JWT 调用 connect/reset/status（底盘一线），结果写回 test_ 前缀表验证；status 实测返回 26 条线体，底盘一线 connected=true / 225 工序 / 完整 steps。

## 治理状态

- `machine_passed`：边界测试通过（见上）。
- `human_approved`：未批准（experimental 演示能力，待 owner 确认）。
- `runtime_verified`：2026-09-30 本地 test 环境（test_ 前缀表，W10-2026 v2 演示版本 gid=205576954294833152，底盘一线 gid=205577258981658628）实测：connect 返回 32 工位 / 225 工序移动 / 260 操作 / 4 装配零件链接（耗时 <10s）；reset 返回移回 225 工序 / 软删 4 链接；重复执行幂等（processes_moved=0）；真实 member 角色用户（gid=203411690962817024）调用被 `demo_super_admin_required` 拒绝。
- 已知修复：输出契约必须显式封闭（`descriptor_adapter._closed_schema` 会递归闭合 `additionalProperties`）；装配零件链接复活逻辑需兼容 reset 软删行命中 `uq_bop_entry_links` 唯一键。
