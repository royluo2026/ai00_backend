# Craft Validation Policy 业务输入与批准模板

日期：`YYYY-MM-DD`
Policy ID：`craft.publish_check`
Policy 版本：`待业务 Owner 确认`
状态：`草案 / 待评审 / 已批准 / 已退役`

## 1. 使用目的

本模板用于完成 `CRAFT-002` 的业务治理输入。它不是研发自行定义规则的地方：来源、业务 Owner、阈值、算法和验收证据必须由有权解释该工艺规则的人确认。

四项检查全部批准前，以下 Capability 保持未注册：

- `craft.bop.version.validate`
- `craft.bop.version.publish`
- `craft.pbom.vpps.validate`

## 2. Policy 级信息

| 字段 | 待填写内容 |
| --- | --- |
| 业务目的 | 这组校验避免什么业务风险 |
| 适用对象 | PBOM/BOP 对象、版本状态和适用项目范围 |
| 生效时点 | 草稿检查、发布检查、仿真检查或工位检查 |
| Policy Owner | 对整套 Policy 最终负责的人员/岗位及 principal GID |
| 批准人 | 有权批准发布规则的人员/岗位及 principal GID |
| Policy 版本 | 不可变版本号；修改规则必须生成新版本 |
| 生效时间 | 新版本开始用于新校验的时间 |
| 历史策略 | 历史版本重放时使用当时 Policy，还是显式对比当前 Policy |
| 失败策略 | 阻断、警告或提示；不得用前端 ignore 代替正式让步 |
| 例外机制 | 当前默认无正式 waiver Capability；如确需例外必须另行治理 |

## 3. 每项规则必须填写的字段

| 字段 | 要求 |
| --- | --- |
| `check_id` | 稳定、唯一，不随显示名称变化 |
| `source_kind` | 标准、制度、工程定义、已验证经验或其他明确类别 |
| `source_ref` | 可追溯文号、章节、版本或受治理知识引用；不能只写“经验” |
| `owner` | 唯一负责解释规则的人/岗位及 principal GID |
| `scope` | 适用项目、对象类型、生命周期状态和排除条件 |
| `severity` | `block / warning / hint`；未验证经验最多只能是 `hint` |
| `mechanism` | 读取哪些稳定数据，经什么确定性步骤得到结论 |
| `threshold` | 数值、枚举、匹配边界和空值行为；无阈值也要明确写“不适用”及原因 |
| `algorithm_ref` | 算法标识和不可变版本；不得只引用当前代码行号 |
| `check_version` | 该项规则自身的不可变版本 |
| `evidence_schema` | 每次命中必须返回的对象引用、字段值、规则版本和解释 |
| `remediation` | 失败后由谁修改什么，不允许模型凭空建议高风险动作 |

## 4. 四项 VPPS 规则输入

请为每项分别复制并填写以下记录；任何 `待确认` 都会继续阻断 Task 13。

### 4.1 `vpps.master_data`

- 业务含义：VPPS 主数据及名称/描述一致性。
- `source_kind/source_ref`：待确认
- `owner`：待确认
- `scope/severity`：待确认
- `mechanism`：待确认
- `threshold`（含空值、大小写、空格和语言差异）：待确认
- `algorithm_ref/check_version`：待确认
- `evidence_schema/remediation`：待确认

### 4.2 `vpps.parent`

- 业务含义：父级字段与实际父零件 VPPS 一致性。
- `source_kind/source_ref`：待确认
- `owner`：待确认
- `scope/severity`：待确认
- `mechanism`：待确认
- `threshold`（含根节点、缺失父项和多父关系）：待确认
- `algorithm_ref/check_version`：待确认
- `evidence_schema/remediation`：待确认

### 4.3 `vpps.hierarchy_prefix`

- 业务含义：子项 VPPS 层级前缀检查。
- `source_kind/source_ref`：待确认
- `owner`：待确认
- `scope/severity`：待确认
- `mechanism`：待确认
- `threshold`（含前缀长度、分隔符和跨层跳级）：待确认
- `algorithm_ref/check_version`：待确认
- `evidence_schema/remediation`：待确认

### 4.4 `vpps.fastener_main_part`

- 业务含义：紧固件几何/描述与主件一致性。
- `source_kind/source_ref`：待确认
- `owner`：待确认
- `scope/severity`：待确认
- `mechanism`：待确认
- `threshold`（含紧固件分类、主件识别和多候选）：待确认
- `algorithm_ref/check_version`：待确认
- `evidence_schema/remediation`：待确认
- 既有前端 `ignore` 是否构成正式例外：默认否；如需改变必须单独批准

## 5. `publish_check` 必备证据包

每项规则至少提交以下四类可重复执行的样本。样本只写对象稳定引用，不在本文复制敏感生产数据。

| 证据类型 | 样本引用 | 固定输入 Hash | 期望结果 | 实际结果 | 业务 Owner 签字 |
| --- | --- | --- | --- | --- | --- |
| 正例 | 待填写 | 待填写 | 通过 | 待执行 | 待签字 |
| 反例 | 待填写 | 待填写 | 按指定严重级别失败 | 待执行 | 待签字 |
| 边界例 | 待填写 | 待填写 | 待填写 | 待执行 | 待签字 |
| 历史回放 | 待填写 | 待填写 | 与批准历史结论一致，或记录有解释的差异 | 待执行 | 待签字 |

## 6. Task 13 启动签署

只有全部问题回答“是”才能将 `CRAFT-002` 标记为已完成：

- [ ] 四项规则的来源、Owner、范围、严重级别和执行机制均已批准。
- [ ] 四项规则的阈值、算法引用、规则版本和证据 Schema 均已冻结。
- [ ] `publish_check` 的正例、反例、边界例和历史回放全部通过并签字。
- [ ] Policy 版本、生效时间、历史策略和失败策略已批准。
- [ ] 业务 Owner 确认现有前端 `ignore` 不会被研发默认为正式让步。
- [ ] 产品/架构 Owner 同意启动 Task 13 的写能力、发布状态机和预览绑定实现。

批准记录：

| 角色 | 姓名/岗位 | principal GID | 决定 | 时间 | 备注 |
| --- | --- | --- | --- | --- | --- |
| 业务 Owner | 待填写 | 待填写 | 待填写 | 待填写 | |
| 工艺专家 | 待填写 | 待填写 | 待填写 | 待填写 | |
| 产品/架构 Owner | 待填写 | 待填写 | 待填写 | 待填写 | |
