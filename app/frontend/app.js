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

function renderResult(r) {
  $('#result').innerHTML = `<div class="card">
    <div class="meta">${statusBadge(r.status)} ${correctBadge(r.is_correct)}
      <span class="muted small">${r.latency_ms} ms${r.row_count != null ? ` · ${r.row_count} dòng` : ''}</span></div>
    <div class="muted"><b>Câu hỏi:</b> ${esc(r.question)}</div>
    ${r.evidence_used ? `<div class="muted small"><b>Evidence đưa vào prompt:</b> ${esc(r.evidence_used)}</div>` : ''}
    ${r.error ? `<p class="error">${esc(r.error)}</p>` : ''}
    ${r.prompt ? collapsible('Prompt gửi cho LLM', r.prompt) : ''}
    ${r.llm_output !== null ? collapsible('Văn bản thô model trả về', r.llm_output) : ''}
    ${r.sql ? collapsible('SQL đã chạy', r.sql) : ''}
    ${r.gold_sql ? collapsible('SQL đáp án chuẩn (gold)', r.gold_sql) : ''}
    ${r.status === 'EXECUTED' ? `<h3>Dữ liệu${r.truncated ? ' (hiển thị 1000 dòng đầu)' : ''}</h3>${resultTable(r.columns, r.rows)}` : ''}
    ${r.answer ? `<div class="answer"><div class="answer-label">Trả lời</div><p>${esc(r.answer)}</p>
      <span class="small muted">${r.answer_source === 'llm' ? 'Model diễn giải từ kết quả truy vấn' : 'Tóm tắt tự động từ kết quả truy vấn'}</span></div>` : ''}
  </div>`;
}

start().catch((err) => { $('#result').innerHTML = `<div class="card error">${esc(err.message)}</div>`; });
