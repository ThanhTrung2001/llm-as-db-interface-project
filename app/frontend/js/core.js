// ClubQuery — tiện ích dùng chung: API, định dạng, icon, bảng, modal, form, toast, biểu đồ
export const state = { token: null, user: null, lookups: null };
try { state.token = localStorage.getItem('cq_token'); } catch { /* bộ nhớ trình duyệt bị chặn */ }

export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];
export const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const can = (perm) => !!state.user?.permissions.includes(perm);

export function h(html) {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

// ---------- API ----------
export class ApiError extends Error {}
let onUnauthorized = () => {};
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn; };

export async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...(state.token ? { Authorization: 'Bearer ' + state.token } : {}) },
    body: opts.body && typeof opts.body !== 'string' ? JSON.stringify(opts.body) : opts.body,
  });
  if (res.status === 401 && path !== '/api/login') { onUnauthorized(); throw new ApiError('Your session has expired'); }
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch {}
    throw new ApiError(msg);
  }
  return (res.headers.get('content-type') || '').includes('json') ? res.json() : res;
}

// ---------- Định dạng ----------
export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const fmt = {
  date(v) { if (!v) return '—'; if (document.documentElement.lang === 'vi') { const [y, m, d] = String(v).slice(0, 10).split('-'); if (d) return `${d}/${m}/${y}`; } const [y, m, d] = String(v).slice(0, 10).split('-'); return d && MONTHS[+m - 1] ? `${d} ${MONTHS[+m - 1]} ${y}` : esc(v); },  // 07 Apr 2020
  datetime(v) { if (!v) return '—'; const t = String(v).slice(11, 16); return fmt.date(v) + (t ? ' ' + t : ''); },
  money(v) { if (v == null || v === '') return '—'; const n = Number(v); return (n < 0 ? '−$' : '$') + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: Number.isInteger(n) ? 0 : 2, maximumFractionDigits: 2 }); },
  num(v) { return v == null ? '—' : Number(v).toLocaleString('en-US'); },
  pct(v) { return v == null ? '—' : `${Number(v).toLocaleString('en-US', { maximumFractionDigits: 1 })}%`; },
  initials(name) { return String(name || '?').split(/\s+/).filter(Boolean).slice(-2).map((w) => w[0]).join('').toUpperCase(); },
};
export const today = () => { const d = new Date(); return new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); };  // theo giờ máy, không theo UTC

// ---------- Icon (nét vẽ 24×24, cùng phong cách Lucide) ----------
const ICONS = {
  dashboard: '<rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/>',
  chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="M8 9h8"/><path d="M8 13h5"/>',
  history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  calendar: '<rect width="18" height="18" x="3" y="4" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/><path d="M3 10h18"/>',
  wallet: '<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"/><path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/>',
  chart: '<path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
  book: '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  file: '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  edit: '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
  send: '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
  menu: '<path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h16"/>',
  key: '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6"/><path d="m15.5 7.5 3 3L22 7l-3-3"/>',
  code: '<path d="m16 18 6-6-6-6"/><path d="m8 6-6 6 6 6"/>',
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  cpu: '<rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/>',
  moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
  sparkle: '<path d="M12 3l1.9 5.8L19.7 10.7 13.9 12.6 12 18.4 10.1 12.6 4.3 10.7 10.1 8.8Z"/><path d="M19 3v4"/><path d="M21 5h-4"/>',
  clipboard: '<rect width="8" height="4" x="8" y="2" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>',
  trend: '<path d="m22 7-8.5 8.5-5-5L2 17"/><path d="M16 7h6v6"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  pin: '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
  thumbUp: '<path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"/>',
  thumbDown: '<path d="M17 14V2"/><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z"/>',
  lock: '<rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  database: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/>',
};
export const icon = (name, cls = '') =>
  `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ''}</svg>`;

