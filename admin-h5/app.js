/**
 * YiLuAn Admin H5 — MVP
 * Vanilla JS, no framework, no build step.
 *
 * Modules:
 *  - companions: 陪诊师审核 (#/companions)
 *  - orders:     订单管理   (#/orders)
 *  - users:      用户管理   (#/users)
 *
 * Auth: header X-Admin-Token, token in localStorage `yiluan.admin.token`
 */

const LS_TOKEN_KEY = 'yiluan.admin.token';
const LS_API_BASE_KEY = 'yiluan.admin.apiBase';
const DEFAULT_API_BASE = 'http://127.0.0.1:8000';
const PAGE_SIZE = 20;

const state = {
  apiBase: localStorage.getItem(LS_API_BASE_KEY) || DEFAULT_API_BASE,
  token: localStorage.getItem(LS_TOKEN_KEY) || '',
  route: '',
  // companions
  companions: { page: 1, total: 0, items: [], pendingRejectId: null },
  // orders
  orders: {
    page: 1, total: 0, items: [],
    filters: { status: '', patient_id: '', companion_id: '', date_from: '', date_to: '' },
    pendingActionId: null,
  },
  // users
  users: {
    page: 1, total: 0, items: [],
    filters: { role: '', status: '', phone: '' },
    pendingDisableId: null,
  },
};

// ---------- DOM helpers ----------
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);
function show(el) { if (el) el.hidden = false; }
function hide(el) { if (el) el.hidden = true; }

function toast(msg, kind) {
  const t = $('#toast');
  t.className = 'toast' + (kind ? ' toast-' + kind : '');
  t.textContent = msg;
  show(t);
  clearTimeout(toast._t);
  toast._t = setTimeout(() => hide(t), 3000);
}

function escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
const escapeAttr = escapeHtml;

function statusPill(value) {
  const v = value || '-';
  const cls = 'status-pill status-pill--' + escapeAttr(String(v).toLowerCase());
  return '<span class="' + cls + '">' + escapeHtml(v) + '</span>';
}

