// Tài chính: ngân sách, khoản chi có quy trình duyệt (BR06–BR08), khoản thu
import { $, api, badge, can, CATEGORY_VI, confirmDialog, dataTable, esc, fmt, formModal, h, icon, modal, progress, SOURCE_VI, state, tabs, today, toast, toastError, vi } from '../core.js';
import { refreshBadges } from '../app.js';

const memberOpts = () => state.lookups.members.map((m) => [m.id, m.name]);

async function budgetOptions() {
  const budgets = await api('/api/budgets');
  return budgets.filter((b) => b.event_status !== 'Closed')
    .map((b) => [b.budget_id, `${b.event_name} · ${vi(CATEGORY_VI, b.category)} (${fmt.money(b.remaining)} left)`]);
}

async function expenseForm(x, reload) {
  const opts = await budgetOptions();
  if (x && !opts.some(([id]) => id === x.link_to_budget)) opts.unshift([x.link_to_budget, `${x.event_name} · ${vi(CATEGORY_VI, x.category)}`]);
  return formModal({
    title: x ? 'Edit expense proposal' : 'Propose expense', values: x || { expense_date: today() }, submitLabel: x ? 'Save' : 'Submit proposal',
    fields: [
      { name: 'expense_description', label: 'Description', required: true, span: 2, placeholder: 'e.g. Drinks and pastries' },
      { name: 'link_to_budget', label: 'Budget (event · category)', type: 'select', required: true, span: 2, options: opts, help: 'Only budgets of events that are not closed are listed' },
      { name: 'cost', label: 'Amount ($)', type: 'number', required: true, min: 0.01, step: 0.01 },
      { name: 'expense_date', label: 'Expense date', type: 'date', required: true },
      { name: 'link_to_member', label: 'Paid by', type: 'select', span: 2, options: memberOpts() },
    ],
    onSubmit: async (v) => {
      const r = await api(x ? `/api/expenses/${x.expense_id}` : '/api/expenses', { method: x ? 'PUT' : 'POST', body: v });
      if (r.warning) toast(r.warning, 'warn'); else toast(x ? 'Proposal updated.' : 'Proposal submitted; awaiting approval by the President.');
      reload();
    },
  });
}

async function review(x, approve, reload) {
  if (approve) {
    const ok = await modal({ title: 'Approve expense', size: 'sm', body: `<dl class="kv">
        <dt>Description</dt><dd>${esc(x.expense_description)}</dd><dt>Amount</dt><dd><b>${fmt.money(x.cost)}</b></dd>
        <dt>Budget</dt><dd>${esc(x.event_name)} · ${esc(vi(CATEGORY_VI, x.category))}</dd>
        <dt>Remaining</dt><dd>${fmt.money(x.budget_remaining)} → <b class="${x.cost > x.budget_remaining ? 'text-bad' : ''}">${fmt.money(x.budget_remaining - x.cost)}</b></dd>
        <dt>Proposed by</dt><dd>${esc(x.proposed_by_name || '—')}</dd></dl>
        ${x.cost > x.budget_remaining ? `<div class="alert bad">${icon('alert')}<div><b>Over budget</b><p>The system will not allow approval. The Treasurer must increase the budget first.</p></div></div>` : ''}`,
      actions: [{ label: 'Cancel', value: false }, { label: 'Approve expense', kind: 'primary', icon: 'check', value: true }] });
    if (!ok) return;
    try { await api(`/api/expenses/${x.expense_id}/approve`, { method: 'POST', body: {} }); toast('Expense approved; the budget has been updated.'); }
    catch (err) { return toastError(err); }
  } else {
    const r = await formModal({ title: 'Reject expense', size: 'sm', submitLabel: 'Reject',
      fields: [{ name: 'note', label: 'Reason for rejection', type: 'textarea', required: true, span: 2 }],
      onSubmit: (v) => api(`/api/expenses/${x.expense_id}/reject`, { method: 'POST', body: v }) });
    if (!r) return;
    toast('Expense rejected.');
  }
  refreshBadges();
  reload();
}

