# 后端双环境配置模板

本机测试后端使用 `backend/.env.test.template`，服务器生产后端使用 `backend/.env.production.template`。两份文件只有占位值，不能直接作为运行配置，也不得填入真实凭据后提交到仓库。由部署负责人在各自机器的仓库外建立独立配置文件，用绝对 `ENV_FILE` 路径启动对应服务。

- A/B 的请求统一到本机 `http://127.0.0.1:8080`，后端固定 `AI00_DEPLOY_PROFILE=test`、`TABLE_PREFIX=test_`；C/D 的请求统一到生产 HTTPS 后端，后端部署基线为 `AI00_DEPLOY_PROFILE=production`、`TABLE_PREFIX=pp_`；启用下方受控机制后可由超管切换无前缀生产数据。普通业务请求不选择前缀。
- 为 Base、Craft、Agent、Simulation、Device、Project Management、Knowledge、Digital Model、Integration、Factory、Ontology 配置不同运行账号，且全部指向 DBA 批准的同一物理 host、port 和 schema。迁移 DDL 账号另行保管，不放进客户端或运行账号配置。
- 填写飞书应用及回调、独立 JWT 密钥和真实 CORS 来源。生产 CORS 来源必须由平台 Owner 确认；模板中的占位值会被预检拒绝。生产 `AI00_REQUIRE_MIGRATIONS=1` 只检查迁移账本，不执行 DDL。
- 在任何服务变更前执行 `python -B -m backend.scripts.runtime_preflight --env-file <绝对配置文件路径>`；该检查不连接数据库。还须按实施计划单独验证真实账号权限、表前缀隔离、TLS、OAuth 与 `/ready`。预检通过既不是 DBA/平台批准，也不是运行验收。

受管运行时必须显式指定 `ENV_FILE`，文件内必须有匹配的 profile、前缀和公开地址；启动会在插件路由注册前再次预检。不复制、覆盖或重启现有 8080 服务来试验配置。生产迁移、切流与更新必须走单独批准的变更窗口。

## 远端预生产／生产切换

远端仍使用 `AI00_DEPLOY_PROFILE=production` 和 `TABLE_PREFIX=pp_` 作为部署基线；不修改配置文件的前缀来切换生产。启用后的首次启动连接 pp_，后续启动读取持久化选择。部署配置另加：

```env
AI00_ALLOW_DATA_ENVIRONMENT_SWITCH=1
AI00_DATA_ENVIRONMENT_STATE_FILE=/chj/data/data-environment-state.json
AI00_WEB_WORKERS=1
```

- 必须单个 Linux 后端实例、单个 Gunicorn worker。容器把 `/chj/data` 挂载为可写持久化目录；ENV_FILE 放在镜像／仓库外，通过绝对路径挂载。状态与 `.audit.jsonl` 只允许服务账号和部署管理员写入，不上传本机 `.runtime`。本机制不支持多副本并行部署。
- 容器入口及 `scripts/start_backend.sh` 自动走 `python -m backend.scripts.supervise_environment`。自定义 systemd/平台命令也必须使用这个入口；直接运行 Gunicorn 并启用切换会拒绝启动。关闭切换时仍使用原 Gunicorn 路径。
- 设置只允许在预生产（pp_）与生产（无前缀）间切换。远端默认启动 pp_，启动不做跨环境结构比较；只有选择无前缀生产环境时，才要求其结构与 pp_ 一致，提交及生产环境重启时重新检查。test_ 不参与远端结构准入且不可选。本机开发环境保留 test_ 基准规则。
- 运行账号必须具备各自业务域在 pp_ 与无前缀表上的必要权限；远端结构检查不依赖 test_ 元数据。不要给运行账号授予迁移 DDL 权限。切换机制不会修复表结构、同步数据或扩大数据库权限。
- 超管提交会持久化选择及审计；主管进程等待回应窗口，停止整个旧 Gunicorn 进程组，再启动新环境。旧进程退出前不启动目标，避免两种环境同时服务。新环境 180 秒内未通过 `/ready` 和实际前缀检查时，恢复 previous_prefix，记录回退；原环境也失败则退出交给平台告警，不无限切换。
- 切换影响此后端全部用户；两套前缀的登录会话可能不同，需要重新登录。发布新镜像时已有持久化选择保持不变，不会每次重置 pp_。首次发布应使用空的持久化目录；已有目录先核对选择，禁止为重置环境而直接删除业务数据。

发布验收：先运行 `python -B -m backend.scripts.runtime_preflight --env-file /绝对路径/backend.env`；在部署平台启动新入口后，确认 `/ready` 为 200、`/api/runtime/data-environment` 返回预期前缀；确认远端 test_ 不可选、生产结构不一致时不可选。结构就绪后，在授权窗口验证两方向切换、重新登录和启动失败回退。Windows 单元测试不代替 Linux 进程组／远端数据库运行验收。
