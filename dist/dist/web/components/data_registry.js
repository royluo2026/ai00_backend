'use strict';
/**
 * DataRegistry — 模块数据注册协议
 * 每个模块在 init() 末尾调用 DataRegistry.register(id, spec) 并向父窗口 postMessage
 *
 * spec 字段：
 *   label        string     显示名
 *   icon         string     图标名
 *   capabilities string[]   能力 id 列表（对应 capabilities.html 中的 id）
 *   columns      ColDef[]   GridEditor 列定义（可选）
 *   getRows      ()=>row[]  获取当前行数据（可选）
 *   onRowsChange (rows)=>   行变更回调（可选）
 *   cellRenderers object    cellRenderer 映射（可选）
 *   rowCount     number     当前行数（postMessage 时附带）
 */
class DataRegistry {
  constructor() {
    this._modules = new Map();
  }

  /**
   * 注册模块并向父窗口广播
   * @param {string} moduleId
   * @param {object} spec
   */
  register(moduleId, spec) {
    this._modules.set(moduleId, spec);
    // Broadcast to parent window (workbench relay)
    try {
      const rowCount = typeof spec.getRows === 'function'
        ? spec.getRows().length
        : (spec.rowCount ?? 0);
      window.parent.postMessage({
        type: 'dr:register',
        moduleId,
        spec: {
          label:        spec.label        || moduleId,
          icon:         spec.icon         || 'icon-table',
          capabilities: spec.capabilities || [],
          rowCount,
        },
      }, '*');
    } catch (_) {}
  }

  get(moduleId)  { return this._modules.get(moduleId); }
  all()          { return [...this._modules.values()]; }
  ids()          { return [...this._modules.keys()]; }
}

window.DataRegistry = new DataRegistry();

