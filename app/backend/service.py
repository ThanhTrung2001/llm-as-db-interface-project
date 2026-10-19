"""Nghiệp vụ UC02 Đặt câu hỏi: sinh SQL → kiểm tra → thực thi chỉ đọc → so đáp án chuẩn → ghi log."""
import json
import time
from typing import Optional

from . import answer, config, guard, llm, prompt
from .appdb import now
from evidence_norm import normalize_pseudo_sql  # Gap 3: chuẩn hoá hàm giả trong evidence


def match_glossary(conn, question: str) -> list:
    """UC02d: các thuật ngữ đang bật có xuất hiện trong câu hỏi."""
    q = question.lower()
    terms = conn.execute('SELECT term, definition FROM glossary_term WHERE is_active = 1').fetchall()
    return [dict(t) for t in terms if t['term'].lower() in q]


def same_result(rows_a, rows_b) -> bool:
    # cùng tiêu chí với evaluation.py của BIRD
    return set(rows_a) == set(rows_b)


def ask(conn, user, question: str, mode: str, model_id: Optional[int] = None,
        run_id: Optional[int] = None, dev_question_id: Optional[int] = None,
        use_evidence: bool = True, evidence: Optional[str] = None,
        use_glossary: bool = True) -> dict:
    started = time.monotonic()
    out = {'mode': mode, 'status': None, 'sql': None, 'columns': [], 'rows': [], 'truncated': False,
           'answer': None, 'answer_source': None,
           'error': None, 'is_correct': None, 'gold_sql': None, 'evidence_used': None, 'glossary_used': []}
    dev_q = None
    model = None
    if dev_question_id is not None:
        dev_q = conn.execute('SELECT * FROM dev_question WHERE id = ?', (dev_question_id,)).fetchone()
        if dev_q is None:
            raise ValueError('Không có câu hỏi dev này')
        question = dev_q['question']

    try:
        # 1. Sinh SQL (UC02a) hoặc lấy SQL đã sinh lúc benchmark (chế độ phát lại)
        if mode == 'replay':
            if dev_q is None or run_id is None:
                raise ValueError('Chế độ phát lại cần chọn câu hỏi dev và lượt benchmark')
            item = conn.execute('SELECT b.predicted_sql, r.model_id FROM benchmark_item b '
                                'JOIN benchmark_run r ON r.id = b.run_id '
                                'WHERE b.run_id = ? AND b.question_id = ?', (run_id, dev_question_id)).fetchone()
            if item is None:
                raise ValueError('Lượt benchmark không có câu hỏi này')
            model_id = item['model_id']
            sql = item['predicted_sql']
        else:
            model = conn.execute('SELECT * FROM model_config WHERE id = ? AND is_active = 1',
                                 (model_id,)).fetchone()
            if model is None:
                raise ValueError('Model không tồn tại hoặc đang tắt')
            parts = []
            if dev_q is not None and use_evidence and dev_q['evidence']:
                parts.append(dev_q['evidence'])
            elif evidence:
                parts.append(evidence)
            if use_glossary:
                out['glossary_used'] = match_glossary(conn, question)
                parts += [f"{t['term']} refers to {t['definition']}" for t in out['glossary_used']]
            knowledge = normalize_pseudo_sql('; '.join(parts)) if parts else None
            out['evidence_used'] = knowledge
            try:
                sql = llm.generate_sql(dict(model), prompt.build_prompt(question, knowledge, user['role']))
            except llm.LLMError as e:
                raise guard.QueryRejected('FAILED_GENERATION', str(e))
        out['sql'] = sql

        # 2. Kiểm tra an toàn (UC02b, BR01) và 3. thực thi chỉ đọc theo quyền (UC02c, BR02, BR03)
        sql = guard.check_select(sql)
        columns, rows = guard.execute(sql, user['role'])
        out['status'] = 'EXECUTED'
        out['columns'] = columns
        out['row_count'] = len(rows)
        out['truncated'] = len(rows) > config.MAX_ROWS
        out['rows'] = [list(r) for r in rows[:config.MAX_ROWS]]

        # 3b. Diễn giải kết quả thành câu trả lời (UC02f): hỏi trực tiếp dùng model, phát lại dùng mẫu
        out['answer'], out['answer_source'] = answer.make_answer(
            question, columns, rows, dict(model) if model is not None else None)

        # 4. So với đáp án chuẩn khi câu hỏi thuộc bộ dev (UC02e)
        if dev_q is not None:
            out['gold_sql'] = dev_q['gold_sql']
            try:
                _, gold_rows = guard.execute(dev_q['gold_sql'], 'admin', timeout_s=30)
                out['is_correct'] = int(same_result(rows, gold_rows))
            except guard.QueryRejected:
                out['is_correct'] = None
    except guard.QueryRejected as e:
        out['status'] = e.status
        out['error'] = e.message
        if dev_q is not None:
            out['gold_sql'] = dev_q['gold_sql']
            # bị chặn quyền thì không chấm (không phải lỗi của model); còn lại tính là sai như BIRD
            out['is_correct'] = None if e.status == 'REJECTED_PERMISSION' else 0
    finally:
        # BR04: mọi câu hỏi đều được ghi log, kể cả khi bị từ chối
        if out['status'] is not None:
            out['latency_ms'] = int((time.monotonic() - started) * 1000)
            out['log_id'] = conn.execute(
                'INSERT INTO query_log (user_id, question, mode, model_id, run_id, dev_question_id, '
                'evidence_used, glossary_used, generated_sql, answer, status, error, latency_ms, row_count, '
                'is_correct, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (user['id'], question, mode, model_id, run_id, dev_question_id, out['evidence_used'],
                 json.dumps([t['term'] for t in out['glossary_used']], ensure_ascii=False),
                 out['sql'], out['answer'], out['status'], out['error'], out['latency_ms'],
                 out.get('row_count'), out['is_correct'], now())).lastrowid
            conn.commit()
    out['question'] = question
    return out
