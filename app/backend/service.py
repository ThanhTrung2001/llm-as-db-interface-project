"""
Luồng hỏi đáp Text-to-SQL. POST /api/ask → ask() gọi lần lượt:

    1. load_question()            lấy câu hỏi + evidence (câu mẫu BIRD hoặc câu tự gõ)
    2. load_model()               đọc cấu hình model đã chọn
    3. prompt.build_prompt()      schema + "\\n\\n" + câu hỏi (kèm evidence) + câu chặn
    4. llm.call_llm_for_sql()     gửi prompt (văn bản) cho LLM, nhận văn bản thô. Bên trong model server
                                  (ví dụ thật: câu mẫu 1379, Qwen2.5-Coder 7B trên Ollama):
         A. template     prompt 2.600 ký tự → "<|im_start|>system…<|im_start|>user\\n{prompt}<|im_end|>\\n<|im_start|>assistant\\n"
         B. tokenize     chuỗi đó → 606 token ID, ví dụ " SQLite" → 28334, "<|im_start|>" → 151644
         C. embedding    mỗi ID → 1 dòng của ma trận 152.064 × 3.584 → ma trận 606 × 3.584 số thực
         D. transformer  606 × 3.584 → 28 tầng (attention + feed-forward) → 606 × 3.584
         E. decode       vector cuối → xác suất cho 152.064 token → chọn cao nhất ("```" 99,6%) → nối vào → lặp
                         27 lần, rồi sinh <|im_end|> thì dừng
         F. detokenize   27 ID → "```sql\\nSELECT COUNT(event_id) FROM event WHERE type = 'Meeting' AND …\\n```"
                                  inside_model.py chạy lại A, B, C, F bằng chính file model và đối chiếu với server;
                                  pipeline.build_inside() gom thành out['inside'] để giao diện hiển thị
    5. llm.extract_sql()          tách câu SQL khỏi văn bản thô (chép từ script benchmark)
                                  → "SELECT COUNT(event_id) FROM event WHERE type = 'Meeting' AND …"
    6. execute_sql()              chạy SQL trên student_club.sqlite (chỉ đọc) → cột + dòng
    7. answer.make_answer()       diễn giải kết quả thành câu trả lời
    8. compare_with_gold()        (câu mẫu) so kết quả với SQL đáp án như evaluation.py
    → dict trả về giao diện, app.js renderResult() hiển thị

Trạng thái (status) trả về:
    EXECUTED           chạy SQL thành công
    FAILED_GENERATION  không lấy được SQL (lỗi gọi model / model không sinh SQL)
    EXEC_ERROR         SQL lỗi khi chạy (sai cú pháp, sai tên cột, lệnh ghi bị CSDL chỉ đọc từ chối...)
    TIMEOUT            SQL chạy quá config.QUERY_TIMEOUT_S giây
"""
import pathlib
import sqlite3
import time
from typing import Optional

from . import answer, config, llm, pipeline, prompt


class QueryFailed(Exception):
    """Luồng dừng giữa chừng; status là một trong các trạng thái ở đầu file."""

    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def load_question(conn, question: str, dev_question_id: Optional[int], use_evidence: bool,
                  evidence: Optional[str]) -> tuple:
    """Bước 1. Trả về (câu hỏi, evidence đưa vào prompt, SQL đáp án).

    - Chọn câu mẫu BIRD: lấy câu hỏi, evidence, SQL đáp án trong bảng dev_question;
      bỏ tick "Dùng evidence" thì evidence = None.
    - Câu tự gõ: dùng nguyên câu hỏi + evidence tự nhập (nếu có), không có SQL đáp án.
    """
    if dev_question_id is None:
        return question, (evidence or None), None
    row = conn.execute('SELECT question, evidence, gold_sql FROM dev_question WHERE id = ?',
                       (dev_question_id,)).fetchone()
    if row is None:
        raise ValueError('Không có câu hỏi mẫu này')
    return row['question'], (row['evidence'] if use_evidence else None), row['gold_sql']


def load_model(conn, model_id: int) -> dict:
    """Bước 2. Đọc model trong bảng model_config: provider, model_tag, base_url, api_key_env."""
    row = conn.execute('SELECT * FROM model_config WHERE id = ? AND is_active = 1', (model_id,)).fetchone()
    if row is None:
        raise ValueError('Model không tồn tại hoặc đang tắt')
    return dict(row)