// ---------- Nhãn và huy hiệu ----------
export const ROLE_NAME = { president: 'President', treasurer: 'Treasurer', event: 'Event team', admin: 'System admin' };
export const LABEL = {
  // trạng thái truy vấn
  EXECUTED: ['Success', 'good'], REJECTED_PERMISSION: ['Permission denied', 'bad'], REJECTED_UNSAFE: ['Unsafe query', 'bad'],
  FAILED_GENERATION: ['No SQL generated', 'warn'], EXEC_ERROR: ['Execution error', 'warn'], TIMEOUT: ['Timed out', 'warn'],
  // khoản chi
  PENDING: ['Pending', 'warn'], APPROVED: ['Approved', 'good'], REJECTED: ['Rejected', 'bad'],
  // sự kiện
  Planning: ['Planning', 'info'], Open: ['Open', 'good'], Closed: ['Closed', 'muted'],
  // nhật ký thay đổi
  CREATE: ['Create', 'good'], UPDATE: ['Update', 'info'], DELETE: ['Delete', 'bad'], APPROVE: ['Approve', 'good'], REJECT: ['Reject', 'bad'],
};
export const POSITION_VI = { President: 'President', 'Vice President': 'Vice President', Secretary: 'Secretary', Treasurer: 'Treasurer', Member: 'Member', Inactive: 'Former member' };
export const EVENT_TYPE_VI = { Meeting: 'Meeting', Election: 'Election', Game: 'Game', 'Guest Speaker': 'Guest speaker', Social: 'Social', 'Community Service': 'Community service', Budget: 'Budget', Registration: 'Registration' };
export const CATEGORY_VI = { Advertisement: 'Advertisement', Food: 'Food', Parking: 'Parking', 'Speaker Gifts': 'Speaker Gifts', 'Club T-Shirts': 'Club T-Shirts' };
export const SOURCE_VI = { Dues: 'Dues', Fundraising: 'Fundraising', Sponsorship: 'Sponsorship', 'School Appropration': 'School appropriation' };
export const ENTITY_VI = { member: 'Member', event: 'Event', attendance: 'Attendance', budget: 'Budget', expense: 'Expense', income: 'Income', glossary: 'Glossary term' };
export const vi = (dict, v) => (v == null ? '—' : dict[v] || v);

export function badge(key, text) {
  const [t, c] = LABEL[key] || [key, 'muted'];
  return `<span class="badge ${c}">${esc(text ?? t)}</span>`;
}
export const pill = (text, cls = 'muted') => `<span class="badge ${cls}">${esc(text)}</span>`;
export const avatar = (name, cls = '') => `<span class="avatar ${cls}" aria-hidden="true">${esc(fmt.initials(name))}</span>`;

// ---------- Toast ----------
export function toast(msg, type = 'good') {
  const el = h(`<div class="toast ${type}" role="status">${icon(type === 'bad' ? 'alert' : type === 'warn' ? 'info' : 'check')}<span>${esc(msg)}</span></div>`);
  $('#toasts').append(el);
  setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 250); }, type === 'bad' ? 5000 : 3000);
}
export const toastError = (err) => toast(err.message || String(err), 'bad');

// ---------- Modal ----------
export function modal({ title, body = '', size = '', actions = [] }) {
  return new Promise((resolve) => {
    const el = h(`<div class="modal-backdrop"><div class="modal ${size}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
      <header><h2>${esc(title)}</h2><button class="icon-btn" data-close aria-label="Close">${icon('x')}</button></header>
      <div class="modal-body"></div><footer></footer></div></div>`);
    const bodyEl = $('.modal-body', el);
    typeof body === 'string' ? (bodyEl.innerHTML = body) : bodyEl.append(body);
    const foot = $('footer', el);
    if (!actions.length) foot.remove();
    const close = (v) => { el.classList.add('out'); setTimeout(() => el.remove(), 150); document.removeEventListener('keydown', onKey); resolve(v); };
    const onKey = (e) => { if (e.key === 'Escape') close(null); };
    actions.forEach((a) => {
      const b = h(`<button class="btn ${a.kind || ''}">${a.icon ? icon(a.icon) : ''}${esc(a.label)}</button>`);
      b.addEventListener('click', async () => {
        if (!a.onClick) return close(a.value ?? null);
        b.disabled = true;
        try { const r = await a.onClick(el); if (r !== false) close(r ?? true); } finally { b.disabled = false; }
      });
      foot.append(b);
    });
    el.addEventListener('mousedown', (e) => { if (e.target === el) close(null); });
    $('[data-close]', el).addEventListener('click', () => close(null));
    document.addEventListener('keydown', onKey);
    $('#modals').append(el);
    setTimeout(() => ($('input:not([type=hidden]), select, textarea', bodyEl) || $('button', foot) || $('[data-close]', el))?.focus(), 30);
    el._close = close;
  });
}

