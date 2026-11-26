// ClubQuery — giao diện hỏi đáp Text-to-SQL, gọi API /api/*
const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const DEFAULT_MODEL = 'Qwen2.5-Coder';  // model mặc định của demo (chạy Ollama trên máy)
const STATUS = {
  EXECUTED: ['Đã thực thi', 'good'],
  FAILED_GENERATION: ['Không sinh được SQL', 'warning'],
  EXEC_ERROR: ['Lỗi thực thi', 'warning'],
  TIMEOUT: ['Quá thời gian', 'warning'],
};

let devQuestions = [];

async function api(path, body) {
  const opts = body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {};
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch {}
    throw new Error(msg);
  }
  return res.json();
}

// ---------- form hỏi ----------
async function start() {
  const models = await api('/api/models');
  devQuestions = await api('/api/dev-questions');

  $('#model').innerHTML = models.map((m) => `<option value="${m.id}">${esc(m.name)} (${esc(m.provider)})</option>`).join('');
  const defModel = models.find((m) => m.name === DEFAULT_MODEL);
  if (defModel) $('#model').value = defModel.id;

  $('#devq').innerHTML = '<option value="">— tự nhập câu hỏi —</option>' + devQuestions.map((q) =>
    `<option value="${q.id}">#${q.id} [${q.difficulty}] ${esc(q.question.slice(0, 110))}</option>`).join('');
  onDevqChange();
}

// chọn câu mẫu → ẩn ô gõ câu hỏi, hiện ô "Dùng evidence của câu mẫu" và xem trước câu hỏi + evidence
function onDevqChange() {
  const q = devQuestions.find((x) => String(x.id) === $('#devq').value);
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
  try { renderResult(await api('/api/ask', body)); }
  catch (err) { $('#result').innerHTML = `<div class="card error">${esc(err.message)}</div>`; }
  finally { btn.disabled = false; btn.textContent = 'Hỏi'; }
});

// ---------- hiển thị kết quả, theo thứ tự các bước của luồng ----------
function statusBadge(status) {
  const [text, color] = STATUS[status] || [status, ''];
  return `<span class="badge ${color}">${esc(text)}</span>`;
}

function correctBadge(isCorrect) {
  if (isCorrect === 1) return '<span class="badge good">✓ Đúng đáp án</span>';
  if (isCorrect === 0) return '<span class="badge critical">✗ Sai đáp án</span>';
  return '';  // câu tự gõ: không có đáp án để so
}

function resultTable(columns, rows) {
  if (!rows.length) return '<p class="muted small">Không có dòng nào.</p>';
  const head = columns.map((c) => `<th>${esc(c)}</th>`).join('');
  const body = rows.map((row) => `<tr>${row.map((v) => `<td>${esc(v)}</td>`).join('')}</tr>`).join('');
  return `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

const collapsible = (title, content) => `<details><summary class="small">${title}</summary><pre>${esc(content)}</pre></details>`;


// ---------- "Bên trong model": giữa "Prompt gửi cho LLM" và "Văn bản thô model trả về" ----------
// dữ liệu do backend/pipeline.py dựng: mỗi bước A–F có đầu vào → đầu ra thật, đối chiếu với server, và văn nói
const pct = (p) => `${(p * 100).toFixed(p >= 0.995 || p < 0.01 ? 1 : 0)}%`;
// hiện ranh giới token: "·" = dấu cách, "↵" = xuống dòng
const showToken = (t) => esc(t).replace(/ /g, '·').replace(/\n/g, '↵');
const num = (v) => (typeof v === 'number' ? v.toLocaleString('en-US') : v);

function factsTable(facts) {
  const rows = Object.entries(facts || {}).filter(([, v]) => v != null && v !== '');
  if (!rows.length) return '';
  return `<table class="facts">${rows.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(num(v))}</td></tr>`).join('')}</table>`;
}

// A. phần Ollama thêm vào (tô màu) + đuôi prompt của mình
function templateView(t) {
  return `<pre class="tpl"><mark>${esc(t.before)}</mark><span class="muted">… (${num(t.prompt_len)} ký tự prompt, đoạn cuối:)</span>
${esc(t.prompt_tail)}<mark>${esc(t.after)}</mark></pre>`;
}

// B. toàn bộ token của prompt, mỗi ô một token, rê chuột xem ID
function tokenChipsView(tokens) {
  const chips = tokens.map(([id, piece, special], i) =>
    `<span class="tok ${special ? 'special' : ''}" title="#${i + 1} · ID ${id}">${showToken(piece)}</span>`).join('');
  const first = tokens.slice(0, 40).map(([id, piece]) => `<tr><td><code>${showToken(piece)}</code></td><td>${id}</td></tr>`).join('');
  return `<div class="toks scroll">${chips}</div>
    <details><summary class="small">Bảng mảnh → ID (40 token đầu)</summary>
      <div class="table-wrap"><table><thead><tr><th>Mảnh văn bản</th><th>Token ID</th></tr></thead><tbody>${first}</tbody></table></div></details>`;
}

// C. vector embedding thật của các token trong câu hỏi
function embedView(rows, dim) {
  const body = rows.map((r) => `<tr><td><code>${showToken(r.piece)}</code></td><td>${r.id}</td>
    <td><code>[${r.head.map((x) => (x >= 0 ? ' ' : '') + x.toFixed(4)).join(', ')}, … ]</code></td><td>${r.norm}</td></tr>`).join('');
  return `<div class="table-wrap"><table><thead><tr><th>Token</th><th>ID</th>
    <th>Vector (${rows[0]?.head.length} / ${num(dim)} số đầu tiên)</th><th>Độ dài ‖v‖</th></tr></thead><tbody>${body}</tbody></table></div>`;
}

