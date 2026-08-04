# OceanBase MySQL 兼容基线

AI00 的正式数据库目标不是“任意 MySQL”，而是 **OceanBase 4.3.5 及以上、MySQL 兼容模式**。低版本、Oracle 模式或未开启严格 SQL 模式的实例不得执行部署迁移。

## 发布硬门槛

部署前在 `workmanship-backend` 执行：

```powershell
python backend\scripts\oceanbase_compatibility_audit.py
python backend\scripts\oceanbase_compatibility_audit.py --connect
python backend\scripts\run_migrations.py
```

第二、第三条命令使用仅供部署的 `AI00_DDL_DB_URL`。迁移入口会再次验证：

- 服务端版本不低于 4.3.5；
- `ob_compatibility_mode=MYSQL`；
- `sql_mode` 含 `STRICT_TRANS_TABLES` 或 `STRICT_ALL_TABLES`；
- `GET_LOCK` / `RELEASE_LOCK` 可用；
- 线上 schema 不含带默认值的 TEXT/BLOB 列。

## 仓库 SQL 规则

1. 所有新 DDL 只进入 `backend/db/migrations`，运行进程不得执行 DDL。
2. DDL 必须可安全重放。目前只允许：
   - `CREATE TABLE IF NOT EXISTS`；
   - `CREATE [UNIQUE] INDEX IF NOT EXISTS`；
   - `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`。
3. TEXT/BLOB（含 TINY/MEDIUM/LONG 变体）不得声明任何 `DEFAULT`，包括显式 `DEFAULT NULL`。需要默认值的短文本应使用有明确上限的 `VARCHAR(n)`。
4. 禁止 PostgreSQL 方言：`::type`、`ILIKE`、`JSONB`、`ON CONFLICT`、`RETURNING`、`SERIAL`、`NULLS FIRST/LAST`。
5. 索引名不超过 64 字节，表名不超过 64 字符；标识符避免 OceanBase/MySQL 保留字。
6. 运行时允许使用 `INSERT IGNORE`、`ON DUPLICATE KEY UPDATE`、`GET_LOCK` 和 `FOR UPDATE SKIP LOCKED`，因此最低版本固定为 4.3.5，不得私自降低。
7. 不把 DDL 当作可回滚事务。OceanBase 会在 DDL 前后隐式提交；迁移器逐条提交，仅依赖幂等重放恢复。
8. 已成功应用的迁移校验和不可变化；失败迁移允许修正文件后以新校验和续跑。

## 初始化与历史文件

- 新环境以 `backend/db/mysql_schema.sql` 建立基线，再执行版本化迁移。
- `backend/db/schema.sql`、`backend/db/init_full.sql`、`backend/db/bop_schema_v2.sql` 等是 PostgreSQL 历史材料，不是部署入口。
- `mysql_schema.sql` 已去除 OceanBase 不支持的 TEXT/BLOB 默认值；后续修改必须通过静态审计。

## 向量检索

原知识库接口曾直接执行 pgvector 的 `::vector` / `<=>` SQL。该路径已关闭并返回 501，直到接入明确的 OceanBase 向量能力或独立检索适配器。不得以字符串替换方式把 pgvector SQL 带入生产。

## 官方依据

- [OceanBase MySQL compatibility](https://en.oceanbase.com/docs/common-oceanbase-database-10000000000829643)
- [DDL implicit commit](https://en.oceanbase.com/docs/common-oceanbase-database-10000000000829680)
- [TEXT/BLOB default restriction](https://en.oceanbase.com/docs/common-oceanbase-database-10000000003455977)
- [GET_LOCK](https://en.oceanbase.com/docs/common-oceanbase-database-10000000001379158)
- [SELECT and SKIP LOCKED](https://en.oceanbase.com/docs/common-oceanbase-database-10000000003683917)
- [Reserved keywords](https://en.oceanbase.com/docs/common-oceanbase-database-10000000001103417)
- [Identifier limits](https://en.oceanbase.com/docs/common-oceanbase-database-10000000001103406)