export function confirmDialog(message, { title = 'Confirm', ok = 'Confirm', danger = false } = {}) {
  return modal({ title, body: `<p class="confirm-text">${esc(message)}</p>`, size: 'sm',
    actions: [{ label: 'Cancel', value: false }, { label: ok, kind: danger ? 'danger' : 'primary', value: true }] });
}

// ---------- Form ----------
// field: {name, label, type: text|number|date|datetime|select|textarea|checkbox|password|email, options:[[v,t]], required, value, help, span:2, min, step}
export function formModal({ title, fields, values = {}, submitLabel = 'Save', onSubmit, size = '' }) {
  const form = h('<form class="form-grid" novalidate></form>');
  fields.forEach((f) => {
    const v = values[f.name] ?? f.value ?? '';
    const id = 'f_' + f.name;
    const req = f.required ? ' required' : '';
    let input;
    if (f.type === 'select') {
      input = `<select id="${id}" name="${f.name}"${req}>${f.placeholder !== false ? `<option value="">${esc(f.placeholder || '— Select —')}</option>` : ''}${
        f.options.map(([ov, ot]) => `<option value="${esc(ov)}" ${String(ov) === String(v) ? 'selected' : ''}>${esc(ot)}</option>`).join('')}</select>`;
    } else if (f.type === 'textarea') {
      input = `<textarea id="${id}" name="${f.name}" rows="${f.rows || 3}"${req}>${esc(v)}</textarea>`;
    } else if (f.type === 'checkbox') {
      input = `<label class="switch"><input type="checkbox" id="${id}" name="${f.name}" ${v ? 'checked' : ''}><span></span>${esc(f.text || '')}</label>`;
    } else {
      const type = f.type === 'datetime' ? 'datetime-local' : f.type || 'text';
      const val = f.type === 'datetime' && v ? String(v).slice(0, 16) : v;
      input = `<input id="${id}" name="${f.name}" type="${type}" value="${esc(val)}"${req}${f.min != null ? ` min="${f.min}"` : ''}${f.step ? ` step="${f.step}"` : ''}${f.placeholder ? ` placeholder="${esc(f.placeholder)}"` : ''}${f.disabled ? ' disabled' : ''} autocomplete="off">`;
    }
    form.append(h(`<div class="field ${f.span === 2 ? 'span2' : ''}">
      ${f.type === 'checkbox' ? '' : `<label for="${id}">${esc(f.label)}${f.required ? ' <i>*</i>' : ''}</label>`}${input}
      ${f.help ? `<small>${esc(f.help)}</small>` : ''}</div>`));
  });
  form.append(h('<p class="form-error span2" hidden></p>'));
  const read = () => Object.fromEntries(fields.map((f) => {
    const el = form.elements[f.name];
    if (f.type === 'checkbox') return [f.name, el.checked];
    const raw = el.value.trim();
    if (f.type === 'number') return [f.name, raw === '' ? null : Number(raw)];
    return [f.name, raw === '' ? null : raw];
  }));
  form.addEventListener('submit', (e) => { e.preventDefault(); form.closest('.modal').querySelector('footer .primary')?.click(); });
  return modal({ title, body: form, size, actions: [
    { label: 'Cancel', value: null },
    { label: submitLabel, kind: 'primary', onClick: async () => {
      const err = $('.form-error', form);
      const missing = fields.find((f) => f.required && f.type !== 'checkbox' && !form.elements[f.name].value.trim());
      if (missing) { err.textContent = `Please enter "${missing.label}".`; err.hidden = false; form.elements[missing.name].focus(); return false; }
      try { return (await onSubmit(read())) ?? true; }
      catch (e) { err.textContent = e.message; err.hidden = false; return false; }
    } }] });
}

