# Capability V2 单数据库领域隔离与建表设计

**日期：** 2026-08-13  
**状态：** 待用户书面复核  
**适用环境：** OceanBase 4.3.5+、MySQL 兼容模式、公司仅提供一个业务数据库和一个生产运行账号

## 1. 背景与决定

Capability V2 必须继续满足三个业务目标：

1. 插件和 Agent 能够发现并调用受治理的能力；
2. 各领域能够独立维护代码、表结构、迁移和数据访问边界；
3. 各领域只能通过 Capability 共享业务能力。

公司实际生产环境只提供一个 OceanBase 业务数据库和一个运行账号，不能创建十一套物理数据库，也不能长期维护二十二个领域账号。因此，原设计中的“十一数据库、每域 DDL/Runtime 双账号”保留为强化隔离配置，但不再作为公司环境的唯一完成条件。公司环境采用 `single_database_domain_tables` 配置：一个数据库中维护十一组有明确所有权的领域表，使用代码、迁移、审计和 Capability Gateway 实现逻辑隔离。

本设计不把逻辑隔离描述成物理数据库隔离。生产共享账号泄露会扩大到整个业务数据库，这是已知剩余风险，必须由最小表权限、密钥管理、SQL 边界审计和 Gateway-only 调用补偿。

现有数据库 `ai00_test` 和现有数据保持原样。禁止为了领域重构执行删库、清表、批量改名或破坏性重建。

## 2. 正式领域模型

十一个一级领域为：

1. Base Platform (`base`)
2. Project Management (`project_management`)
3. Factory (`factory`)
4. Craft (`craft`)
5. Knowledge (`knowledge`)
6. Ontology (`ontology`)
7. Agent (`agent`)
8. Integration (`integration`)
9. Device (`device`)
10. Digital Model (`digital_model`)
11. Simulation (`simulation`)

Device 替换原一级领域 Local Runtime。Device 拥有设备主数据、选型、招投标、供应商协同、采购与验收、设备台账、连接状态、操作记录和设备生命周期等业务结果。Local Runtime 降为 Device 使用的技术运行组件，只负责本地协议适配、设备连接、指令执行、离线队列和回执；它不能拥有独立于 Device 的业务表或业务结果。

Digital Model 与 Simulation 保持两个领域。Digital Model 拥有模型、模型版本、组件、拓扑和发布快照；Simulation 通过 Capability 获取已发布模型，并拥有工况、参数集、求解配置、运行和结果。两个领域可以由同一开发人员和同一开发账号维护，但不能共享表所有权。

## 3. 单数据库中的领域边界

“十一组领域表”不是十一张表。每个领域可以拥有任意数量的表，但每张表只能有一个一级领域 owner。所有业务表名必须以 `workmanship_` 开头。

仓库当前原始盘点结果为 49 个 SQL migration 文件、184 条 `CREATE TABLE`、151 个唯一表名、33 个重复表定义和 86 条 `ALTER TABLE`。151 个已识别唯一表名均满足 `workmanship_` 前缀要求。该数字是原始候选集，不是未经解析即可执行的最终建表数量；最终数量由 Schema 编译器消解重复定义和增量变更后冻结。

为了保护旧表和旧数据：

- 不批量重命名现有 `workmanship_*` 表；
- 不根据缩写前缀猜测 owner；
- 建立逐表枚举的 `domain_table_ownership` 清单作为唯一所有权事实源；
- 新表采用 `workmanship_<domain_token>_<entity>`；
- 旧表即使使用 `workmanship_app_*`、`workmanship_know_*`、`workmanship_sim_*`、`workmanship_model_*`、`workmanship_runtime_*` 等历史前缀，也必须逐表绑定到唯一 owner；
- 未登记表、重复 owner 和跨领域外键均使生成与验收失败。

单数据库下的“独立数据库开发”准确解释为：每个领域独立拥有代码目录、Provider、Repository、表清单、migration 目录、migration ledger、测试和发布版本。它不表示独立数据库实例或独立 OceanBase database。

## 4. 账号与权限模型

### 4.1 测试开发账号

测试环境维护四个人类开发账号：

| 账号职责 | 可维护领域 |
|---|---|
| 工艺 | Craft |
| 数模与仿真 | Digital Model、Simulation |
| 设备 | Device |
| 综合 | Base Platform、Project Management、Factory、Knowledge、Ontology、Agent、Integration |