// ---------- API ----------
async function apiCall(path, options) {
  options = options || {};
  const url = state.apiBase.replace(/\/$/, '') + path;
  const headers = Object.assign({
    'X-Admin-Token': state.token,
    'Content-Type': 'application/json',
  }, options.headers || {});
  const resp = await fetch(url, {
    method: options.method || 'GET',
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  let data = null;
  const text = await resp.text();
  if (text) {
    try { data = JSON.parse(text); } catch (e) { data = { raw: text }; }
  }
  if (!resp.ok) {
    const detail = (data && (data.detail || data.message)) || resp.statusText;
    const err = new Error(detail || ('HTTP ' + resp.status));
    err.status = resp.status;
    err.data = data;
    throw err;
  }
  return data;
}

function handleAuthError(e) {
  if (e && (e.status === 401 || e.status === 403)) {
    toast('Token 无效或无权限，请重新登录', 'error');
    localStorage.removeItem(LS_TOKEN_KEY);
    state.token = '';
    showLogin();
    return true;
  }
  return false;
}

function buildQuery(params) {
  const parts = [];
  Object.keys(params).forEach((k) => {
    const v = params[k];
    if (v !== undefined && v !== null && v !== '') {
      parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(v));
    }
  });
  return parts.length ? ('?' + parts.join('&')) : '';
}

// ---------- Detail modal ----------
function openDetail(title, payload) {
  $('#detailModalTitle').textContent = title;
  $('#detailModalBody').textContent = typeof payload === 'string'
    ? payload : JSON.stringify(payload, null, 2);
  show($('#detailModal'));
}
function closeDetail() { hide($('#detailModal')); }

// ===================================================================
// Module: companions
// ===================================================================
const Companions = {
  async load() {
    const tbody = $('#companionsTbody');
    tbody.innerHTML = '<tr><td colspan="6" class="empty">加载中…</td></tr>';
    try {
      const res = await apiCall('/api/v1/admin/companions/?page=' + state.companions.page + '&page_size=' + PAGE_SIZE);
      state.companions.items = res.items || [];
      state.companions.total = res.total || 0;
      this.render();
    } catch (e) {
      if (handleAuthError(e)) return;
      toast('加载失败：' + e.message, 'error');
      tbody.innerHTML = '<tr><td colspan="6" class="empty">加载失败</td></tr>';
    }
  },
  render() {
    const tbody = $('#companionsTbody');
    const items = state.companions.items;
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty">暂无待审核陪诊师 🎉</td></tr>';
    } else {
      tbody.innerHTML = items.map((c) => {
        const cert = c.certifications || '<span style="color:#bfbfbf">未提交</span>';
        return (
          '<tr>' +
          '<td class="id-cell">' + escapeHtml(c.id) + '</td>' +
          '<td>' + escapeHtml(c.real_name || '-') + '</td>' +
          '<td>' + escapeHtml(c.id_number || '-') + '</td>' +
          '<td class="cert-cell">' + escapeHtml(cert) + '</td>' +
          '<td>' + escapeHtml(c.created_at || '-') + '</td>' +
          '<td class="actions-cell">' +
            '<button class="btn btn-primary btn-sm" data-action="approve" data-id="' + escapeAttr(c.id) + '">通过</button>' +
            '<button class="btn btn-danger btn-sm" data-action="reject" data-id="' + escapeAttr(c.id) + '">拒绝</button>' +
          '</td>' +
          '</tr>'
        );
      }).join('');
    }
    const totalPages = Math.max(1, Math.ceil(state.companions.total / PAGE_SIZE));
    $('#pageInfo').textContent = '第 ' + state.companions.page + ' / ' + totalPages + ' 页 · 共 ' + state.companions.total + ' 条';
    $('#prevPageBtn').disabled = state.companions.page <= 1;
    $('#nextPageBtn').disabled = state.companions.page >= totalPages;
  },
  async approve(id) {
    if (!confirm('确认通过该陪诊师审核？此操作将写入审计日志。')) return;
    try {
      await apiCall('/api/v1/admin/companions/' + id + '/approve', { method: 'POST' });
      toast('已通过', 'success');
      this.load();
    } catch (e) {
      if (handleAuthError(e)) return;
      toast('通过失败：' + e.message, 'error');
    }
  },
  openReject(id) {
    state.companions.pendingRejectId = id;
    $('#rejectReason').value = '';
    show($('#rejectModal'));
    setTimeout(() => $('#rejectReason').focus(), 0);
  },
  closeReject() {
    state.companions.pendingRejectId = null;
    hide($('#rejectModal'));
  },
  async confirmReject() {
    const reason = ($('#rejectReason').value || '').trim();
    if (!reason) { toast('请填写拒绝原因', 'error'); return; }
    if (reason.length > 500) { toast('原因不能超过 500 字', 'error'); return; }
    const id = state.companions.pendingRejectId;
    this.closeReject();
    try {
      await apiCall('/api/v1/admin/companions/' + id + '/reject', { method: 'POST', body: { reason } });
      toast('已拒绝', 'success');
      this.load();
    } catch (e) {
      if (handleAuthError(e)) return;
      toast('拒绝失败：' + e.message, 'error');
    }
  },
  bind() {
    $('#refreshBtn').addEventListener('click', () => this.load());
    $('#prevPageBtn').addEventListener('click', () => { if (state.companions.page > 1) { state.companions.page--; this.load(); } });
    $('#nextPageBtn').addEventListener('click', () => { state.companions.page++; this.load(); });
    $('#companionsTbody').addEventListener('click', (ev) => {
      const btn = ev.target.closest('button[data-action]');
      if (!btn) return;
      const action = btn.dataset.action;
      const id = btn.dataset.id;
      if (action === 'approve') this.approve(id);
      else if (action === 'reject') this.openReject(id);
    });
    $('#rejectCancelBtn').addEventListener('click', () => this.closeReject());
    $('#rejectConfirmBtn').addEventListener('click', () => this.confirmReject());
  },
};

