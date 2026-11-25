// Quản trị hệ thống: tài khoản (UC11), model (UC07), nhật ký truy vấn (UC10), ma trận phân quyền
import { $, api, badge, dataTable, esc, fmt, formModal, h, icon, LABEL, modal, ROLE_NAME, state, tabs, toast } from '../core.js';

function userForm(u, reload) {
  return formModal({
    title: u ? `Edit account — ${u.username}` : 'Add account', values: u || { role: 'event', is_active: true },
    fields: [
      { name: 'username', label: 'Username', required: true, disabled: !!u, help: u ? '' : 'Letters, digits, dots, underscores' },
      { name: 'full_name', label: 'Full name', required: true },
      { name: 'role', label: 'Role', type: 'select', required: true, placeholder: false, options: Object.entries(ROLE_NAME) },
      { name: 'password', label: u ? 'New password' : 'Password', type: 'password', required: !u, help: u ? 'Leave blank to keep the current password' : 'At least 6 characters' },
      { name: 'is_active', type: 'checkbox', text: 'Allow login', span: 2 },
    ],
    onSubmit: async (v) => {
      await api(u ? `/api/users/${u.id}` : '/api/users', { method: u ? 'PUT' : 'POST', body: { ...v, username: u ? u.username : v.username } });
      toast(u ? 'Account updated.' : 'Account created.');
      reload();
    },
  });
}

async function usersTab(box, setActions) {
  const load = () => usersTab(box, setActions);
  const rows = await api('/api/users');
  setActions([{ label: 'Add account', icon: 'plus', onClick: () => userForm(null, load) }]);
  box.innerHTML = '';
  const card = h('<section class="card"></section>');
  card.append(dataTable({
    rows, search: true, pageSize: 15, searchKeys: ['username', 'full_name', 'role'],
    columns: [
      { key: 'username', label: 'Username', render: (r) => `<b>${esc(r.username)}</b>${r.id === state.user.id ? ' <span class="badge info">You</span>' : ''}` },
      { key: 'full_name', label: 'Full name' },
      { key: 'role', label: 'Role', render: (r) => `<span class="badge accent">${esc(ROLE_NAME[r.role] || r.role)}</span>` },
      { key: 'is_active', label: 'Status', render: (r) => (r.is_active ? '<span class="badge good">Active</span>' : '<span class="badge muted">Locked</span>') },
    ],
    onRow: (r) => userForm(r, load),
  }));
  box.append(card);
}

function modelForm(m, reload) {
  return formModal({
    title: `Model settings — ${m.name}`, values: m,
    fields: [
      { name: 'model_tag', label: 'Model tag', required: true, help: m.provider === 'ollama' ? 'Name of a model pulled in Ollama' : 'Model name at the provider' },
      { name: 'base_url', label: 'Base URL', help: 'Ollama: http://localhost:11434/v1' },
      { name: 'is_active', type: 'checkbox', text: 'Enabled' },
      { name: 'is_default', type: 'checkbox', text: 'Default model for questions' },
    ],
    onSubmit: async (v) => { await api(`/api/models/${m.id}`, { method: 'PUT', body: v }); toast('Model settings saved.'); reload(); },
  });
}

async function modelsTab(box, setActions) {
  const load = () => modelsTab(box, setActions);
  const rows = await api('/api/models');
  setActions([]);
  box.innerHTML = `<div class="alert info">${icon('info')}<div><p>Ollama models run locally at <code>localhost:11434</code> and send no data outside. Groq needs a <code>GROQ_API_KEY</code> key in the <code>.env</code> file.</p></div></div>`;
  const card = h('<section class="card"></section>');
  card.append(dataTable({
    rows, search: false, columns: [
      { key: 'name', label: 'Model', render: (r) => `<b>${esc(r.name)}</b>${r.is_default ? ' <span class="badge accent">Default</span>' : ''}` },
      { key: 'provider', label: 'Provider' },
      { key: 'model_tag', label: 'Model tag', render: (r) => `<code>${esc(r.model_tag)}</code>` },
      { key: 'base_url', label: 'Base URL', render: (r) => `<small>${esc(r.base_url || '—')}</small>` },
      { key: 'api_key_env', label: 'Key variable', render: (r) => (r.api_key_env ? `<code>${esc(r.api_key_env)}</code>` : '<span class="muted">not needed</span>') },
      { key: 'is_active', label: 'Status', render: (r) => (r.is_active ? '<span class="badge good">On</span>' : '<span class="badge muted">Off</span>') },
    ],
    onRow: (r) => modelForm(r, load),
  }));
  box.append(card);
}

