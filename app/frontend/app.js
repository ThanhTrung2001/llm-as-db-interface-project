// ClubQuery — giao diện một trang, gọi API /api/*
const $ = (s, el = document) => el.querySelector(s);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const ROLE_NAME = { member: 'Thành viên', board: 'Ban chủ nhiệm', admin: 'Quản trị' };
const CONFIG_NAME = { no_evidence: 'Không evidence', evidence: 'Có evidence', evidence_norm: 'Evidence chuẩn hoá' };
const STATUS = {
  EXECUTED: ['Đã thực thi', 'good'],
  REJECTED_PERMISSION: ['Từ chối: không đủ quyền', 'critical'],
  REJECTED_UNSAFE: ['Từ chối: không an toàn', 'critical'],
  FAILED_GENERATION: ['Không sinh được SQL', 'warning'],
  EXEC_ERROR: ['Lỗi thực thi', 'warning'],
  TIMEOUT: ['Quá thời gian', 'warning'],
};
const TABS = [
  ['ask', 'Hỏi đáp', ['member', 'board', 'admin']],
  ['history', 'Lịch sử', ['member', 'board', 'admin']],
  ['bench', 'Benchmark', ['board', 'admin']],
  ['glossary', 'Từ điển', ['member', 'board', 'admin']],
  ['admin', 'Quản trị', ['admin']],
];

let state = { token: null, user: null, mode: 'replay', devQuestions: [], runs: [], models: [] };
try { state.token = localStorage.getItem('cq_token'); } catch { /* bộ nhớ trình duyệt bị chặn */ }

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...(state.token ? { Authorization: 'Bearer ' + state.token } : {}) },
    body: opts.body && typeof opts.body !== 'string' ? JSON.stringify(opts.body) : opts.body,
  });
  if (res.status === 401 && path !== '/api/login') { logout(); throw new Error('Phiên đăng nhập đã hết'); }
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

function table(cols, rows, { onClick } = {}) {
  if (!rows.length) return '<p class="muted small">Chưa có dữ liệu.</p>';
  const head = cols.map((c) => `<th class="${c.num ? 'num' : ''}">${esc(c.label)}</th>`).join('');
  const body = rows.map((r, i) => `<tr data-i="${i}" class="${onClick ? 'clickable' : ''}">${cols.map((c) =>
    `<td class="${c.num ? 'num' : ''}">${c.html ? c.html(r) : esc(c.get ? c.get(r) : r[c.key])}</td>`).join('')}</tr>`).join('');
  return `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}
function bindRows(container, rows, onClick) {
  container.querySelectorAll('tr[data-i]').forEach((tr) => tr.addEventListener('click', () => onClick(rows[+tr.dataset.i])));
}

// ---------- Đăng nhập ----------
$('#login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  try {
    const r = await api('/api/login', { method: 'POST', body: { username: f.get('username'), password: f.get('password') } });
    state.token = r.token;
    try { localStorage.setItem('cq_token', r.token); } catch {}
    await start();
  } catch (err) { $('#login-error').textContent = err.message; $('#login-error').hidden = false; }
});
$('#logout').addEventListener('click', async () => { try { await api('/api/logout', { method: 'POST' }); } catch {} logout(); });
function logout() {
  state.token = null; state.user = null;
  try { localStorage.removeItem('cq_token'); } catch {}
  $('#app-view').hidden = true; $('#login-view').hidden = false;
}

async function start() {
  try { state.user = await api('/api/me'); } catch { return logout(); }
  $('#login-view').hidden = true; $('#app-view').hidden = false;
  $('#who').textContent = `${state.user.full_name} · ${ROLE_NAME[state.user.role]}`;
  const tabs = TABS.filter((t) => t[2].includes(state.user.role));
  $('#tabs').innerHTML = tabs.map(([id, name]) => `<button data-go="${id}">${esc(name)}</button>`).join('');
  $('#tabs').querySelectorAll('button').forEach((b) => b.addEventListener('click', () => go(b.dataset.go)));
  document.querySelectorAll('.admin-only').forEach((el) => { el.hidden = state.user.role !== 'admin'; });
  [state.devQuestions, state.runs, state.models] = await Promise.all([
    api('/api/dev-questions'), api('/api/benchmark/runs'), api('/api/models')]);
  fillAskForm();
  go('ask');
}

function go(tab) {
  document.querySelectorAll('main > section').forEach((s) => { s.hidden = s.dataset.tab !== tab; });
  $('#tabs').querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.go === tab));
  ({ history: loadHistory, bench: loadBench, glossary: loadGlossary, admin: loadAdmin }[tab] || (() => {}))();
}

// ---------- UC02 Hỏi đáp ----------
function fillAskForm() {
  $('#run').innerHTML = state.runs.map((r) =>
    `<option value="${r.id}">${esc(r.model_name)} · ${esc(CONFIG_NAME[r.config])} — EX ${r.ex}%${r.note?.includes('tạm') ? ' (tạm thời)' : ''}</option>`).join('');
  const def = state.runs.find((r) => r.model_name === 'GPT-3.5-Turbo' && r.config === 'evidence');
  if (def) $('#run').value = def.id;
  $('#model').innerHTML = state.models.filter((m) => m.is_active).map((m) =>
    `<option value="${m.id}">${esc(m.name)} (${esc(m.provider)})</option>`).join('');
  $('#devq').innerHTML = '<option value="">— tự nhập câu hỏi —</option>' + state.devQuestions.map((q) =>
    `<option value="${q.id}">#${q.id} [${q.difficulty}] ${esc(q.question.slice(0, 110))}</option>`).join('');
  setMode('replay');
}