// E. từng bước sinh token: token được chọn + 5 ứng viên cao nhất
function decodeView(rows) {
  if (!rows?.length) return '';
  const chips = rows.map((t) => {
    const level = t.prob >= 0.9 ? 'sure' : t.prob >= 0.5 ? 'mid' : 'low';
    const alts = t.top.map((a) => `${a.token.replace(/\n/g, '↵')}  ${pct(a.prob)}`).join('\n');
    return `<span class="tok ${level}" title="Bước ${t.step}: chọn ${pct(t.prob)}\n${esc(alts)}">${showToken(t.token)}</span>`;
  }).join('');
  const body = rows.map((t) => `<tr class="${t.prob < 0.9 ? 'unsure' : ''}"><td>${t.step}</td>
    <td>${t.top.map((a) => `<span class="${a.token === t.token ? 'chosen' : ''}"><code>${showToken(a.token)}</code> ${pct(a.prob)}</span>`).join(' · ')}</td>
    <td><code>${showToken(t.token)}</code></td><td>${t.id ?? ''}</td></tr>`).join('');
  return `<div class="toks">${chips}</div>
    <p class="small muted">Xanh ≥ 90% · Vàng 50–90% · Đỏ &lt; 50%. Rê chuột lên token để xem ứng viên.</p>
    <div class="table-wrap"><table><thead><tr><th>Bước</th><th>Xác suất 5 token cao nhất (in đậm = được chọn)</th>
      <th>Token chọn</th><th>ID</th></tr></thead><tbody>${body}</tbody></table></div>`;
}

function stepView(s) {
  const check = s.check ? `<div class="check ${s.check.ok ? 'ok' : 'bad'}">${s.check.ok ? '✓' : '✗'} ${esc(s.check.text)}</div>` : '';
  return `<li class="step side-server">
    <div class="step-head"><span class="step-no">${s.key}</span><b>${esc(s.title)}</b></div>
    <div class="io">${esc(s.io)}</div>
    <p class="small">${esc(s.explain)}</p>
    ${s.template ? templateView(s.template) : ''}
    ${s.tokens ? tokenChipsView(s.tokens) : ''}
    ${s.embed_rows ? embedView(s.embed_rows, s.embed_dim) : ''}
    ${factsTable(s.facts)}
    ${decodeView(s.decode_rows)}
    ${s.ids ? `<pre class="small">[${s.ids.join(', ')}]</pre>` : ''}
    ${check}
    <div class="small muted">Code: <code>${esc(s.code)}</code></div>
  </li>`;
}

function insideView(inside) {
  if (!inside?.request) return '';
  return `<details class="pipeline" open><summary><b>Bên trong model: từ prompt đến văn bản trả về</b></summary>
    <p class="small muted">App gửi request dưới đây (chỉ có văn bản), rồi bên trong Ollama prompt đi qua các bước A → F.
      Bước A, B, C, F được chạy lại bằng chính file model Ollama dùng và đối chiếu với server (dấu ✓). D chỉ server chạy được,
      E là dữ liệu thật server trả (logprobs).</p>
    <details><summary class="small">Request app gửi cho model server</summary><pre>${esc(inside.request)}</pre></details>
    ${inside.note ? `<p class="small warning-text">${esc(inside.note)}</p>` : ''}
    <ol class="steps">${inside.steps.map(stepView).join('')}</ol></details>`;
}

function extractView(list) {
  if (!list?.length) return '';
  return `<details class="pipeline" open><summary><b>Tách câu SQL khỏi văn bản thô</b> <span class="small muted">(llm.extract_sql — cùng code với script benchmark)</span></summary>
    ${list.map((t, i) => `<div class="small"><b>${i + 1}. ${esc(t.what)}</b></div><pre>${esc(t.text)}</pre>`).join('')}</details>`;
}

function renderResult(r) {
  $('#result').innerHTML = `<div class="card">
    <div class="meta">${statusBadge(r.status)} ${correctBadge(r.is_correct)}
      <span class="muted small">${r.latency_ms} ms${r.row_count != null ? ` · ${r.row_count} dòng` : ''}</span></div>
    <div class="muted"><b>Câu hỏi:</b> ${esc(r.question)}</div>
    ${r.evidence_used ? `<div class="muted small"><b>Evidence đưa vào prompt:</b> ${esc(r.evidence_used)}</div>` : ''}
    ${r.error ? `<p class="error">${esc(r.error)}</p>` : ''}
    ${r.prompt ? collapsible('Prompt gửi cho LLM', r.prompt) : ''}
    ${insideView(r.inside)}
    ${r.llm_output !== null ? collapsible('Văn bản thô model trả về', r.llm_output) : ''}
    ${extractView(r.extract_steps)}
    ${r.sql ? `<div class="small muted"><b>SQL đã chạy</b></div><pre class="sql">${esc(r.sql)}</pre>` : ''}
    ${r.gold_sql ? collapsible('SQL đáp án chuẩn (gold)', r.gold_sql) : ''}
    ${r.status === 'EXECUTED' ? `<h3>Dữ liệu${r.truncated ? ' (hiển thị 1000 dòng đầu)' : ''}</h3>${resultTable(r.columns, r.rows)}` : ''}
    ${r.answer ? `<div class="answer"><div class="answer-label">Trả lời</div><p>${esc(r.answer)}</p>
      <span class="small muted">${r.answer_source === 'llm' ? 'Model diễn giải từ kết quả truy vấn' : 'Tóm tắt tự động từ kết quả truy vấn'}</span></div>` : ''}
  </div>`;
}

start().catch((err) => { $('#result').innerHTML = `<div class="card error">${esc(err.message)}</div>`; });
