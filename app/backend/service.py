"""Nghiệp vụ UC02 Đặt câu hỏi: sinh SQL → kiểm tra → thực thi chỉ đọc → so đáp án chuẩn → ghi log."""
import time
from typing import Optional

from . import answer, config, guard, llm, prompt, trace
from .appdb import now


def same_result(rows_a, rows_b) -> bool:
    # cùng tiêu chí với evaluation.py của BIRD
    return set(rows_a) == set(rows_b)


def _execute_traced(label: str, sql: str, role: str, purpose: str, timeout_s: float = None):
    """Gọi guard.execute và ghi log input/output (kể cả khi bị chặn)."""
    r = config.restrictions(role)
    params = [
        ('sql', sql, 'Câu SELECT cần chạy'),
        ('role', role, 'Vai trò dùng để phân quyền; authorizer chặn bảng/cột bị cấm ngay trong SQLite'),
        ('bảng/cột bị cấm', {'tables': sorted(r['tables']), 'columns': sorted(r['columns'])},
         'Theo config.RESTRICTED (BR03)'),
        ('timeout_s', timeout_s or config.QUERY_TIMEOUT_S, 'Quá số giây này thì progress_handler ngắt truy vấn (BR02)'),
        ('db', config.SOURCE_DB, 'Mở ở chế độ chỉ đọc (?mode=ro)'),
    ]
    started = time.monotonic()
    try:
        columns, rows = guard.execute(sql, role, timeout_s=timeout_s)
    except guard.QueryRejected as e:
        trace.step(label, 'guard.execute', purpose, params, f'QueryRejected(status={e.status!r}, message={e.message!r})',
                   output_desc='REJECTED_PERMISSION | REJECTED_UNSAFE | TIMEOUT | EXEC_ERROR')
        raise
    trace.step(label, 'guard.execute', purpose, params, {'columns': columns, 'rows': '(xem dưới)'},
               note=f'thời gian chạy {int((time.monotonic() - started) * 1000)} ms')
    trace.step(label, 'guard.execute (rows)', 'Các dòng kết quả thật', None, [tuple(x) for x in rows]
               if rows else [], output_desc='list các tuple, mỗi tuple là một dòng')
    return columns, rows


