# 内部 GitLab 源码配置部署

按平台管理员要求，本次 deploy 分支包含 backend/.env，镜像复制源码后即可读取。
这些文件只发布到公司内部 GitLab；不要同步到公开仓库或 App 更新仓库。

| 文件 | 用途 |
| --- | --- |
| backend/.env | 当前远端实际配置：backend-test 域名、80 端口、默认 pp_ |
| backend/.env.production.template | 当前远端配置副本，远端只允许 pp_ 和无前缀 |
| backend/.env.test.template | 本机测试配置，test_、127.0.0.1:8080 |
| backend/.env.dev | 本机直接运行时读取的测试配置 |

模板不会自动加载。Docker 默认 ENV_FILE=/chj/app/backend/.env。
正式域名部署时，将 PUBLIC_URL 和 FEISHU_REDIRECT_URI 一起改为正式后端域名；
BACKEND_BASE_URL 使用当前容器的 http://127.0.0.1:80。

平台现有 COPY 源码和 Uvicorn 启动命令可以保留。backend.main 读取容器 .env 后，
在已配置远端切换且尚未由 supervisor 管理时，用 exec 替换为 supervisor；
supervisor 子进程带标记，不会重复启动。平台通过 COMP_NAME=workmanship-backend
和 LI_ENV 注入的环境也会识别为容器，避免误读 .env.dev。

如以后选择同步仓库 Dockerfile，可使用以下入口；本次不要求修改平台配置：

```dockerfile
ARG sdkVersion=3.12
FROM artifactory.ep.chehejia.com/licloud-docker/base/run/python:${sdkVersion}
RUN mkdir -p /chj/app /chj/app/backend/static/uploads && chmod 775 -R /chj
WORKDIR /chj/app
ENV SOURCE_PATH=.
ENV SERVICE_PORT=80
ENV PORT=80
ENV ENV_FILE=/chj/app/backend/.env
COPY ${SOURCE_PATH} .
RUN pip install --upgrade pip && pip install -r backend/requirements.txt
RUN python -m backend.scripts.audit_official_domain_artifacts
EXPOSE 80
CMD ["python", "-m", "backend.scripts.supervise_environment"]
```

切换状态保存至 /chj/data/data-environment-state.json，需要可写且持久化。
启动检查保留：表结构不一致或迁移未就绪时拒绝运行/切换，不自动执行数据库迁移。

Connector 计划签名使用稳定 P-256 密钥；远端与本机各自使用独立密钥。
四项 AI00_CONNECTOR_PLAN_SIGNING_P256_* 配置必须同时存在，重建和重启不得临时生成新密钥。
本次密钥有效期一年，轮换时必须同步 Connector 客户端的信任公钥；这与 Windows 安装包代码签名不同。
就绪检查不会因缺少签名配置而放宽，配置回归测试同时校验密钥处于有效期。
