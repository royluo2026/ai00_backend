/**
 * Viewer3D — 基于 online-3d-viewer (OV.EmbeddedViewer) 的数模查看器
 * 支持格式：STEP / IGES / BREP / STL / OBJ / GLTF 等
 * 全部本地渲染，无任何网络请求。
 *
 * 加载策略：使用 electronAPI.readFileBase64 读取本地文件，
 * 转为 File 对象后调用 LoadModelFromFileList，
 * 绕过 file:// URL 在 Electron 中被拦截的问题。
 */
class Viewer3D {
  constructor(containerEl) {
    this._container = containerEl;
    this._viewer = null;    // OV.EmbeddedViewer 实例
    this._ready = false;
    this._currentPath = null;
    this._pendingPath = null;  // 初始化未就绪时缓存的文件路径
    this._init();
  }

  _init() {
    if (typeof OV === 'undefined' || typeof OV.EmbeddedViewer === 'undefined') {
      this._showUnavailable('online-3d-viewer 未加载');
      return;
    }
    // 等待容器有真实像素尺寸
    const doInit = () => {
      const w = this._container.clientWidth;
      const h = this._container.clientHeight;
      if (!w || !h) { requestAnimationFrame(doInit); return; }
      this._createViewer();
    };
    requestAnimationFrame(doInit);
  }

  _createViewer() {
    try {
      this._viewer = new OV.EmbeddedViewer(this._container, {
        backgroundColor: new OV.RGBAColor(30, 30, 46, 255),  // Catppuccin Mocha base
        defaultColor:    new OV.RGBColor(137, 180, 250),      // #89b4fa blue
        edgeSettings:    new OV.EdgeSettings(false, new OV.RGBColor(100, 100, 120), 1),
        onModelLoaded:   () => { /* 加载完成 */ },
        onModelLoadFailed: () => { this._showUnavailable('模型加载失败，请检查文件格式'); },
      });
      this._ready = true;
      // 处理初始化前缓存的文件
      if (this._pendingPath) {
        const p = this._pendingPath;
        this._pendingPath = null;
        this.loadCADFile(p);
      }
    } catch (e) {
      this._showUnavailable('3D 查看器初始化失败: ' + e.message);
    }
  }

  /**
   * 加载本地 CAD 文件（STEP/IGES/STL 等）
   * 通过 electronAPI.readFileBase64 读取文件内容，
   * 构造 File 对象后交给 OV.EmbeddedViewer.LoadModelFromFileList。
   */
  async loadCADFile(filePath) {
    if (!filePath) return;
    if (!this._ready) {
      this._pendingPath = filePath;
      return;
    }
    if (this._currentPath === filePath) return;
    this._currentPath = filePath;

    try {
      // 获取 electronAPI（iframe 内需从 parent 取）
      const eAPI = window.electronAPI || window.parent?.electronAPI;

      if (eAPI?.readFileBase64) {
        // 通过 Electron IPC 读取文件，返回 base64 字符串
        const b64 = await eAPI.readFileBase64(filePath);
        if (!b64) { this._showUnavailable('文件读取失败'); return; }

        // base64 → Uint8Array → File 对象（保留原始文件名用于格式识别）
        const binary = atob(b64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        const fileName = filePath.replace(/\\/g, '/').split('/').pop();
        const file = new File([bytes], fileName, { type: 'application/octet-stream' });

        this._viewer.LoadModelFromFileList([file]);
      } else {
        // 降级：直接使用 file:// URL（可能被拦截）
        const fileUrl = filePath.startsWith('file://')
          ? filePath
          : 'file:///' + filePath.replace(/\\/g, '/');
        this._viewer.LoadModelFromUrlList([fileUrl]);
      }
    } catch (e) {
      console.error('[Viewer3D] loadCADFile error:', e);
      this._showUnavailable('模型加载出错: ' + e.message);
    }
  }

  // ── 兼容旧接口 ──────────────────────────────────────────────────────────

  loadSTL(base64Data, nodeId) {
    // o3dv 统一由 loadCADFile 处理，此接口忽略
  }

  clearMeshes() {
    if (!this._ready) return;
    this._currentPath = null;
    this._pendingPath = null;
    try { this._viewer.Clear(); } catch (_) {}
  }

  resetCamera() {
    if (!this._ready) return;
    try { this._viewer.FitModelToWindow(true); } catch (_) {}
  }

  setOperationColors() { /* BOP 工序着色在 o3dv 模式下暂不支持 */ }
  fitCameraToNodes()   { this.resetCamera(); }
  _showPlaceholderMesh() { /* o3dv 有内置的加载状态，无需占位体 */ }

  takeScreenshot() {
    return new Promise(resolve => {
      try {
        const canvas = this._container.querySelector('canvas');
        if (!canvas) { resolve(null); return; }
        canvas.toBlob(blob => resolve(blob), 'image/png');
      } catch (_) { resolve(null); }
    });
  }

  // ── 内部 ────────────────────────────────────────────────────────────────

  _showUnavailable(msg) {
    this._container.innerHTML = `
      <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;
                  height:100%;color:var(--text-muted);gap:12px;font-size:13px;opacity:.6">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
          <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/>
          <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
          <line x1="12" y1="22.08" x2="12" y2="12"/>
        </svg>
        <div>${msg}</div>
      </div>`;
  }

  destroy() {
    try { this._viewer?.Clear?.(); } catch (_) {}
  }
}

window.Viewer3D = Viewer3D;