def ask(conn, user, question: str, mode: str, model_id: Optional[int] = None,
        run_id: Optional[int] = None, dev_question_id: Optional[int] = None,
        use_evidence: bool = True, evidence: Optional[str] = None) -> dict:
    started = time.monotonic()
    trace.begin(question, user, mode)
    trace.step(
        '0', 'service.ask',
        'Điều phối toàn bộ luồng: lấy SQL → kiểm tra → chạy chỉ đọc → diễn giải → so đáp án → ghi nhật ký.',
        [('user', {k: user.get(k) for k in ('id', 'username', 'role')}, 'Người hỏi; role quyết định bảng/cột được xem'),
         ('question', question, 'Câu tự gõ; rỗng nếu chọn câu mẫu (sẽ thay bằng câu dev)'),
         ('mode', mode, 'live = gọi model ngay; replay = dùng SQL đã sinh lúc benchmark'),
         ('model_id', model_id, '(live) id trong bảng model_config'),
         ('run_id', run_id, '(replay) id lượt benchmark (model × cấu hình evidence)'),
         ('dev_question_id', dev_question_id, 'question_id của câu mẫu BIRD dev (1312–1469); None = câu tự gõ'),
         ('use_evidence', use_evidence, 'Có đưa evidence của câu mẫu vào prompt không'),
         ('evidence', evidence, 'Evidence tự nhập (chỉ dùng khi không chọn câu mẫu)')],
        '(xem các bước bên dưới)')

    out = {'mode': mode, 'status': None, 'sql': None, 'columns': [], 'rows': [], 'truncated': False,
           'answer': None, 'answer_source': None,
           'error': None, 'is_correct': None, 'gold_sql': None, 'evidence_used': None}
    dev_q = None
    model = None
    if dev_question_id is not None:
        dev_q = conn.execute('SELECT * FROM dev_question WHERE id = ?', (dev_question_id,)).fetchone()
        trace.step(
            '1', 'đọc dev_question',
            'Đọc câu hỏi mẫu của BIRD dev; câu hỏi người dùng được thay bằng câu gốc.',
            [('dev_question_id', dev_question_id, 'Khoá chính của bảng dev_question trong app.sqlite')],
            dict(dev_q) if dev_q else None,
            output_desc='question, evidence (External Knowledge của BIRD), gold_sql (đáp án), difficulty')
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
            trace.step(
                '2a', 'đọc benchmark_item (replay)',
                'Lấy SQL model đã sinh lúc chạy benchmark, không gọi model.',
                [('run_id', run_id, 'Lượt benchmark'), ('question_id', dev_question_id, 'Câu dev')],
                dict(item) if item else None, output_desc='predicted_sql + model_id của lượt đó')
            if item is None:
                raise ValueError('Lượt benchmark không có câu hỏi này')
            model_id = item['model_id']
            sql = item['predicted_sql']
        else:
            model = conn.execute('SELECT * FROM model_config WHERE id = ? AND is_active = 1',
                                 (model_id,)).fetchone()
            trace.step(
                '2b.1', 'đọc model_config',
                'Lấy cấu hình model đang bật.',
                [('model_id', model_id, 'id model người dùng chọn')],
                dict(model) if model else None,
                output_desc='provider, model_tag (tên model), base_url (địa chỉ API), api_key_env (tên biến chứa khoá)')
            if model is None:
                raise ValueError('Model không tồn tại hoặc đang tắt')
            if dev_q is not None and use_evidence and dev_q['evidence']:
                knowledge = dev_q['evidence']
                src = 'evidence của câu dev (use_evidence = True)'
            elif evidence:
                knowledge = evidence
                src = 'evidence người dùng tự nhập'
            else:
                knowledge = None
                src = 'không có evidence (use_evidence = False)'
            trace.step(
                '2b.3', 'chọn knowledge',
                'Lấy evidence đưa vào prompt, dùng NGUYÊN VĂN như benchmark gốc (không chuẩn hoá).',
                [('use_evidence', use_evidence, 'Ô "Dùng evidence của câu mẫu"'),
                 ('dev_q.evidence', dev_q['evidence'] if dev_q is not None else None, 'Evidence của câu mẫu BIRD'),
                 ('evidence', evidence, 'Evidence tự nhập (khi không chọn câu mẫu)')],
                knowledge, output_desc=f'{src} → dòng "-- External Knowledge:" trong prompt; None = không có')
            out['evidence_used'] = knowledge
            try:
                sql = llm.generate_sql(dict(model), prompt.build_prompt(question, knowledge, user['role'],
                                                                        model['provider']))
            except llm.LLMError as e:
                raise guard.QueryRejected('FAILED_GENERATION', str(e))
        out['sql'] = sql

        # 2. Kiểm tra an toàn (UC02b, BR01) và 3. thực thi chỉ đọc theo quyền (UC02c, BR02, BR03)
        try:
            checked = guard.check_select(sql)
        except guard.QueryRejected as e:
            trace.step('3', 'guard.check_select',
                       'Lớp kiểm tra 1 (trên chuỗi): đúng 1 câu lệnh, bắt đầu bằng SELECT/WITH, không phải lệnh ghi.',
                       [('sql', sql, 'SQL lấy được ở bước 2')],
                       f'QueryRejected(status={e.status!r}, message={e.message!r})')
            raise
        trace.step('3', 'guard.check_select',
                   'Lớp kiểm tra 1 (trên chuỗi): đúng 1 câu lệnh, bắt đầu bằng SELECT/WITH, không phải lệnh ghi.',
                   [('sql', sql, 'SQL lấy được ở bước 2')],
                   checked, output_desc='SQL đã làm sạch (bỏ khoảng trắng và dấu ";" cuối)')
        sql = checked
        columns, rows = _execute_traced(
            '4', sql, user['role'],
            'Lớp kiểm tra 2: chạy SQL trên student_club.sqlite chỉ đọc, authorizer chặn bảng/cột bị cấm, '
            'có timeout.')
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
                _, gold_rows = _execute_traced(
                    '6a', dev_q['gold_sql'], 'admin',
                    'Chạy SQL đáp án (gold) với quyền admin để có kết quả chuẩn.', timeout_s=30)
                out['is_correct'] = int(same_result(rows, gold_rows))
                trace.step(
                    '6b', 'service.same_result',
                    'So kết quả model với kết quả gold: set(rows) == set(gold_rows), cùng tiêu chí EX của BIRD '
                    '(không quan tâm thứ tự, bỏ trùng).',
                    [('rows_a (model)', f'<{len(rows)} dòng>', 'Kết quả SQL của model (bước 4)'),
                     ('rows_b (gold)', f'<{len(gold_rows)} dòng>', 'Kết quả SQL đáp án (bước 6a)')],
                    out['is_correct'], output_desc='is_correct: 1 = đúng, 0 = sai')
            except guard.QueryRejected:
                out['is_correct'] = None
    except guard.QueryRejected as e:
        out['status'] = e.status
        out['error'] = e.message
        if dev_q is not None:
            out['gold_sql'] = dev_q['gold_sql']
            # bị chặn quyền thì không chấm (không phải lỗi của model); còn lại tính là sai như BIRD
            out['is_correct'] = None if e.status == 'REJECTED_PERMISSION' else 0
        trace.step('ERR', 'xử lý QueryRejected', 'Truy vấn bị từ chối hoặc lỗi → ghi trạng thái lỗi.',
                   [('status', e.status, None), ('message', e.message, None)],
                   {'status': out['status'], 'is_correct': out['is_correct']},
                   output_desc='REJECTED_PERMISSION không chấm (None); lỗi khác tính là sai (0) như BIRD')
    finally:
        # BR04: mọi câu hỏi đều được ghi log, kể cả khi bị từ chối
        if out['status'] is not None:
            out['latency_ms'] = int((time.monotonic() - started) * 1000)
            out['log_id'] = conn.execute(
                'INSERT INTO query_log (user_id, question, mode, model_id, run_id, dev_question_id, '
                'evidence_used, generated_sql, answer, status, error, latency_ms, row_count, '
                'is_correct, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (user['id'], question, mode, model_id, run_id, dev_question_id, out['evidence_used'],
                 out['sql'], out['answer'], out['status'], out['error'], out['latency_ms'],
                 out.get('row_count'), out['is_correct'], now())).lastrowid
            conn.commit()
            trace.step('7', 'ghi query_log',
                       'Ghi nhật ký mọi câu hỏi, kể cả bị từ chối (BR04).',
                       [('status', out['status'], None), ('latency_ms', out['latency_ms'], 'Tổng thời gian xử lý'),
                        ('row_count', out.get('row_count'), None), ('is_correct', out['is_correct'], None)],
                       out['log_id'], output_desc='id dòng vừa ghi trong bảng query_log')
    out['question'] = question
    trace.step('8', 'service.ask (trả về)', 'JSON trả về trình duyệt, renderResult() hiển thị.', None,
               {k: v for k, v in out.items() if k != 'rows'} | {'rows': f'<{len(out["rows"])} dòng>'})
    trace.end(out)
    return out