function setMode(mode) {
  state.mode = mode;
  document.querySelectorAll('.seg button').forEach((b) => b.classList.toggle('on', b.dataset.mode === mode));
  const live = mode === 'live';
  $('#run-field').hidden = live; $('#model-field').hidden = !live; $('#live-opts').hidden = !live;
  $('#question-field').hidden = !live || !!$('#devq').value;
  $('#devq').options[0].hidden = !live;
  if (!live && !$('#devq').value) $('#devq').selectedIndex = 1;
  $('#mode-hint').textContent = live
    ? 'Gọi model ngay lúc hỏi. Câu hỏi tiếng Anh cho kết quả ổn định nhất (bộ BIRD bằng tiếng Anh).'
    : 'Dùng SQL model đã sinh trong lần benchmark. Không cần mạng, trả lời tức thì, vẫn qua kiểm tra quyền và thực thi thật.';
  previewDevq();
}
document.querySelectorAll('.seg button').forEach((b) => b.addEventListener('click', () => setMode(b.dataset.mode)));
$('#devq').addEventListener('change', () => { $('#question-field').hidden = state.mode !== 'live' || !!$('#devq').value; previewDevq(); });
function previewDevq() {
  const q = state.devQuestions.find((x) => String(x.id) === $('#devq').value);
  $('#devq-preview').innerHTML = q ? `<b>Câu hỏi:</b> ${esc(q.question)}<br><b>Evidence:</b> ${esc(q.evidence || '—')}` : '';
}

$('#ask-btn').addEventListener('click', async () => {
  const devId = $('#devq').value ? +$('#devq').value : null;
  const body = { mode: state.mode, dev_question_id: devId };
  if (state.mode === 'replay') body.run_id = +$('#run').value;
  else Object.assign(body, { model_id: +$('#model').value, question: $('#question').value.trim(),
    use_evidence: $('#use-evidence').checked, use_glossary: $('#use-glossary').checked });
  const btn = $('#ask-btn');
  btn.disabled = true; btn.textContent = state.mode === 'live' ? 'Đang gọi model…' : 'Đang chạy…';
  try { renderResult(await api('/api/ask', { method: 'POST', body })); }
  catch (err) { $('#result').innerHTML = `<div class="card error">${esc(err.message)}</div>`; }
  finally { btn.disabled = false; btn.textContent = 'Hỏi'; }
});

