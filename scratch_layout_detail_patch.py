from pathlib import Path

p = Path(r'D:/luoyi8/vault/projects/py/AI00/AI00_root/workmanship-web/packages/craft-plugin/web/lineage_view/layout_detail_panel.js')
text = p.read_text(encoding='utf-8')

start = text.rfind('  async _renderRels(gid, mountEl = this._relsBody) {')
if start == -1:
    raise SystemExit('start not found')
end = text.find('\n  }\n}', start)
if end == -1:
    raise SystemExit('end not found')
end += len('\n  }')

new_method = """  async _renderRels(gid, mountEl = this._relsBody) {
    if (!mountEl) return;
    mountEl.innerHTML = '<div style="color:var(--surface2);font-size:11px;padding:8px">加载中…</div>';
    const data = this._getLineageData();
    const lineGrantSet = data?.lineGrantSet || new Set();
    const lineReadOnly = !!data?.lineReadOnly;
    const row = data?.rowByGid?.get(gid);
    const currentLineGid = this._findAncestorOfType(gid, 'line_process', data?.rowByGid) || (row?.node_type === 'line_process' ? row.gid : null);
    const canEditCurrentLine = !lineReadOnly || !currentLineGid || lineGrantSet.has(currentLineGid);
    const hasChildren = data ? (data.childMap.get(gid) || []).filter(r => !r.is_deleted).length > 0 : false;

    let links = [];
    try {
      const resp = await this._cf(
        `/api/bop/entry-links?entry_gid=${encodeURIComponent(gid)}${hasChildren ? '&recursive=true' : ''}`
      );
      links = resp?.data || [];
    } catch {}
    this._relLinks = links;

    const childRows = data ? (data.childMap.get(gid) || []).filter(r => !r.is_deleted) : [];

    if ((!this._relationConfigByLinkType || this._relationConfigByLinkType.size === 0) && row?.node_type) {
      try {
        const schemaResp = await this._cf(`/api/ontology/schema/${encodeURIComponent(row.node_type)}`);
        this._hiddenLinkTypes = new Set(
          (schemaResp?.relations || [])
            .filter(r => r.show_in_detail === false)
            .map(r => r.link_type_binding)
        );
        this._relationConfigByLinkType = new Map(
          (schemaResp?.relations || [])
            .filter(r => r.link_type_binding)
            .map(r => [r.link_type_binding, r])
        );
      } catch {}
    }

    const relationConfigs = Array.from(this._relationConfigByLinkType?.values() || [])
      .filter(r => r.link_type_binding && r.show_in_detail !== false)
      .sort((a, b) => (a.sort_order ?? 99) - (b.sort_order ?? 99) || String(a.label_zh || a.name || '').localeCompare(String(b.label_zh || b.name || '')));

    const groups = [
      { key: 'child', name: '子节点', ntType: 'process', linkTypes: null, linkType: null },
      ...relationConfigs.map(r => ({
        key: `link:${r.link_type_binding}`,
        name: r.label_zh || r.name || r.link_type_binding,
        ntType: r.range_node_type || 'process',
        linkTypes: [r.link_type_binding],
        linkType: r.link_type_binding,
        relation: r,
      })),
    ];
    this._currentRelGroups = groups;

    let html = '';
    for (const grp of groups) {
      let items = [];
      if (grp.key === 'child') {
        items = childRows.map(r => ({
          _key: 'child', _title: r.title || r.gid, _badge: r.node_type,
          _ntType: r.node_type || 'process',
          _row: r, _sourceGid: gid, _sourceTitle: null,
          link: { link_type: 'child', entity_gid: r.gid }, source_entry_gid: gid, source_entry_title: null,
        }));
      } else {
        items = links
          .filter(l => grp.linkTypes.includes(l.link_type))
          .map(l => ({
            _key: grp.key, _title: l.entity_title || l.entity_gid, _badge: l.link_type,
            _ntType: grp.ntType, link: l,
            source_entry_gid: l.source_entry_gid || gid,
            source_entry_title: l.source_entry_title,
          }));
      }

      const isOpen = !items.length ? false : true;
      const addSupported = grp.key === 'child' || [
        'pbom_part',
        'physical_equipment', 'project_equipment',
        'physical_tool', 'project_tools',
        'physical_fixture', 'project_tooling',
        'issue', 'task_std', 'task_custom',
        'knowledge', 'rule_std', 'rule_custom',
      ].includes(grp.linkType);
      html += `
        <div class="ll-rg">
          <div class="ll-rg-hdr" data-key="${_he(grp.key)}">
            <span class="ll-rg-tog">${isOpen ? '▼' : '▶'}</span>
            <span class="lv-nt-dot lv-nt-${_he(grp.ntType)}"></span>
            <span class="ll-rg-name">${_he(grp.name)}</span>
            <span class="ll-rg-cnt">${items.length}</span>
            <button class="ll-rg-add" data-key="${_he(grp.key)}" title="${_he(addSupported ? `添加${grp.name}` : `${grp.name} 暂不支持在此处新增`)}"${canEditCurrentLine && addSupported ? '' : ' disabled style="opacity:.45;cursor:not-allowed"'}>＋</button>
          </div>
          <div class="ll-rg-items${isOpen ? ' open' : ''}">
            ${items.length ? items.map((item, idx) => {
              const fromOther = item.source_entry_gid && item.source_entry_gid !== gid;
              return `
                <div class="ll-ri" data-key="${_he(grp.key)}" data-idx="${idx}">
                  <span class="lv-nt-dot lv-nt-${_he(item._ntType || 'process')}"></span>
                  <span class="ll-ri-title">${_he(item._title || item.link?.entity_gid || '—')}</span>
                  <span class="ll-ri-badge ${_statusBadgeClass(item._badge)}">${_he(item._badge || '')}</span>
                </div>
                ${fromOther ? `<div class="ll-ri-src" data-src-gid="${_he(item.source_entry_gid)}">来自：${_he(item.source_entry_title || item.source_entry_gid)}</div>` : ''}`;
            }).join('') : `<div class="ll-rg-empty">暂无关联${grp.key === 'child' ? '，点击 ＋ 添加' : ''}</div>`}
          </div>
        </div>`;
    }
    mountEl.innerHTML = html;

    mountEl.querySelectorAll('.ll-rg-hdr').forEach(hdr => {
      hdr.addEventListener('click', e => {
        if (e.target.classList.contains('ll-rg-add')) return;
        const wrap = hdr.nextElementSibling;
        const open = wrap.classList.contains('open');
        wrap.classList.toggle('open', !open);
        hdr.querySelector('.ll-rg-tog').textContent = !open ? '▼' : '▶';
      });
    });

    mountEl.querySelectorAll('.ll-ri').forEach(ri => {
      ri.addEventListener('click', () => {
        mountEl.querySelectorAll('.ll-ri').forEach(r => r.classList.remove('sel'));
        ri.classList.add('sel');
        const key = ri.dataset.key;
        const idx = parseInt(ri.dataset.idx);
        const grp = groups.find(g => g.key === key);
        if (!grp) return;

        if (key === 'child') {
          const childItems = childRows.map(r => ({
            _key: 'child', _title: r.title || r.gid, _row: r,
            source_entry_gid: gid, source_entry_title: null, link: { link_type: 'child', entity_gid: r.gid },
          }));
          this._openViewDetail(childItems[idx], gid);
        } else {
          const grpLinks = links.filter(l => grp.linkTypes.includes(l.link_type))
            .map(l => ({ _key: key, _title: l.entity_title || l.entity_gid, link: l,
              source_entry_gid: l.source_entry_gid || gid, source_entry_title: l.source_entry_title }));
          this._openViewDetail(grpLinks[idx], gid);
        }
      });
    });

    mountEl.querySelectorAll('.ll-ri-src').forEach(src => {
      src.addEventListener('click', () => {
        const srcGid = src.dataset.srcGid;
        if (srcGid) this.open(srcGid);
      });
    });

    mountEl.querySelectorAll('.ll-rg-add').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        if (btn.disabled) return;
        if (!canEditCurrentLine) {
          this._toast?.('当前线体无编辑权限（只读）', 'warn');
          return;
        }
        const key = btn.dataset.key;
        const grp = groups.find(g => g.key === key);
        if (!grp) return;
        const currentRow = this._currentRow;
        if (key === 'child') {
          const childInfo = CHILD_TYPE_MAP[currentRow?.node_type || null];
          this._openAddDetail(key, gid, childInfo?.type, childInfo?.label || '子节点');
        } else {
          this._openAddDetail(key, gid, grp.linkType, grp.name);
        }
      });
    });
  }"""

text = text[:start] + new_method + text[end:]
p.write_text(text, encoding='utf-8')
print('patched')
