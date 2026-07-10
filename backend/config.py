"""
backend/config.py
─────────────────
从环境变量读取所有配置。
App Secret 只在这里，永远不序列化到任何响应体。

加载顺序：
    1. 若设置 ENV_FILE，优先加载该文件
    2. 未设置时：
       - 容器内：按同目录 .env -> .env.test.example 依次加载首个存在的文件（跳过 .env.dev）
       - 非容器：按同目录 .env.dev -> .env.test.example -> .env 依次加载首个存在的文件
    3. 系统环境变量
"""
import os
import logging
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

_log = logging.getLogger(__name__)

# backend/.env.example 全量兜底配置（仅在对应环境变量缺失时使用）
_FALLBACK_ENV = {
    "FEISHU_APP_ID": "cli_a9f2faec80f85cef",
    "FEISHU_APP_SECRET": "lM0mSvcfOyK2XMeD6upnQgbnHA81rGCB",
    "FEISHU_REDIRECT_URI": "https://workmanship-backend-test.chehejia.com/auth/feishu/callback",
    "JWT_SECRET": "549bfca71485c1832a064d3f4d251fcbc360b662e72d44fe0aec19c1ebc36a5a",
    "JWT_EXPIRE_HOURS": "72",
    "USERS_DB_URL": "mysql://sht_mes_tool%40mom%23test_bdms01:Hsb2Q%2B6_@sam-bdmsdb01-test.chj.cloud:2883/sht_mes_tool",
    "HOST": "0.0.0.0",
    "PORT": "8081",
    "DEBUG": "true",
    "FIRST_SUPER_ADMIN_EMAIL": "luoyi8@lixiang.com",
    "OIS_REGION": "cnhb01",
    "OIS_IDENTIFY": "vrdos-wms-0xeeEXoe-public",
    "OIS_LICLOUD_APPID": "factory-mes-trial-tool-api",
    "OIS_IDAAS_CLIENT_ID": "79HDtleGluGq0NzrfLDhJh",
    "OIS_IDAAS_CLIENT_SECRET": "eyJrdHkiOiJvY3QiLCJraWQiOiJsVC1mQy1JemdnIiwiYWxnIjoiSFMyNTYiLCJrIjoiUEYwWDd0Y1ZCYXJXMl81MGZTTjhRajVQSkRtQUU5czdPU3hpQ3ctNUlacyJ9",
    "OIS_IDAAS_SERVICE_ID": "5Nku9Oc7V7kAzSwK1aTcNU",
    "OIS_IDAAS_URL": "https://id-ontest.lixiang.com/api",
    "OIS_OIS3_URL": "https://ois3-cnhbnp01-ontest.inner.chj.cloud",
}


def _get_with_fallback(key: str) -> str:
    val = os.getenv(key, "").strip()
    if val:
        return val
    fallback = _FALLBACK_ENV.get(key, "")
    if fallback:
        _log.warning("%s 未注入，使用内置兜底配置", key)
    return fallback

# 兼容部署场景：支持通过 ENV_FILE 显式指定配置文件。
# 容器内未指定 ENV_FILE 时，跳过 .env.dev，避免误读本地开发配置。
# 兼容 Windows 下 GBK/ANSI 编码的 .env 文件。
_HERE = Path(__file__).parent
_env_file = os.getenv("ENV_FILE", "").strip()
_in_container = Path("/.dockerenv").exists()
if _env_file:
    _candidates = [_env_file]
elif _in_container:
    _candidates = [".env", ".env.test.example"]
else:
    _candidates = [".env.dev", ".env.test.example", ".env"]
if _env_file:
    _must_exist = Path(_env_file) if Path(_env_file).is_absolute() else (_HERE / _env_file)
    if not _must_exist.exists():
        raise RuntimeError(f"ENV_FILE 指定的配置文件不存在: {_must_exist}")
    # 避免继承镜像或运行时残留的旧数据库地址（例如 127.0.0.1）。
    os.environ.pop("USERS_DB_URL", None)

_loaded_env_path = None
for _fname in _candidates:
    _p = Path(_fname) if Path(_fname).is_absolute() else (_HERE / _fname)
    if _p.exists():
        # 显式指定 ENV_FILE 或容器内运行时，以文件为准覆盖已有环境变量，避免残留默认值干扰。
        _override = bool(_env_file or _in_container)
        try:
            load_dotenv(_p, override=_override, encoding='utf-8')
        except UnicodeDecodeError:
            load_dotenv(_p, override=_override, encoding='gbk')
        _loaded_env_path = str(_p)
        break

if _loaded_env_path:
    _log.info("配置加载文件: %s | override=%s | in_container=%s", _loaded_env_path, bool(_env_file or _in_container), _in_container)
else:
    _log.info("配置加载文件: 未命中文件候选，使用运行时环境变量")


def _require(key: str) -> str:
    val = _get_with_fallback(key)
    if not val:
        raise RuntimeError(
            f"环境变量 {key} 未设置，且无可用兜底配置。"
        )
    return val


