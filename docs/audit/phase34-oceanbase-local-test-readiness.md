# Phase 34：本地 OceanBase 测试环境与部署就绪门禁

日期：2026-08-05

## 目标

- 测试环境与生产环境统一使用 OceanBase MySQL 模式。
- 测试后台不得因机器遗留配置重新连接生产数据库。
- 部署前验证依赖、关键路由、基线表、版本化迁移和领域数据库配置。
- 恢复插件市场路由，并把运行账号限制在各自领域表内。

## 环境结果

- WSL2：Ubuntu 22.04。
- OceanBase CE：4.3.5.1，MySQL 模式，严格 SQL 模式。
- Observer：仅用于本机测试，端口 2881。
- 租户与数据库：`test` / `ai00_test`。
- 账号：DDL、base、craft、agent、simulation、device 共六个独立账号。
- 凭证仅保存在本机 WSL 状态目录和测试部署运行配置中，未写入 Git。
- 原 MySQL 9.7 临时实例和数据目录已删除，端口 3307 已释放。
- 未修改生产数据库，未向 GitLab 推送。

## 代码改动

1. 显式 `ENV_FILE` 成为部署数据库边界，`USERS_DB_URL` 不再被桌面保存的旧生产配置覆盖。
2. `run_migrations.py` 支持空库基线初始化，再执行版本化迁移。
3. 迁移器兼容 OceanBase 4.3.5.1：
   - 执行期去除旧迁移中的 JSON 表达式默认值，同时保持原文件校验值不变；
   - 对 `ADD COLUMN IF NOT EXISTS` 和 `CREATE INDEX IF NOT EXISTS` 先查询系统目录，再执行标准 DDL；
   - OceanBase 隐式提交后仍可安全重试。
4. 修正 `mysql_schema.sql` 中 113 处 JSON 默认值及五处不兼容的前缀主键。
5. 新增两份正式迁移，补齐原先依赖运行时临时建表的 8 张表。
6. 新增 `/ready`，检查关键路由、领域数据库配置、迁移账本和工艺数据库连接。
7. 路由自检改用 OpenAPI 路径清单，兼容 FastAPI 0.139+ 的延迟路由包装。
8. Gitea 测试部署先安装后端依赖、执行预检和迁移，`/ready` 成功后才判定部署成功。
9. 插件市场所需 `cryptography` 已在测试虚拟环境安装，依赖安装也已进入工作流。

## 验证证据

- OceanBase 静态与在线兼容审计：通过。
- 基线与版本化迁移：16/16 应用成功（原 14 + 新增 2）。
- 表清单：136 expected / 136 live / 0 missing / 0 extra。
- 领域权限隔离：690/690 通过，包括本域读取、跨域拒绝、运行账号 DDL 拒绝。
- 聚焦回归测试：35/35 通过。
- 临时实例烟雾测试：`/health` 200、`/ready` 200；插件市场 registry 已挂载，缺少调用参数时返回 422 而非 404。
- 完整历史测试集：428 通过、45 失败。失败集中在已经拆分后仍引用旧前端路径、旧接口返回结构和旧 mock 契约的历史测试；本阶段相关测试全部通过，未把这 45 项伪装成通过。

## 运维注意

- Windows 重启后，必须先启动 WSL 中的 `demo` OceanBase 集群，再启动或重启 `AI00Backend-V2`。
- 测试部署配置位于 `E:\projects\ai00-v2\backend\.env.v2.runtime`，不得复制到生产环境。
- DDL 账号只存在于 `.env.v2.migration` 并只允许部署任务使用；应用进程加载 `.env.v2.runtime`，其中只有五个领域运行账号。
- 本地 OceanBase 的启停与升级应通过 OBD 管理，并在升级前备份 `ai00_test`。
