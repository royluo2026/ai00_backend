"""
backend/plugin_loader.py — 后端插件路由加载器

扫描顺序（优先级从低到高，后者覆盖重复 plugin_id）：
  1. packages/*/manifest.json  — monorepo 开发时使用（含完整 frontend + backend 配置）
  2. plugins/*/manifest.json   — 拆分后的 backend repo 使用（只含 backend 配置）

两个目录均不存在时，后端以无插件模式启动（仅 warning）。
"""
import importlib
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent
_PACKAGES_DIR = _PROJECT_ROOT / "packages"
_PLUGINS_DIR  = _PROJECT_ROOT / "plugins"


class PluginLoader:
    def __init__(self, packages_dir: Path = _PACKAGES_DIR, plugins_dir: Path = _PLUGINS_DIR):
        self._packages_dir = packages_dir
        self._plugins_dir  = plugins_dir
        self._plugins: list[dict] = []
        self._plugin_dirs: dict[str, Path] = {}         # plugin_id → 插件目录（web 路径用）
        self._plugin_backend_dirs: dict[str, Path] = {} # plugin_id → 后端代码目录（sys.path 注入用）

    def _scan_dir(self, base_dir: Path, seen_ids: set, is_backend_dir: bool = False) -> None:
        """扫描一个目录下的 manifest.json，写入 self._plugins / self._plugin_dirs。

        is_backend_dir=True 时（plugins/）：只合并 backend 段，并更新 _plugin_dirs 为
        包含后端代码的目录（供 sys.path 注入），frontend 段保持原有值。
        """
        if not base_dir.exists():
            return
        for pkg_dir in sorted(base_dir.iterdir()):
            if not pkg_dir.is_dir():
                continue
            manifest_path = pkg_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                plugin_id = manifest.get("plugin_id")
                if not plugin_id:
                    logger.warning(f"[PluginLoader] manifest 缺少 plugin_id: {manifest_path}")
                    continue
                if "backend" in manifest and not str(plugin_id).startswith("official."):
                    logger.error(f"[PluginLoader] 拒绝第三方后端代码声明: {manifest_path}")
                    manifest.pop("backend", None)
                if plugin_id in seen_ids:
                    # 已存在：合并 backend 段，更新 backend 目录（用于 sys.path 注入）
                    idx = next(i for i, p in enumerate(self._plugins) if p.get("plugin_id") == plugin_id)
                    if "backend" in manifest:
                        self._plugins[idx]["backend"] = manifest["backend"]
                        self._plugin_backend_dirs[plugin_id] = pkg_dir
                        logger.debug(f"[PluginLoader] plugin_id={plugin_id} backend 段由 {manifest_path} 提供")
                    continue
                seen_ids.add(plugin_id)
                self._plugins.append(manifest)
                self._plugin_dirs[plugin_id] = pkg_dir
                if "backend" in manifest:
                    self._plugin_backend_dirs[plugin_id] = pkg_dir
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"[PluginLoader] 解析 manifest 失败，跳过: {manifest_path} — {e}")

    def discover(self) -> list[dict]:
        """扫描 packages/ 和 plugins/ 目录，返回有效 manifest 列表。"""
        self._plugins = []
        self._plugin_dirs = {}
        self._plugin_backend_dirs = {}
        seen_ids: set[str] = set()

        # packages/：完整 manifest（frontend 段为主），先扫
        self._scan_dir(self._packages_dir, seen_ids)
        # plugins/：backend-only stub，后扫合并 backend 段 + 更新 backend dir
        self._scan_dir(self._plugins_dir,  seen_ids)

        if not self._plugins:
            logger.warning("[PluginLoader] 未发现任何插件（packages/ 和 plugins/ 均为空或不存在）")
        else:
            logger.info(f"[PluginLoader] 发现 {len(self._plugins)} 个插件: {[p['plugin_id'] for p in self._plugins]}")
        return self._plugins

    def get_routers(self) -> list:
        """
        遍历已发现的插件，动态 import routers_module，收集所有路由。

        在 import 前将插件目录注入 sys.path，支持目录名含连字符的 npm 包
        （如 packages/craft-plugin/ 内的 craft_backend.routers）以及
        新结构（plugins/craft/ 内的 craft_backend.routers）。
        """
        routers = []
        for manifest in self._plugins:
            module_path = manifest.get("backend", {}).get("routers_module")
            if not module_path:
                continue

            plugin_id = manifest.get("plugin_id", "")
            # 优先用 _plugin_backend_dirs（plugins/ 目录），fallback 到 _plugin_dirs（packages/）
            pkg_dir = self._plugin_backend_dirs.get(plugin_id) or self._plugin_dirs.get(plugin_id)
            pkg_dir_str = str(pkg_dir) if pkg_dir else None

            # 将插件目录临时注入 sys.path，让 craft_backend 等模块可被 import
            injected = False
            if pkg_dir_str and pkg_dir_str not in sys.path:
                sys.path.insert(0, pkg_dir_str)
                injected = True

            try:
                mod = importlib.import_module(module_path)
                plugin_routers = mod.get_routers()
                routers.extend(plugin_routers)
                logger.info(f"[PluginLoader] 加载路由 {len(plugin_routers)} 个 from {module_path}")
            except ImportError as e:
                logger.warning(f"[PluginLoader] import 失败，跳过: {module_path} — {e}")
            except AttributeError:
                logger.warning(f"[PluginLoader] {module_path} 缺少 get_routers()，跳过")
            except Exception as e:
                logger.error(f"[PluginLoader] 加载路由异常: {module_path} — {e}")
            finally:
                # 加载完成后移除临时 sys.path 条目，避免污染
                if injected and pkg_dir_str in sys.path:
                    sys.path.remove(pkg_dir_str)

        return routers

    def register_capabilities(self, registry) -> tuple[str, ...]:
        """Load Capability providers declared by official backend manifests."""
        loaded: list[str] = []
        for manifest in self._plugins:
            plugin_id = str(manifest.get("plugin_id") or "")
            if not plugin_id.startswith("official."):
                continue
            module_path = manifest.get("backend", {}).get("capabilities_module")
            if not module_path:
                continue

            pkg_dir = self._plugin_backend_dirs.get(plugin_id) or self._plugin_dirs.get(plugin_id)
            pkg_dir_str = str(pkg_dir) if pkg_dir else None
            injected = False
            if pkg_dir_str and pkg_dir_str not in sys.path:
                sys.path.insert(0, pkg_dir_str)
                injected = True

            try:
                mod = importlib.import_module(module_path)
                register = getattr(mod, "register_capabilities")
                register(registry)
                loaded.append(plugin_id)
                logger.info(f"[PluginLoader] 加载 Capability provider: {plugin_id} from {module_path}")
            except Exception as exc:
                raise RuntimeError(
                    f"Capability provider load failed: {plugin_id} ({module_path})"
                ) from exc
            finally:
                if injected and pkg_dir_str in sys.path:
                    sys.path.remove(pkg_dir_str)

        return tuple(loaded)

    def get_web_registry(self) -> dict:
        """
        为网页版构建插件注册表（tab 定义 + nav 项）。
        tab.src 路径转换为 /packages/<plugin_dir>/web/<src> 格式，
        供前端 web_compat.js 的 getPluginRegistry() 调用。
        plugins/ 下的 stub manifest（无 frontend 段）不产生 tab/nav 条目。
        """
        tab_defs = {}
        nav_items = []

        for manifest in self._plugins:
            plugin_id = manifest.get("plugin_id", "")
            if not plugin_id.startswith("official."):
                continue  # third-party Web plugins use the signed tenant registry
            frontend = manifest.get("frontend", {})
            if not frontend:
                continue  # backend-only stub manifest，跳过
            base_path = frontend.get("base_path", "web")
            pkg_dir = self._plugin_dirs.get(plugin_id)

            # 推导 web 可访问的前缀路径
            # base_path 例：'packages/craft-plugin/web' 或 'web'
            if base_path and base_path != "web":
                web_prefix = "/" + base_path.lstrip("/")
            elif pkg_dir:
                # 默认：/packages/<dir_name>/web
                web_prefix = f"/packages/{pkg_dir.name}/web"
            else:
                web_prefix = "/web"

            for tab in frontend.get("tabs", []):
                tid = tab.get("id")
                if not tid or tid in tab_defs:
                    continue
                src = tab.get("src", "")
                resolved_src = f"{web_prefix}/{src}" if src else None
                tab_defs[tid] = {**tab, "src": resolved_src, "_pluginId": plugin_id}

            for nav in frontend.get("nav_items", []):
                nav_items.append({**nav, "_pluginId": plugin_id})

        nav_items.sort(key=lambda x: x.get("order", 9999))
        return {"tabDefs": tab_defs, "navItems": nav_items}