// ===================================================================
// Module: orders
// ===================================================================
const Orders = {
  async load() {
    const tbody = $('#ordersTbody');
    tbody.innerHTML = '<tr><td colspan="7" class="empty">加载中…</td></tr>';
    const f = state.orders.filters;
    const qs = buildQuery({
      page: state.orders.page,
      page_size: PAGE_SIZE,
      status: f.status,
      patient_id: f.patient_id,
      companion_id: f.companion_id,
      date_from: f.date_from,
      date_to: f.date_to,
    });
    try {
      const res = await apiCall('/api/v1/admin/orders' + qs);
      state.orders.items = res.items || [];
      state.orders.total = res.total || 0;
      this.render();
    } catch (e) {
      if (handleAuthError(e)) return;
      toast('加载订单失败：' + e.message, 'error');
      tbody.innerHTML = '<tr><td colspan="7" class="empty">加载失败</td></tr>';
    }
  },
  render() {
    const tbody = $('#ordersTbody');
    const items = state.orders.items;
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty">暂无订单</td></tr>';
    } else {
      tbody.innerHTML = items.map((o) => {
        const orderNo = o.order_no || o.id || '-';
        const patient = o.patient_name || o.patient_id || '-';
        const companion = o.companion_name || o.companion_id || '-';
        const amount = (o.amount !== undefined && o.amount !== null) ? o.amount : '-';
        return (
          '<tr>' +
          '<td class="id-cell">' + escapeHtml(orderNo) + '</td>' +
          '<td>' + statusPill(o.status) + '</td>' +
          '<td>' + escapeHtml(patient) + '</td>' +
          '<td>' + escapeHtml(companion) + '</td>' +
          '<td>' + escapeHtml(amount) + '</td>' +
          '<td>' + escapeHtml(o.created_at || '-') + '</td>' +
          '<td class="actions-cell">' +
            '<button class="btn btn-sm" data-action="detail" data-id="' + escapeAttr(o.id) + '">详情</button>' +
            '<button class="btn btn-sm" data-action="force" data-id="' + escapeAttr(o.id) + '">改状态</button>' +
            '<button class="btn btn-danger btn-sm" data-action="refund" data-id="' + escapeAttr(o.id) + '">退款</button>' +
          '</td>' +
          '</tr>'
        );
      }).join('');
    }
    const totalPages = Math.max(1, Math.ceil(state.orders.total / PAGE_SIZE));
    $('#ordersPageInfo').textContent = '第 ' + state.orders.page + ' / ' + totalPages + ' 页 · 共 ' + state.orders.total + ' 条';
    $('#ordersPrevBtn').disabled = state.orders.page <= 1;
    $('#ordersNextBtn').disabled = state.orders.page >= totalPages;
  },
  applyFiltersFromUI() {
    state.orders.filters = {
      status: $('#ordersFilterStatus').value,
      patient_id: $('#ordersFilterPatient').value.trim(),
      companion_id: $('#ordersFilterCompanion').value.trim(),
      date_from: $('#ordersFilterFrom').value,
      date_to: $('#ordersFilterTo').value,
    };
    state.orders.page = 1;
  },
  resetFilters() {
    $('#ordersFilterStatus').value = '';
    $('#ordersFilterPatient').value = '';
    $('#ordersFilterCompanion').value = '';
    $('#ordersFilterFrom').value = '';
    $('#ordersFilterTo').value = '';
    this.applyFiltersFromUI();
    this.load();
  },
  async openDetail(id) {
    openDetail('订单详情 · ' + id, '加载中…');
    try {
      const data = await apiCall('/api/v1/admin/orders/' + id);
      openDetail('订单详情 · ' + id, data);
    } catch (e) {
      if (handleAuthError(e)) return;
      toast('加载详情失败：' + e.message, 'error');
      closeDetail();
    }
  },
  openForceStatus(id) {
    state.orders.pendingActionId = id;
    $('#forceStatusSelect').value = 'paid';
    $('#forceStatusReason').value = '';
    show($('#forceStatusModal'));
  },
  closeForceStatus() {
    state.orders.pendingActionId = null;
    hide($('#forceStatusModal'));
  },
  async confirmForceStatus() {
    const id = state.orders.pendingActionId;
    const status = $('#forceStatusSelect').value;
    const reason = $('#forceStatusReason').value.trim();
    if (!reason) { toast('请填写原因', 'error'); return; }
    if (!confirm('确认将订单 ' + id + ' 状态改为 ' + status + ' ?')) return;
    this.closeForceStatus();
    try {
      await apiCall('/api/v1/admin/orders/' + id + '/force-status', { method: 'POST', body: { status, reason } });
      toast('状态已更新', 'success');
      this.load();
    } catch (e) {
      if (handleAuthError(e)) return;
      toast('改状态失败：' + e.message, 'error');
    }
  },
  openRefund(id) {
    state.orders.pendingActionId = id;
    $('#refundAmountInput').value = '';
    $('#refundReason').value = '';
    show($('#refundModal'));
  },
  closeRefund() {
    state.orders.pendingActionId = null;
    hide($('#refundModal'));
  },
  async confirmRefund() {
    const id = state.orders.pendingActionId;
    const amountRaw = $('#refundAmountInput').value.trim();
    const reason = $('#refundReason').value.trim();
    if (!amountRaw || isNaN(Number(amountRaw)) || Number(amountRaw) < 0) {
      toast('请输入有效退款金额', 'error'); return;
    }
    if (!reason) { toast('请填写退款原因', 'error'); return; }
    if (!confirm('确认对订单 ' + id + ' 退款 ' + amountRaw + ' ?')) return;
    this.closeRefund();
    try {
      await apiCall('/api/v1/admin/orders/' + id + '/refund', {
        method: 'POST',
        body: { amount: Number(amountRaw), reason },
      });
      toast('退款已提交', 'success');
      this.load();
    } catch (e) {
      if (handleAuthError(e)) return;
      toast('退款失败：' + e.message, 'error');
    }
  },
  bind() {
    $('#ordersRefreshBtn').addEventListener('click', () => this.load());
    $('#ordersSearchBtn').addEventListener('click', () => { this.applyFiltersFromUI(); this.load(); });
    $('#ordersResetBtn').addEventListener('click', () => this.resetFilters());
    $('#ordersPrevBtn').addEventListener('click', () => { if (state.orders.page > 1) { state.orders.page--; this.load(); } });
    $('#ordersNextBtn').addEventListener('click', () => { state.orders.page++; this.load(); });
    $('#ordersTbody').addEventListener('click', (ev) => {
      const btn = ev.target.closest('button[data-action]');
      if (!btn) return;
      const a = btn.dataset.action; const id = btn.dataset.id;
      if (a === 'detail') this.openDetail(id);
      else if (a === 'force') this.openForceStatus(id);
      else if (a === 'refund') this.openRefund(id);
    });
    $('#forceStatusCancelBtn').addEventListener('click', () => this.closeForceStatus());
    $('#forceStatusConfirmBtn').addEventListener('click', () => this.confirmForceStatus());
    $('#refundCancelBtn').addEventListener('click', () => this.closeRefund());
    $('#refundConfirmBtn').addEventListener('click', () => this.confirmRefund());
  },
};

