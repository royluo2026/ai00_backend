/**
 * web/icons.js — 全局 SVG 图标精灵注入器
 *
 * 用法（放在 <body> 最顶部，在任何 SVG <use> 之前）：
 *   <script src="icons.js"></script>          — web/ 根目录页面
 *   <script src="../icons.js"></script>        — 子目录页面
 *
 * 使用方式：
 *   <svg class="icon" width="16" height="16"><use href="#icon-settings"/></svg>
 *
 * 辅助函数（注入后可调用）：
 *   window.svgIcon(id, size)  → '<svg class="icon" width="N" height="N"><use href="#id"/></svg>'
 */
(function () {
  var S = (id, paths) =>
    `<symbol id="${id}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${paths}</symbol>`;

  var sprite = `<svg xmlns="http://www.w3.org/2000/svg" style="display:none">

    ${/* ── 系统 / 导航 ────────────────────────────────────── */''}
    ${S('icon-settings',
      '<circle cx="12" cy="12" r="3"/>' +
      '<path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>'
    )}
    ${S('icon-home',
      '<path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>' +
      '<polyline points="9,22 9,12 15,12 15,22"/>'
    )}
    ${S('icon-files',
      '<path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>' +
      '<line x1="9" y1="14" x2="15" y2="14"/>' +
      '<line x1="12" y1="11" x2="12" y2="17"/>'
    )}
    ${S('icon-canvas',
      '<path d="M12 2L2 7l10 5 10-5-10-5z"/>' +
      '<path d="M2 17l10 5 10-5"/>' +
      '<path d="M2 12l10 5 10-5"/>'
    )}
    ${S('icon-table',
      '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>' +
      '<line x1="3" y1="9" x2="21" y2="9"/>' +
      '<line x1="3" y1="15" x2="21" y2="15"/>' +
      '<line x1="9" y1="3" x2="9" y2="21"/>' +
      '<line x1="15" y1="3" x2="15" y2="21"/>'
    )}
    ${S('icon-project',
      '<path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/>' +
      '<rect x="9" y="3" width="6" height="4" rx="1"/>' +
      '<line x1="9" y1="12" x2="15" y2="12"/>' +
      '<line x1="9" y1="16" x2="13" y2="16"/>'
    )}
    ${S('icon-knowledge',
      '<path d="M4 19.5A2.5 2.5 0 016.5 17H20"/>' +
      '<path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/>'
    )}
    ${S('icon-log',
      '<line x1="8" y1="6" x2="21" y2="6"/>' +
      '<line x1="8" y1="12" x2="21" y2="12"/>' +
      '<line x1="8" y1="18" x2="21" y2="18"/>' +
      '<line x1="3" y1="6" x2="3.01" y2="6"/>' +
      '<line x1="3" y1="12" x2="3.01" y2="12"/>' +
      '<line x1="3" y1="18" x2="3.01" y2="18"/>'
    )}
    ${S('icon-tool',
      '<path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/>'
    )}
    ${S('icon-shield',
      '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>'
    )}
    ${S('icon-book-open',
      '<path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/>' +
      '<path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/>'
    )}
    ${S('icon-help',
      '<circle cx="12" cy="12" r="10"/>' +
      '<path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/>' +
      '<line x1="12" y1="17" x2="12.01" y2="17"/>'
    )}
    ${S('icon-factory',
      '<path d="M2 20V8l6-4v4l6-4v4l4-2v14H2z"/>' +
      '<line x1="2" y1="20" x2="22" y2="20"/>' +
      '<line x1="6" y1="12" x2="6" y2="16"/>' +
      '<line x1="10" y1="12" x2="10" y2="16"/>' +
      '<line x1="14" y1="12" x2="14" y2="16"/>'
    )}

    ${/* ── 状态 / 操作 ────────────────────────────────────── */''}
    ${S('icon-robot',
      '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>'
    )}
    ${S('icon-check',
      '<polyline points="20,6 9,17 4,12"/>'
    )}
    ${S('icon-check-circle',
      '<path d="M22 11.08V12a10 10 0 11-5.93-9.14"/>' +
      '<polyline points="22,4 12,14.01 9,11.01"/>'
    )}
    ${S('icon-x',
      '<line x1="18" y1="6" x2="6" y2="18"/>' +
      '<line x1="6" y1="6" x2="18" y2="18"/>'
    )}
    ${S('icon-x-circle',
      '<circle cx="12" cy="12" r="10"/>' +
      '<line x1="15" y1="9" x2="9" y2="15"/>' +
      '<line x1="9" y1="9" x2="15" y2="15"/>'
    )}
    ${S('icon-warning',
      '<path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>' +
      '<line x1="12" y1="9" x2="12" y2="13"/>' +
      '<line x1="12" y1="17" x2="12.01" y2="17"/>'
    )}
    ${S('icon-alert-circle',
      '<circle cx="12" cy="12" r="10"/>' +
      '<line x1="12" y1="8" x2="12" y2="12"/>' +
      '<line x1="12" y1="16" x2="12.01" y2="16"/>'
    )}
    ${S('icon-lock',
      '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>' +
      '<path d="M7 11V7a5 5 0 0110 0v4"/>'
    )}
    ${S('icon-package',
      '<line x1="16.5" y1="9.4" x2="7.5" y2="4.21"/>' +
      '<path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 002 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/>' +
      '<polyline points="3.27,6.96 12,12.01 20.73,6.96"/>' +
      '<line x1="12" y1="22.08" x2="12" y2="12"/>'
    )}

    ${/* ── 用户 / 协同 ────────────────────────────────────── */''}
    ${S('icon-user',
      '<path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/>' +
      '<circle cx="12" cy="7" r="4"/>'
    )}
    ${S('icon-users',
      '<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/>' +
      '<circle cx="9" cy="7" r="4"/>' +
      '<path d="M23 21v-2a4 4 0 00-3-3.87"/>' +
      '<path d="M16 3.13a4 4 0 010 7.75"/>'
    )}

    ${/* ── 业务 / 内容 ────────────────────────────────────── */''}
    ${S('icon-chart',
      '<line x1="18" y1="20" x2="18" y2="10"/>' +
      '<line x1="12" y1="20" x2="12" y2="4"/>' +
      '<line x1="6" y1="20" x2="6" y2="14"/>'
    )}
    ${S('icon-chat',
      '<path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>'
    )}
    ${S('icon-doc',
      '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>' +
      '<polyline points="14,2 14,8 20,8"/>'
    )}
    ${S('icon-mail',
      '<path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>' +
      '<polyline points="22,6 12,13 2,6"/>'
    )}
    ${S('icon-note',
      '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>' +
      '<polyline points="14,2 14,8 20,8"/>' +
      '<line x1="16" y1="13" x2="8" y2="13"/>' +
      '<line x1="16" y1="17" x2="8" y2="17"/>' +
      '<polyline points="10,9 9,9 8,9"/>'
    )}

    ${/* ── 主题 / 外观 ────────────────────────────────────── */''}
    ${S('icon-moon',
      '<path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>'
    )}
    ${S('icon-sun',
      '<circle cx="12" cy="12" r="5"/>' +
      '<line x1="12" y1="1" x2="12" y2="3"/>' +
      '<line x1="12" y1="21" x2="12" y2="23"/>' +
      '<line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>' +
      '<line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>' +
      '<line x1="1" y1="12" x2="3" y2="12"/>' +
      '<line x1="21" y1="12" x2="23" y2="12"/>' +
      '<line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>' +
      '<line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>'
    )}
    ${S('icon-contrast',
      '<circle cx="12" cy="12" r="10"/>' +
      '<path d="M12 2a10 10 0 000 20z" stroke="none" fill="currentColor"/>'
    )}

    ${/* ── UI 操作 ─────────────────────────────────────────── */''}
    ${S('icon-plus',
      '<line x1="12" y1="5" x2="12" y2="19"/>' +
      '<line x1="5" y1="12" x2="19" y2="12"/>'
    )}
    ${S('icon-refresh',
      '<polyline points="23 4 23 10 17 10"/>' +
      '<polyline points="1 20 1 14 7 14"/>' +
      '<path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>'
    )}
    ${S('icon-save',
      '<path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/>' +
      '<polyline points="17,21 17,13 7,13 7,21"/>' +
      '<polyline points="7,3 7,8 15,8"/>'
    )}
    ${S('icon-pin',
      '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/>' +
      '<circle cx="12" cy="10" r="3"/>'
    )}
    ${S('icon-clip',
      '<path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/>'
    )}
    ${S('icon-monitor',
      '<rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>' +
      '<line x1="8" y1="21" x2="16" y2="21"/>' +
      '<line x1="12" y1="17" x2="12" y2="21"/>'
    )}
    ${S('icon-inbox',
      '<polyline points="8,17 12,21 16,17"/>' +
      '<line x1="12" y1="12" x2="12" y2="21"/>' +
      '<path d="M20.88 18.09A5 5 0 0018 9h-1.26A8 8 0 103 16.29"/>'
    )}
    ${S('icon-apps',
      '<circle cx="4" cy="4" r="1.5"/>' +
      '<circle cx="12" cy="4" r="1.5"/>' +
      '<circle cx="20" cy="4" r="1.5"/>' +
      '<circle cx="4" cy="12" r="1.5"/>' +
      '<circle cx="12" cy="12" r="1.5"/>' +
      '<circle cx="20" cy="12" r="1.5"/>' +
      '<circle cx="4" cy="20" r="1.5"/>' +
      '<circle cx="12" cy="20" r="1.5"/>' +
      '<circle cx="20" cy="20" r="1.5"/>'
    )}
    ${S('icon-org',
      '<circle cx="12" cy="5" r="2"/>' +
      '<path d="M12 7v4"/>' +
      '<path d="M6 15a2 2 0 100-4 2 2 0 000 4z"/>' +
      '<path d="M18 15a2 2 0 100-4 2 2 0 000 4z"/>' +
      '<path d="M12 11H6v2M12 11h6v2"/>'
    )}
    ${S('icon-team',
      '<path d="M17 21v-2a4 4 0 00-4-4H7a4 4 0 00-4 4v2"/>' +
      '<circle cx="10" cy="7" r="4"/>' +
      '<path d="M23 21v-2a4 4 0 00-3-3.87"/>' +
      '<path d="M16 3.13a4 4 0 010 7.75"/>'
    )}
    ${S('icon-md-doc',
      '<rect x="3" y="2" width="14" height="18" rx="2"/>' +
      '<path d="M7 8h6M7 12h6M7 16h3"/>' +
      '<path d="M17 6l2 2-2 2"/>' +
      '<path d="M17 14l2-2-2-2" opacity=".4"/>'
    )}
    ${S('icon-bell',
      '<path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/>' +
      '<path d="M13.73 21a2 2 0 01-3.46 0"/>'
    )}
    ${S('icon-star',
      '<polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"/>'
    )}
    ${S('icon-star-filled',
      '<polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26" fill="currentColor"/>'
    )}
    ${S('icon-ebom',
      '<rect x="2" y="3" width="7" height="5" rx="1"/>' +
      '<rect x="2" y="16" width="7" height="5" rx="1"/>' +
      '<rect x="15" y="9" width="7" height="5" rx="1"/>' +
      '<path d="M9 5.5h3.5v5H9"/>' +
      '<path d="M12.5 8h2.5M9 18.5h3.5v-5H9"/>' +
      '<path d="M12.5 16h2.5"/>'
    )}
    ${S('icon-cube',
      '<path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/>' +
      '<polyline points="3.27 6.96 12 12.01 20.73 6.96"/>' +
      '<line x1="12" y1="22.08" x2="12" y2="12"/>'
    )}
    ${S('icon-onto',
      '<circle cx="12" cy="5" r="2.5"/>' +
      '<circle cx="4" cy="18" r="2.5"/>' +
      '<circle cx="20" cy="18" r="2.5"/>' +
      '<line x1="12" y1="7.5" x2="5.5" y2="16"/>' +
      '<line x1="12" y1="7.5" x2="18.5" y2="16"/>' +
      '<line x1="6.5" y1="18" x2="17.5" y2="18"/>'
    )}
    ${S('icon-datasource',
      '<ellipse cx="12" cy="5" rx="7" ry="2.5"/>' +
      '<path d="M5 5v4c0 1.38 3.13 2.5 7 2.5s7-1.12 7-2.5V5"/>' +
      '<path d="M5 9v5c0 1.38 3.13 2.5 7 2.5s7-1.12 7-2.5V9"/>' +
      '<path d="M5 14v4c0 1.38 3.13 2.5 7 2.5s7-1.12 7-2.5v-4"/>' +
      '<path d="M17 19l2 2 4-4" stroke-width="2"/>'
    )}

  </svg>`;

  var div = document.createElement('div');
  div.innerHTML = sprite;
  function _insertSprite() {
    document.body.insertBefore(div.firstChild, document.body.firstChild);
  }
  if (document.body) {
    _insertSprite();
  } else {
    document.addEventListener('DOMContentLoaded', _insertSprite);
  }

  /** 生成 SVG <use> 引用字符串，供 JS innerHTML 使用 */
  window.svgIcon = function (id, size) {
    size = size || 16;
    return '<svg class="icon" width="' + size + '" height="' + size + '"><use href="#' + id + '"/></svg>';
  };
})();
