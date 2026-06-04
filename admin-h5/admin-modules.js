// Auto-generated module file. Loaded after app.js to add Dashboard / AuditLog /
// OrderDetailDrawer modules without surgically slicing the monolithic app.js.
// (The original app.js wires init() to look up these globals via the patched
//  ROUTES table and bind() calls.)

const Dashboard = {
  async load() {
    const cards = $('#dashboardCards');
    cards.innerHTML = '<div class="empty" style="padding:24px">加载中…</div>';
    try {
      const data = await apiCall('/api/v1/admin/dashboard/summary');
      this.render(data);
      state.dashboard.loaded = true;
    } catch (e) {
      if (handleAuthError(e)) return;
      cards.innerHTML = '<div class="empty" style="padding:24px;color:#ff4d4f">加载失败：' + escapeHtml(e.message) + '</div>';
    }
  },
  render(data) {
    const c = data.cards || {};
    const items = [
      { label: '今日订单', value: c.today_order_count, hint: 'created ≥ 今日 00:00 UTC' },
      { label: '今日 GMV (¥)', value: fmtAmount(c.today_gmv), hint: 'payment_state = paid' },
      { label: '待审陪诊师', value: c.pending_companion_verifications, mod: c.pending_companion_verifications > 0 ? 'alert' : 'ok' },
      { label: '未关闭对账差异', value: c.open_reconciliation_diffs, mod: c.open_reconciliation_diffs > 0 ? 'alert' : 'ok' },
      { label: '退款处理中', value: c.refund_pending_orders, mod: c.refund_pending_orders > 0 ? 'alert' : '' },
      { label: '近 7 日新增用户', value: c.active_users_7d },
    ];
    $('#dashboardCards').innerHTML = items.map((it) => (
      '<div class="kpi-card' + (it.mod ? ' kpi-card--' + it.mod : '') + '">' +
        '<div class="kpi-card__label">' + escapeHtml(it.label) + '</div>' +
        '<div class="kpi-card__value">' + escapeHtml(String(it.value ?? '-')) + '</div>' +
        (it.hint ? '<div class="kpi-card__hint">' + escapeHtml(it.hint) + '</div>' : '') +
      '</div>'
    )).join('');

    const trend = data.trend_7d || [];
    $('#dashboardTrendTbody').innerHTML = trend.length
      ? trend.map((p) => (
          '<tr><td>' + escapeHtml(p.date) + '</td>' +
          '<td style="text-align:right">' + p.orders + '</td>' +
          '<td style="text-align:right">' + escapeHtml(fmtAmount(p.gmv)) + '</td></tr>'
        )).join('')
      : '<tr><td colspan="3" class="empty">暂无数据</td></tr>';

    $('#dashboardSparkline').innerHTML = this.renderSparkline(trend);
    $('#dashboardGeneratedAt').textContent = data.generated_at
      ? '生成于 ' + new Date(data.generated_at).toLocaleString()
      : '';
  },
  renderSparkline(trend) {
    if (!trend.length) return '<div class="spark-empty">暂无数据</div>';
    const totalOrders = trend.reduce((s, p) => s + (p.orders || 0), 0);
    if (totalOrders === 0) {
      return '<div class="spark-empty">近 7 日暂无订单。上表可查看明细。</div>';
    }
    const W = 720, H = 140;
    const PAD_L = 12, PAD_R = 12, PAD_T = 22, PAD_B = 28;
    const max = Math.max(1, ...trend.map((p) => p.orders));
    const stepX = (W - PAD_L - PAD_R) / Math.max(1, trend.length - 1);
    const baselineY = H - PAD_B;
    const pts = trend.map((p, i) => {
      const x = PAD_L + i * stepX;
      const y = baselineY - ((p.orders / max) * (H - PAD_T - PAD_B));
      return [x, y, p];
    });
    const linePath = pts.map((pt, i) => (i === 0 ? 'M' : 'L') + pt[0].toFixed(1) + ',' + pt[1].toFixed(1)).join(' ');
    const areaPath = linePath + ' L' + pts[pts.length - 1][0].toFixed(1) + ',' + baselineY + ' L' + pts[0][0].toFixed(1) + ',' + baselineY + ' Z';
    const dots = pts.map((pt) => (
      '<circle class="spark-dot" cx="' + pt[0].toFixed(1) + '" cy="' + pt[1].toFixed(1) + '" r="3.5">' +
        '<title>' + escapeHtml(pt[2].date + ' · ' + pt[2].orders + ' 单') + '</title>' +
      '</circle>'
    )).join('');
    const valueLabels = pts.map((pt) => (
      pt[2].orders > 0
        ? '<text class="spark-value" x="' + pt[0].toFixed(1) + '" y="' + (pt[1] - 8).toFixed(1) + '" text-anchor="middle">' + pt[2].orders + '</text>'
        : ''
    )).join('');
    const xLabels = pts.map((pt) => (
      '<text class="spark-label" x="' + pt[0].toFixed(1) + '" y="' + (H - 8) + '" text-anchor="middle">' + escapeHtml(pt[2].date.slice(5)) + '</text>'
    )).join('');
    const baseline = '<line class="spark-axis" x1="' + PAD_L + '" y1="' + baselineY + '" x2="' + (W - PAD_R) + '" y2="' + baselineY + '"/>';
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMidYMid meet">' +
      baseline +
      '<path class="spark-area" d="' + areaPath + '"/>' +
      '<path class="spark-line" d="' + linePath + '"/>' +
      dots + valueLabels + xLabels +
    '</svg>';
  },
  bind() {
    const btn = $('#dashboardRefreshBtn');
    if (btn) btn.addEventListener('click', () => this.load());
  },
};