function renderResult(r) {
  const canExport = r.status === 'EXECUTED' && state.user.role !== 'member';
  const cols = r.columns.map((c, i) => ({ label: c, get: (row) => row[i] }));
  $('#result').innerHTML = `<div class="card">
    <div class="meta">${badge(r.status)} ${correctBadge(r.is_correct)}
      <span class="muted small">${r.latency_ms} ms · ${r.mode === 'replay' ? 'phát lại' : 'trực tiếp'}${r.row_count != null ? ` · ${r.row_count} dòng` : ''}</span></div>
    <div class="muted"><b>Câu hỏi:</b> ${esc(r.question)}</div>
    ${r.answer ? `<div class="answer"><div class="answer-label">Trả lời</div><p>${esc(r.answer)}</p>
      <span class="small muted">${r.answer_source === 'llm' ? 'Model diễn giải từ kết quả truy vấn' : 'Tóm tắt tự động từ kết quả truy vấn'}</span></div>` : ''}
    ${r.error ? `<p class="error">${esc(r.error)}</p>` : ''}
    ${r.status === 'EXECUTED' ? `<h3>Dữ liệu${r.truncated ? ' (hiển thị 1000 dòng đầu)' : ''}</h3>${table(cols, r.rows)}` : ''}
    ${r.sql ? `<details><summary class="small">Xem SQL hệ thống đã chạy</summary><pre>${esc(r.sql)}</pre>
      ${r.glossary_used?.length ? `<p class="small muted">Thuật ngữ áp dụng: ${r.glossary_used.map((t) => `<b>${esc(t.term)}</b> → ${esc(t.definition)}`).join('; ')}</p>` : ''}
      ${r.evidence_used ? `<p class="small muted">Evidence đưa vào prompt: ${esc(r.evidence_used)}</p>` : ''}</details>` : ''}
    ${r.gold_sql ? `<details><summary class="small">SQL đáp án chuẩn (gold)</summary><pre>${esc(r.gold_sql)}</pre></details>` : ''}
    <div class="row">
      <span class="small muted">Câu trả lời này có đúng không?</span>
      <button data-fb="1">👍 Đúng</button><button data-fb="-1">👎 Sai</button>
      ${canExport ? `<a href="#" id="export" class="small">Xuất CSV</a>` : ''}
      <span id="fb-msg" class="small muted"></span>
    </div></div>`;
  $('#result').querySelectorAll('[data-fb]').forEach((b) => b.addEventListener('click', async () => {
    await api('/api/feedback', { method: 'POST', body: { query_log_id: r.log_id, rating: +b.dataset.fb } });
    $('#fb-msg').textContent = 'Đã ghi nhận đánh giá.';
  }));
  if (canExport) $('#export').addEventListener('click', async (e) => {
    e.preventDefault();
    const blob = await (await api(`/api/export/${r.log_id}`)).blob();
    const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: `clubquery_${r.log_id}.csv` });
    a.click(); URL.revokeObjectURL(a.href);
  });
}

// ---------- UC03 Lịch sử ----------
async function loadHistory() {
  const rows = await api('/api/history');
  $('#history-table').innerHTML = table([
    { label: 'Thời gian', key: 'created_at' }, { label: 'Câu hỏi', key: 'question' },
    { label: 'Trả lời', get: (r) => r.answer || r.error || '' }, { label: 'Model', key: 'model_name' }, { label: 'Chế độ', get: (r) => r.mode === 'replay' ? 'Phát lại' : 'Trực tiếp' },
    { label: 'Trạng thái', html: (r) => badge(r.status) + ' ' + correctBadge(r.is_correct) },
    { label: 'ms', key: 'latency_ms', num: true }], rows);
}

// ---------- UC09 Benchmark ----------
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

// ---------- UC06 Từ điển ----------
async function loadGlossary() {
  const rows = await api('/api/glossary');
  const isAdmin = state.user.role === 'admin';
  $('#glossary-table').innerHTML = table([
    { label: 'Thuật ngữ', key: 'term' }, { label: 'Định nghĩa', html: (r) => `<code>${esc(r.definition)}</code>` },
    { label: 'Trạng thái', html: (r) => r.is_active ? '<span class="badge good">Đang bật</span>' : '<span class="badge">Tắt</span>' },
    ...(isAdmin ? [{ label: '', html: (r) => `<button data-toggle="${r.id}" class="small">${r.is_active ? 'Tắt' : 'Bật'}</button>
      <button data-del="${r.id}" class="small">Xoá</button>` }] : [])], rows);
  $('#glossary-table').querySelectorAll('[data-toggle]').forEach((b) => b.addEventListener('click', async () => {
    const t = rows.find((r) => r.id === +b.dataset.toggle);
    await api(`/api/glossary/${t.id}`, { method: 'PUT', body: { term: t.term, definition: t.definition, is_active: !t.is_active } });
    loadGlossary();
  }));
  $('#glossary-table').querySelectorAll('[data-del]').forEach((b) => b.addEventListener('click', async () => {
    if (!confirm('Xoá thuật ngữ này?')) return;
    await api(`/api/glossary/${b.dataset.del}`, { method: 'DELETE' }); loadGlossary();
  }));
}
$('#term-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  try { await api('/api/glossary', { method: 'POST', body: { term: f.get('term'), definition: f.get('definition') } }); e.target.reset(); loadGlossary(); }
  catch (err) { alert(err.message); }
});