def execute_sql(sql: str, timeout_s: float = config.QUERY_TIMEOUT_S) -> tuple:
    """Bước 6. Chạy SQL trên student_club.sqlite, trả về (columns, rows).

    - mở với ?mode=ro  → mọi lệnh ghi (INSERT/UPDATE/DELETE/DROP...) bị SQLite từ chối
    - conn.execute()   → chỉ chạy được MỘT câu lệnh (giống cursor.execute trong evaluation.py)
    - progress_handler → quá timeout_s giây thì ngắt truy vấn
    """
    uri = pathlib.Path(config.SOURCE_DB).resolve().as_uri() + '?mode=ro'
    conn = sqlite3.connect(uri, uri=True)
    try:
        deadline = time.monotonic() + timeout_s
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
        try:
            cursor = conn.execute(sql)
            rows = cursor.fetchall()
        except sqlite3.Error as e:
            if 'interrupted' in str(e):
                raise QueryFailed('TIMEOUT', f'Truy vấn vượt quá {timeout_s:g} giây.')
            raise QueryFailed('EXEC_ERROR', str(e))
        columns = [d[0] for d in cursor.description or []]
        return columns, rows
    finally:
        conn.close()


def compare_with_gold(rows: list, gold_sql: str) -> int:
    """Bước 8. Chạy SQL đáp án rồi so như evaluation.py của BIRD: set(kết quả) == set(đáp án).
    Không quan tâm thứ tự dòng, bỏ dòng trùng. Trả về 1 (đúng) hoặc 0 (sai)."""
    _, gold_rows = execute_sql(gold_sql, timeout_s=30)
    return int(set(rows) == set(gold_rows))


def ask(conn, question: str, model_id: int, dev_question_id: Optional[int] = None,
        use_evidence: bool = True, evidence: Optional[str] = None) -> dict:
    started = time.monotonic()
    question, evidence, gold_sql = load_question(conn, question, dev_question_id, use_evidence, evidence)  # 1
    model = load_model(conn, model_id)                                                                     # 2

    out = {'question': question, 'model_id': model_id, 'evidence_used': evidence, 'gold_sql': gold_sql,
           'prompt': None, 'llm_output': None, 'sql': None, 'status': None, 'error': None,
           'columns': [], 'rows': [], 'row_count': None, 'truncated': False,
           'answer': None, 'answer_source': None, 'is_correct': None,
           'inside': None, 'extract_steps': []}
    trace = {}  # llm.call_llm ghi request, số token, logprobs vào đây → dùng cho mục "Bên trong model"
    try:
        out['prompt'] = prompt.build_prompt(question, evidence, model['provider'])                        # 3
        try:
            out['llm_output'] = llm.call_llm_for_sql(model, out['prompt'], trace=trace)                   # 4
        except llm.LLMError as e:
            raise QueryFailed('FAILED_GENERATION', str(e))
        out['sql'] = llm.extract_sql(model['provider'], out['llm_output'], out['extract_steps'])          # 5
        if not out['sql'].strip():
            raise QueryFailed('FAILED_GENERATION', 'Model không sinh được câu truy vấn.')

        columns, rows = execute_sql(out['sql'])                                                           # 6
        out['status'] = 'EXECUTED'
        out['columns'] = columns
        out['row_count'] = len(rows)
        out['truncated'] = len(rows) > config.MAX_ROWS
        out['rows'] = [list(r) for r in rows[:config.MAX_ROWS]]

        out['answer'], out['answer_source'] = answer.make_answer(question, columns, rows, model)          # 7
        if gold_sql:
            out['is_correct'] = compare_with_gold(rows, gold_sql)                                         # 8
    except QueryFailed as e:
        out['status'] = e.status
        out['error'] = e.message
        if gold_sql:
            out['is_correct'] = 0  # lỗi sinh/chạy SQL tính là sai, như BIRD

    # bước 4 nhìn từ bên trong model (A–F); trace rỗng khi gọi model lỗi hoặc test giả lập → bỏ qua
    out['inside'] = pipeline.build_inside(out['prompt'], out['llm_output'], question, model, trace)

    out['latency_ms'] = int((time.monotonic() - started) * 1000)
    return out