const AuditLog = {
  async load() {
    const tbody = $('#auditTbody');
    tbody.innerHTML = '<tr><td colspan="6" class="empty">加载中…</td></tr>';
    const f = state.audit.filters;
    const qs = buildQuery({
      page: state.audit.page,
      page_size: PAGE_SIZE,
      target_type: f.target_type,
      target_id: f.target_id,
      action: f.action,
      operator: f.operator,
      since: f.since ? new Date(f.since).toISOString() : '',
      until: f.until ? new Date(f.until).toISOString() : '',
    });
    try {
      const res = await apiCall('/api/v1/admin/audit-logs' + qs);
      state.audit.items = res.items || [];
      state.audit.total = res.total || 0;
      this.render();
    } catch (e) {
      if (handleAuthError(e)) return;
      toast('加载审计日志失败：' + e.message, 'error');
      tbody.innerHTML = '<tr><td colspan="6" class="empty">加载失败</td></tr>';
    }
  },
  render() {
    const tbody = $('#auditTbody');
    const items = state.audit.items;
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty">暂无记录</td></tr>';
    } else {
      tbody.innerHTML = items.map((r) => (
        '<tr>' +
          '<td>' + escapeHtml(new Date(r.created_at).toLocaleString()) + '</td>' +
          '<td><code>' + escapeHtml(r.action) + '</code></td>' +
          '<td>' + escapeHtml(r.target_type) + '</td>' +
          '<td class="id-cell">' + escapeHtml(r.target_id) + '</td>' +
          '<td>' + escapeHtml(r.operator) + '</td>' +
          '<td>' + escapeHtml(r.reason || '-') + '</td>' +
        '</tr>'
      )).join('');
    }
    const totalPages = Math.max(1, Math.ceil(state.audit.total / PAGE_SIZE));
    $('#auditPageInfo').textContent = '第 ' + state.audit.page + ' / ' + totalPages + ' 页 · 共 ' + state.audit.total + ' 条';
    $('#auditPrevBtn').disabled = state.audit.page <= 1;
    $('#auditNextBtn').disabled = state.audit.page >= totalPages;
  },
  applyFiltersFromUI() {
    state.audit.filters = {
      target_type: $('#auditFilterTargetType').value.trim(),
      target_id: $('#auditFilterTargetId').value.trim(),
      action: $('#auditFilterAction').value.trim(),
      operator: $('#auditFilterOperator').value.trim(),
      since: $('#auditFilterSince').value,
      until: $('#auditFilterUntil').value,
    };
    state.audit.page = 1;
  },
  resetFilters() {
    ['#auditFilterTargetType','#auditFilterTargetId','#auditFilterAction','#auditFilterOperator','#auditFilterSince','#auditFilterUntil']
      .forEach((s) => { $(s).value = ''; });
    this.applyFiltersFromUI();
    this.load();
  },
  bind() {
    $('#auditRefreshBtn').addEventListener('click', () => this.load());
    $('#auditSearchBtn').addEventListener('click', () => { this.applyFiltersFromUI(); this.load(); });
    $('#auditResetBtn').addEventListener('click', () => this.resetFilters());
    $('#auditPrevBtn').addEventListener('click', () => { if (state.audit.page > 1) { state.audit.page--; this.load(); } });
    $('#auditNextBtn').addEventListener('click', () => { state.audit.page++; this.load(); });
  },
};