// ---------- Quản trị ----------
async function loadAdmin() {
  const status = $('#log-filter').value;
  const [logs, models, users] = await Promise.all([
    api('/api/logs' + (status ? `?status=${status}` : '')), api('/api/models'), api('/api/users')]);
  if ($('#log-filter').options.length === 1)
    $('#log-filter').innerHTML += Object.keys(STATUS).map((s) => `<option value="${s}">${esc(STATUS[s][0])}</option>`).join('');
  $('#log-stats').innerHTML = logs.stats.map((s) => `${badge(s.status)} <span class="small muted">${s.n} lần · TB ${s.avg_ms} ms</span>`).join(' ');
  $('#logs-table').innerHTML = table([
    { label: '#', key: 'id', num: true }, { label: 'Người dùng', key: 'username' }, { label: 'Câu hỏi', key: 'question' },
    { label: 'Model', key: 'model_name' }, { label: 'Trạng thái', html: (r) => badge(r.status) + ' ' + correctBadge(r.is_correct) },
    { label: 'Lỗi', key: 'error' }, { label: 'ms', key: 'latency_ms', num: true }, { label: 'Lúc', key: 'created_at' }], logs.rows);

  $('#models-table').innerHTML = table([
    { label: 'Tên', key: 'name' }, { label: 'Nhà cung cấp', key: 'provider' },
    { label: 'Model tag', html: (r) => `<input data-tag="${r.id}" value="${esc(r.model_tag)}">` },
    { label: 'Base URL', html: (r) => `<input data-url="${r.id}" value="${esc(r.base_url || '')}">` },
    { label: 'Bật', html: (r) => `<input type="checkbox" data-active="${r.id}" ${r.is_active ? 'checked' : ''}>` },
    { label: '', html: (r) => `<button data-save="${r.id}">Lưu</button>` }], models);
  $('#models-table').querySelectorAll('[data-save]').forEach((b) => b.addEventListener('click', async () => {
    const id = b.dataset.save;
    await api(`/api/models/${id}`, { method: 'PUT', body: { model_tag: $(`[data-tag="${id}"]`).value,
      base_url: $(`[data-url="${id}"]`).value, is_active: $(`[data-active="${id}"]`).checked } });
    state.models = await api('/api/models'); fillAskForm(); b.textContent = 'Đã lưu';
  }));

  $('#users-table').innerHTML = table([
    { label: 'Tên đăng nhập', key: 'username' }, { label: 'Họ tên', key: 'full_name' },
    { label: 'Vai trò', html: (r) => `<select data-role="${r.id}">${Object.entries(ROLE_NAME).map(([k, v]) =>
      `<option value="${k}" ${k === r.role ? 'selected' : ''}>${v}</option>`).join('')}</select>` },
    { label: 'Hoạt động', html: (r) => `<input type="checkbox" data-uactive="${r.id}" ${r.is_active ? 'checked' : ''}>` },
    { label: '', html: (r) => `<button data-usave="${r.id}">Lưu</button>` }], users);
  $('#users-table').querySelectorAll('[data-usave]').forEach((b) => b.addEventListener('click', async () => {
    const u = users.find((x) => x.id === +b.dataset.usave);
    try {
      await api(`/api/users/${u.id}`, { method: 'PUT', body: { username: u.username, full_name: u.full_name,
        role: $(`[data-role="${u.id}"]`).value, is_active: $(`[data-uactive="${u.id}"]`).checked } });
      b.textContent = 'Đã lưu';
    } catch (err) { alert(err.message); }
  }));
}
$('#log-filter').addEventListener('change', loadAdmin);
$('#user-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = Object.fromEntries(new FormData(e.target));
  try { await api('/api/users', { method: 'POST', body: f }); e.target.reset(); loadAdmin(); }
  catch (err) { alert(err.message); }
});
$('#bench-import').addEventListener('click', async () => {
  const file = $('#bench-file').files[0];
  if (!file) return;
  try {
    const r = await api('/api/benchmark/import', { method: 'POST', body: await file.text() });
    $('#bench-msg').textContent = `Đã nhập ${r.runs} lượt benchmark.`;
    state.runs = await api('/api/benchmark/runs'); fillAskForm();
  } catch (err) { $('#bench-msg').textContent = 'Lỗi: ' + err.message; }
});

// khởi động
if (state.token) start(); else $('#login-view').hidden = false;