// ---------- Bảng: tìm kiếm, sắp xếp, phân trang ----------
// columns: {key, label, render(row) -> html, sort(row) -> value, num, width, cls}
export function dataTable({ columns, rows, search = true, pageSize = 12, onRow, empty = 'No data yet.', filters = '', searchKeys }) {
  const root = h(`<div class="dt">
    ${search || filters ? `<div class="dt-tools">${search ? `<label class="search">${icon('search')}<input type="search" placeholder="Search…" aria-label="Search"></label>` : ''}<div class="dt-filters">${filters}</div></div>` : ''}
    <div class="table-wrap"></div><div class="dt-foot"></div></div>`);
  let data = rows, q = '', page = 0, sortKey = null, sortDir = 1;
  const text = (r) => (searchKeys ? searchKeys.map((k) => r[k]) : Object.values(r)).join(' ').toLowerCase();
  const render = () => {
    let view = q ? data.filter((r) => text(r).includes(q)) : data;
    if (sortKey) {
      const col = columns.find((c) => c.key === sortKey);
      const val = col.sort || ((r) => r[col.key]);
      view = [...view].sort((a, b) => { const x = val(a), y = val(b); return (x == null) - (y == null) || (x > y ? 1 : x < y ? -1 : 0) * sortDir; });
    }
    const pages = Math.max(1, Math.ceil(view.length / pageSize));
    page = Math.min(page, pages - 1);
    const slice = view.slice(page * pageSize, (page + 1) * pageSize);
    $('.table-wrap', root).innerHTML = !view.length ? `<div class="empty">${icon('database')}<p>${esc(q ? 'No matching results.' : empty)}</p></div>` :
      `<table><thead><tr>${columns.map((c) => `<th class="${c.num ? 'num' : ''} ${c.key && c.sortable !== false ? 'sortable' : ''}" data-k="${c.key || ''}" style="${c.width ? `width:${c.width}` : ''}">${esc(c.label)}${sortKey === c.key ? (sortDir > 0 ? ' ↑' : ' ↓') : ''}</th>`).join('')}</tr></thead>
      <tbody>${slice.map((r, i) => `<tr data-i="${i}" class="${onRow ? 'clickable' : ''}">${columns.map((c) => `<td class="${c.num ? 'num' : ''} ${c.cls || ''}" data-label="${esc(c.label)}">${c.render ? c.render(r) : esc(r[c.key] ?? '')}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
    $('.dt-foot', root).innerHTML = view.length > pageSize ? `<span>${page * pageSize + 1}–${page * pageSize + slice.length} / ${view.length}</span>
      <button class="btn sm" data-p="-1" ${page === 0 ? 'disabled' : ''}>Previous</button><button class="btn sm" data-p="1" ${page >= pages - 1 ? 'disabled' : ''}>Next</button>`
      : view.length ? `<span>${view.length} ${view.length === 1 ? 'row' : 'rows'}</span>` : '';
    $$('th.sortable', root).forEach((th) => th.addEventListener('click', () => {
      sortDir = sortKey === th.dataset.k ? -sortDir : 1; sortKey = th.dataset.k; render();
    }));
    $$('[data-p]', root).forEach((b) => b.addEventListener('click', () => { page += +b.dataset.p; render(); }));
    if (onRow) $$('tbody tr', root).forEach((tr) => tr.addEventListener('click', (e) => {
      if (e.target.closest('button, a, input, select, label')) return;
      onRow(slice[+tr.dataset.i]);
    }));
    root.dispatchEvent(new CustomEvent('rendered', { detail: slice }));
  };
  const input = $('.search input', root);
  input?.addEventListener('input', () => { q = input.value.trim().toLowerCase(); page = 0; render(); });
  root.setRows = (r) => { data = r; render(); };
  render();
  return root;
}

// ---------- Biểu đồ (SVG thuần, dùng biến màu của theme) ----------
export function hbar(items, { format = fmt.num, color = 'var(--c1)', max } = {}) {
  if (!items.length) return '<p class="muted small">No data yet.</p>';
  const top = max ?? Math.max(...items.map((i) => +i.value || 0), 1);
  return `<div class="hbar">${items.map((i) => `<div class="hbar-row" title="${esc(i.label)}: ${esc(format(i.value))}">
    <span class="hbar-label">${esc(i.label)}</span>
    <span class="hbar-track"><span style="width:${Math.max(1.5, (100 * (+i.value || 0)) / top)}%;background:${i.color || color}"></span></span>
    <span class="hbar-val">${esc(format(i.value))}</span></div>`).join('')}</div>`;
}

export function columns(points, series, { format = fmt.num, height = 220 } = {}) {
  // points: [{label, a: 1, b: 2}], series: [{key, name, color}]
  if (!points.length) return '<p class="muted small">No data yet.</p>';
  const W = 640, H = height, m = { t: 14, r: 8, b: 28, l: 44 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const top = Math.max(...points.flatMap((p) => series.map((s) => +p[s.key] || 0)), 1);
  const nice = Math.pow(10, Math.floor(Math.log10(top))) * (top / Math.pow(10, Math.floor(Math.log10(top))) > 5 ? 10 : top / Math.pow(10, Math.floor(Math.log10(top))) > 2 ? 5 : 2);
  const y = (v) => m.t + ih - (v / nice) * ih;
  const gw = iw / points.length, bw = Math.min(22, (gw - 8) / series.length);
  let s = `<svg viewBox="0 0 ${W} ${H}" class="colchart" role="img">`;
  for (let k = 0; k <= 4; k++) {
    const v = (nice * k) / 4;
    s += `<line class="grid" x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}"/><text class="axis" x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end">${esc(format(v))}</text>`;
  }
  points.forEach((p, i) => {
    const x0 = m.l + i * gw + (gw - bw * series.length) / 2;
    series.forEach((se, j) => {
      const v = +p[se.key] || 0, top_ = y(v), hgt = m.t + ih - top_;
      s += `<rect x="${x0 + j * bw + 1}" y="${top_}" width="${bw - 2}" height="${Math.max(0, hgt)}" rx="3" fill="${se.color}"><title>${esc(p.label)} · ${esc(se.name)}: ${esc(format(v))}</title></rect>`;
    });
    if (points.length <= 14 || i % 2 === 0) s += `<text class="axis" x="${m.l + i * gw + gw / 2}" y="${H - 8}" text-anchor="middle">${esc(p.label)}</text>`;
  });
  return s + '</svg>' + `<div class="legend">${series.map((se) => `<span><i style="background:${se.color}"></i>${esc(se.name)}</span>`).join('')}</div>`;
}

export function progress(value, total) {
  const pct = total ? Math.min(100, (100 * value) / total) : 0;
  const cls = pct >= 100 ? 'bad' : pct >= 85 ? 'warn' : 'good';
  return `<span class="progress ${cls}" title="${fmt.pct(pct)}"><span style="width:${pct}%"></span></span>`;
}

// ---------- Xuất CSV phía trình duyệt ----------
export function downloadCsv(filename, header, rows) {
  const cell = (v) => { const s = String(v ?? ''); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const csv = '﻿' + [header, ...rows].map((r) => r.map(cell).join(',')).join('\r\n');
  const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(new Blob([csv], { type: 'text/csv' })), download: filename });
  a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export function tabs(items, active, onChange) {
  const el = h(`<div class="tabs" role="tablist">${items.map(([k, t, n]) => `<button role="tab" data-k="${k}" class="${k === active ? 'on' : ''}">${esc(t)}${n != null ? ` <b>${n}</b>` : ''}</button>`).join('')}</div>`);
  $$('button', el).forEach((b) => b.addEventListener('click', () => {
    $$('button', el).forEach((x) => x.classList.toggle('on', x === b)); onChange(b.dataset.k);
  }));
  return el;
}

export const loading = () => '<div class="loading"><span class="spinner"></span>Loading…</div>';
