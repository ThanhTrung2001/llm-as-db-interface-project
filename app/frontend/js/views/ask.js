// UC02 Ask AI — natural-language questions over club data, with optional external knowledge (BIRD "evidence")
import { $, $$, api, badge, can, esc, fmt, h, hbar, icon, modal, state, toast, toastError } from '../core.js';

const SUGGEST = [
  ['Members', null, ['How many active members does the club have?', 'List the full names and positions of the officers.', 'Which major has the most members?']],
  ['Events', null, ['How many meetings were held in 2020?', 'Which event had the most attendees?', 'How many events are there of each type?']],
  ['Finance', 'finance.read', ['How much has been spent in each budget category?', 'What is the total amount of dues collected?', 'Which event has the most remaining budget?']],
  ['Contacts', 'pii.read', ['What are the email addresses of the officers?']],
];
const DIFF = { simple: 'good', moderate: 'warn', challenging: 'bad' };
const isNum = (v) => typeof v === 'number';

// Results survive navigating away and back within the session
state.askResults = state.askResults || [];

function visual(r) {
  if (r.status !== 'EXECUTED' || r.rows.length < 2 || r.rows.length > 25 || r.columns.length !== 2) return '';
  const [a, b] = [0, 1].map((i) => r.rows.every((row) => isNum(row[i]) || row[i] == null));
  if (a === b) return '';
  const [li, vi] = b ? [0, 1] : [1, 0];
  return `<div class="viz">${hbar(r.rows.map((row) => ({ label: String(row[li] ?? '(empty)'), value: row[vi] })), { format: (v) => fmt.num(v) })}</div>`;
}

