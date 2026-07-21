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
import json
import logging
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from urllib.parse import quote

from dotenv import load_dotenv

_log = logging.getLogger(__name__)

_FALLBACK_ENV = {
    "JWT_EXPIRE_HOURS": "72",
    "HOST": "0.0.0.0",
    "PORT": "8080",
    "PUBLIC_URL": "",
    "BACKEND_BASE_URL": "",
    "CORS_ALLOW_ORIGINS": "http://127.0.0.1:5173,http://localhost:5173,https://workmanship-web-test.chehejia.com,app://root,null",
    "DEBUG": "true",
    "FIRST_SUPER_ADMIN_EMAIL": "",
}


def _system_json_path() -> Path:
    return Path.home() / '.ai00' / 'config' / 'system.json'


def _load_system_json() -> dict:
    path = _system_json_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _cloud_db_url_from_saved_config(cfg: dict) -> str:
    host = str(cfg.get('host') or '').strip()
    user = str(cfg.get('user') or '').strip()
    password = str(cfg.get('password') or '').strip()
    collab_db = str(cfg.get('collab_db') or '').strip()
    if not (host and user and password and collab_db):
        return ''
    port = int(cfg.get('port') or 2883)
    return (
        f"mysql://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{quote(collab_db, safe='')}"
    )



def _load_saved_cloud_db_url() -> str:
    cfg = _load_system_json().get('cloud_db_config') or {}
    if not isinstance(cfg, dict):
        return ''
    rebuilt = _cloud_db_url_from_saved_config(cfg)
    if rebuilt:
        return rebuilt
    return ''


def _load_saved_feishu_config() -> dict:
    cfg = _load_system_json().get('feishu_config') or {}
    return cfg if isinstance(cfg, dict) else {}


def _load_saved_ois_config() -> dict:
    cfg = _load_system_json().get('ois_config') or {}
    return cfg if isinstance(cfg, dict) else {}


def _get_with_fallback(key: str) -> str:
    val = os.getenv(key, "").strip()
    if val:
        return val
    fallback = _FALLBACK_ENV.get(key, "")
    if fallback:
        _log.warning("%s 未注入，使用内置兜底配置", key)
    return fallback


def _get_csv_list(key: str, default: str = "") -> list[str]:
    raw = _get_with_fallback(key) or default
    return [item.strip() for item in raw.split(",") if item.strip()]

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
    backend_base_url:         str = ""
    cors_allow_origins:       list[str] = []
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

    @property
    def internal_backend_base_url(self) -> str:
        if self.backend_base_url:
            return self.backend_base_url
        host = (self.host or "0.0.0.0").strip()
        if host in {"0.0.0.0", "::", "::0", ""}:
            host = "127.0.0.1"
        return f"http://{host}:{self.port}"

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
        _feishu_saved = _load_saved_feishu_config()
        self.feishu_app_id            = str(_feishu_saved.get("app_id") or _require("FEISHU_APP_ID")).strip()
        self.feishu_app_secret        = str(_feishu_saved.get("app_secret") or _require("FEISHU_APP_SECRET")).strip()
        self.feishu_redirect_uri      = str(_feishu_saved.get("redirect_uri") or _require("FEISHU_REDIRECT_URI")).strip()
        self.jwt_secret               = _require("JWT_SECRET")
        self.users_db_url             = _load_saved_cloud_db_url() or _require("USERS_DB_URL")
        self.jwt_expire_hours         = int(_get_with_fallback("JWT_EXPIRE_HOURS") or "72")
        self.host                     = (_get_with_fallback("HOST") or "0.0.0.0").strip()
        self.port                     = int(_get_with_fallback("PORT") or "8080")
        self.debug                    = (_get_with_fallback("DEBUG") or "false").lower() == "true"
        self.public_url               = _get_with_fallback("PUBLIC_URL").rstrip("/")
        self.backend_base_url         = _get_with_fallback("BACKEND_BASE_URL").rstrip("/")
        self.cors_allow_origins       = _get_csv_list("CORS_ALLOW_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173,https://workmanship-web-test.chehejia.com,app://root,null")
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
        _ois_saved = _load_saved_ois_config()
        self.ois_identify            = str(_ois_saved.get("identify") or _get_with_fallback("OIS_IDENTIFY")).strip()
        self.ois_env                 = str(_ois_saved.get("env") or os.getenv("OIS_ENV", "")).strip()
        self.ois_ois3_url            = str(_ois_saved.get("ois3_url") or _get_with_fallback("OIS_OIS3_URL")).strip()
        self.ois_region              = str(_ois_saved.get("region") or _get_with_fallback("OIS_REGION")).strip()
        self.ois_licloud_appid       = str(_ois_saved.get("licloud_appid") or _get_with_fallback("OIS_LICLOUD_APPID")).strip()
        self.ois_idaas_url           = str(_ois_saved.get("idaas_url") or _get_with_fallback("OIS_IDAAS_URL")).strip()
        self.ois_idaas_client_id     = str(_ois_saved.get("idaas_client_id") or _get_with_fallback("OIS_IDAAS_CLIENT_ID")).strip()
        self.ois_idaas_client_secret = str(_ois_saved.get("idaas_client_secret") or _get_with_fallback("OIS_IDAAS_CLIENT_SECRET")).strip()
        self.ois_idaas_service_id    = str(_ois_saved.get("idaas_service_id") or _get_with_fallback("OIS_IDAAS_SERVICE_ID")).strip()
        self.ois_public_base_url     = str(_ois_saved.get("public_base_url") or os.getenv("OIS_PUBLIC_BASE_URL", "")).strip()
        # Gitea token（用于查询 pipeline 状态）
        self.gitea_token            = os.getenv("GITEA_TOKEN", "").strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()