async function expensesTab(box, reload) {
  const rows = await api('/api/expenses');
  const pending = rows.filter((r) => r.status === 'PENDING');
  const canApprove = can('expense.approve'), canWrite = can('finance.write');
  box.innerHTML = '';
  if (pending.length) box.append(h(`<div class="alert warn">${icon('clock')}<div><b>${pending.length} ${pending.length === 1 ? 'expense' : 'expenses'} pending approval (${fmt.money(pending.reduce((s, r) => s + r.cost, 0))})</b>
    <p>${canApprove ? 'Review and approve or reject each item below.' : 'The President will approve or reject these items.'}</p></div></div>`));
  const statuses = [['', 'All statuses'], ['PENDING', 'Pending'], ['APPROVED', 'Approved'], ['REJECTED', 'Rejected']];
  const table = dataTable({
    rows, pageSize: 12, searchKeys: ['expense_description', 'event_name', 'category', 'member_name', 'proposed_by_name'],
    filters: `<select id="x-status" aria-label="Filter by status">${statuses.map(([k, t]) => `<option value="${k}">${t}</option>`).join('')}</select>`,
    columns: [
      { key: 'expense_date', label: 'Date', render: (r) => `<span class="nowrap">${fmt.date(r.expense_date)}</span>`, width: '100px' },
      { key: 'expense_description', label: 'Description', render: (r) => `<b>${esc(r.expense_description)}</b><small class="muted block">${esc(r.event_name || '')} · ${esc(vi(CATEGORY_VI, r.category))}</small>` },
      { key: 'cost', label: 'Amount', num: true, render: (r) => `<b>${fmt.money(r.cost)}</b>` },
      { key: 'member_name', label: 'Paid by', render: (r) => esc(r.member_name || '—') },
      { key: 'status', label: 'Status', render: (r) => `${badge(r.status)}${r.review_note ? `<small class="muted block" title="${esc(r.review_note)}">${esc(r.review_note)}</small>` : ''}` },
      { key: 'proposed_by_name', label: 'Proposed / reviewed by', render: (r) => r.proposed_by_name ? `<small>${esc(r.proposed_by_name)}${r.reviewed_by_name ? `<br>→ ${esc(r.reviewed_by_name)}` : ''}</small>` : '<small class="muted">Original data</small>' },
      { label: '', sortable: false, render: (r) => r.status !== 'PENDING' ? '' : `<span class="row-actions">
        ${canApprove ? `<button class="btn sm primary" data-act="approve" data-id="${r.expense_id}">${icon('check')}Approve</button><button class="btn sm danger ghost" data-act="reject" data-id="${r.expense_id}">${icon('x')}Reject</button>` : ''}
        ${canWrite && r.proposed_by === state.user.id ? `<button class="icon-btn" title="Edit" aria-label="Edit" data-act="edit" data-id="${r.expense_id}">${icon('edit')}</button><button class="icon-btn" title="Withdraw proposal" aria-label="Withdraw proposal" data-act="delete" data-id="${r.expense_id}">${icon('trash')}</button>` : ''}</span>` },
    ],
  });
  const card = h('<section class="card"></section>');
  card.append(table);
  box.append(card);
  $('#x-status', table).addEventListener('change', (e) => table.setRows(e.target.value ? rows.filter((r) => r.status === e.target.value) : rows));
  table.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    const x = rows.find((r) => r.expense_id === b.dataset.id);
    if (b.dataset.act === 'approve') return review(x, true, reload);
    if (b.dataset.act === 'reject') return review(x, false, reload);
    if (b.dataset.act === 'edit') return expenseForm(x, reload);
    if (await confirmDialog(`Withdraw proposal "${x.expense_description}"?`, { danger: true, ok: 'Withdraw proposal' })) {
      try { await api(`/api/expenses/${x.expense_id}`, { method: 'DELETE' }); toast('Proposal withdrawn.'); refreshBadges(); reload(); } catch (err) { toastError(err); }
    }
  });
}

