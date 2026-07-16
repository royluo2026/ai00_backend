/**
 * 全局快捷键/命令管理（Obsidian 风格）
 * 命令注册 → 快捷键绑定 → 执行命令，无硬编码
 */
window.ShortcutManager = (() => {
  let config = {
    enabled: true,
    shortcuts: {}, // 命令ID → 快捷键
    commands: []   // 所有注册命令
  };

  function _api() {
    return null;
  }

  async function init() {
    try {
      const eAPI = window.electronAPI;
      if (!eAPI?.loadShortcuts) return;
      const shortcutData = await eAPI.loadShortcuts();
      const allCommands  = await eAPI.getAllCommands?.() || [];

      config.enabled   = shortcutData?.enabled ?? true;
      config.shortcuts = shortcutData?.keys || {};
      config.commands  = allCommands;

      bindCommandEvents();
      console.log("✅ 命令系统初始化完成", config);
    } catch(e) {
      console.warn("ShortcutManager.init 失败:", e);
    }
  }

  // ===================== 【无硬编码】统一监听命令执行 =====================
  function bindCommandEvents() {
    // 后端执行命令通知
    eventBus.on("command:executed", (commandId) => {
      const cmd = config.commands.find(c => c.id === commandId);
      if (cmd) showToast(`执行：${cmd.name}`);
    });

    // 快捷键更新
    eventBus.on("shortcut:updated", (commandId, newKey) => {
      config.shortcuts[commandId] = newKey;
      showToast(`快捷键已更新`);
    });

    eventBus.on("shortcut:toggled", (enabled) => {
      config.enabled = enabled;
      showToast(enabled ? "快捷键已启用" : "快捷键已禁用");
    });

    eventBus.on("shortcut:reset", async () => {
      const eAPI = window.electronAPI;
      if (!eAPI?.loadShortcuts) return;
      const data = await eAPI.loadShortcuts();
      config.shortcuts = data?.keys || {};
      config.enabled = data?.enabled ?? true;
      showToast("快捷键已重置");
    });

    // 刷新界面命令
    eventBus.on("app:refresh", () => location.reload());
  }

  // ===================== 对外 API =====================
  return {
    init,
    getConfig: () => JSON.parse(JSON.stringify(config)),

    // 启用/禁用快捷键
    async toggle(enabled) {
      await window.electronAPI?.saveShortcuts?.({ ...config, enabled });
    },

    // 给命令设置快捷键
    async setShortcut(commandId, newKey) {
      config.shortcuts[commandId] = newKey;
      await window.electronAPI?.saveShortcuts?.(config);
      return true;
    },

    // 执行命令
    async executeCommand(commandId) {
      await _api().execute_command(commandId);
    },

    // 重置所有快捷键
    async reset() {
      await _api().reset_shortcuts();
    }
  };
})();

// 提示工具
function showToast(msg, type = "success") {
  console.log(`[${type}] ${msg}`);
  alert(msg);
}

// 初始化
document.addEventListener('DOMContentLoaded', () => ShortcutManager.init());