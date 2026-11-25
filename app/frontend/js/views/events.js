// Sự kiện và điểm danh (BR11 vòng đời một chiều, BR12 chỉ điểm danh khi sự kiện đang mở)
import { $, $$, api, avatar, badge, can, CATEGORY_VI, confirmDialog, dataTable, esc, EVENT_TYPE_VI, fmt, formModal, h, icon, modal, POSITION_VI, progress, state, tabs, toast, toastError, vi } from '../core.js';

const NEXT = { Planning: ['Open', 'Open event', 'Attendance can be recorded from now on'], Open: ['Closed', 'Close event', 'Attendance and spending will be locked'] };

function eventForm(e, reload) {
  const L = state.lookups;
  return formModal({
    title: e ? 'Edit event' : 'Create event', values: e || {},
    fields: [
      { name: 'event_name', label: 'Event name', required: true, span: 2 },
      { name: 'event_date', label: 'Date & time', type: 'datetime', required: true },
      { name: 'type', label: 'Type', type: 'select', required: true, options: L.event_types.map((t) => [t, vi(EVENT_TYPE_VI, t)]) },
      { name: 'location', label: 'Location' },
      e ? { name: 'status', label: 'Status', type: 'select', placeholder: false, options: L.event_statuses.map((s) => [s, s]), help: 'Forward only: Planning → Open → Closed' } : null,
      { name: 'notes', label: 'Notes', type: 'textarea', span: 2 },
    ].filter(Boolean),
    onSubmit: async (v) => {
      const body = { ...v, status: v.status || e?.status || 'Planning' };
      await api(e ? `/api/events/${e.event_id}` : '/api/events', { method: e ? 'PUT' : 'POST', body });
      toast(e ? 'Event updated.' : 'Event created with status "Planning".');
      state.lookups = await api('/api/lookups');
      reload();
    },
  });
}

async function detail(id, reload) {
  const e = await api(`/api/events/${id}`);
  const members = state.lookups.members;
  const editable = can('attendance.write') && e.status === 'Open';
  const chosen = new Set(e.attendees);
  const body = h(`<div>
    <div class="ev-head">${badge(e.status)}<span>${icon('calendar')}${fmt.datetime(e.event_date)}</span><span>${icon('pin')}${esc(e.location || 'No location yet')}</span><span>${esc(vi(EVENT_TYPE_VI, e.type))}</span></div>
    ${e.notes ? `<p class="muted">${esc(e.notes)}</p>` : ''}
    ${e.budgets ? `<h4>Budget</h4>${e.budgets.length ? `<table class="compact"><thead><tr><th>Category</th><th class="num">Budget</th><th class="num">Spent</th><th></th></tr></thead><tbody>${e.budgets.map((b) => `<tr><td>${esc(vi(CATEGORY_VI, b.category))}</td><td class="num">${fmt.money(b.amount)}</td><td class="num">${fmt.money(b.spent)}</td><td>${progress(b.spent, b.amount)}</td></tr>`).join('')}</tbody></table>` : '<p class="muted small">No budget set yet.</p>'}` : ''}
    <h4>Attendance <span class="muted" id="att-count">${chosen.size} ${chosen.size === 1 ? 'person' : 'people'}</span></h4>
    ${!editable ? `<p class="small muted">${icon('info')} ${e.status === 'Planning' ? 'The event is not open yet, so attendance cannot be recorded.' : e.status === 'Closed' ? 'The event is closed; the attendance list is locked.' : 'You do not have permission to record attendance.'}</p>` : ''}
    ${editable ? `<div class="att-tools"><label class="search">${icon('search')}<input type="search" placeholder="Search members…" id="att-q"></label>
      <button class="btn sm ghost" id="att-all">Select all</button><button class="btn sm ghost" id="att-none">Clear</button></div>` : ''}
    <div class="att-list">${members.filter((m) => editable ? m.position !== 'Inactive' || chosen.has(m.id) : chosen.has(m.id)).map((m) => `
      <label class="att-item" data-name="${esc(m.name.toLowerCase())}"><input type="checkbox" value="${m.id}" ${chosen.has(m.id) ? 'checked' : ''} ${editable ? '' : 'disabled'}>
      ${avatar(m.name, 'sm')}<span>${esc(m.name)}<small>${esc(vi(POSITION_VI, m.position))}</small></span></label>`).join('') || '<p class="muted small">No one yet.</p>'}</div></div>`);
  if (editable) {
    const boxes = () => $$('input[type=checkbox]', body);
    const count = () => { $('#att-count', body).textContent = (n => `${n} ${n === 1 ? 'person' : 'people'}`)(boxes().filter((b) => b.checked).length); };
    body.addEventListener('change', count);
    $('#att-q', body).addEventListener('input', (ev) => {
      const q = ev.target.value.trim().toLowerCase();
      $$('.att-item', body).forEach((l) => { l.hidden = q && !l.dataset.name.includes(q); });
    });
    $('#att-all', body).addEventListener('click', () => { boxes().forEach((b) => { if (!b.closest('.att-item').hidden) b.checked = true; }); count(); });
    $('#att-none', body).addEventListener('click', () => { boxes().forEach((b) => { b.checked = false; }); count(); });
  }
  const actions = [];
  if (can('event.write')) {
    if (e.status === 'Planning') actions.push({ label: 'Delete', kind: 'danger ghost', icon: 'trash', onClick: async () => {
      if (!(await confirmDialog(`Delete event "${e.event_name}"?`, { danger: true, ok: 'Delete' }))) return false;
      try { await api(`/api/events/${id}`, { method: 'DELETE' }); toast('Event deleted.'); reload(); } catch (err) { toastError(err); return false; }
    } });
    actions.push({ label: 'Edit', kind: 'ghost', icon: 'edit', onClick: () => { setTimeout(() => eventForm(e, reload), 160); } });
    const nx = NEXT[e.status];
    if (nx) actions.push({ label: nx[1], kind: editable ? 'ghost' : 'primary', onClick: async () => {
      if (!(await confirmDialog(`${nx[1]} "${e.event_name}"? ${nx[2]}. This cannot be undone.`, { ok: nx[1] }))) return false;
      try { await api(`/api/events/${id}`, { method: 'PUT', body: { ...e, status: nx[0] } }); toast(`Status changed to "${nx[0]}".`); reload(); }
      catch (err) { toastError(err); return false; }
    } });
  }
  if (editable) actions.push({ label: 'Save attendance', kind: 'primary', icon: 'check', onClick: async () => {
    try {
      const ids = $$('input[type=checkbox]:checked', body).map((b) => b.value);
      const r = await api(`/api/events/${id}/attendance`, { method: 'PUT', body: { member_ids: ids } });
      toast(`Attendance saved: ${r.count} ${r.count === 1 ? 'person' : 'people'}.`); reload();
    } catch (err) { toastError(err); return false; }
  } });
  modal({ title: e.event_name, body, size: 'lg', actions });
}