export async function budgetForm(b, reload, eventId = null) {
  if (!b) state.lookups = await api('/api/lookups');  // include events created since login
  const L = state.lookups;
  return formModal({
    title: b ? `Edit budget — ${vi(CATEGORY_VI, b.category)}` : 'Create budget', values: b || (eventId ? { link_to_event: eventId } : {}),
    fields: [
      { name: 'link_to_event', label: 'Event', type: 'select', required: true, span: 2, disabled: !!b,
        options: L.events.filter((e) => e.status !== 'Closed' || b).map((e) => [e.id, `${e.name} (${fmt.date(e.date)})`]) },
      { name: 'category', label: 'Category', type: 'select', required: true, options: L.budget_categories.map((c) => [c, vi(CATEGORY_VI, c)]) },
      { name: 'amount', label: 'Amount ($)', type: 'number', required: true, min: 1, help: b ? `Cannot be less than the amount spent (${fmt.money(b.spent)})` : '' },
    ],
    onSubmit: async (v) => {
      await api(b ? `/api/budgets/${b.budget_id}` : '/api/budgets', { method: b ? 'PUT' : 'POST', body: b ? { ...v, link_to_event: b.link_to_event, category: b.category } : v });
      toast(b ? 'Budget updated.' : 'Budget created.');
      reload();
    },
  });
}

async function budgetsTab(box, reload) {
  const rows = await api('/api/budgets');
  const canWrite = can('finance.write');
  const table = dataTable({
    rows, pageSize: 12, searchKeys: ['event_name', 'category'],
    columns: [
      { key: 'event_name', label: 'Event', render: (r) => `<b>${esc(r.event_name)}</b><small class="muted block">${fmt.date(r.event_date)}</small>` },
      { key: 'category', label: 'Category', render: (r) => esc(vi(CATEGORY_VI, r.category)) },
      { key: 'event_status', label: 'Event status', render: (r) => badge(r.event_status) },
      { key: 'amount', label: 'Budget', num: true, render: (r) => fmt.money(r.amount) },
      { key: 'spent', label: 'Spent', num: true, render: (r) => fmt.money(r.spent) },
      { key: 'remaining', label: 'Remaining', num: true, render: (r) => `<b class="${r.remaining < 0 ? 'text-bad' : ''}">${fmt.money(r.remaining)}</b>${r.pending ? `<small class="muted block">${fmt.money(r.pending)} pending</small>` : ''}` },
      { label: 'Usage', sortable: false, render: (r) => progress(r.spent, r.amount) },
      ...(canWrite ? [{ label: '', sortable: false, render: (r) => `<span class="row-actions"><button class="icon-btn" title="Edit" aria-label="Edit" data-act="edit" data-id="${r.budget_id}">${icon('edit')}</button>${r.n_expenses ? '' : `<button class="icon-btn" title="Delete" aria-label="Delete" data-act="delete" data-id="${r.budget_id}">${icon('trash')}</button>`}</span>` }] : []),
    ],
  });
  box.innerHTML = '';
  const card = h('<section class="card"></section>');
  card.append(table);
  box.append(card);
  table.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    const x = rows.find((r) => r.budget_id === b.dataset.id);
    if (b.dataset.act === 'edit') return budgetForm(x, reload);
    if (await confirmDialog(`Delete the ${vi(CATEGORY_VI, x.category)} budget of "${x.event_name}"?`, { danger: true, ok: 'Delete' })) {
      try { await api(`/api/budgets/${x.budget_id}`, { method: 'DELETE' }); toast('Budget deleted.'); reload(); } catch (err) { toastError(err); }
    }
  });
}

function incomeForm(x, reload) {
  return formModal({
    title: x ? 'Edit income' : 'Record income', values: x || { date_received: today(), source: 'Dues' },
    fields: [
      { name: 'source', label: 'Source', type: 'select', required: true, options: state.lookups.income_sources.map((s) => [s, vi(SOURCE_VI, s)]) },
      { name: 'amount', label: 'Amount ($)', type: 'number', required: true, min: 1 },
      { name: 'date_received', label: 'Date received', type: 'date', required: true },
      { name: 'link_to_member', label: 'Paid by member', type: 'select', options: memberOpts() },
      { name: 'notes', label: 'Notes', type: 'textarea', span: 2 },
    ],
    onSubmit: async (v) => {
      await api(x ? `/api/incomes/${x.income_id}` : '/api/incomes', { method: x ? 'PUT' : 'POST', body: v });
      toast(x ? 'Income updated.' : 'Income recorded.');
      reload();
    },
  });
}

