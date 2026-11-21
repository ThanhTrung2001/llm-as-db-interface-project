// ClubQuery — giao diện một trang, gọi API /api/*
const $ = (s, el = document) => el.querySelector(s);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const CONFIG_NAME = { no_evidence: 'Không evidence', evidence: 'Có evidence', evidence_norm: 'Evidence chuẩn hoá' };
const STATUS = {
  EXECUTED: ['Đã thực thi', 'good'],
  FAILED_GENERATION: ['Không sinh được SQL', 'warning'],
  EXEC_ERROR: ['Lỗi thực thi', 'warning'],
  TIMEOUT: ['Quá thời gian', 'warning'],
};

let state = { devQuestions: [], models: [] };

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { 'Content-Type': 'application/json' },
    body: opts.body && typeof opts.body !== 'string' ? JSON.stringify(opts.body) : opts.body,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch {}
    throw new Error(msg);
  }
  return (res.headers.get('content-type') || '').includes('json') ? res.json() : res;
}

const badge = (status) => { const [t, c] = STATUS[status] || [status, '']; return `<span class="badge ${c}">${esc(t)}</span>`; };
const correctBadge = (v) => v === 1 ? '<span class="badge good">✓ Đúng đáp án</span>'
  : v === 0 ? '<span class="badge critical">✗ Sai đáp án</span>' : '';

function table(cols, rows) {
  if (!rows.length) return '<p class="muted small">Chưa có dữ liệu.</p>';
  const head = cols.map((c) => `<th class="${c.num ? 'num' : ''}">${esc(c.label)}</th>`).join('');
  const body = rows.map((r) => `<tr>${cols.map((c) =>
    `<td class="${c.num ? 'num' : ''}">${c.html ? c.html(r) : esc(c.get ? c.get(r) : r[c.key])}</td>`).join('')}</tr>`).join('');
  return `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

async function start() {
  $('#tabs').querySelectorAll('button').forEach((b) => b.addEventListener('click', () => go(b.dataset.go)));
  [state.devQuestions, state.models] = await Promise.all([api('/api/dev-questions'), api('/api/models')]);
  fillAskForm();
  go('ask');
}

function go(tab) {
  document.querySelectorAll('main > section').forEach((s) => { s.hidden = s.dataset.tab !== tab; });
  $('#tabs').querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.go === tab));
  if (tab === 'bench') loadBench();
}

// ---------- Hỏi đáp ----------
function fillAskForm() {
  const DEFAULT_MODEL = 'Qwen2.5-Coder';  // model mặc định của demo (EX benchmark tốt nhất, chạy Ollama trên máy)
  $('#model').innerHTML = state.models.filter((m) => m.is_active).map((m) =>
    `<option value="${m.id}">${esc(m.name)} (${esc(m.provider)})</option>`).join('');
  const defModel = state.models.find((m) => m.is_active && m.name === DEFAULT_MODEL);
  if (defModel) $('#model').value = defModel.id;
  $('#devq').innerHTML = '<option value="">— tự nhập câu hỏi —</option>' + state.devQuestions.map((q) =>
    `<option value="${q.id}">#${q.id} [${q.difficulty}] ${esc(q.question.slice(0, 110))}</option>`).join('');
  onDevqChange();
}

// chọn câu mẫu → ẩn ô gõ câu hỏi, hiện ô "Dùng evidence của câu mẫu" và xem trước câu hỏi + evidence
function onDevqChange() {
  const q = state.devQuestions.find((x) => String(x.id) === $('#devq').value);
  $('#question-field').hidden = !!q;
  $('#evidence-opt').hidden = !q;
  $('#devq-preview').innerHTML = q ? `<b>Câu hỏi:</b> ${esc(q.question)}<br><b>Evidence:</b> ${esc(q.evidence || '—')}` : '';
}
$('#devq').addEventListener('change', onDevqChange);

// bấm "Hỏi" → POST /api/ask → service.ask()
$('#ask-btn').addEventListener('click', async () => {
  const body = {
    model_id: +$('#model').value,
    dev_question_id: $('#devq').value ? +$('#devq').value : null,
    question: $('#question').value.trim(),
    use_evidence: $('#use-evidence').checked,
  };
  const btn = $('#ask-btn');
  btn.disabled = true; btn.textContent = 'Đang gọi model…';
  try { renderResult(await api('/api/ask', { method: 'POST', body })); }
  catch (err) { $('#result').innerHTML = `<div class="card error">${esc(err.message)}</div>`; }
  finally { btn.disabled = false; btn.textContent = 'Hỏi'; }
});