function resultCard(r) {
  const chart = visual(r);
  const el = h(`<article class="card answer-card">
    <div class="q-line">${icon('chat')}<p>${esc(r.question)}</p></div>
    <div class="meta">${badge(r.status)}<span>${icon('cpu')}${esc(r.model_name || '')}</span><span>${icon('clock')}${fmt.num(r.latency_ms)} ms</span>
      ${r.row_count != null ? `<span>${icon('database')}${fmt.num(r.row_count)} ${r.row_count === 1 ? "row" : "rows"}</span>` : ''}
      ${r.sample_id ? `<span class="badge info">BIRD sample #${r.sample_id}</span>` : ''}</div>
    ${r.evidence || r.glossary_used?.length ? `<div class="terms">${icon('book')}Knowledge added to the prompt:
      ${r.evidence ? '<span class="badge accent">external knowledge</span>' : ''}
      ${(r.glossary_used || []).map((t) => `<span class="badge info" title="${esc(t.definition)}">${esc(t.term)}</span>`).join(' ')}</div>` : ''}
    ${r.answer ? `<div class="answer"><p>${esc(r.answer)}</p><small>${r.answer_source === 'llm' ? 'Summarised by the model from the query result' : 'Generated automatically from the query result'}</small></div>` : ''}
    ${r.error ? `<div class="alert ${r.status === 'REJECTED_PERMISSION' || r.status === 'REJECTED_UNSAFE' ? 'bad' : 'warn'}">${icon(r.status === 'REJECTED_PERMISSION' ? 'lock' : 'alert')}<div><b>${esc(r.status === 'REJECTED_PERMISSION' ? 'This question needs data your role cannot see' : 'Could not answer')}</b><p>${esc(r.error)}</p></div></div>` : ''}
    ${chart}
    ${r.status === 'EXECUTED' && r.rows.length ? `<details class="data" ${!chart && r.rows.length <= 12 && r.columns.length > 1 ? 'open' : ''}><summary>Data table${r.truncated ? ' (first 1,000 rows)' : ''}</summary>
      <div class="table-wrap"><table><thead><tr>${r.columns.map((c) => `<th>${esc(c)}</th>`).join('')}</tr></thead>
      <tbody>${r.rows.slice(0, 200).map((row) => `<tr>${row.map((v) => `<td class="${isNum(v) ? 'num' : ''}">${esc(v == null ? '—' : isNum(v) ? fmt.num(v) : v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
      ${r.rows.length > 200 ? '<p class="small muted">Showing the first 200 rows — download the CSV for everything.</p>' : ''}</details>` : ''}
    ${r.knowledge ? `<details class="sql"><summary>${icon('book')}External knowledge sent to the model</summary><pre>-- External Knowledge: ${esc(r.knowledge)}</pre></details>` : ''}
    ${r.sql ? `<details class="sql"><summary>${icon('code')}SQL executed</summary><pre>${esc(r.sql)}</pre></details>` : ''}
    <footer class="answer-actions">
      ${r.log_id ? `<span class="muted small">Was this answer correct?</span>
      <button class="btn sm ghost" data-fb="1" aria-pressed="${r.rating === 1}">${icon('thumbUp')}Correct</button>
      <button class="btn sm ghost" data-fb="-1" aria-pressed="${r.rating === -1}">${icon('thumbDown')}Wrong</button>` : ''}
      <span class="spacer"></span>
      ${r.status === 'EXECUTED' ? `<button class="btn sm" data-export>${icon('download')}CSV</button>` : ''}
      <button class="btn sm" data-again>${icon('refresh')}Ask again</button>
    </footer></article>`);
  $$('[data-fb]', el).forEach((b) => b.addEventListener('click', async () => {
    try {
      await api('/api/feedback', { method: 'POST', body: { query_log_id: r.log_id, rating: +b.dataset.fb } });
      r.rating = +b.dataset.fb;
      $$('[data-fb]', el).forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
      toast('Thanks — feedback recorded.');
    } catch (err) { toastError(err); }
  }));
  $('[data-export]', el)?.addEventListener('click', async () => {
    try {
      const blob = await (await api(`/api/export/${r.log_id}`)).blob();
      const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: `clubquery_${r.log_id}.csv` });
      a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } catch (err) { toastError(err); }
  });
  $('[data-again]', el).addEventListener('click', () => el.dispatchEvent(new CustomEvent('again', { bubbles: true, detail: r })));
  return el;
}

// Picker for the 158 BIRD dev questions on student_club (each with its evidence)
function pickSample(samples) {
  let level = '', q = '';
  const body = h(`<div class="samples">
    <p class="small muted">Questions from the BIRD dev set for the <code>student_club</code> database (Li et al., NeurIPS 2023). Picking one fills the question and its evidence as external knowledge.</p>
    <div class="sample-tools"><label class="search">${icon('search')}<input type="search" placeholder="Search questions or evidence…" aria-label="Search sample questions"></label>
      <div class="seg" role="tablist">${[['', 'All'], ['simple', 'Simple'], ['moderate', 'Moderate'], ['challenging', 'Challenging']].map(([k, t]) => `<button type="button" data-l="${k}" class="${k ? '' : 'on'}">${t}</button>`).join('')}</div></div>
    <div class="sample-list" role="listbox"></div></div>`);
  const list = $('.sample-list', body);
  const render = () => {
    const view = samples.filter((s) => (!level || s.difficulty === level) && (!q || `${s.id} ${s.question} ${s.evidence || ''}`.toLowerCase().includes(q)));
    list.innerHTML = view.length ? view.map((s) => `<button type="button" class="sample" data-id="${s.id}" role="option">
      <span class="sample-head"><b>#${s.id}</b><span class="badge ${DIFF[s.difficulty]}">${s.difficulty}</span>${s.evidence ? '' : '<span class="badge muted">no evidence</span>'}</span>
      <span class="sample-q">${esc(s.question)}</span>
      ${s.evidence ? `<span class="sample-e">${icon('book')}${esc(s.evidence)}</span>` : ''}</button>`).join('')
      : `<div class="empty">${icon('search')}<p>No matching questions.</p></div>`;
  };
  $('input', body).addEventListener('input', (e) => { q = e.target.value.trim().toLowerCase(); render(); });
  $$('[data-l]', body).forEach((b) => b.addEventListener('click', () => {
    level = b.dataset.l; $$('[data-l]', body).forEach((x) => x.classList.toggle('on', x === b)); render();
  }));
  render();
  const p = modal({ title: `BIRD sample questions (${samples.length})`, body, size: 'lg' });
  return new Promise((resolve) => {
    list.addEventListener('click', (e) => {
      const b = e.target.closest('[data-id]');
      if (!b) return;
      resolve(samples.find((s) => s.id === +b.dataset.id));
      body.closest('.modal-backdrop')._close(null);
    });
    p.then(() => resolve(null));
  });
}

export default async function ask({ view, setHeader }) {
  setHeader('Ask in plain English — the system writes the SQL, checks your permissions and answers.');
  const [models, recent, samples] = await Promise.all([api('/api/models'), api('/api/history'), api('/api/sample-questions')]);
  const active = models.filter((m) => m.is_active !== 0);
  const hidden = [!can('finance.read') && 'budgets, expenses and income', !can('pii.read') && 'member email addresses and phone numbers'].filter(Boolean);
  let sample = null;  // selected BIRD sample question

  view.innerHTML = `<div class="ask-layout">
    <div class="ask-main">
      <form class="card ask-box" id="ask-form">
        <div id="sample-chip" hidden></div>
        <textarea id="question" rows="3" placeholder="e.g. How many members attended the March meeting?" aria-label="Question"></textarea>
        <div class="knowledge">
          <label for="evidence">${icon('book')}External knowledge <span class="muted">(optional)</span></label>
          <textarea id="evidence" rows="2" placeholder="Hints that help the model map your words to the data, e.g. full name refers to first_name, last_name; 'approved' refers to approved = 'true'"></textarea>
        </div>
        <div class="ask-bar">
          <label class="model-pick">${icon('cpu')}<select id="model" aria-label="Model">${active.map((m) => `<option value="${m.id}">${esc(m.name)}</option>`).join('')}</select></label>
          <button type="button" class="btn sm ghost" id="browse">${icon('book')}BIRD sample questions <b class="count">${samples.length}</b></button>
          <span class="muted small hide-sm">Enter to send · Shift+Enter for a new line</span>
          <button class="btn primary" id="ask-btn">${icon('send')}<span>Ask</span></button>
        </div>
      </form>
      <div class="suggest">${SUGGEST.filter(([, p]) => !p || can(p)).map(([g, , qs]) => `<div><p class="nav-group">${esc(g)}</p>${qs.map((q) => `<button class="chip" data-q="${esc(q)}">${esc(q)}</button>`).join('')}</div>`).join('')}</div>
      <div id="results"></div>
    </div>
    <aside class="ask-side">
      <section class="card"><header class="card-h"><h2>${icon('shield')}Your data access</h2></header>
        ${hidden.length ? `<p class="small">As <b>${esc(state.user.role_name)}</b> you cannot see: ${esc(hidden.join('; '))}. Questions that need this data are rejected, even if the AI writes the SQL.</p>`
          : '<p class="small">You can read all club data (read-only).</p>'}
        <p class="small muted">Only single SELECT queries run, with a 10-second limit and at most 1,000 rows.</p></section>
      <section class="card"><header class="card-h"><h2>Recent questions</h2><a href="#/history" class="link">All</a></header>
        ${recent.length ? `<ul class="recent">${recent.slice(0, 8).map((r, i) => `<li><button data-recent="${i}">${badge(r.status, ' ')}<span>${esc(r.question)}</span></button></li>`).join('')}</ul>` : '<p class="muted small">No questions yet.</p>'}</section>
    </aside></div>`;

  const ta = $('#question', view), ev = $('#evidence', view), results = $('#results', view), chip = $('#sample-chip', view);
  const setSample = (s) => {
    sample = s;
    chip.hidden = !s;
    chip.innerHTML = s ? `<span class="badge info">BIRD sample #${s.id} · ${esc(s.difficulty)}</span><button type="button" class="link small" id="clear-sample">Clear</button>` : '';
    $('#clear-sample', chip)?.addEventListener('click', () => { setSample(null); ta.value = ''; ev.value = ''; ta.focus(); });
  };
  const fill = (question, evidence = '', s = null) => { ta.value = question; ev.value = evidence || ''; setSample(s); ta.focus(); };
  ta.addEventListener('input', () => { if (sample && ta.value.trim() !== sample.question) setSample(null); });

  state.askResults.forEach((r) => results.append(resultCard(r)));
  const submit = async (q = ta.value, evidence = ev.value, sid = sample?.id ?? null) => {
    q = q.trim();
    if (q.length < 3) { ta.focus(); return toast('Please enter a question (at least 3 characters).', 'warn'); }
    const btn = $('#ask-btn', view);
    btn.disabled = true;
    const pending = h(`<article class="card answer-card pending"><div class="q-line">${icon('chat')}<p>${esc(q)}</p></div><div class="thinking"><span></span><span></span><span></span> Generating SQL and querying the data…</div></article>`);
    results.prepend(pending);
    try {
      const r = await api('/api/ask', { method: 'POST', body: { question: q, model_id: +$('#model', view).value || null, evidence: evidence.trim() || null, sample_id: sid } });
      state.askResults.unshift(r);
      state.askResults.length = Math.min(state.askResults.length, 20);
      pending.replaceWith(resultCard(r));
      fill('', '');
    } catch (err) { pending.remove(); toastError(err); }
    finally { btn.disabled = false; ta.focus(); }
  };
  $('#ask-form', view).addEventListener('submit', (e) => { e.preventDefault(); submit(); });
  ta.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } });
  $$('[data-q]', view).forEach((b) => b.addEventListener('click', () => fill(b.dataset.q)));
  $$('[data-recent]', view).forEach((b) => b.addEventListener('click', () => {
    const r = recent[+b.dataset.recent];
    fill(r.question, r.evidence, r.sample_id ? samples.find((s) => s.id === r.sample_id) : null);
  }));
  $('#browse', view).addEventListener('click', async () => {
    const s = await pickSample(samples);
    if (s) fill(s.question, s.evidence, s);
  });
  results.addEventListener('again', (e) => {  // listener on a fresh element, not on #view (reused across pages)
    const r = e.detail;
    submit(r.question, r.evidence || '', r.sample_id ?? null);
  });
  if (state.pendingQuestion) {
    const p = state.pendingQuestion; state.pendingQuestion = null;
    if (typeof p === 'string') submit(p, '', null);
    else submit(p.question, p.evidence || '', p.sample_id ?? null);
  } else ta.focus();
}
