// Báo cáo chuyên cần và tài chính, xuất CSV
import { api, badge, can, dataTable, downloadCsv, esc, EVENT_TYPE_VI, fmt, h, hbar, POSITION_VI, progress, SOURCE_VI, tabs, vi } from '../core.js';

async function attendance(box) {
  const d = await api('/api/reports/attendance');
  const active = d.members.filter((m) => m.position !== 'Inactive');
  const avg = active.length ? active.reduce((s, m) => s + m.rate, 0) / active.length : 0;
  box.innerHTML = `<div class="kpis compact">
    <div class="kpi"><div><p>Events held / open</p><b>${d.total_events}</b></div></div>
    <div class="kpi"><div><p>Avg. attendance rate (active members)</p><b>${fmt.pct(avg)}</b></div></div>
    <div class="kpi"><div><p>Never attended</p><b>${active.filter((m) => !m.attended).length} members</b></div></div></div>
    <div class="grid-2 wide-left"><section class="card" id="r-members"><header class="card-h"><h2>Attendance by member</h2><button class="btn sm" id="csv-m">Export CSV</button></header></section>
    <section class="card"><header class="card-h"><h2>Attendees per event</h2><button class="btn sm" id="csv-e">Export CSV</button></header>
    ${hbar(d.events.filter((e) => e.status !== 'Planning').sort((a, b) => b.attendees - a.attendees).slice(0, 15).map((e) => ({ label: e.event_name, value: e.attendees })), { color: 'var(--c3)', format: (v) => `${v} ${v === 1 ? 'attendee' : 'attendees'}` })}</section></div>`;
  box.querySelector('#r-members').append(dataTable({
    rows: d.members, pageSize: 10, searchKeys: ['full_name', 'position', 'major_name'],
    columns: [
      { key: 'full_name', label: 'Member', render: (m) => `<b>${esc(m.full_name)}</b><small class="muted block">${esc(vi(POSITION_VI, m.position))}</small>` },
      { key: 'attended', label: 'Events attended', num: true },
      { key: 'rate', label: 'Rate', num: true, render: (m) => fmt.pct(m.rate) },
      { label: '', sortable: false, render: (m) => progress(m.rate, 100).replace(/progress (good|warn|bad)/, 'progress good') },
    ],
  }));
  box.querySelector('#csv-m').addEventListener('click', () => downloadCsv('member_attendance.csv', ['Member', 'Position', 'Major', 'Events attended', 'Total events', 'Rate (%)'],
    d.members.map((m) => [m.full_name, m.position, m.major_name, m.attended, d.total_events, m.rate])));
  box.querySelector('#csv-e').addEventListener('click', () => downloadCsv('attendance_by_event.csv', ['Event', 'Date', 'Type', 'Status', 'Attendees'],
    d.events.map((e) => [e.event_name, e.event_date.slice(0, 10), vi(EVENT_TYPE_VI, e.type), e.status, e.attendees])));
}

async function financeReport(box) {
  const d = await api('/api/reports/finance');
  const t = d.by_event.reduce((s, e) => ({ budget: s.budget + e.budget, spent: s.spent + e.spent, remaining: s.remaining + e.remaining }), { budget: 0, spent: 0, remaining: 0 });
  const income = d.income.reduce((s, i) => s + i.total, 0);
  box.innerHTML = `<div class="kpis compact">
    <div class="kpi"><div><p>Total income</p><b>${fmt.money(income)}</b></div></div>
    <div class="kpi"><div><p>Total expenses (approved)</p><b>${fmt.money(t.spent)}</b></div></div>
    <div class="kpi"><div><p>Net (income − expenses)</p><b class="${income - t.spent < 0 ? 'text-bad' : 'text-good'}">${fmt.money(income - t.spent)}</b></div></div>
    <div class="kpi"><div><p>Unused budget</p><b>${fmt.money(t.remaining)}</b></div></div></div>
    <div class="grid-2 wide-left"><section class="card" id="r-fin"><header class="card-h"><h2>Finances by event</h2><button class="btn sm" id="csv-f">Export CSV</button></header></section>
    <section class="card"><header class="card-h"><h2>Income by source</h2></header>
    ${hbar(d.income.map((i) => ({ label: `${vi(SOURCE_VI, i.source)} (${i.n} ${i.n === 1 ? 'entry' : 'entries'})`, value: i.total })), { format: fmt.money, color: 'var(--c2)' })}</section></div>`;
  box.querySelector('#r-fin').append(dataTable({
    rows: d.by_event, pageSize: 10, searchKeys: ['event_name'],
    columns: [
      { key: 'event_name', label: 'Event', render: (e) => `<b>${esc(e.event_name)}</b><small class="muted block">${fmt.date(e.event_date)}</small>` },
      { key: 'status', label: 'Status', render: (e) => badge(e.status) },
      { key: 'budget', label: 'Budget', num: true, render: (e) => fmt.money(e.budget) },
      { key: 'spent', label: 'Spent', num: true, render: (e) => `${fmt.money(e.spent)}${e.pending ? `<small class="muted block">+${fmt.money(e.pending)} pending</small>` : ''}` },
      { key: 'remaining', label: 'Remaining', num: true, render: (e) => fmt.money(e.remaining) },
      { label: '', sortable: false, render: (e) => progress(e.spent, e.budget) },
    ],
  }));
  box.querySelector('#csv-f').addEventListener('click', () => downloadCsv('finance_by_event.csv', ['Event', 'Date', 'Status', 'Budget', 'Spent', 'Remaining', 'Expense count', 'Pending'],
    d.by_event.map((e) => [e.event_name, e.event_date.slice(0, 10), e.status, e.budget, e.spent, e.remaining, e.n_expenses, e.pending])));
}

export default async function reports({ view, setHeader }) {
  setHeader('Summary figures; download as CSV to open in Excel.');
  const items = [['attendance', 'Attendance'], ...(can('finance.read') ? [['finance', 'Finance']] : [])];
  const box = h('<div></div>');
  const show = (k) => (k === 'finance' ? financeReport(box) : attendance(box));
  view.innerHTML = '';
  view.append(tabs(items, 'attendance', (k) => show(k)), box);
  await show('attendance');
}