const OrderDetailDrawer = {
  async open(orderId) {
    state.orderDetail = { id: orderId, raw: null, timeline: [], notes: [] };
    $('#orderDetailTitle').textContent = '订单详情 · ' + orderId;
    $('#orderDetailRaw').textContent = '加载中…';
    const famEl = $('#orderFamilyMember');
    if (famEl) { famEl.hidden = true; famEl.innerHTML = ''; }
    $('#orderTimelineList').innerHTML = '<li class="empty">加载中…</li>';
    $('#orderNotesList').innerHTML = '<div class="empty">加载中…</div>';
    $('#orderNoteInput').value = '';
    show($('#orderDetailModal'));
    await Promise.all([this.loadRaw(), this.loadTimeline(), this.loadNotes()]);
  },
  close() {
    hide($('#orderDetailModal'));
    state.orderDetail.id = null;
  },
  async loadRaw() {
    try {
      const data = await apiCall('/api/v1/admin/orders/' + state.orderDetail.id);
      state.orderDetail.raw = data;
      $('#orderDetailRaw').textContent = JSON.stringify(data, null, 2);
      this.renderFamilyMember(data);
    } catch (e) {
      if (handleAuthError(e)) return;
      $('#orderDetailRaw').textContent = '加载失败：' + e.message;
    }
  },

  /** [F-05] 代他人下单：接口返回 order.family_member (可为 null)，非空时在原始 JSON 上方额外渲染一条醒目提示 */
  renderFamilyMember(order) {
    const el = $('#orderFamilyMember');
    if (!el) return;
    const fm = order && order.family_member;
    if (!fm || !fm.name) { el.hidden = true; el.innerHTML = ''; return; }
    const relMap = {
      self: '本人', parent: '父母', spouse: '配偶', child: '子女',
      sibling: '兄弟姐妹', grandparent: '祖父母', relative: '亲戚',
      friend: '朋友', other: '其他',
    };
    const relLabel = relMap[fm.relation] || '其他';
    const phone = fm.phone ? escapeHtml(fm.phone) : '-';
    el.innerHTML =
      '<div class="detail-family__label">实际就诊人</div>' +
      '<div class="detail-family__value">' +
        escapeHtml(fm.name) + '（' + escapeHtml(relLabel) + '） · ' + phone +
      '</div>';
    el.hidden = false;
  },
  async loadTimeline() {
    try {
      const data = await apiCall('/api/v1/admin/orders/' + state.orderDetail.id + '/timeline');
      state.orderDetail.timeline = data.entries || [];
      this.renderTimeline();
    } catch (e) {
      if (handleAuthError(e)) return;
      $('#orderTimelineList').innerHTML = '<li class="empty">加载失败：' + escapeHtml(e.message) + '</li>';
    }
  },
  renderTimeline() {
    const list = $('#orderTimelineList');
    const entries = state.orderDetail.timeline;
    if (!entries.length) { list.innerHTML = '<li class="empty">没有状态变迁记录</li>'; return; }
    list.innerHTML = entries.map((e) => (
      '<li>' +
        '<div class="ts">' + escapeHtml(new Date(e.created_at).toLocaleString()) + '</div>' +
        '<div class="transition">' +
          escapeHtml(statusLabel(e.from_status) + ' → ') +
          statusPill(e.to_status, statusLabel(e.to_status)) +
        '</div>' +
        (e.note ? '<div class="note">备注：' + escapeHtml(e.note) + '</div>' : '') +
        '<div class="ts">by ' + escapeHtml(e.changed_by) + '</div>' +
      '</li>'
    )).join('');
  },
  async loadNotes() {
    try {
      const qs = buildQuery({ target_type: 'order', target_id: state.orderDetail.id, limit: 100 });
      const data = await apiCall('/api/v1/admin/notes' + qs);
      state.orderDetail.notes = data.items || [];
      this.renderNotes();
    } catch (e) {
      if (handleAuthError(e)) return;
      $('#orderNotesList').innerHTML = '<div class="empty">加载失败：' + escapeHtml(e.message) + '</div>';
    }
  },
  renderNotes() {
    const list = $('#orderNotesList');
    const notes = state.orderDetail.notes;
    if (!notes.length) { list.innerHTML = '<div class="empty">暂无备注</div>'; return; }
    list.innerHTML = notes.map((n) => {
      const mine = n.operator === state.operator;
      const updated = n.updated_at && n.updated_at !== n.created_at
        ? ' · 编辑于 ' + new Date(n.updated_at).toLocaleString()
        : '';
      return (
        '<div class="note-item" data-id="' + escapeAttr(n.id) + '">' +
          '<div class="note-item__meta">' +
            '<span>' + escapeHtml(n.operator) + ' · ' + escapeHtml(new Date(n.created_at).toLocaleString()) + escapeHtml(updated) + '</span>' +
            (mine
              ? '<span class="note-item__actions">' +
                  '<button class="btn btn-ghost" data-note-action="edit">编辑</button>' +
                  '<button class="btn btn-danger" data-note-action="delete">删除</button>' +
                '</span>'
              : '') +
          '</div>' +
          '<pre class="note-item__body">' + escapeHtml(n.body) + '</pre>' +
        '</div>'
      );
    }).join('');
  },
  async submitNote() {
    const body = $('#orderNoteInput').value.trim();
    if (!body) { toast('备注内容不能为空', 'error'); return; }
    try {
      await apiCall('/api/v1/admin/notes', { method: 'POST', body: { target_type: 'order', target_id: state.orderDetail.id, body } });
      $('#orderNoteInput').value = '';
      toast('已添加备注', 'success');
      this.loadNotes();
    } catch (e) {
      if (handleAuthError(e)) return;
      toast('提交备注失败：' + e.message, 'error');
    }
  },
  async editNote(id) {
    const note = state.orderDetail.notes.find((n) => n.id === id);
    if (!note) return;
    const next = prompt('编辑备注：', note.body);
    if (next == null) return;
    const trimmed = next.trim();
    if (!trimmed) { toast('备注不能为空', 'error'); return; }
    try {
      await apiCall('/api/v1/admin/notes/' + id, { method: 'PATCH', body: { body: trimmed } });
      toast('已更新', 'success');
      this.loadNotes();
    } catch (e) {
      if (handleAuthError(e)) return;
      toast('更新失败：' + e.message, 'error');
    }
  },
  async deleteNote(id) {
    if (!confirm('确认删除该备注？此操作会写审计。')) return;
    try {
      await apiCall('/api/v1/admin/notes/' + id, { method: 'DELETE' });
      toast('已删除', 'success');
      this.loadNotes();
    } catch (e) {
      if (handleAuthError(e)) return;
      toast('删除失败：' + e.message, 'error');
    }
  },
  bind() {
    $('#orderDetailCloseBtn').addEventListener('click', () => this.close());
    $('#orderNoteSubmitBtn').addEventListener('click', () => this.submitNote());
    $('#orderNotesList').addEventListener('click', (ev) => {
      const btn = ev.target.closest('button[data-note-action]');
      if (!btn) return;
      const id = btn.closest('.note-item').dataset.id;
      const action = btn.dataset.noteAction;
      if (action === 'edit') this.editNote(id);
      else if (action === 'delete') this.deleteNote(id);
    });
  },
};