class Settings:
    # 飞书凭证
    feishu_app_id:       str = ""
    feishu_app_secret:   str = ""
    feishu_redirect_uri: str = ""
    feishu_api_base:     str = "https://open.feishu.cn/open-apis"

    # JWT
    jwt_secret:          str = ""
    jwt_expire_hours:    int = 72

    # 数据库
    users_db_url:        str = ""

    # 服务
    host:                     str = "0.0.0.0"
    port:                     int = 8080
    debug:                    bool = False
    # 对外访问 URL（用于网页版 /config 端点告知前端后端地址，留空时前端用 window.location.origin）
    public_url:               str = ""
    # 超管自举：第一个以此邮箱登录飞书的用户自动获得 super_admin 角色
    # 一旦 DB 中已有超管，此配置自动失效（防止被持续滥用为提权通道）
    first_super_admin_email:  str = ""

    # MinIO / S3 兼容对象存储（可选，留空则回退到本地磁盘）
    minio_endpoint:   str = ""   # e.g. "http://192.168.1.100:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket:     str = "ai00"
    minio_public_url: str = ""   # 留空时自动推断为 minio_endpoint/minio_bucket

    @property
    def minio_enabled(self) -> bool:
        return bool(self.minio_endpoint and self.minio_access_key and self.minio_secret_key)

    def get_db_params(self) -> dict:
        """将 USERS_DB_URL 解析为 PyMySQL 连接参数字典。
        支持格式：mysql://user:password@host:port/dbname
        """
        import re
        from urllib.parse import unquote
        url = self.users_db_url
        m = re.match(
            r"(?:mysql|postgresql)://([^:]+):([^@]*)@([^:/]+):?(\d*)/(.+)",
            url,
        )
        if not m:
            raise RuntimeError(
                f"USERS_DB_URL 格式不合法：{url!r}\n"
                "期望格式：mysql://user:password@host:3306/dbname\n"
                "若用户名/密码包含 @ # + 等特殊字符，请先做 URL 编码。"
            )
        user, password, host, port_str, db = m.groups()
        # 配置中允许使用 URL 编码（如 %40、%23、%2B），连接前恢复原始凭证。
        user = unquote(user)
        password = unquote(password)
        db = unquote(db)
        return {
            "host": host,
            "port": int(port_str) if port_str else 3306,
            "user": user,
            "password": password,
            "db": db,
        }

    def __init__(self) -> None:
        self.feishu_app_id            = _require("FEISHU_APP_ID")
        self.feishu_app_secret        = _require("FEISHU_APP_SECRET")
        self.feishu_redirect_uri      = _require("FEISHU_REDIRECT_URI")
        self.jwt_secret               = _require("JWT_SECRET")
        self.users_db_url             = _require("USERS_DB_URL")
        self.jwt_expire_hours         = int(_get_with_fallback("JWT_EXPIRE_HOURS") or "72")
        self.host                     = _get_with_fallback("HOST") or "0.0.0.0"
        self.port                     = int(_get_with_fallback("PORT") or "8080")
        self.debug                    = (_get_with_fallback("DEBUG") or "false").lower() == "true"
        self.public_url               = os.getenv("PUBLIC_URL", "").rstrip("/")
        self.first_super_admin_email  = (_get_with_fallback("FIRST_SUPER_ADMIN_EMAIL") or "").strip().lower()
        # MinIO（可选）
        self.minio_endpoint   = os.getenv("MINIO_ENDPOINT",   "").strip().rstrip("/")
        self.minio_access_key = os.getenv("MINIO_ACCESS_KEY", "").strip()
        self.minio_secret_key = os.getenv("MINIO_SECRET_KEY", "")
        self.minio_bucket     = os.getenv("MINIO_BUCKET",     "ai00").strip()
        _pub = os.getenv("MINIO_PUBLIC_URL", "").strip().rstrip("/")
        if not _pub and self.minio_endpoint:
            _pub = f"{self.minio_endpoint}/{self.minio_bucket}"
        self.minio_public_url = _pub
        # OIS 对象存储（理想汽车内网，可选）— SDK: ois3-sdk-python
        self.ois_identify            = _get_with_fallback("OIS_IDENTIFY").strip()
        self.ois_env                 = os.getenv("OIS_ENV",                 "").strip()
        self.ois_ois3_url            = _get_with_fallback("OIS_OIS3_URL").strip()
        self.ois_region              = _get_with_fallback("OIS_REGION").strip()
        self.ois_licloud_appid       = _get_with_fallback("OIS_LICLOUD_APPID").strip()
        self.ois_idaas_url           = _get_with_fallback("OIS_IDAAS_URL").strip()
        self.ois_idaas_client_id     = _get_with_fallback("OIS_IDAAS_CLIENT_ID").strip()
        self.ois_idaas_client_secret = _get_with_fallback("OIS_IDAAS_CLIENT_SECRET").strip()
        self.ois_idaas_service_id    = _get_with_fallback("OIS_IDAAS_SERVICE_ID").strip()
        self.ois_public_base_url     = os.getenv("OIS_PUBLIC_BASE_URL",     "").strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()