async function incomesTab(box, reload) {
  const rows = await api('/api/incomes');
  const canWrite = can('finance.write');
  const table = dataTable({
    rows, pageSize: 12, searchKeys: ['source', 'member_name', 'notes'],
    columns: [
      { key: 'date_received', label: 'Date', render: (r) => fmt.date(r.date_received), width: '110px' },
      { key: 'source', label: 'Source', render: (r) => esc(vi(SOURCE_VI, r.source)) },
      { key: 'amount', label: 'Amount', num: true, render: (r) => `<b>${fmt.money(r.amount)}</b>` },
      { key: 'member_name', label: 'Member', render: (r) => esc(r.member_name || '—') },
      { key: 'notes', label: 'Notes', render: (r) => esc(r.notes || ''), cls: 'clamp' },
      ...(canWrite ? [{ label: '', sortable: false, render: (r) => `<span class="row-actions"><button class="icon-btn" title="Edit" aria-label="Edit" data-act="edit" data-id="${r.income_id}">${icon('edit')}</button><button class="icon-btn" title="Delete" aria-label="Delete" data-act="delete" data-id="${r.income_id}">${icon('trash')}</button></span>` }] : []),
    ],
  });
  box.innerHTML = '';
  const card = h('<section class="card"></section>');
  card.append(table);
  box.append(card);
  table.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    const x = rows.find((r) => r.income_id === b.dataset.id);
    if (b.dataset.act === 'edit') return incomeForm(x, reload);
    if (await confirmDialog(`Delete ${vi(SOURCE_VI, x.source)} income of ${fmt.money(x.amount)}?`, { danger: true, ok: 'Delete' })) {
      try { await api(`/api/incomes/${x.income_id}`, { method: 'DELETE' }); toast('Income deleted.'); reload(); } catch (err) { toastError(err); }
    }
  });
}

const TABS = { expenses: ['Expenses', expensesTab], budgets: ['Budgets', budgetsTab], incomes: ['Income', incomesTab] };

export default async function finance({ view, setHeader, params }) {
  let tab = TABS[params[0]] ? params[0] : 'expenses';
  const kpiBox = h('<div class="kpis compact"></div>');
  const body = h('<div></div>');
  const header = () => {
    const actions = [];
    if (can('finance.write')) {
      if (tab === 'expenses') actions.push({ label: 'Propose expense', icon: 'plus', onClick: () => expenseForm(null, reload) });
      if (tab === 'budgets') actions.push({ label: 'Create budget', icon: 'plus', onClick: () => budgetForm(null, reload) });
      if (tab === 'incomes') actions.push({ label: 'Record income', icon: 'plus', onClick: () => incomeForm(null, reload) });
    }
    setHeader(can('finance.write') ? 'The Treasurer sets budgets, proposes expenses and records income; the President approves expenses.'
      : can('expense.approve') ? 'Approve expenses proposed by the Treasurer. Budgets update automatically on approval.' : 'View the club’s finances (read-only).', actions);
  };
  async function reload() {
    const d = (await api('/api/dashboard')).finance;
    kpiBox.innerHTML = [['Total budget', fmt.money(d.budget)], ['Spent', fmt.money(d.spent)], ['Remaining', fmt.money(d.remaining)],
      ['Total income', fmt.money(d.income)], ['Pending approval', `${d.pending_count} ${d.pending_count === 1 ? 'item' : 'items'} · ${fmt.money(d.pending_sum)}`]]
      .map(([l, v], i) => `<div class="kpi ${i === 4 && d.pending_count ? 'warn' : ''}"><div><p>${l}</p><b>${v}</b></div></div>`).join('');
    await TABS[tab][1](body, reload);
  }
  view.innerHTML = '';
  view.append(kpiBox, tabs(Object.entries(TABS).map(([k, [t]]) => [k, t]), tab, (k) => {
    tab = k; history.replaceState(null, '', `#/finance/${k}`); header(); body.innerHTML = ''; reload().catch(toastError);
  }), body);
  header();
  await reload();
}