开发账号只获得已存在且归属于负责领域表的必要 DML 权限。OceanBase MySQL 模式下，单数据库的 `CREATE TABLE` 权限不能安全地按未来表名前缀约束，所以四个开发账号不直接持有数据库级 DDL 权限。开发人员提交 migration 文件，由工具校验 owner、表名和变更类型，再交给 DBA 或专用迁移身份执行。

### 4.2 Runtime 与迁移身份

测试环境另有一个生产同构 Runtime 账号；生产环境使用公司提供的一个 Runtime 账号。Runtime 账号只获得应用实际需要的表级 `SELECT/INSERT/UPDATE/DELETE` 权限，不获得 `CREATE/ALTER/DROP/GRANT`。

DDL 由 DBA 或临时迁移身份在 DBeaver 中执行。该身份不写入 Git、不写入生成产物、不进入服务环境变量，执行完成后撤销或停用。当前 `ai00_test_base@test` 的已知授权只有 `USAGE` 和部分现有表的 DML，不能用于建表或授权。

## 5. Schema 唯一来源与完整性

人工维护一份“全量建表 SQL”容易漏表、漏字段或与增量 migration 漂移，因此仓库 migration 是 Schema 事实来源，工具负责把它们编译为确定性最终状态。

Schema 编译器必须：

1. 只读取 official domain manifest 登记的 migration 路径；
2. 解析每条 `CREATE TABLE`、`ALTER TABLE`、索引和约束语句；
3. 对无法解析的 DDL 立即失败，不得静默跳过；
4. 合并同一表的重复 `CREATE TABLE` 和后续 `ALTER TABLE`；
5. 对字段类型、空值、默认值、主键或索引的冲突定义立即失败；
6. 为每张表、字段、索引和约束保留来源 migration；
7. 校验所有表均以 `workmanship_` 开头且有唯一领域 owner；
8. 禁止跨领域外键；领域关系只能保存稳定引用并通过 Capability 解析；
9. 输出确定性排序和 SHA-256，保证相同提交产生相同 Schema 清单。

编译产物至少包括：

- `domain-table-ownership.json`：表到领域的精确映射；
- `expected-schema.json`：表、字段、类型、空值、默认值、Extra、主键、索引和约束；
- `schema-source-map.json`：每个 Schema 元素的 migration 来源；
- `schema-build-summary.json`：提交、manifest hash、表/字段/索引数量和 Schema hash。

这些文件不得包含数据库密码、连接串或业务行数据。

## 6. 现库只读采集与差异生成

用户在 DBeaver 对 `ai00_test` 执行只读 `information_schema` 查询，导出：

- `ai00_test_tables.csv`
- `ai00_test_columns.csv`
- `ai00_test_indexes.csv`

导出文件只包含结构元数据，不包含业务记录。文件放在 `E:/Projects/ai00_v3/.runtime/schema-audit/`，不得加入 Git。

差异工具读取冻结的 `expected-schema.json` 和三份现场 CSV，输出：

- 缺失表；
- 缺失字段；
- 缺失索引；
- 现场多余表或字段；
- 类型、长度、空值、默认值、主键和索引不一致；
- 未登记或多 owner 表；
- 不安全或需要人工决策的变更。

生成器只自动生成以下非破坏性动作：

- `CREATE TABLE IF NOT EXISTS` 创建缺失表；
- `ADD COLUMN` 添加可安全创建的缺失字段；
- `ADD INDEX` 或 `ADD UNIQUE INDEX` 添加缺失索引。

下列动作不得自动生成或执行：

- `DROP DATABASE`、`DROP TABLE`、`TRUNCATE`、`DELETE`；
- 表或字段重命名；
- 字段类型缩窄；
- 删除字段、索引或约束；
- 修改已有字段为不兼容类型或更严格的非空约束；
- 未提供确定性回填策略的 `NOT NULL` 新字段；
- 任何业务数据复制或覆盖。

遇到不兼容差异时，生成器必须 fail closed，并把差异列入人工审核报告，不能用 `IF NOT EXISTS` 掩盖结构漂移。

## 7. DBeaver 执行包

工具生成一个不含密钥的执行目录：

