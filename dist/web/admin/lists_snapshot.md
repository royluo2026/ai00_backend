# 清单注册表快照

> 导出时间：2026/5/2 20:53:19
> 共 45 张表

## 系统域

| 表名 | 对应清单 | 聚合根 | 业务含义 | 状态 | 备注 |
|-----|---------|------|---------|------|------|
| teams | 组织管理 | Team | 团队（逻辑租户隔离单位） | active |  |
| users | 用户管理 | User | 全局用户（飞书身份 + 系统角色） | active |  |
| system_config | 系统配置 | — | 全局热重载配置（飞书凭证、能力备注等） | active |  |
| auth_pending | —（内部） | — | OAuth 登录状态轮询（state→jwt，10 min 过期） | active |  |
| view_configs | 视图管理（各模块内） | ViewConfig | 用户自定义视图（字段显隐 / 顺序 / 筛选 / 排序） | active |  |
| export_templates | 导出模板编辑器 | ExportTemplate | Excel 导出样式模板（列宽、表头色等） | active |  |
| workbench_configs | 工作台 | WorkbenchConfig | 多工作台配置（个人或团队，每 owner 最多 3 个） | active |  |
| workbench_member_overrides | 工作台（个性化） | WorkbenchConfig | 团队工作台的成员个性化覆盖 | active |  |

## 项目域

| 表名 | 对应清单 | 聚合根 | 业务含义 | 状态 | 备注 |
|-----|---------|------|---------|------|------|
| vehicle_models | 车型清单 | VehicleModel | 车型（项目归属的产品对象） | active | 项目域的这个表和project表本身内容和更新频次应该不高。做成一个模块有点浪费了。看集成到哪里吧。 |
| projects | 项目清单 | Project | 项目（工艺开发主体，含状态 / 范围 / 负责人） | active |  |
| project_members | 项目成员（项目详情内） | Project | 项目成员（project_role: member/admin/viewer） | active |  |

## 工艺域（旧）

| 表名 | 对应清单 | 聚合根 | 业务含义 | 状态 | 备注 |
|-----|---------|------|---------|------|------|
| work_plans | 工艺计划清单（旧） | WorkPlan | 工艺计划（旧五层根节点，已被 BOP 五层替代） | legacy | bop_versions 替代，暂保留兼容 |
| sections | 工段清单（旧） | WorkPlan | 工段（旧：工艺计划→工段→工序） | legacy | 已被 factory_sections / bop_posts 替代 |
| operation_flat | 工艺清单（旧） | WorkPlan | 工序平铺（旧结构，含工位/岗位/标准工序引用） | legacy | 已被 bop_operations 替代 |

## 工艺域（BOP五层）

| 表名 | 对应清单 | 聚合根 | 业务含义 | 状态 | 备注 |
|-----|---------|------|---------|------|------|
| bop_versions | BOP 画布（版本选择） | BopVersion | BOP 版本（项目 + 车型 + 工厂的工艺方案根节点） | active |  |
| bop_posts | BOP 画布（岗位层） | BopVersion | 岗位（工位内人员岗位，第二层） | active | 工段工位不放工艺域会不会不行啊？会断层吗？工厂域的工段和工位引用过来吗？ |
| bop_operations | BOP 画布（工序层）/ 工艺清单 | BopVersion | 工序（第三层，含标准工序克隆 + drift 追踪） | active |  |
| bop_steps | BOP 画布（工步层） | BopVersion | 工步（第四层，工序的细化步骤） | active |  |
| operation_resources | BOP 画布（工序资源） | BopVersion | 工序资源规格（画布层：工具 / 夹具 / 设备需求） | active |  |
| step_resources | BOP 画布（工步资源） | BopVersion | 工步资源规格（清单层：工具 / 夹具 / 设备需求） | active |  |

## eBOM域

| 表名 | 对应清单 | 聚合根 | 业务含义 | 状态 | 备注 |
|-----|---------|------|---------|------|------|
| bom_snapshots | EBOM 清单（版本选择） | BomSnapshot | eBOM 快照（项目某时刻的物料清单版本） | active |  |
| part_entries | EBOM 清单（零件树） | BomSnapshot | 零件条目（快照内树形零件清单节点，自引用 parent_gid） | active |  |
| part_model_instances | EBOM 清单（3D 模型） | BomSnapshot | 零件 3D 模型实例（坐标变换，关联零件条目） | partial | 3D 模型读写能力待完善 |

## 知识域

