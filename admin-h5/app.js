/**
 * YiLuAn Admin H5 — companion audit MVP
 * Vanilla JS, no framework, no build step.
 *
 * Backend: GET  /api/v1/admin/companions/?page=&page_size=
 *          POST /api/v1/admin/companions/{id}/approve
 *          POST /api/v1/admin/companions/{id}/reject  body: { reason }
 * Auth: header X-Admin-Token
 */

const LS_TOKEN_KEY = 'yiluan.admin.token';
const LS_API_BASE_KEY = 'yiluan.admin.apiBase';
const DEFAULT_API_BASE = 'http://127.0.0.1:8000';
const PAGE_SIZE = 20;

const state = {
  apiBase: localStorage.getItem(LS_API_BASE_KEY) || DEFAULT_API_BASE,
  token: localStorage.getItem(LS_TOKEN_KEY) || '',
  page: 1,
  total: 0,
  items: [],
  pendingRejectId: null,
};

// ---------- DOM helpers ----------
const $ = (sel) => document.querySelector(sel);
function show(el) { el.hidden = false; }
function hide(el) { el.hidden = true; }

function toast(msg, kind) {
  const t = $('#toast');
  t.className = 'toast' + (kind ? ' toast-' + kind : '');
  t.textContent = msg;
  show(t);
  clearTimeout(toast._t);
  toast._t = setTimeout(() => hide(t), 2400);
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

async function fetchPending(page) {
  return apiCall('/api/v1/admin/companions/?page=' + page + '&page_size=' + PAGE_SIZE);
}

async function approveCompanion(id) {
  return apiCall('/api/v1/admin/companions/' + id + '/approve', { method: 'POST' });
}

async function rejectCompanion(id, reason) {
  return apiCall('/api/v1/admin/companions/' + id + '/reject', {
    method: 'POST',
    body: { reason },
  });
}

// ---------- Views ----------
function showLoginView() {
  hide($('#listView'));
  show($('#loginView'));
  hide($('#logoutBtn'));
  $('#adminInfo').textContent = '';
  $('#apiBaseInput').value = state.apiBase;
  $('#tokenInput').value = state.token;
}

function showListView() {
  hide($('#loginView'));
  show($('#listView'));
  show($('#logoutBtn'));
  $('#adminInfo').textContent = state.apiBase;
  loadList();
}

function renderRows() {
  const tbody = $('#companionsTbody');
  if (!state.items.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty">暂无待审核陪诊师 🎉</td></tr>';
  } else {
    tbody.innerHTML = state.items.map((c) => {
      const cert = c.certifications || '<span style="color:#bfbfbf">未提交</span>';
      const created = c.created_at || '-';
      return (
        '<tr>' +
        '<td class="id-cell">' + escapeHtml(c.id) + '</td>' +
        '<td>' + escapeHtml(c.real_name || '-') + '</td>' +
        '<td>' + escapeHtml(c.id_number || '-') + '</td>' +
        '<td class="cert-cell">' + escapeHtml(cert) + '</td>' +
        '<td>' + escapeHtml(created) + '</td>' +
        '<td class="actions-cell">' +
          '<button class="btn btn-primary btn-sm" data-action="approve" data-id="' + escapeAttr(c.id) + '">通过</button>' +
          '<button class="btn btn-danger btn-sm" data-action="reject" data-id="' + escapeAttr(c.id) + '">拒绝</button>' +
        '</td>' +
        '</tr>'
      );
    }).join('');
  }
  const totalPages = Math.max(1, Math.ceil(state.total / PAGE_SIZE));
  $('#pageInfo').textContent = '第 ' + state.page + ' / ' + totalPages + ' 页 · 共 ' + state.total + ' 条';
  $('#prevPageBtn').disabled = state.page <= 1;
  $('#nextPageBtn').disabled = state.page >= totalPages;
}

function escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function escapeAttr(s) { return escapeHtml(s); }

async function loadList() {
  $('#companionsTbody').innerHTML = '<tr><td colspan="6" class="empty">加载中…</td></tr>';
  try {
    const res = await fetchPending(state.page);
    state.items = res.items || [];
    state.total = res.total || 0;
    renderRows();
  } catch (e) {
    if (e.status === 401 || e.status === 403) {
      toast('登录失败：Token 无效或已过期', 'error');
      localStorage.removeItem(LS_TOKEN_KEY);
      state.token = '';
      showLoginView();
      return;
    }
    toast('加载失败：' + e.message, 'error');
    $('#companionsTbody').innerHTML = '<tr><td colspan="6" class="empty">加载失败</td></tr>';
  }
}

// ---------- Event wiring ----------
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
  state.page = 1;
  localStorage.setItem(LS_API_BASE_KEY, apiBase);
  localStorage.setItem(LS_TOKEN_KEY, token);
  showListView();
}

function onLogout() {
  localStorage.removeItem(LS_TOKEN_KEY);
  state.token = '';
  state.items = [];
  state.total = 0;
  showLoginView();
}

async function onApprove(id) {
  if (!confirm('确认通过该陪诊师审核？此操作将写入审计日志。')) return;
  try {
    await approveCompanion(id);
    toast('已通过', 'success');
    loadList();
  } catch (e) {
    toast('通过失败：' + e.message, 'error');
  }
}

function openRejectModal(id) {
  state.pendingRejectId = id;
  $('#rejectReason').value = '';
  show($('#rejectModal'));
  setTimeout(() => $('#rejectReason').focus(), 0);
}

function closeRejectModal() {
  state.pendingRejectId = null;
  hide($('#rejectModal'));
}

async function onConfirmReject() {
  const reason = ($('#rejectReason').value || '').trim();
  if (!reason) { toast('请填写拒绝原因', 'error'); return; }
  if (reason.length > 500) { toast('原因不能超过 500 字', 'error'); return; }
  const id = state.pendingRejectId;
  closeRejectModal();
  try {
    await rejectCompanion(id, reason);
    toast('已拒绝', 'success');
    loadList();
  } catch (e) {
    toast('拒绝失败：' + e.message, 'error');
  }
}

function onTbodyClick(ev) {
  const btn = ev.target.closest('button[data-action]');
  if (!btn) return;
  const action = btn.dataset.action;
  const id = btn.dataset.id;
  if (action === 'approve') onApprove(id);
  else if (action === 'reject') openRejectModal(id);
}

function bind() {
  $('#loginBtn').addEventListener('click', onLogin);
  $('#tokenInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') onLogin(); });
  $('#logoutBtn').addEventListener('click', onLogout);
  $('#refreshBtn').addEventListener('click', loadList);
  $('#prevPageBtn').addEventListener('click', () => { if (state.page > 1) { state.page--; loadList(); } });
  $('#nextPageBtn').addEventListener('click', () => { state.page++; loadList(); });
  $('#companionsTbody').addEventListener('click', onTbodyClick);
  $('#rejectCancelBtn').addEventListener('click', closeRejectModal);
  $('#rejectConfirmBtn').addEventListener('click', onConfirmReject);
}

function init() {
  bind();
  if (state.token) showListView(); else showLoginView();
}

document.addEventListener('DOMContentLoaded', init);
