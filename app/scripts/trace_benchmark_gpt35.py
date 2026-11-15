"""
Demo log từng bước của LUỒNG BENCHMARK Text-to-SQL với GPT-3.5-Turbo, cho MỘT câu hỏi.

Gọi thẳng các hàm của src/DAMO-ConvAI/bird/llm/src/openai_request.py và evaluation.py
(đúng code đã dùng để đo EX), chỉ thêm log quanh mỗi hàm:

  dev.json ─► decouple_question_schema ─► generate_schema_prompt
          ─► generate_comment_prompt ─► generate_combined_prompts_one ─► call_openai
          ─► extract_sql ─► dòng predict_dev.json ─► package_sqls ─► execute_model (chấm EX)

Chạy (từ thư mục gốc repo):
  venv/Scripts/python app/scripts/trace_benchmark_gpt35.py                  # câu 1379, có evidence
  venv/Scripts/python app/scripts/trace_benchmark_gpt35.py --question_id 1400
  venv/Scripts/python app/scripts/trace_benchmark_gpt35.py --no_knowledge
  venv/Scripts/python app/scripts/trace_benchmark_gpt35.py --raw "COUNT(*) FROM event"   # không gọi API
  venv/Scripts/python app/scripts/trace_benchmark_gpt35.py \
      --from_pred src/DAMO-ConvAI/bird/llm/exp_result/openai_output/predict_dev.json   # dùng SQL đã lưu

Lưu ý: OpenAI đã ngừng model gpt-3.5-turbo (API trả 404 model_not_found). Khi đó bước 5 ghi lỗi và
xử lý y như collect_response(): sql = "SELECT" → chấm 0. Dùng --from_pred để demo với output thật đã lưu.

Log in ra màn hình và ghi vào app/logs/benchmark_trace_<question_id>.log
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from types import SimpleNamespace

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)


def parse_args():
    from app.backend import config
    p = argparse.ArgumentParser()
    p.add_argument('--question_id', type=int, default=1379, help='chỉ số câu trong dev.json (student_club: 1312–1469)')
    p.add_argument('--model', default='gpt-3.5-turbo')
    p.add_argument('--eval_path', default=os.path.join(config.BIRD, 'data', 'dev.json'))
    p.add_argument('--db_root_path', default=os.path.join(config.BIRD, 'data', 'dev_databases') + os.sep)
    p.add_argument('--no_knowledge', action='store_true', help='chạy không evidence (lượt "no_evidence")')
    p.add_argument('--raw', default=None, help='giả lập output của model, không gọi API')
    p.add_argument('--from_pred', default=None,
                   help='predict_dev.json của một lượt benchmark đã chạy: lấy SQL đã lưu của câu này làm output '
                        'giả lập (bỏ "SELECT " đầu, vì model chỉ viết phần sau SELECT), không gọi API')
    args = p.parse_args()
    if args.from_pred:
        preds = json.load(open(args.from_pred, encoding='utf-8'))
        sql = preds[str(args.question_id)].split('\t----- bird -----\t')[0]
        args.raw = sql[len('SELECT'):].lstrip() if sql.upper().startswith('SELECT') else sql
    return args


class RecordingClient:
    """Bọc OpenAI client để ghi lại ĐÚNG tham số call_openai() gửi đi và response nhận về."""

    def __init__(self, client=None, fake_raw=None):
        self._client, self._fake = client, fake_raw
        self.calls = []
        self.last_kwargs = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.last_kwargs = kwargs
        started = time.monotonic()
        if self._fake is not None:
            msg = SimpleNamespace(content=self._fake)
            resp = SimpleNamespace(id='(GIẢ LẬP — không gọi API)', model=kwargs['model'], usage=None,
                                   choices=[SimpleNamespace(message=msg, finish_reason='(giả lập)')])
        else:
            resp = self._client.chat.completions.create(**kwargs)
        self.calls.append((kwargs, resp, int((time.monotonic() - started) * 1000)))
        return resp


def main():
    args = parse_args()
    log_file = os.path.join(ROOT, 'app', 'logs', f'benchmark_trace_{args.question_id}.log')
    os.environ['CLUBQUERY_TRACE_FILE'] = log_file
    os.environ['CLUBQUERY_TRACE'] = '1'
    from app.backend import config, trace  # noqa: F401  (config thêm bird/llm/src vào sys.path)
    trace.PREFIX = 'BENCH'
    trace._current['id'] = args.question_id

    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, '.env'))
    import openai_request as oa
    from evaluation import execute_model

    config_name = 'no_evidence' if args.no_knowledge else 'evidence'
    trace.log.info('\n' + '=' * 100 + f'\n[BENCH #{args.question_id}] LUỒNG BENCHMARK GPT-3.5-Turbo — '
                   f'cấu hình {config_name}\n' + '=' * 100)

    # ---------- Bước 0: tham số dòng lệnh ----------
    trace.step(
        '0', 'openai_request.py (argparse)',
        'Tham số dòng lệnh của lượt benchmark. Bản gốc chạy cả 1534 câu; ở đây chỉ chạy 1 câu.',
        [('--model', args.model, 'Tên model OpenAI gửi trong request'),
         ('--eval_path', args.eval_path, 'File câu hỏi BIRD dev (1534 câu: question, evidence, SQL gold, db_id)'),
         ('--db_root_path', args.db_root_path, 'Thư mục chứa các CSDL <db_id>/<db_id>.sqlite'),
         ('--no_knowledge', args.no_knowledge, 'True → knowledge_list = [None] * n, lượt "no_evidence"'),
         ('question_id', args.question_id, 'Chỉ số câu trong dev.json (= key trong predict_dev.json)')],
        f'cấu hình = {config_name}')

    # ---------- Bước 1: đọc dev.json ----------
    eval_data = json.load(open(args.eval_path, 'r', encoding='utf-8'))
    item = eval_data[args.question_id]
    trace.step(
        '1', 'json.load(dev.json)[question_id]',
        'Đọc toàn bộ bộ dev rồi lấy câu cần chạy.',
        [('eval_path', args.eval_path, None), ('question_id', args.question_id, None)],
        item, output_desc=f'1 phần tử trong {len(eval_data)} câu: db_id, question, evidence (External Knowledge), '
                          'SQL (gold), difficulty')

    # ---------- Bước 2: tách câu hỏi / đường dẫn CSDL / evidence ----------
    question_list, db_path_list, knowledge_list = oa.decouple_question_schema([item], args.db_root_path)
    trace.step(
        '2', 'openai_request.decouple_question_schema',
        'Tách từ mỗi câu dev ra 3 danh sách song song: câu hỏi, đường dẫn file .sqlite, evidence.',
        [('datasets', '[item ở bước 1]', 'Danh sách câu dev (ở đây 1 câu)'),
         ('db_root_path', args.db_root_path, 'Ghép thành <db_root_path>/<db_id>/<db_id>.sqlite')],
        {'question_list': question_list, 'db_path_list': db_path_list, 'knowledge_list': knowledge_list})
    question, db_path, knowledge = question_list[0], db_path_list[0], knowledge_list[0]

    # ---------- Bước 3: knowledge ----------
    if args.no_knowledge:
        trace.step('3', 'knowledge = None (--no_knowledge)', 'Bỏ evidence: prompt sẽ không có dòng External Knowledge.',
                   [('knowledge (trước)', knowledge, 'Evidence gốc của BIRD')], None)
        knowledge = None
    else:
        trace.step('3', 'knowledge = evidence gốc', 'Dùng nguyên evidence của BIRD, không chuẩn hoá.',
                   [('evidence', knowledge, None)], knowledge)

    # ---------- Bước 4: dựng prompt ----------
    schema = oa.generate_schema_prompt(db_path)
    trace.step(
        '4.1', 'openai_request.generate_schema_prompt',
        'Mở file .sqlite, lấy câu CREATE TABLE của mọi bảng (trừ sqlite_sequence) trong sqlite_master, nối bằng "\\n\\n".',
        [('db_path', db_path, 'CSDL của câu hỏi')],
        schema, output_desc='Phần schema ở đầu prompt')

    comment = oa.generate_comment_prompt(question, knowledge)
    trace.step(
        '4.2', 'openai_request.generate_comment_prompt',
        'Dựng phần comment: "-- External Knowledge: ..." (nếu có) + câu hướng dẫn + "-- <câu hỏi>".',
        [('question', question, 'Câu hỏi tiếng Anh'),
         ('knowledge', knowledge, 'None/rỗng → dùng câu "-- Using valid SQLite, answer ..." (không có External Knowledge)')],
        comment)

    prompt = oa.generate_combined_prompts_one(db_path, question, knowledge)
    trace.step(
        '4.3', 'openai_request.generate_combined_prompts_one',
        'Ghép schema + "\\n\\n" + comment + "\\nGenerate the SQL after thinking step by step: " + "\\nSELECT ". '
        'Giữ câu nhắc của gpt_request.py gốc: prompt kết thúc ở "SELECT " để model viết tiếp phần còn lại.',
        [('db_path', db_path, 'Gọi lại generate_schema_prompt bên trong'),
         ('question', question, None), ('knowledge', knowledge, None)],
        prompt, output_desc='Prompt hoàn chỉnh gửi cho GPT-3.5-Turbo')

    # ---------- Bước 5: gọi LLM ----------
    if args.raw is not None:
        client = RecordingClient(fake_raw=args.raw)
    else:
        from openai import OpenAI
        api_key = os.environ.get('OPEN_AI_KEY') or os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise SystemExit('Chưa có OPEN_AI_KEY trong .env (hoặc chạy với --raw "..." để giả lập)')
        client = RecordingClient(OpenAI(api_key=api_key))
    params = [
        ('client', type(client).__name__, 'OpenAI(api_key=OPEN_AI_KEY) (bọc lại để ghi log request/response)'),
        ('model', args.model, 'Tên model'),
        ('prompt', f'<{len(prompt)} ký tự, bước 4.3>', 'Gửi làm 1 tin nhắn role="user"'),
        ('max_retries', 5, 'Số lần thử lại khi bị rate limit (mặc định của hàm)'),
        ('max_tokens', 256, 'Số token tối đa được sinh (mặc định của hàm, giống gpt_request.py gốc)'),
    ]
    explain_req = ('temperature=0: luôn chọn token chắc nhất, chạy lại ra cùng kết quả; '
                   "stop=['--', '\\n\\n', ';', '#']: gặp một trong các chuỗi này thì dừng (để model chỉ viết "
                   '1 câu SQL, không viết thêm comment / câu thứ hai)')
    purpose = 'Gọi OpenAI Chat Completions; lỗi 429 (rate limit) thì chờ và thử lại tối đa max_retries lần.'

    def sent_of(kwargs):
        return dict(kwargs, messages=[{'role': m['role'], 'content': f'<prompt {len(m["content"])} ký tự, bước 4.3>'}
                                      for m in kwargs['messages']])
    try:
        raw = oa.call_openai(client, args.model, prompt)
    except Exception as e:
        # giống collect_response(): lỗi gọi model → sql = "SELECT", vẫn ghi vào predict_dev.json và bị chấm 0
        req = [('→ request thật gửi đi', sent_of(client.last_kwargs), explain_req)] if client.last_kwargs else []
        trace.step('5', 'openai_request.call_openai', purpose, params + req,
                   f'{type(e).__name__}: {e}',
                   note='collect_response() bắt lỗi này, in "[warn] question i: ..." và đặt sql = "SELECT"')
        raw, sql = None, 'SELECT'
    else:
        kwargs, resp, ms = client.calls[-1]
        usage = getattr(resp, 'usage', None)
        trace.step(
            '5', 'openai_request.call_openai', purpose,
            params + [('→ request thật gửi đi', sent_of(kwargs), explain_req)],
            raw, output_desc='response.choices[0].message.content — văn bản thô, thường là phần SQL SAU chữ "SELECT "',
            note=(f'response.id={resp.id}; model={resp.model}; finish_reason={resp.choices[0].finish_reason}; '
                  f'prompt_tokens={getattr(usage, "prompt_tokens", None)}, '
                  f'completion_tokens={getattr(usage, "completion_tokens", None)}; {ms} ms'))

        # ---------- Bước 6: tách SQL ----------
        sql = oa.extract_sql(raw)
        trace.step(
            '6', 'openai_request.extract_sql',
            'Bỏ khối ```sql nếu có; nếu model tự viết lại "SELECT" thì bỏ đi; cắt ở dấu ";" đầu tiên; '
            'ghép lại "SELECT " + phần còn lại (giống "SELECT" + text của gpt_request.py gốc). Rỗng → "SELECT".',
            [('raw_text', raw, 'Output bước 5')],
            sql, output_desc='Câu SQL dự đoán')

    # ---------- Bước 7: dòng ghi vào predict_dev.json ----------
    db_id = os.path.basename(db_path).replace('.sqlite', '')
    line = sql + '\t----- bird -----\t' + db_id
    trace.step(
        '7', 'collect_response → generate_sql_file',
        'Ghép SQL với db_id theo định dạng BIRD rồi ghi vào exp_result/.../predict_dev.json.',
        [('sql', sql, 'Bước 6'), ('db_id', db_id, 'Tên CSDL, lấy từ tên file .sqlite')],
        {str(args.question_id): line},
        output_desc='1 mục trong predict_dev.json: key = chỉ số câu (openai_request2.py giữ chỉ số gốc; '
                    'openai_request.py đánh số theo thứ tự chạy)')

    # ---------- Bước 8: evaluation.py đọc lại ----------
    pred_sql, db_name = line.split('\t----- bird -----\t')
    eval_db = args.db_root_path + db_name + '/' + db_name + '.sqlite'
    gold_sql = item['SQL']
    trace.step(
        '8', 'evaluation.package_sqls',
        'evaluation.py đọc predict_dev.json, tách "sql\\t----- bird -----\\tdb_id" thành SQL và đường dẫn CSDL; '
        'đọc SQL gold từ dev_gold.sql theo cùng thứ tự.',
        [('sql_str', line, 'Giá trị trong predict_dev.json'),
         ('db_root_path', args.db_root_path, None)],
        {'predicted_sql': pred_sql, 'ground_truth': gold_sql, 'db_place': eval_db})

    # ---------- Bước 9: chấm EX ----------
    def run(q):
        try:
            conn = sqlite3.connect(eval_db)
            try:
                return conn.execute(q).fetchall()
            finally:
                conn.close()
        except Exception as e:
            return f'LỖI: {e}'
    pred_rows, gold_rows = run(pred_sql), run(gold_sql)
    trace.step('9a', 'cursor.execute(predicted_sql).fetchall()', 'Kết quả chạy SQL dự đoán (để xem, bước 9c chấm lại).',
               [('predicted_sql', pred_sql, None)], pred_rows)
    trace.step('9b', 'cursor.execute(ground_truth).fetchall()', 'Kết quả chạy SQL gold.',
               [('ground_truth', gold_sql, None)], gold_rows)
    result = execute_model(pred_sql, gold_sql, eval_db, args.question_id, 30.0)
    trace.step(
        '9c', 'evaluation.execute_model → execute_sql',
        'Chạy cả 2 câu SQL trên cùng CSDL, so set(predicted_res) == set(ground_truth_res) '
        '(không quan tâm thứ tự dòng, bỏ trùng). Quá thời gian hoặc lỗi SQL → 0.',
        [('predicted_sql', pred_sql, None), ('ground_truth', gold_sql, None), ('db_place', eval_db, None),
         ('idx', args.question_id, 'Chỉ số câu, để sắp xếp lại kết quả chạy song song'),
         ('meta_time_out', 30.0, 'Giới hạn thời gian (giây) cho mỗi cặp câu (func_timeout)')],
        result, output_desc='res = 1 → đúng (tính vào EX), res = 0 → sai')

    trace.log.info(f'\n[BENCH #{args.question_id}] KẾT THÚC — SQL: {sql} — EX res={result["res"]}\n'
                   f'Log đã ghi vào {log_file}\n' + '=' * 100)


if __name__ == '__main__':
    main()
