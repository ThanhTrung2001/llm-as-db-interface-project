"""Nghiệp vụ UC02 Hỏi đáp: tra từ điển → sinh SQL → kiểm tra → thực thi chỉ đọc theo quyền → diễn giải → ghi log."""
import time
from typing import Optional

from evidence_norm import normalize_pseudo_sql  # Gap 3: chuẩn hoá hàm giả (DIVIDE, YEAR…) trong tri thức

from . import answer, config, guard, llm, prompt, trace
from .appdb import now


def match_glossary(conn, question: str) -> list:
    """UC02d: các thuật ngữ đang bật xuất hiện trong câu hỏi (không phân biệt hoa thường)."""
    q = question.lower()
    terms = conn.execute('SELECT term, definition FROM glossary_term WHERE is_active = 1 ORDER BY term').fetchall()
    return [dict(t) for t in terms if t['term'].lower() in q]


def build_knowledge(evidence: Optional[str], terms: list) -> Optional[str]:
    """
    Dòng "-- External Knowledge:" của prompt BIRD = tri thức ngoài người dùng nhập (hoặc evidence của câu mẫu,
    giữ nguyên văn như lúc benchmark) + định nghĩa các thuật ngữ trong từ điển (đã chuẩn hoá hàm giả, Gap 3).
    """
    parts = [evidence.strip()] if evidence and evidence.strip() else []
    if terms:
        parts.append(normalize_pseudo_sql('; '.join(f"{t['term']} refers to {t['definition']}" for t in terms)))
    return '; '.join(parts) or None


def _execute_traced(sql: str, role: str):
    r = config.restrictions(role)
    params = [
        ('sql', sql, 'Câu SELECT cần chạy'),
        ('role', role, 'Vai trò; authorizer chặn bảng/cột bị cấm ngay trong SQLite'),
        ('bảng/cột bị cấm', {'tables': sorted(r['tables']), 'columns': sorted(r['columns'])},
         'Suy ra từ ma trận quyền config.PERMISSIONS (BR03)'),
        ('timeout_s', config.QUERY_TIMEOUT_S, 'Quá số giây này thì progress_handler ngắt truy vấn (BR02)'),
        ('db', config.CLUB_DB, 'Mở ở chế độ chỉ đọc (?mode=ro)'),
    ]
    started = time.monotonic()
    try:
        columns, rows = guard.execute(sql, role)
    except guard.QueryRejected as e:
        trace.step('4', 'guard.execute', 'Thực thi chỉ đọc theo quyền', params,
                   f'QueryRejected(status={e.status!r}, message={e.message!r})')
        raise
    trace.step('4', 'guard.execute', 'Thực thi chỉ đọc theo quyền', params,
               {'columns': columns, 'rows': [tuple(x) for x in rows]},
               note=f'thời gian chạy {int((time.monotonic() - started) * 1000)} ms')
    return columns, rows


def ask(conn, user: dict, question: str, model_id: Optional[int] = None, evidence: Optional[str] = None,
        sample_id: Optional[int] = None) -> dict:
    question = (question or '').strip()
    if not question:
        raise ValueError('Please enter a question')
    started = time.monotonic()
    trace.begin(question, user, 'live')

    if model_id is None:
        model = conn.execute('SELECT * FROM model_config WHERE is_active = 1 '
                             'ORDER BY is_default DESC, id LIMIT 1').fetchone()
    else:
        model = conn.execute('SELECT * FROM model_config WHERE id = ? AND is_active = 1', (model_id,)).fetchone()
    if model is None:
        raise ValueError('The model does not exist or is disabled')

    evidence = (evidence or '').strip() or None
    if sample_id is not None and not conn.execute('SELECT 1 FROM sample_question WHERE id = ?', (sample_id,)).fetchone():
        sample_id = None
    out = {'question': question, 'evidence': evidence, 'sample_id': sample_id, 'knowledge': None, 'model_name': model['name'], 'status': None, 'sql': None, 'columns': [],
           'rows': [], 'row_count': None, 'truncated': False, 'answer': None, 'answer_source': None,
           'error': None, 'glossary_used': []}
    try:
        # 1. Tra từ điển thuật ngữ → tri thức nghiệp vụ đưa vào prompt (vai trò của evidence trong BIRD)
        out['glossary_used'] = match_glossary(conn, question)
        knowledge = out['knowledge'] = build_knowledge(evidence, out['glossary_used'])
        trace.step('1', 'service.build_knowledge', 'Ghép tri thức ngoài + thuật ngữ trong từ điển',
                   [('question', question, None), ('evidence', evidence, 'Tri thức ngoài người dùng nhập / của câu mẫu'),
                    ('sample_id', sample_id, 'Câu mẫu BIRD (question_id) nếu có')],
                   knowledge, output_desc='Dòng "-- External Knowledge:"')

        # 2. Sinh SQL (UC02a); schema trong prompt chỉ gồm bảng/cột vai trò được xem
        try:
            sql = llm.generate_sql(dict(model), prompt.build_prompt(question, knowledge, user['role'],
                                                                    model['provider']))
        except llm.LLMError as e:
            raise guard.QueryRejected('FAILED_GENERATION', str(e))
        out['sql'] = sql

        # 3. Kiểm tra an toàn (BR01), 4. thực thi chỉ đọc theo quyền (BR02, BR03)
        sql = guard.check_select(sql)
        out['sql'] = sql
        columns, rows = _execute_traced(sql, user['role'])
        out.update(status='EXECUTED', columns=columns, row_count=len(rows),
                   truncated=len(rows) > config.MAX_ROWS, rows=[list(r) for r in rows[:config.MAX_ROWS]])

        # 5. Diễn giải kết quả thành câu trả lời (UC02f)
        out['answer'], out['answer_source'] = answer.make_answer(question, columns, rows, dict(model))
    except guard.QueryRejected as e:
        out['status'], out['error'] = e.status, e.message
    finally:
        # BR04: mọi câu hỏi đều được ghi log, kể cả khi bị từ chối
        if out['status'] is not None:
            out['latency_ms'] = int((time.monotonic() - started) * 1000)
            out['log_id'] = conn.execute(
                'INSERT INTO query_log (user_id, question, model_id, sample_id, evidence, glossary_used, generated_sql, '
                'answer, status, error, latency_ms, row_count, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (user['id'], question, model['id'], sample_id, evidence,
                 '; '.join(t['term'] for t in out['glossary_used']) or None, out['sql'], out['answer'],
                 out['status'], out['error'], out['latency_ms'], out['row_count'], now())).lastrowid
            conn.commit()
    trace.end(out)
    return out
