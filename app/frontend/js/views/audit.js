// Nhật ký thay đổi dữ liệu (BR10)
import { $, api, badge, dataTable, ENTITY_VI, esc, fmt, h, modal } from '../core.js';

const pretty = (v) => (v == null ? '—' : esc(JSON.stringify(v, null, 2)));

export default async function audit({ view, setHeader }) {
  const rows = await api('/api/audit');
  setHeader('Every create, update, delete and approval is recorded along with who did it.');
  const entities = [...new Set(rows.map((r) => r.entity))];
  const table = dataTable({
    rows, pageSize: 15, searchKeys: ['summary', 'username', 'full_name', 'entity'],
    filters: `<select id="a-entity" aria-label="Filter by record type"><option value="">All record types</option>${entities.map((e) => `<option value="${e}">${esc(ENTITY_VI[e] || e)}</option>`).join('')}</select>`,
    columns: [
      { key: 'created_at', label: 'Time', render: (r) => `<span class="nowrap">${fmt.datetime(r.created_at)}</span>`, width: '130px' },
      { key: 'full_name', label: 'User', render: (r) => `${esc(r.full_name)}<small class="muted block">${esc(r.username)}</small>` },
      { key: 'action', label: 'Action', render: (r) => badge(r.action) },
      { key: 'entity', label: 'Record type', render: (r) => esc(ENTITY_VI[r.entity] || r.entity) },
      { key: 'summary', label: 'Summary', render: (r) => esc(r.summary) },
    ],
    empty: 'No changes yet.',
    onRow: (r) => {
      const d = r.detail ? JSON.parse(r.detail) : null;
      modal({ title: r.summary, size: 'lg', body: `<dl class="kv"><dt>User</dt><dd>${esc(r.full_name)} (${esc(r.username)})</dd><dt>Time</dt><dd>${fmt.datetime(r.created_at)}</dd><dt>Record ID</dt><dd><code>${esc(r.entity_id)}</code></dd></dl>
        ${d ? `<div class="diff"><div><h4>Before</h4><pre>${pretty(d.before)}</pre></div><div><h4>After</h4><pre>${pretty(d.after)}</pre></div></div>` : ''}` });
    },
  });
  view.innerHTML = '';
  const card = h('<section class="card"></section>');
  card.append(table);
  view.append(card);
  $('#a-entity', table).addEventListener('change', (e) => table.setRows(e.target.value ? rows.filter((r) => r.entity === e.target.value) : rows));
}