| 表名 | 对应清单 | 聚合根 | 业务含义 | 状态 | 备注 |
|-----|---------|------|---------|------|------|
| std_operations | 标准工序库 | StdOperation | 标准工序库（可克隆到 BOP，version 字段用于 drift 追踪） | active | 把这几个标准清单放一个模块里面 |
| tool_templates | 工艺元素库（工具） | ToolTemplate | 工具模板库（工具种类 / 规格定义） | active | 把这几个标准清单放一个模块里面 |
| equipment_templates | 工艺元素库（设备） | EquipmentTemplate | 设备模板库（设备种类 / 规格定义） | active | 把这几个标准清单放一个模块里面 |
| fixture_templates | 工艺元素库（夹具） | FixtureTemplate | 夹具模板库（夹具种类 / 规格定义） | active | 把这几个标准清单放一个模块里面 |
| standard_fasteners | 工艺元素库（紧固件） | StandardFastener | 标准紧固件库（件号唯一，含料号 / 规格 / 材料） | active | 把这几个标准清单放一个模块里面 |
| standard_part_names | 工艺元素库（零件名） | StandardPartName | 标准零件名称库（规范命名，防歧义） | active | 把这几个标准清单放一个模块里面 |
| 知识库的metadata表 |  |  |  | planned | 缺一张这样的表。本地和云端应该都缺。注意里面要有附件和图片的链接。 |

## 工厂域

| 表名 | 对应清单 | 聚合根 | 业务含义 | 状态 | 备注 |
|-----|---------|------|---------|------|------|
| factories | 工厂资源（工厂列表） | Factory | 工厂（物理工厂实体，含工段 / 工位） | active |  |
| factory_sections | 工厂资源（工段） | Factory | 工段（工厂内物理区域，画布中大矩形） | active |  |
| factory_stations | 工厂资源（工位） | Factory | 工位（独立站位如 TB01L/TB01R，含节拍 / 人机高度） | active |  |
| factory_layout_templates | 工厂资源（布局模板库） | FactoryLayoutTemplate | 工厂布局模板（产线积木，保存一组工位相对坐标） | active |  |
| physical_tools | 工厂资源（实物工具） | ToolTemplate | 实物工具（资产编号唯一，关联工具模板） | active |  |
| physical_equipments | 工厂资源（实物设备） | EquipmentTemplate | 实物设备（资产编号唯一，关联设备模板） | active |  |
| physical_fixtures | 工厂资源（实物夹具） | FixtureTemplate | 实物夹具（资产编号唯一，关联夹具模板） | active |  |

## 协作域

| 表名 | 对应清单 | 聚合根 | 业务含义 | 状态 | 备注 |
|-----|---------|------|---------|------|------|
| collab_sessions | —（内部锁定） | CollabSession | 协同编辑会话（多人编辑工段时的锁定会话） | partial | 实时协同能力待完善 |
| approval_orders | 审批管理 | ApprovalOrder | 审批单（工艺变更 / 偏差 / 范围升级等流程） | active |  |
| follows | 关注 / 订阅（各模块内） | Follow | 关注（订阅任务/问题/项目等，条件式通知） | active | notify_on 已从 TEXT 迁移至 JSONB 数组 |
| notifications | 通知中心 | Notification | 通知（状态变更 / @提及 / 关注触发的消息） | active |  |

## 任务域

| 表名 | 对应清单 | 聚合根 | 业务含义 | 状态 | 备注 |
|-----|---------|------|---------|------|------|
| tasks | 任务清单 | Task | 任务（本地 SQLite + 云端 PG 双存储，可提升到云端） | active | 提升后本地记录补充 migrated_to_cloud_gid。  里面有图片和文档链接，还有飞书文档链接，飞书联系人和飞书群聊入口等的字段了吗 |
| task_templates | 任务模板管理 | TaskTemplate | 任务模板（项目标准内容清单，可批量实例化） | active |  |
| task_template_items | 任务模板条目（模板详情内） | TaskTemplate | 任务模板条目（含变量插值，支持偏移天数） | active |  |

## 问题域

| 表名 | 对应清单 | 聚合根 | 业务含义 | 状态 | 备注 |
|-----|---------|------|---------|------|------|
| issues | 问题清单 | Issue | 问题（本地 SQLite + 云端 PG 双存储，含八大要素字段） | active | 与 tasks 同理双存储。问题清单里面有图片和文档链接，还有飞书文档链接，飞书联系人和飞书群聊入口等的字段了吗 |
