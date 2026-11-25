// Quản lý thành viên (BR09: đã có dữ liệu liên quan thì chỉ chuyển sang "Inactive")
import { $, api, avatar, can, confirmDialog, dataTable, esc, EVENT_TYPE_VI, fmt, formModal, icon, modal, POSITION_VI, state, toast, toastError, vi } from '../core.js';

const posBadge = (p) => `<span class="badge ${p === 'Inactive' ? 'muted' : p === 'Member' ? 'info' : 'accent'}">${esc(vi(POSITION_VI, p))}</span>`;

function memberForm(m, reload) {
  const L = state.lookups;
  return formModal({
    title: m ? `Edit member — ${m.full_name}` : 'Add member', values: m || { position: 'Member' },
    fields: [
      { name: 'last_name', label: 'Last name', required: true },
      { name: 'first_name', label: 'First name', required: true },
      { name: 'email', label: 'Email', type: 'email', placeholder: 'name@lpu.edu' },
      { name: 'phone', label: 'Phone' },
      { name: 'position', label: 'Position', type: 'select', required: true, placeholder: false, options: L.positions.map((p) => [p, vi(POSITION_VI, p)]) },
      { name: 't_shirt_size', label: 'T-shirt size', type: 'select', options: L.shirt_sizes.map((s) => [s, s]) },
      { name: 'link_to_major', label: 'Major', type: 'select', span: 2, options: L.majors.map((x) => [x.id, x.name]) },
      { name: 'zip', label: 'ZIP code', type: 'number', help: 'Must exist in the ZIP code list, e.g. 55108' },
    ],
    onSubmit: async (v) => {
      await api(m ? `/api/members/${m.member_id}` : '/api/members', { method: m ? 'PUT' : 'POST', body: v });
      toast(m ? 'Member updated.' : 'Member added.');
      state.lookups = await api('/api/lookups');
      reload();
    },
  });
}

async function detail(id, reload) {
  const m = await api(`/api/members/${id}`);
  const body = `<div class="profile">${avatar(m.full_name, 'lg')}<div><h3>${esc(m.full_name)}</h3>${posBadge(m.position)}</div></div>
    <dl class="kv">
      <dt>Major</dt><dd>${esc(m.major_name || '—')}</dd>
      <dt>Email</dt><dd>${can('pii.read') ? esc(m.email || '—') : `<span class="muted">${icon('lock')} hidden for your role</span>`}</dd>
      <dt>Phone</dt><dd>${can('pii.read') ? esc(m.phone || '—') : `<span class="muted">${icon('lock')} hidden for your role</span>`}</dd>
      <dt>T-shirt size</dt><dd>${esc(m.t_shirt_size || '—')}</dd><dt>ZIP code</dt><dd>${esc(m.zip ?? '—')}</dd>
    </dl>
    <h4>Attended ${m.events.length} ${m.events.length === 1 ? 'event' : 'events'}</h4>
    ${m.events.length ? `<ul class="mini-list">${m.events.map((e) => `<li><span>${esc(e.event_name)}</span><small>${fmt.date(e.event_date)} · ${esc(vi(EVENT_TYPE_VI, e.type))}</small></li>`).join('')}</ul>` : '<p class="muted small">Has not attended any events yet.</p>'}`;
  const actions = can('member.write') ? [
    { label: 'Delete', kind: 'danger ghost', icon: 'trash', onClick: async () => {
      if (!(await confirmDialog(`Delete member ${m.full_name}?`, { danger: true, ok: 'Delete' }))) return false;
      try { await api(`/api/members/${id}`, { method: 'DELETE' }); toast('Member deleted.'); reload(); }
      catch (err) { toastError(err); return false; }
    } },
    { label: 'Edit', kind: 'primary', icon: 'edit', onClick: () => { setTimeout(() => memberForm(m, reload), 160); } },
  ] : [];
  modal({ title: 'Member profile', body, actions });
}

export default async function members({ view, setHeader, params }) {
  const load = async () => {
    const rows = await api('/api/members');
    const active = rows.filter((r) => r.position !== 'Inactive');
    setHeader(`${active.length} active · ${rows.length - active.length} former`,
      can('member.write') ? [{ label: 'Add member', icon: 'plus', onClick: () => memberForm(null, load) }] : []);
    const pii = can('pii.read');
    const table = dataTable({
      rows: active, pageSize: 12, searchKeys: ['full_name', 'position', 'major_name', 'email', 'phone', 'department'],
      filters: `<select id="m-pos" aria-label="Filter by position"><option value="">Position: all</option>${state.lookups.positions.filter((p) => p !== 'Inactive').map((p) => `<option value="${p}">${esc(vi(POSITION_VI, p))}</option>`).join('')}</select>
        <label class="switch small"><input type="checkbox" id="m-inactive"><span></span>Include former members</label>`,
      columns: [
        { key: 'full_name', label: 'Name', render: (r) => `<span class="person">${avatar(r.full_name)}<b>${esc(r.full_name)}</b></span>` },
        { key: 'position', label: 'Position', render: (r) => posBadge(r.position) },
        { key: 'major_name', label: 'Major', render: (r) => `${esc(r.major_name || '—')}${r.department ? `<small class="muted block">${esc(r.department)}</small>` : ''}`, cls: 'clamp' },
        pii ? { key: 'email', label: 'Contact', render: (r) => `${esc(r.email || '—')}<small class="muted block">${esc(r.phone || '')}</small>` }
          : { label: 'Contact', sortable: false, render: () => `<span class="muted small">${icon('lock')} Hidden</span>` },
        { key: 't_shirt_size', label: 'T-shirt size' },
        { key: 'attended', label: 'Attended', num: true, render: (r) => `${r.attended} ${r.attended === 1 ? 'event' : 'events'}` },
      ],
      onRow: (r) => detail(r.member_id, load).catch(toastError),
    });
    view.innerHTML = '<section class="card"></section>';
    view.firstElementChild.append(table);
    const apply = () => {
      const pos = $('#m-pos', table).value, all = $('#m-inactive', table).checked;
      table.setRows(rows.filter((r) => (all || r.position !== 'Inactive') && (!pos || r.position === pos)));
    };
    $('#m-pos', table).addEventListener('change', apply);
    $('#m-inactive', table).addEventListener('change', apply);
  };
  await load();
  if (params[0]) detail(params[0], load).catch(toastError);
}