// ---------------------------------------------------------------------------
// ServicePackages (S2-REQ-003-P5a) — admin CRUD UI for service_packages
// ---------------------------------------------------------------------------
const ServicePackages = {
  _editing: null, // null = create; object = patch

  async load() {
    const tbody = $('#spTbody');
    tbody.innerHTML = '<tr><td colspan="8" class="empty">加载中…</td></tr>';
    try {
      const data = await apiCall('/api/v1/admin/service-packages/');
      this.render(data.items || []);
    } catch (e) {
      if (handleAuthError(e)) return;
      tbody.innerHTML =
        '<tr><td colspan="8" class="empty" style="color:#ff4d4f">加载失败：' +
        escapeHtml(e.message) + '</td></tr>';
    }
  },

  render(items) {
    const tbody = $('#spTbody');
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="empty">暂无档位</td></tr>';
      return;
    }
    tbody.innerHTML = items.map((it) => (
      '<tr>' +
        '<td>' + escapeHtml(it.code) + '</td>' +
        '<td>' + escapeHtml(it.name) + '</td>' +
        '<td>' + fmtAmount(it.price) + '</td>' +
        '<td>' + (it.is_active ? '<span style="color:#52c41a">启用</span>' : '<span style="color:#999">停用</span>') + '</td>' +
        '<td>' + it.sort_order + '</td>' +
        '<td>' + escapeHtml(it.description || '') + '</td>' +
        '<td>' + escapeHtml(it.created_at || '') + '</td>' +
        '<td>' +
          '<button class="btn btn-ghost btn-sm" data-sp-edit="' + escapeHtml(it.id) + '">编辑</button> ' +
          '<button class="btn btn-ghost btn-sm" data-sp-toggle="' + escapeHtml(it.id) + '" data-sp-active="' + it.is_active + '">' +
            (it.is_active ? '停用' : '启用') +
          '</button> ' +
          '<button class="btn btn-ghost btn-sm" style="color:#ff4d4f" data-sp-delete="' + escapeHtml(it.id) + '">删除</button>' +
        '</td>' +
      '</tr>'
    )).join('');
    state.servicePackages = { items };
  },

  bind() {
    $('#spRefreshBtn').addEventListener('click', () => this.load());
    $('#spCreateBtn').addEventListener('click', () => this.openEdit(null));
    document.querySelectorAll('[data-close-sp]').forEach((el) =>
      el.addEventListener('click', () => this.closeEdit())
    );
    $('#spSubmitBtn').addEventListener('click', () => this.submit());

    // Event delegation on tbody for edit / toggle / delete
    $('#spTbody').addEventListener('click', async (ev) => {
      const t = ev.target;
      const id = t.dataset.spEdit || t.dataset.spToggle || t.dataset.spDelete;
      if (!id) return;
      if (t.dataset.spEdit) {
        const row = (state.servicePackages?.items || []).find((x) => x.id === id);
        this.openEdit(row || null);
      } else if (t.dataset.spToggle) {
        const active = t.dataset.spActive === 'true';
        try {
          await apiCall('/api/v1/admin/service-packages/' + id, {
            method: 'PATCH',
            body: JSON.stringify({ is_active: !active }),
          });
          await this.load();
        } catch (e) {
          if (handleAuthError(e)) return;
          alert('操作失败：' + e.message);
        }
      } else if (t.dataset.spDelete) {
        if (!confirm('确认删除此档位？(软删，历史订单不受影响)')) return;
        try {
          await apiCall('/api/v1/admin/service-packages/' + id, { method: 'DELETE' });
          await this.load();
        } catch (e) {
          if (handleAuthError(e)) return;
          alert('删除失败：' + e.message);
        }
      }
    });
  },

  openEdit(row) {
    this._editing = row;
    $('#spEditTitle').textContent = row ? '编辑档位' : '新建档位';
    $('#spFieldCode').value = row ? row.code : '';
    $('#spFieldCode').disabled = !!row; // code 不可改
    $('#spFieldName').value = row ? row.name : '';
    $('#spFieldPrice').value = row ? row.price : '';
    $('#spFieldSortOrder').value = row ? row.sort_order : 10;
    $('#spFieldIsActive').value = row ? String(row.is_active) : 'true';
    $('#spFieldDescription').value = row ? (row.description || '') : '';
    $('#spEditError').hidden = true;
    $('#spEditModal').hidden = false;
  },

  closeEdit() {
    $('#spEditModal').hidden = true;
  },

  async submit() {
    const err = $('#spEditError');
    err.hidden = true;
    const payload = {
      name: $('#spFieldName').value.trim(),
      price: $('#spFieldPrice').value.trim(),
      sort_order: parseInt($('#spFieldSortOrder').value, 10) || 0,
      is_active: $('#spFieldIsActive').value === 'true',
      description: $('#spFieldDescription').value.trim() || null,
    };
    if (!this._editing) payload.code = $('#spFieldCode').value.trim();
    if (!payload.name || !payload.price) {
      err.textContent = '名称和价格必填';
      err.hidden = false;
      return;
    }
    try {
      if (this._editing) {
        await apiCall('/api/v1/admin/service-packages/' + this._editing.id, {
          method: 'PATCH',
          body: JSON.stringify(payload),
        });
      } else {
        if (!payload.code) {
          err.textContent = '代码必填';
          err.hidden = false;
          return;
        }
        await apiCall('/api/v1/admin/service-packages/', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
      }
      this.closeEdit();
      await this.load();
    } catch (e) {
      if (handleAuthError(e)) return;
      err.textContent = '保存失败：' + e.message;
      err.hidden = false;
    }
  },
};
