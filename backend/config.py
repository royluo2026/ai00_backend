"""
backend/config.py
─────────────────
从环境变量读取所有配置。
App Secret 只在这里，永远不序列化到任何响应体。

加载顺序：
    1. 若设置 ENV_FILE，优先加载该文件
    2. 未设置时，按同目录 .env.dev -> .env.test -> .env 依次加载首个存在的文件
    3. 系统环境变量
"""
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# 兼容部署场景：支持通过 ENV_FILE 显式指定配置文件。
# 未指定时，按 .env.dev -> .env.test -> .env 顺序加载首个存在的文件。
# 兼容 Windows 下 GBK/ANSI 编码的 .env 文件。
_HERE = Path(__file__).parent
_env_file = os.getenv("ENV_FILE", "").strip()
_candidates = [_env_file] if _env_file else [".env.dev", ".env.test", ".env"]
for _fname in _candidates:
    _p = Path(_fname) if Path(_fname).is_absolute() else (_HERE / _fname)
    if _p.exists():
        try:
            load_dotenv(_p, override=False, encoding='utf-8')
        except UnicodeDecodeError:
            load_dotenv(_p, override=False, encoding='gbk')
        break


def _require(key: str) -> str:
    val = os.getenv(key, "")
    if not val:
        raise RuntimeError(
            f"环境变量 {key} 未设置。请复制 backend/.env.example 为 backend/.env.dev 并填写。"
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
        url = self.users_db_url
        m = re.match(
            r"(?:mysql|postgresql)://([^:]+):([^@]*)@([^:/]+):?(\d*)/(.+)",
            url,
        )
        if not m:
            raise RuntimeError(
                f"USERS_DB_URL 格式不合法：{url!r}\n"
                "期望格式：mysql://user:password@host:3306/dbname"
            )
        user, password, host, port_str, db = m.groups()
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
        self.jwt_expire_hours         = int(os.getenv("JWT_EXPIRE_HOURS", "72"))
        self.host                     = os.getenv("HOST", "0.0.0.0")
        self.port                     = int(os.getenv("PORT", "8080"))
        self.debug                    = os.getenv("DEBUG", "false").lower() == "true"
        self.public_url               = os.getenv("PUBLIC_URL", "").rstrip("/")
        self.first_super_admin_email  = os.getenv("FIRST_SUPER_ADMIN_EMAIL", "").strip().lower()
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
        self.ois_identify            = os.getenv("OIS_IDENTIFY",            "").strip()
        self.ois_env                 = os.getenv("OIS_ENV",                 "").strip()
        self.ois_ois3_url            = os.getenv("OIS_OIS3_URL",            "").strip()
        self.ois_region              = os.getenv("OIS_REGION",              "").strip()
        self.ois_licloud_appid       = os.getenv("OIS_LICLOUD_APPID",       "").strip()
        self.ois_idaas_url           = os.getenv("OIS_IDAAS_URL",           "").strip()
        self.ois_idaas_client_id     = os.getenv("OIS_IDAAS_CLIENT_ID",     "").strip()
        self.ois_idaas_client_secret = os.getenv("OIS_IDAAS_CLIENT_SECRET", "").strip()
        self.ois_idaas_service_id    = os.getenv("OIS_IDAAS_SERVICE_ID",    "").strip()
        self.ois_public_base_url     = os.getenv("OIS_PUBLIC_BASE_URL",     "").strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()