function renderResult(r) {
  const cols = r.columns.map((c, i) => ({ label: c, get: (row) => row[i] }));
  $('#result').innerHTML = `<div class="card">
    <div class="meta">${badge(r.status)} ${correctBadge(r.is_correct)}
      <span class="muted small">${r.latency_ms} ms${r.row_count != null ? ` · ${r.row_count} dòng` : ''}</span></div>
    <div class="muted"><b>Câu hỏi:</b> ${esc(r.question)}</div>
    ${r.error ? `<p class="error">${esc(r.error)}</p>` : ''}
    ${r.prompt ? `<details><summary class="small">Prompt gửi cho LLM</summary><pre>${esc(r.prompt)}</pre></details>` : ''}
    ${r.llm_output !== null ? `<details><summary class="small">Văn bản thô model trả về</summary><pre>${esc(r.llm_output)}</pre></details>` : ''}
    ${r.sql ? `<details><summary class="small">Xem SQL hệ thống đã chạy</summary><pre>${esc(r.sql)}</pre>
      ${r.evidence_used ? `<p class="small muted">Evidence đưa vào prompt: ${esc(r.evidence_used)}</p>` : ''}</details>` : ''}
    ${r.gold_sql ? `<details><summary class="small">SQL đáp án chuẩn (gold)</summary><pre>${esc(r.gold_sql)}</pre></details>` : ''}
    ${r.status === 'EXECUTED' ? `<h3>Dữ liệu${r.truncated ? ' (hiển thị 1000 dòng đầu)' : ''}</h3>${table(cols, r.rows)}` : ''}
    ${r.answer ? `<div class="answer"><div class="answer-label">Trả lời</div><p>${esc(r.answer)}</p>
      <span class="small muted">${r.answer_source === 'llm' ? 'Model diễn giải từ kết quả truy vấn' : 'Tóm tắt tự động từ kết quả truy vấn'}</span></div>` : ''}
  </div>`;
}

// ---------- Benchmark ----------
async function loadBench() {
  const runs = await api('/api/benchmark/summary');
  const models = [...new Set(runs.map((r) => r.model_name))];
  const configs = ['no_evidence', 'evidence', 'evidence_norm'];
  const by = (m, c) => runs.find((r) => r.model_name === m && r.config === c);
  $('#legend').innerHTML = configs.map((c, i) => `<span><i style="background:var(--series-${i + 1})"></i>${CONFIG_NAME[c]}</span>`).join('');
  drawBars(models, configs, by);
  const lv = (r, k) => r.levels[k]?.ex ?? '';
  $('#bench-table').innerHTML = table([
    { label: 'Model', key: 'model_name' }, { label: 'Cấu hình', get: (r) => CONFIG_NAME[r.config] },
    { label: 'Simple', get: (r) => lv(r, 'simple'), num: true }, { label: 'Moderate', get: (r) => lv(r, 'moderate'), num: true },
    { label: 'Challenging', get: (r) => lv(r, 'challenging'), num: true },
    { label: 'student_club', html: (r) => `<b>${r.ex}</b>`, num: true },
    { label: 'Toàn dev (1534)', get: (r) => r.full_dev_ex ?? '—', num: true }, { label: 'Ghi chú', key: 'note' }], runs);
}

function drawBars(models, configs, by) {
  const W = 760, H = 300, m = { t: 22, r: 8, b: 34, l: 36 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const gw = iw / models.length, bw = Math.min(40, (gw - 28) / configs.length);
  const y = (v) => m.t + ih - (v / 100) * ih;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Biểu đồ EX theo model và cấu hình">`;
  s += '<g class="grid axis">' + [0, 25, 50, 75, 100].map((v) =>
    `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`).join('') + '</g>';
  models.forEach((name, gi) => {
    const x0 = m.l + gi * gw + (gw - bw * configs.length) / 2;
    configs.forEach((c, ci) => {
      const r = by(name, c); if (!r) return;
      const x = x0 + ci * bw, top = y(r.ex), h = m.t + ih - top;
      // đầu thanh bo 4px, đáy vuông bám baseline
      const d = `M${x + 1},${m.t + ih} V${top + 4} q0,-4 4,-4 H${x + bw - 5} q4,0 4,4 V${m.t + ih} Z`;
      s += `<g class="mark" data-tip="${esc(`<b>${name}</b><br>${CONFIG_NAME[c]}: <b>${r.ex}%</b>${r.full_dev_ex != null ? `<br>Toàn dev: ${r.full_dev_ex}%` : ''}${r.note?.includes('tạm') ? '<br>(tạm thời)' : ''}`)}">
        <path class="bar" d="${d}" fill="var(--series-${ci + 1})" stroke="var(--surface-1)" stroke-width="2"/>
        <text class="value" x="${x + bw / 2}" y="${top - 5}" text-anchor="middle">${Math.round(r.ex)}</text>
        <rect class="hit" x="${x}" y="${m.t}" width="${bw}" height="${ih}"/></g>`;
      void h;
    });
    s += `<text class="label" x="${m.l + gi * gw + gw / 2}" y="${H - 10}" text-anchor="middle">${esc(name)}</text>`;
  });
  s += `<line class="baseline" x1="${m.l}" x2="${W - m.r}" y1="${m.t + ih}" y2="${m.t + ih}"/></svg>`;
  $('#chart').innerHTML = s;
  const tip = $('#tooltip'), root = $('.viz-root');
  $('#chart').querySelectorAll('g.mark').forEach((g) => {
    g.addEventListener('mousemove', (e) => {
      const b = root.getBoundingClientRect();
      tip.innerHTML = g.dataset.tip; tip.hidden = false;
      tip.style.left = Math.min(e.clientX - b.left + 12, b.width - 180) + 'px';
      tip.style.top = (e.clientY - b.top + 12) + 'px';
    });
    g.addEventListener('mouseleave', () => { tip.hidden = true; });
  });
}


// khởi động
start().catch((err) => { $('#result').innerHTML = `<div class="card error">${esc(err.message)}</div>`; });
