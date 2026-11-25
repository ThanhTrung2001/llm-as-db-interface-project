// ClubQuery — khung ứng dụng: đăng nhập, menu theo quyền, điều hướng theo #hash
import { $, $$, api, can, esc, fmt, formModal, icon, setUnauthorizedHandler, state, toast, loading } from './core.js';
import dashboard from './views/dashboard.js';
import ask from './views/ask.js';
import history from './views/history.js';
import members from './views/members.js';
import events from './views/events.js';
import finance from './views/finance.js';
import reports from './views/reports.js';
import glossary from './views/glossary.js';
import auditView from './views/audit.js';
import admin from './views/admin.js';

// [id, tên, icon, nhóm, quyền cần (null = mọi vai trò), module]
const ROUTES = [
  ['dashboard', 'Dashboard', 'dashboard', 'General', null, dashboard],
  ['ask', 'Ask AI', 'sparkle', 'General', null, ask],
  ['history', 'Question history', 'history', 'General', null, history],
  ['members', 'Members', 'users', 'Management', null, members],
  ['events', 'Events & attendance', 'calendar', 'Management', null, events],
  ['finance', 'Finance', 'wallet', 'Management', 'finance.read', finance],
  ['reports', 'Reports', 'chart', 'Management', null, reports],
  ['glossary', 'Glossary', 'book', 'System', null, glossary],
  ['audit', 'Change log', 'file', 'System', 'audit.read', auditView],
  ['admin', 'Administration', 'shield', 'System', 'system.admin', admin],
];
const allowed = () => ROUTES.filter((r) => !r[4] || can(r[4]));

// ---------- Đăng nhập ----------
$('#login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = new FormData(e.target), err = $('#login-error'), btn = $('button[type=submit]', e.target);
  if (!f.get('username') || !f.get('password')) { err.textContent = 'Enter your username and password.'; err.hidden = false; return; }
  btn.disabled = true;
  try {
    const r = await api('/api/login', { method: 'POST', body: { username: f.get('username'), password: f.get('password') } });
    state.token = r.token;
    try { localStorage.setItem('cq_token', r.token); } catch {}
    err.hidden = true;
    await start();
  } catch (ex) { err.textContent = ex.message; err.hidden = false; }
  finally { btn.disabled = false; }
});
$$('[data-demo]').forEach((b) => b.addEventListener('click', () => {
  const [u, p] = b.dataset.demo.split('/');
  $('#lg-user').value = u; $('#lg-pass').value = p; $('#login-form').requestSubmit();
}));

const closeModals = () => $$('.modal-backdrop').forEach((m) => m._close?.(null));

function logout() {
  closeModals();
  state.token = null; state.user = null; state.askResults = [];
  try { localStorage.removeItem('cq_token'); } catch {}
  $('#app-view').hidden = true; $('#login-view').hidden = false;
  $('#lg-pass').value = '';
}
setUnauthorizedHandler(logout);

async function start() {
  try { state.user = await api('/api/me'); } catch { return logout(); }
  state.lookups = await api('/api/lookups');
  $('#login-view').hidden = true; $('#app-view').hidden = false;
  $('#me-avatar').textContent = fmt.initials(state.user.full_name);
  $('#me-name').textContent = state.user.full_name;
  $('#me-role').textContent = state.user.role_name;
  let group = '';
  $('#nav').innerHTML = allowed().map(([id, name, ic, g]) => {
    const head = g !== group ? `<p class="nav-group">${esc((group = g))}</p>` : '';
    return `${head}<a href="#/${id}" data-route="${id}">${icon(ic)}<span>${esc(name)}</span><b class="nav-badge" data-badge="${id}" hidden></b></a>`;
  }).join('');
  route();
  refreshBadges();
}

export async function refreshBadges() {
  if (!can('expense.approve')) return;
  try {
    const d = await api('/api/dashboard');
    const b = $('[data-badge="finance"]');
    if (b) { b.textContent = d.finance?.pending_count || ''; b.hidden = !d.finance?.pending_count; }
  } catch {}
}

// ---------- Điều hướng ----------
let current = null;
async function route() {
  if (!state.user) return;
  closeModals();
  const [id, ...rest] = (location.hash.replace(/^#\/?/, '') || 'dashboard').split('/');
  const r = allowed().find((x) => x[0] === id) || allowed()[0];
  if (r[0] !== id) { location.hash = '#/' + r[0]; return; }
  $$('#nav a').forEach((a) => a.classList.toggle('on', a.dataset.route === r[0]));
  document.body.classList.remove('menu-open');
  $('#page-title').textContent = r[1];
  $('#page-sub').textContent = '';
  $('#page-actions').innerHTML = '';
  const view = $('#view');
  view.innerHTML = loading();
  current = r[0];
  try {
    await r[5]({ view, params: rest, setHeader, go });
  } catch (err) {
    if (current === r[0]) view.innerHTML = `<div class="card empty">${icon('alert')}<p>${esc(err.message)}</p></div>`;
  }
  document.title = `${r[1]} · ClubQuery`;
}
function setHeader(sub, actions = []) {
  $('#page-sub').textContent = sub || '';
  const box = $('#page-actions');
  box.innerHTML = '';
  actions.forEach((a) => {
    const b = document.createElement('button');
    b.className = 'btn ' + (a.kind || 'primary');
    b.innerHTML = `${a.icon ? icon(a.icon) : ''}<span>${esc(a.label)}</span>`;
    b.addEventListener('click', a.onClick);
    box.append(b);
  });
}
export function go(path) { location.hash = '#/' + path; }
window.addEventListener('hashchange', route);

// ---------- Thanh bên: theme, đổi mật khẩu, đăng xuất, menu di động ----------
const isDark = () => (document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')) === 'dark';
const paintTheme = () => { $('#btn-theme').innerHTML = icon(isDark() ? 'sun' : 'moon'); };
$('#btn-theme').addEventListener('click', () => {
  const t = isDark() ? 'light' : 'dark';
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem('cq_theme', t); } catch {}
  paintTheme();
});
paintTheme();
$('#btn-password').innerHTML = icon('key');
$('#btn-logout').innerHTML = icon('logout');
$('#btn-menu').innerHTML = icon('menu');
$('#btn-menu').addEventListener('click', () => document.body.classList.toggle('menu-open'));
$('#scrim').addEventListener('click', () => document.body.classList.remove('menu-open'));
$('#btn-logout').addEventListener('click', async () => { try { await api('/api/logout', { method: 'POST' }); } catch {} logout(); });
$('#btn-password').addEventListener('click', () => formModal({
  title: 'Change password', size: 'sm', submitLabel: 'Change password',
  fields: [
    { name: 'old_password', label: 'Current password', type: 'password', required: true, span: 2 },
    { name: 'new_password', label: 'New password', type: 'password', required: true, span: 2, help: 'At least 6 characters' },
    { name: 'confirm', label: 'Confirm new password', type: 'password', required: true, span: 2 },
  ],
  onSubmit: async (v) => {
    if (v.new_password !== v.confirm) throw new Error('The passwords do not match.');
    if (v.new_password.length < 6) throw new Error('The new password must be at least 6 characters.');
    await api('/api/me/password', { method: 'POST', body: { old_password: v.old_password, new_password: v.new_password } });
    toast('Password changed.');
  },
}));

if (state.token) start(); else $('#login-view').hidden = false;