export default async function events({ view, setHeader, params }) {
  let status = '';
  const load = async () => {
    const rows = await api('/api/events');
    const count = (s) => rows.filter((r) => r.status === s).length;
    setHeader(`${rows.length} events · ${count('Open')} open`,
      can('event.write') ? [{ label: 'Create event', icon: 'plus', onClick: () => eventForm(null, load) }] : []);
    const fin = can('finance.read');
    const table = dataTable({
      rows: status ? rows.filter((r) => r.status === status) : rows, pageSize: 12,
      searchKeys: ['event_name', 'type', 'location', 'notes'],
      columns: [
        { key: 'event_date', label: 'Date', render: (r) => `<span class="nowrap">${fmt.date(r.event_date)}</span>`, width: '110px' },
        { key: 'event_name', label: 'Event', render: (r) => `<b>${esc(r.event_name)}</b><small class="muted block">${esc(r.location || '')}</small>` },
        { key: 'type', label: 'Type', render: (r) => esc(vi(EVENT_TYPE_VI, r.type)) },
        { key: 'status', label: 'Status', render: (r) => badge(r.status) },
        { key: 'attendees', label: 'Attendees', num: true },
        ...(fin ? [{ key: 'budget_amount', label: 'Budget', num: true, render: (r) => r.budget_amount ? `${fmt.money(r.budget_spent)} / ${fmt.money(r.budget_amount)}` : '<span class="muted">—</span>' }] : []),
      ],
      onRow: (r) => detail(r.event_id, load).catch(toastError),
    });
    view.innerHTML = '';
    view.append(tabs([['', 'All', rows.length], ['Planning', 'Planning', count('Planning')], ['Open', 'Open', count('Open')], ['Closed', 'Closed', count('Closed')]],
      status, (k) => { status = k; table.setRows(k ? rows.filter((r) => r.status === k) : rows); }));
    const card = h('<section class="card"></section>');
    card.append(table);
    view.append(card);
  };
  await load();
  if (params[0]) detail(params[0], load).catch(toastError);
}
