# 插件平台预发验收手册

本手册把插件基础平台的真实环境门槛固定为可重复执行的顺序。所有命令都在预发环境运行，不在生产租户首次试跑。

## 1. 配置预检

```powershell
python workmanship-backend/backend/scripts/plugin_platform_preflight.py
```

预检必须全部通过，包含：

- DDL、Base、Craft、Simulation、Agent、Device六个数据库连接配置。
- `pymysql`、`dbutils`、`cryptography`、`requests`和OIS SDK。
- 平台Ed25519私钥和至少32字节的插件mount secret。
- 完整OIS配置、预发API地址和管理员验收Token。

工具只报告配置是否有效，不输出密码、Token或私钥内容。

## 2. 执行不可变Migration

使用专用DDL账号：

```powershell
python workmanship-backend/backend/scripts/run_migrations.py
```

应用运行账号不得执行该命令。执行后再次启动应用，Migration readiness必须通过。

## 3. 生成并应用最小权限

由脚本生成期望SQL，DBA审核后应用：

```powershell
python workmanship-backend/backend/scripts/generate_domain_grants.py --database workmanship --account base=ai00_base --account craft=ai00_craft --account simulation=ai00_simulation --account agent=ai00_agent --account device=ai00_device --include-revokes
```

随后以五个运行账号逐表验证：本域表必须允许，其他域表必须因权限拒绝。可选DDL探针使用唯一临时表名；如果CREATE意外成功，工具会立即删除探针并判定失败。

```powershell
python workmanship-backend/backend/scripts/verify_domain_db_isolation.py --verify-ddl-denied
```

## 4. 构建并签名参考插件

开发新插件时先复制`packages/plugin-sdk/templates/web-capability`。模板已经覆盖宿主握手、Capability调用、命名空间存储和数据策略说明；构建器会自动把与平台配套的SDK放入ZIP，插件源码不要自行复制SDK文件。

```powershell
python packages/plugin-sdk/tools/build_release.py packages/plugin-sdk/examples/hello-capability --output-dir packages/plugin-sdk/examples/hello-capability/dist
python packages/plugin-sdk/tools/build_release.py packages/plugin-sdk/examples/hello-capability --output-dir packages/plugin-sdk/examples/hello-capability/dist --version 1.1.0
python packages/plugin-sdk/tools/sign_release.py packages/plugin-sdk/examples/hello-capability/dist/acme.ai00.hello-1.0.0.release.json publisher-private.pem
python packages/plugin-sdk/tools/sign_release.py packages/plugin-sdk/examples/hello-capability/dist/acme.ai00.hello-1.1.0.release.json publisher-private.pem
```

把两个签名分别保存为独立文件。私钥和签名文件不进入仓库。

## 5. 跑真实生命周期

设置`AI00_ACCEPTANCE_API_URL`与`AI00_ACCEPTANCE_ADMIN_TOKEN`后执行：

```powershell
python workmanship-backend/backend/scripts/plugin_platform_acceptance.py --package packages/plugin-sdk/examples/hello-capability/dist/acme.ai00.hello-1.0.0.zip --release packages/plugin-sdk/examples/hello-capability/dist/acme.ai00.hello-1.0.0.release.json --signature signature-1.0.0.txt --upgrade-package packages/plugin-sdk/examples/hello-capability/dist/acme.ai00.hello-1.1.0.zip --upgrade-release packages/plugin-sdk/examples/hello-capability/dist/acme.ai00.hello-1.1.0.release.json --upgrade-signature signature-1.1.0.txt --publisher-public-key publisher-public.pem
```

验收链路覆盖：

1. 注册发布者。
2. 上传、发布者签名校验、OIS保存、管理员审核和平台签名。
3. 安装为disabled、启用、tenant registry出现。
4. 通过短期mount token加载OIS沙箱入口。
5. Web调用一次Capability。
6. 同一Agent Run调用两次，验证使用事实采用同一去重身份。
7. 上传1.1.0、进入upgrading、健康验证失败、回滚到1.0.0。
8. 停用后registry立即消失，最后卸载。

发布者已提前注册时增加`--publisher-exists`。

## 6. 验收判定

以下任一项失败即不得开放第三方插件：

- 迁移校验和变化或Migration readiness失败。
- 任一运行账号能读取其他领域表或拥有DDL权限。
- 未签名、错误hash或未经平台审核的版本能够安装。
- 停用插件仍在registry、mount token仍可访问或Capability仍可调用。
- 同一Agent Run形成多条使用计数。
- 升级失败后无法回滚。

月度快照在下月关闭后核对本月、上月、月增量和成功率；关闭接口幂等，已关闭月份不得重算。

部署调度器每天执行一次以下入口即可；它只寻找上月产生过使用事实的租户，以数据库`INSERT IGNORE`原子抢占关闭权，多实例并发不会重复生成：

```powershell
python workmanship-backend/backend/scripts/plugin_usage_monthly_close.py
```