// ===================================================================
// Module: users
// ===================================================================
const Users = {
  async load() {
    const tbody = $('#usersTbody');
    tbody.innerHTML = '<tr><td colspan="6" class="empty">加载中…</td></tr>';
    const f = state.users.filters;
    const qs = buildQuery({
      page: state.users.page,
      page_size: PAGE_SIZE,
      role: f.role,
      status: f.status,
      phone: f.phone,
    });
    try {
      const res = await apiCall('/api/v1/admin/users' + qs);
      state.users.items = res.items || [];
      state.users.total = res.total || 0;
      this.render();
    } catch (e) {
      if (handleAuthError(e)) return;
      toast('加载用户失败：' + e.message, 'error');
      tbody.innerHTML = '<tr><td colspan="6" class="empty">加载失败</td></tr>';
    }
  },
  render() {
    const tbody = $('#usersTbody');
    const items = state.users.items;
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty">暂无用户</td></tr>';
    } else {
      tbody.innerHTML = items.map((u) => {
        const phone = u.phone || u.mobile || '-';
        const nickname = u.nickname || u.name || '-';
        const role = u.role || '-';
        const status = u.status || '-';
        const isDisabled = String(status).toLowerCase() === 'disabled';
        const toggleBtn = isDisabled
          ? '<button class="btn btn-primary btn-sm" data-action="enable" data-id="' + escapeAttr(u.id) + '">启用</button>'
          : '<button class="btn btn-danger btn-sm" data-action="disable" data-id="' + escapeAttr(u.id) + '">禁用</button>';
        return (
          '<tr>' +
          '<td>' + escapeHtml(phone) + '</td>' +
          '<td>' + escapeHtml(nickname) + '</td>' +
          '<td>' + statusPill(role) + '</td>' +
          '<td>' + statusPill(status) + '</td>' +
          '<td>' + escapeHtml(u.created_at || '-') + '</td>' +
          '<td class="actions-cell">' +
            '<button class="btn btn-sm" data-action="detail" data-id="' + escapeAttr(u.id) + '">详情</button>' +
            toggleBtn +
          '</td>' +
          '</tr>'
        );
      }).join('');
    }
    const totalPages = Math.max(1, Math.ceil(state.users.total / PAGE_SIZE));
    $('#usersPageInfo').textContent = '第 ' + state.users.page + ' / ' + totalPages + ' 页 · 共 ' + state.users.total + ' 条';
    $('#usersPrevBtn').disabled = state.users.page <= 1;
    $('#usersNextBtn').disabled = state.users.page >= totalPages;
  },
  applyFiltersFromUI() {
    state.users.filters = {
      role: $('#usersFilterRole').value,
      status: $('#usersFilterStatus').value,
      phone: $('#usersFilterPhone').value.trim(),
    };
    state.users.page = 1;
  },
  resetFilters() {
    $('#usersFilterRole').value = '';
    $('#usersFilterStatus').value = '';
    $('#usersFilterPhone').value = '';
    this.applyFiltersFromUI();
    this.load();
  },
  async openDetail(id) {
    openDetail('用户详情 · ' + id, '加载中…');
    try {
      const data = await apiCall('/api/v1/admin/users/' + id);
      openDetail('用户详情 · ' + id, data);
    } catch (e) {
      if (handleAuthError(e)) return;
      toast('加载详情失败：' + e.message, 'error');
      closeDetail();
    }
  },
  openDisable(id) {
    state.users.pendingDisableId = id;
    $('#disableUserReason').value = '';
    show($('#disableUserModal'));
  },
  closeDisable() {
    state.users.pendingDisableId = null;
    hide($('#disableUserModal'));
  },
  async confirmDisable() {
    const id = state.users.pendingDisableId;
    const reason = $('#disableUserReason').value.trim();
    if (!reason) { toast('请填写原因', 'error'); return; }
    if (!confirm('确认禁用该用户？')) return;
    this.closeDisable();
    try {
      await apiCall('/api/v1/admin/users/' + id + '/disable', { method: 'POST', body: { reason } });
      toast('已禁用', 'success');
      this.load();
    } catch (e) {
      if (handleAuthError(e)) return;
      toast('禁用失败：' + e.message, 'error');
    }
  },
  async enable(id) {
    if (!confirm('确认启用该用户？')) return;
    try {
      await apiCall('/api/v1/admin/users/' + id + '/enable', { method: 'POST' });
      toast('已启用', 'success');
      this.load();
    } catch (e) {
      if (handleAuthError(e)) return;
      toast('启用失败：' + e.message, 'error');
    }
  },
  bind() {
    $('#usersRefreshBtn').addEventListener('click', () => this.load());
    $('#usersSearchBtn').addEventListener('click', () => { this.applyFiltersFromUI(); this.load(); });
    $('#usersResetBtn').addEventListener('click', () => this.resetFilters());
    $('#usersPrevBtn').addEventListener('click', () => { if (state.users.page > 1) { state.users.page--; this.load(); } });
    $('#usersNextBtn').addEventListener('click', () => { state.users.page++; this.load(); });
    $('#usersTbody').addEventListener('click', (ev) => {
      const btn = ev.target.closest('button[data-action]');
      if (!btn) return;
      const a = btn.dataset.action; const id = btn.dataset.id;
      if (a === 'detail') this.openDetail(id);
      else if (a === 'disable') this.openDisable(id);
      else if (a === 'enable') this.enable(id);
    });
    $('#disableUserCancelBtn').addEventListener('click', () => this.closeDisable());
    $('#disableUserConfirmBtn').addEventListener('click', () => this.confirmDisable());
  },
};

