/**
 * 全局跨端事件总线（Web <-> Python）
 * 低耦合、支持订阅/发布/销毁、异常兜底、事件去重
 */
window.eventBus = (() => {
  // 事件中心
  const _events = {};

  return {
    /**
     * 订阅事件
     * @param {string} event 事件名
     * @param {Function} callback 回调
     */
    on(event, callback) {
      if (!event || typeof callback !== 'function') return;
      _events[event] = _events[event] || [];
      // 事件去重：不重复订阅
      if (!_events[event].includes(callback)) {
        _events[event].push(callback);
      }
    },

    /**
     * 取消订阅
     */
    off(event, callback) {
      if (!_events[event]) return;
      _events[event] = _events[event].filter(cb => cb !== callback);
      if (_events[event].length === 0) delete _events[event];
    },

    /**
     * 清空事件
     */
    clear(event) {
      event ? delete _events[event] : Object.keys(_events).forEach(k => delete _events[event]);
    },

    /**
     * 发布事件到 Python
     */
    async emit(event, ...data) {
      this.trigger(event, ...data);
    },

    /**
     * 本地触发事件
     */
    trigger(event, ...data) {
      const callbacks = _events[event] || [];
      callbacks.forEach(cb => {
        try {
          cb(...data);
        } catch (e) {
          console.error('[事件总线] 回调异常:', e);
        }
      });
    },

    /**
     * Python 主动推送事件到 Web（内部调用）
     */
    onWebEvent(event, args = []) {
      this.trigger(event, ...args);
    }
  };
})();