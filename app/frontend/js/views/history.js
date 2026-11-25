// UC03 Lịch sử câu hỏi của tôi
import { $, api, badge, dataTable, esc, fmt, icon, LABEL, state } from '../core.js';

export default async function history({ view, setHeader, go }) {
  const rows = await api('/api/history');
  const ok = rows.filter((r) => r.status === 'EXECUTED').length;
  setHeader(`${rows.length} most recent questions · ${rows.length ? Math.round((100 * ok) / rows.length) : 0}% answered successfully`);
  const statuses = [...new Set(rows.map((r) => r.status))];
  const table = dataTable({
    rows, pageSize: 15, empty: 'You have not asked anything yet. Open "Ask AI" to get started.',
    searchKeys: ['question', 'answer', 'error', 'model_name'],
    filters: `<select id="h-status" aria-label="Filter by status"><option value="">All statuses</option>${statuses.map((s) => `<option value="${s}">${esc(LABEL[s]?.[0] || s)}</option>`).join('')}</select>`,
    columns: [
      { key: 'created_at', label: 'Time', render: (r) => `<span class="nowrap">${fmt.datetime(r.created_at)}</span>`, width: '130px' },
      { key: 'question', label: 'Question', render: (r) => `<b class="q" data-log="${r.id}">${esc(r.question)}</b>${r.evidence ? `<small class="muted block">${icon('book')} ${esc(r.evidence)}</small>` : ''}${r.glossary_used ? `<small class="muted block">${icon('book')} ${esc(r.glossary_used)}</small>` : ''}` },
      { key: 'answer', label: 'Answer', render: (r) => esc(r.answer || r.error || '—'), cls: 'clamp' },
      { key: 'status', label: 'Status', render: (r) => badge(r.status) },
      { key: 'rating', label: 'Rating', render: (r) => (r.rating === 1 ? '<span class="badge good">Correct</span>' : r.rating === -1 ? '<span class="badge bad">Wrong</span>' : '<span class="muted">—</span>') },
      { key: 'latency_ms', label: 'ms', num: true, render: (r) => fmt.num(r.latency_ms) },
      { label: '', sortable: false, render: () => `<button class="btn sm ghost" data-again>${icon('refresh')}Ask again</button>` },
    ],
    onRow: (r) => { state.pendingQuestion = { question: r.question, evidence: r.evidence, sample_id: r.sample_id }; go('ask'); },
  });
  view.innerHTML = '<section class="card"></section>';
  view.firstElementChild.append(table);
  $('#h-status', table).addEventListener('change', (e) => table.setRows(e.target.value ? rows.filter((r) => r.status === e.target.value) : rows));
  table.addEventListener('click', (e) => {
    const b = e.target.closest('[data-again]');
    if (!b) return;
    const r = rows.find((x) => x.id === +b.closest('tr').querySelector('[data-log]').dataset.log);
    state.pendingQuestion = { question: r.question, evidence: r.evidence, sample_id: r.sample_id };
    go('ask');
  });
}