// ===================================================================
// Router & shell
// ===================================================================
const ROUTES = {
  companions: { view: '#companionsView', mod: Companions },
  orders:     { view: '#ordersView',     mod: Orders },
  users:      { view: '#usersView',      mod: Users },
};

function parseHash() {
  const h = (location.hash || '').replace(/^#\/?/, '').split('/')[0];
  return ROUTES[h] ? h : 'companions';
}

function navigate() {
  const route = parseHash();
  state.route = route;
  // Toggle views
  Object.keys(ROUTES).forEach((k) => {
    const el = document.querySelector(ROUTES[k].view);
    if (el) el.hidden = (k !== route);
  });
  // Toggle nav active state
  $$('.side-nav__item').forEach((a) => {
    a.classList.toggle('side-nav__item--active', a.dataset.route === route);
  });
  // Load module
  ROUTES[route].mod.load();
}

function showLogin() {
  show($('#loginMain'));
  hide($('#appShell'));
  hide($('#logoutBtn'));
  $('#adminInfo').textContent = '';
  $('#apiBaseInput').value = state.apiBase;
  $('#tokenInput').value = state.token;
}

function showShell() {
  hide($('#loginMain'));
  show($('#appShell'));
  show($('#logoutBtn'));
  $('#adminInfo').textContent = state.apiBase;
  if (!location.hash) location.hash = '#/companions';
  navigate();
}

function onLogin() {
  const apiBase = ($('#apiBaseInput').value || '').trim() || DEFAULT_API_BASE;
  const token = ($('#tokenInput').value || '').trim();
  hide($('#loginError'));
  if (!token) {
    $('#loginError').textContent = 'Admin Token 不能为空';
    show($('#loginError'));
    return;
  }
  state.apiBase = apiBase;
  state.token = token;
  localStorage.setItem(LS_API_BASE_KEY, apiBase);
  localStorage.setItem(LS_TOKEN_KEY, token);
  showShell();
}

function onLogout() {
  localStorage.removeItem(LS_TOKEN_KEY);
  state.token = '';
  showLogin();
}

function bindShell() {
  $('#loginBtn').addEventListener('click', onLogin);
  $('#tokenInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') onLogin(); });
  $('#logoutBtn').addEventListener('click', onLogout);
  $('#detailModalCloseBtn').addEventListener('click', closeDetail);
  window.addEventListener('hashchange', navigate);
}

function init() {
  bindShell();
  Companions.bind();
  Orders.bind();
  Users.bind();
  if (state.token) showShell(); else showLogin();
}

document.addEventListener('DOMContentLoaded', init);