```text
schema-audit/
├─ 00-preflight.sql
├─ 10-create-missing-tables.sql
├─ 20-add-safe-columns.sql
├─ 30-add-missing-indexes.sql
├─ 40-record-migrations.sql
├─ 90-verify-schema.sql
├─ expected-schema.json
├─ schema-diff.json
├─ execution-checklist.md
└─ SHA256SUMS
```

执行顺序固定。`00-preflight.sql` 验证当前 database、OceanBase 版本、MySQL 兼容模式和执行身份的 DDL 权限，任一不满足即停止。每个阶段均采用确定性语句顺序，并在独立 migration ledger 中记录版本与 checksum。OceanBase/MySQL DDL 可能隐式提交，因此不能假设一个大事务可以回滚全部 DDL；恢复策略依赖幂等语句、阶段检查点和执行前差异冻结，而不是破坏性回滚。

用户只在 DBeaver 中执行经审核的 SQL 文件，不手工拼接表定义。每执行一个阶段都保存 DBeaver 的成功/失败记录；失败后停止，不继续后续阶段。

## 8. 运行时与跨领域共享

单生产账号无法在数据库层阻止代码访问其他领域表，因此还必须有以下边界：

- Domain Repository 通过绑定领域身份的数据访问端口访问数据库；
- 数据访问端口根据 `domain_table_ownership` 拒绝访问非 owner 表；
- 静态边界审计扫描原始 SQL、ORM 表名和内部模块导入；
- Provider 只能返回领域 Capability 合同定义的结果；
- 插件、Agent 和其他领域必须通过 Catalog、授权和 Capability Gateway 调用 Provider；
- 禁止跨领域 SQL、共享 ORM、内部 Repository 导入和复制业务实现；
- 所有写调用保留租户、主体、Capability ID、版本和 correlation ID。

Knowledge 中低频维护、供其他领域计算或算法引用的表，通过版本化 Reference Dataset Capability 发布不可变快照。消费者固定引用发布版本和 hash，可以在本领域建立只读投影，但不能直接查询 Knowledge 原表。发布新版本不静默改变已有计算输入。

## 9. Device 与 Local Runtime 迁移

现有 `official_domains.json`、代码 ownership、migration ownership 和验收证据中与 `local_runtime` 一级领域相关的声明要迁移到 `device`。迁移必须：

- 保留 Local Runtime 可执行程序和协议合同；
- 把其 artifact 标记为 Device 的技术组件；
- 把 `workmanship_runtime_*` 等现有设备连接表精确登记为 Device owner；
- 新设备业务表使用 `workmanship_device_*`；
- 不批量重命名现有 `workmanship_runtime_*` 表；
- 保持设备操作协议兼容，并更新 Catalog、Provider、文档和验收清单。

## 10. 验收标准

只有同时满足以下条件，单数据库配置才可报告完成：

1. 十一个正式领域均存在，Device 为一级领域，Local Runtime 为 Device 技术组件；
2. 所有期望表均以 `workmanship_` 开头且只有一个 owner；
3. Schema 编译器对全部纳入范围的 DDL 零静默跳过；
4. 33 个已知重复定义被一致消解，任何冲突均在生成前失败；
5. 现场与期望 Schema 的表、字段、类型、空值、默认值、主键和索引差异为零，或每个现场额外对象都有明确 legacy owner 与保留决策；
6. 不存在跨领域外键、跨领域 SQL、内部 Repository 导入或消费者绕过 Gateway；
7. 四个开发账号的表级授权与职责矩阵一致；
8. Runtime 账号没有 DDL 或授权能力；
9. 插件与 Agent 的同步和异步 Capability 调用均通过 Gateway；
10. Knowledge Reference Dataset 的发布版本、hash、引用和重放测试通过；
11. Backend、Agent Runtime、MCP Gateway 和 Local Runtime 的测试与本机整体试跑通过；
12. 所有 Schema、差异、SQL 和验收产物通过 secret-shaped 字段扫描。

完成报告必须明确标注 `isolation_profile=single_database_domain_tables`，不得声称实现了物理多数据库隔离或生产账号级领域隔离。

## 11. 明确不做的事项

- 不要求公司提供十一数据库或二十二个长期账号；
- 不安装本地 OceanBase 代替公司测试库；
- 不读取、导出或提交 DBeaver 保存的密码；
- 不修改旧表业务数据；
- 不因重构批量改名现有表；
- 不手工维护一份脱离 migration 的全量建表真相；
- 不用单库约束放宽 Capability Gateway 和领域代码边界。