async function logsTab(box, setActions) {
  setActions([]);
  const d = await api('/api/logs');
  const total = d.stats.reduce((s, x) => s + x.n, 0);
  const fb = Object.fromEntries(d.feedback.map((f) => [f.rating, f.n]));
  box.innerHTML = `<div class="kpis compact">
    <div class="kpi"><div><p>Total questions</p><b>${fmt.num(total)}</b></div></div>
    ${d.stats.slice(0, 3).map((s) => `<div class="kpi"><div><p>${esc(LABEL[s.status]?.[0] || s.status)}</p><b>${fmt.num(s.n)}</b><small>avg ${fmt.num(s.avg_ms)} ms</small></div></div>`).join('')}
    <div class="kpi"><div><p>User ratings</p><b>${fb[1] || 0} correct · ${fb[-1] || 0} wrong</b></div></div></div>`;
  const statuses = d.stats.map((s) => s.status);
  const table = dataTable({
    rows: d.rows, pageSize: 15, searchKeys: ['question', 'username', 'model_name', 'error', 'generated_sql'],
    filters: `<select id="l-status" aria-label="Filter by status"><option value="">All statuses</option>${statuses.map((s) => `<option value="${s}">${esc(LABEL[s]?.[0] || s)}</option>`).join('')}</select>`,
    columns: [
      { key: 'created_at', label: 'Time', render: (r) => `<span class="nowrap">${fmt.datetime(r.created_at)}</span>`, width: '130px' },
      { key: 'username', label: 'Asked by' },
      { key: 'question', label: 'Question', render: (r) => `${esc(r.question)}${r.error ? `<small class="text-bad block">${esc(r.error)}</small>` : ''}`, cls: 'clamp' },
      { key: 'model_name', label: 'Model' },
      { key: 'status', label: 'Status', render: (r) => badge(r.status) },
      { key: 'rating', label: 'Rating', render: (r) => (r.rating === 1 ? '<span class="badge good">Correct</span>' : r.rating === -1 ? '<span class="badge bad">Wrong</span>' : '—') },
      { key: 'latency_ms', label: 'ms', num: true, render: (r) => fmt.num(r.latency_ms) },
    ],
    onRow: (r) => modal({ title: 'Query details', size: 'lg', body: `<dl class="kv">
      <dt>Question</dt><dd>${esc(r.question)}</dd><dt>Asked by</dt><dd>${esc(r.full_name)} (${esc(r.username)})</dd>
      <dt>Status</dt><dd>${badge(r.status)} ${r.error ? esc(r.error) : ''}</dd><dt>Glossary terms</dt><dd>${esc(r.glossary_used || '—')}</dd>
      <dt>Answer</dt><dd>${esc(r.answer || '—')}</dd><dt>Processing time</dt><dd>${fmt.num(r.latency_ms)} ms · ${r.row_count ?? '—'} rows</dd></dl>
      ${r.generated_sql ? `<h4>SQL</h4><pre>${esc(r.generated_sql)}</pre>` : ''}` }),
  });
  const card = h('<section class="card"></section>');
  card.append(table);
  box.append(card);
  $('#l-status', table).addEventListener('change', (e) => table.setRows(e.target.value ? d.rows.filter((r) => r.status === e.target.value) : d.rows));
}

async function rolesTab(box, setActions) {
  setActions([]);
  const d = await api('/api/roles');
  const roles = Object.keys(d.roles);
  box.innerHTML = `<section class="card"><header class="card-h"><h2>Permission matrix</h2></header>
    <p class="small muted">The same matrix governs both the management screens and Ask AI: if a role may not see some data, those tables/columns are hidden from the prompt and blocked by SQLite at execution time.</p>
    <div class="table-wrap"><table class="matrix"><thead><tr><th>Permission</th>${roles.map((r) => `<th class="center">${esc(d.roles[r])}</th>`).join('')}</tr></thead>
    <tbody><tr><td>View members, events, attendance reports; ask questions</td>${roles.map(() => `<td class="center yes">${icon('check')}</td>`).join('')}</tr>
    ${Object.entries(d.permissions).map(([p, name]) => `<tr><td>${esc(name)} <code class="muted">${esc(p)}</code></td>${roles.map((r) => d.matrix[r].includes(p) ? `<td class="center yes">${icon('check')}</td>` : '<td class="center no">—</td>').join('')}</tr>`).join('')}</tbody></table></div></section>`;
}

const TABS = { users: ['Accounts', usersTab], models: ['AI models', modelsTab], logs: ['Query log', logsTab], roles: ['Permissions', rolesTab] };

export default async function admin({ view, setHeader, params }) {
  let tab = TABS[params[0]] ? params[0] : 'users';
  const box = h('<div></div>');
  const setActions = (a) => setHeader('Accounts, AI models, query log and permissions.', a);
  view.innerHTML = '';
  view.append(tabs(Object.entries(TABS).map(([k, [t]]) => [k, t]), tab, (k) => {
    tab = k; history.replaceState(null, '', `#/admin/${k}`); box.innerHTML = ''; TABS[k][1](box, setActions);
  }), box);
  await TABS[tab][1](box, setActions);
}
