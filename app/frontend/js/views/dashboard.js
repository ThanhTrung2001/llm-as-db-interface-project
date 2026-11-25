// Tổng quan CLB — số liệu theo quyền của vai trò
import { api, badge, can, CATEGORY_VI, columns, esc, EVENT_TYPE_VI, fmt, hbar, icon, MONTHS, SOURCE_VI, state, vi } from '../core.js';

const monYear = (iso) => `${MONTHS[+String(iso).slice(5, 7) - 1] || ''} ${String(iso).slice(0, 4)}`;  // 'Apr 2020'

const kpi = (ic, label, value, sub = '', tone = '', href = '') =>
  `<${href ? `a href="${href}"` : 'div'} class="kpi ${tone}"><span class="kpi-ic">${icon(ic)}</span><div><p>${esc(label)}</p><b>${value}</b>${sub ? `<small>${sub}</small>` : ''}</div></${href ? 'a' : 'div'}>`;

export default async function dashboard({ view, setHeader, go }) {
  const d = await api('/api/dashboard');
  const hour = new Date().getHours();
  const hello = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  setHeader(`${hello}, ${state.user.full_name.split(' ')[0]} · ${state.user.role_name}`);
  const f = d.finance;
  const upcoming = (d.events_by_status.Planning || 0) + (d.events_by_status.Open || 0);

  view.innerHTML = `
    <div class="kpis">
      ${kpi('users', 'Active members', fmt.num(d.members.active), `${d.members.officers} officers · ${d.members.inactive} former`, '', '#/members')}
      ${kpi('calendar', 'Upcoming events', fmt.num(upcoming), `${d.events_by_status.Open || 0} open · ${d.events_by_status.Planning || 0} planning`, '', '#/events')}
      ${kpi('clipboard', 'Average attendance', fmt.num(d.avg_attendance), 'people per event')}
      ${f ? kpi('wallet', 'Budget remaining', fmt.money(f.remaining), `${fmt.money(f.spent)} spent of ${fmt.money(f.budget)}`, '', '#/finance')
        : kpi('lock', 'Finance', '—', 'Your role cannot view financial data', 'muted')}
      ${f ? kpi('clock', 'Expenses pending approval', fmt.num(f.pending_count), f.pending_count ? `${fmt.money(f.pending_sum)} total${can('expense.approve') ? ' — awaiting your approval' : ''}` : 'none', f.pending_count ? 'warn' : '', '#/finance/expenses') : ''}
    </div>

    <form class="card quick-ask" id="quick-ask">
      <span class="qa-ic">${icon('sparkle')}</span>
      <input name="q" placeholder="Quick question about club data, e.g. Which event had the most attendees?" aria-label="Quick question">
      <button class="btn primary">${icon('send')}<span>Ask</span></button>
    </form>

    <div class="grid-2">
      ${f ? `<section class="card"><header class="card-h"><h2>Monthly income & expenses</h2><span class="muted small">Approved expenses only</span></header>
        ${columns(f.monthly.map((m) => ({ label: `${MONTHS[+m.month.slice(5, 7) - 1] || m.month.slice(5)} '${m.month.slice(2, 4)}`, income: m.income, expense: m.expense })),
          [{ key: 'income', name: 'Income', color: 'var(--c2)' }, { key: 'expense', name: 'Expenses', color: 'var(--c1)' }], { format: fmt.money })}</section>` : ''}
      <section class="card"><header class="card-h"><h2>Upcoming events</h2><a href="#/events" class="link">View all</a></header>
        ${d.upcoming.length ? `<ul class="event-list">${d.upcoming.map((e) => `<li><a href="#/events/${e.event_id}">
          <span class="date-chip"><b>${esc(String(e.event_date).slice(8, 10))}</b><small>${esc(monYear(e.event_date))}</small></span>
          <span class="ev-main"><b>${esc(e.event_name)}</b><small>${esc(vi(EVENT_TYPE_VI, e.type))}${e.location ? ' · ' + esc(e.location) : ''} · ${e.attendees} ${e.attendees === 1 ? 'attendee' : 'attendees'}</small></span>
          ${badge(e.status)}</a></li>`).join('')}</ul>` : '<p class="muted">No open events.</p>'}</section>
      ${f ? `<section class="card"><header class="card-h"><h2>Spending by category</h2></header>
        ${hbar(f.spend_by_category.map((x) => ({ label: vi(CATEGORY_VI, x.label), value: x.value })), { format: fmt.money })}</section>
        <section class="card"><header class="card-h"><h2>Income sources</h2></header>
        ${hbar(f.income_by_source.map((x) => ({ label: vi(SOURCE_VI, x.label), value: x.value })), { format: fmt.money, color: 'var(--c2)' })}</section>` : ''}
      <section class="card"><header class="card-h"><h2>Events by type</h2></header>
        ${hbar(d.events_by_type.map((x) => ({ label: vi(EVENT_TYPE_VI, x.label), value: x.value })), { color: 'var(--c3)' })}</section>
      <section class="card"><header class="card-h"><h2>Top attendees</h2><a href="#/reports" class="link">Attendance report</a></header>
        ${hbar(d.top_attendees, { color: 'var(--c4)', format: (v) => `${v} ${v === 1 ? 'event' : 'events'}` })}</section>
    </div>`;

  view.querySelector('#quick-ask').addEventListener('submit', (e) => {
    e.preventDefault();
    const q = e.target.q.value.trim();
    if (!q) return e.target.q.focus();
    state.pendingQuestion = q;
    go('ask');
  });
}
