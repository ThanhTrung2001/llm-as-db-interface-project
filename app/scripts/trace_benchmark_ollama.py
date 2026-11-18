"""
Demo log từng bước của LUỒNG BENCHMARK Text-to-SQL với Ollama (mặc định qwen2.5-coder:7b-instruct,
model có EX cao nhất trong các lượt benchmark), cho MỘT câu hỏi.

Gọi thẳng các hàm của src/DAMO-ConvAI/bird/llm/src/ollama_request.py và evaluation.py
(đúng code benchmark gốc, evidence dùng nguyên văn, KHÔNG chuẩn hoá), chỉ thêm log quanh mỗi hàm:

  dev.json ─► decouple_question_schema ─► generate_schema_prompt ─► generate_comment_prompt
          ─► generate_combined_prompts_one ─► call_ollama (POST /api/chat)
          ─► extract_sql ─► dòng predict_dev.json ─► package_sqls ─► execute_model (chấm EX)

Cần: `ollama serve` đang chạy và đã `ollama pull qwen2.5-coder:7b-instruct`.

Chạy (từ thư mục gốc repo):
  venv/Scripts/python app/scripts/trace_benchmark_ollama.py                  # câu 1379, có tri thức ngoài
  venv/Scripts/python app/scripts/trace_benchmark_ollama.py --no_knowledge   # không có tri thức ngoài
  venv/Scripts/python app/scripts/trace_benchmark_ollama.py --question_id 1400
  venv/Scripts/python app/scripts/trace_benchmark_ollama.py --model gemma3:12b

Log in ra màn hình và ghi vào app/logs/benchmark_ollama_<question_id>_<cấu hình>.log
"""
import argparse
import json
import os
import sqlite3
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)


def parse_args():
    from app.backend import config
    p = argparse.ArgumentParser()
    p.add_argument('--question_id', type=int, default=1379, help='chỉ số câu trong dev.json (student_club: 1312–1469)')
    p.add_argument('--model', default='qwen2.5-coder:7b-instruct')
    p.add_argument('--eval_path', default=os.path.join(config.BIRD, 'data', 'dev.json'))
    p.add_argument('--db_root_path', default=os.path.join(config.BIRD, 'data', 'dev_databases') + os.sep)
    p.add_argument('--no_knowledge', action='store_true', help='chạy không evidence (lượt "no_evidence")')
    return p.parse_args()


def main():
    args = parse_args()
    config_name = 'no_evidence' if args.no_knowledge else 'evidence'
    log_file = os.path.join(ROOT, 'app', 'logs', f'benchmark_ollama_{args.question_id}_{config_name}.log')
    if os.path.exists(log_file):
        os.remove(log_file)  # mỗi lần chạy ghi lại từ đầu
    os.environ['CLUBQUERY_TRACE_FILE'] = log_file
    os.environ['CLUBQUERY_TRACE'] = '1'
    from app.backend import config, trace  # noqa: F401  (config thêm bird/llm/src vào sys.path)
    trace.PREFIX = 'OLLAMA'
    trace._current['id'] = args.question_id

    import ollama_request as ol
    from evaluation import execute_model

    # Ghi lại đúng request HTTP mà call_ollama() gửi đi và response nhận về
    http = {}
    real_post = ol.requests.post

    def recording_post(url, json=None, timeout=None, **kw):
        http.update(url=url, payload=json, timeout=timeout, started=time.monotonic())
        resp = real_post(url, json=json, timeout=timeout, **kw)
        http.update(ms=int((time.monotonic() - http['started']) * 1000), status=resp.status_code)
        try:
            http['body'] = resp.json()
        except ValueError:
            http['body'] = resp.text
        return resp
    ol.requests.post = recording_post

    trace.log.info('\n' + '=' * 100 + f'\n[OLLAMA #{args.question_id}] LUỒNG BENCHMARK OLLAMA — {args.model} — '
                   f'cấu hình {config_name}\n' + '=' * 100)

    # ---------- Bước 0: tham số dòng lệnh ----------
    trace.step(
        '0', 'ollama_request.py (argparse)',
        'Tham số dòng lệnh của lượt benchmark. Bản gốc chạy cả 1534 câu; ở đây chỉ chạy 1 câu.',
        [('--model', args.model, 'Tên model đã pull về Ollama (tag)'),
         ('--eval_path', args.eval_path, 'File câu hỏi BIRD dev (1534 câu: question, evidence, SQL gold, db_id)'),
         ('--db_root_path', args.db_root_path, 'Thư mục chứa các CSDL <db_id>/<db_id>.sqlite'),
         ('--no_knowledge', args.no_knowledge,
          'True → knowledge_list = [None] * n (như openai_request.py), lượt "no_evidence"'),
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

    # ---------- Bước 2: đường dẫn CSDL + knowledge ----------
    question_list, db_path_list, knowledge_list = ol.decouple_question_schema([item], args.db_root_path)
    trace.step(
        '2', 'ollama_request.decouple_question_schema',
        'Tách từ mỗi câu dev ra 3 danh sách song song: câu hỏi, đường dẫn file .sqlite, evidence.',
        [('datasets', '[item ở bước 1]', 'Danh sách câu dev (ở đây 1 câu)'),
         ('db_root_path', args.db_root_path, 'Ghép thành <db_root_path>/<db_id>/<db_id>.sqlite')],
        {'question_list': question_list, 'db_path_list': db_path_list, 'knowledge_list': knowledge_list})
    question, db_path = question_list[0], db_path_list[0]

    # ---------- Bước 3: knowledge ----------
    if args.no_knowledge:
        knowledge_list = [None] * len(knowledge_list)
        trace.step('3', 'knowledge_list = [None] * len(knowledge_list)  (--no_knowledge)',
                   'Bỏ evidence: prompt sẽ không có dòng "-- External Knowledge:".',
                   [('knowledge_list (trước)', [item['evidence']], 'Evidence gốc của BIRD')], knowledge_list)
    else:
        trace.step('3', 'knowledge = knowledge_list[i]',
                   'Dùng NGUYÊN VĂN evidence của BIRD (benchmark gốc không chuẩn hoá).',
                   [('knowledge_list', knowledge_list, 'Output bước 2')], knowledge_list[0])
    knowledge = knowledge_list[0]

    # ---------- Bước 4: dựng prompt ----------
    schema = ol.generate_schema_prompt(db_path)
    trace.step(
        '4.1', 'ollama_request.generate_schema_prompt',
        'Mở file .sqlite, lấy câu CREATE TABLE của mọi bảng (trừ sqlite_sequence) trong sqlite_master, nối bằng "\\n\\n".',
        [('db_path', db_path, 'CSDL của câu hỏi')],
        schema, output_desc='Phần schema ở đầu prompt')

    comment = ol.generate_comment_prompt(question, knowledge)
    trace.step(
        '4.2', 'ollama_request.generate_comment_prompt',
        'Dựng phần comment: "-- External Knowledge: ..." (nếu có) + câu hướng dẫn + "-- <câu hỏi>".',
        [('question', question, 'Câu hỏi tiếng Anh'),
         ('knowledge', knowledge, 'None/rỗng → câu "-- Using valid SQLite, answer ..." (không có External Knowledge)')],
        comment)

    prompt = ol.generate_combined_prompts_one(db_path, question, knowledge)
    trace.step(
        '4.3', 'ollama_request.generate_combined_prompts_one',
        'Ghép schema + "\\n\\n" + comment + "\\nRespond with the final SQLite query only, inside a ```sql code '
        'block. Do not add any explanation." (model chat cần yêu cầu rõ định dạng trả về).',
        [('db_path', db_path, 'Gọi lại generate_schema_prompt bên trong'),
         ('question', question, None), ('knowledge', knowledge, None)],
        prompt, output_desc='Prompt hoàn chỉnh gửi cho model')

    # ---------- Bước 5: gọi Ollama ----------
    params = [
        ('model', args.model, 'Tag model trong Ollama'),
        ('prompt', f'<{len(prompt)} ký tự, bước 4.3>', 'Gửi làm 1 tin nhắn role="user"'),
        ('max_retries', 3, 'Lỗi (mạng, server chưa sẵn sàng...) thì chờ 3 giây rồi thử lại, tối đa 3 lần'),
        ('timeout', 120, 'Chờ tối đa 120 giây cho mỗi lần gọi'),
    ]
    explain_payload = ('POST http://localhost:11434/api/chat. stream=False: nhận cả câu trả lời một lần; '
                       'options.temperature=0: luôn chọn token chắc nhất, chạy lại ra cùng kết quả. '
                       'Không giới hạn số token, không có chuỗi dừng (khác call_openai)')

    def payload_view():
        p = http.get('payload') or {}
        return dict(p, messages=[{'role': m['role'], 'content': f'<prompt {len(m["content"])} ký tự, bước 4.3>'}
                                 for m in p.get('messages', [])])
    try:
        raw = ol.call_ollama(args.model, prompt)
    except Exception as e:
        # giống ollama_request2.collect_response(): lỗi → sql = "SELECT", vẫn ghi vào predict_dev.json, chấm 0
        trace.step('5', 'ollama_request.call_ollama', 'Gọi Ollama /api/chat trên máy (không cần khoá API).',
                   params + [('→ request thật gửi đi', payload_view(), explain_payload)],
                   f'{type(e).__name__}: {e}',
                   note='collect_response() bắt lỗi này, in "[warn] question i: ..." và đặt sql = "SELECT"')
        raw, sql = None, 'SELECT'
    else:
        body = http.get('body') if isinstance(http.get('body'), dict) else {}
        ns = 1e9
        trace.step(
            '5', 'ollama_request.call_ollama', 'Gọi Ollama /api/chat trên máy (không cần khoá API).',
            params + [('→ request thật gửi đi', payload_view(), explain_payload)],
            raw, output_desc='resp.json()["message"]["content"] — văn bản thô model trả về',
            note=(f'HTTP {http.get("status")}; model={body.get("model")}; done_reason={body.get("done_reason")}; '
                  f'prompt_eval_count={body.get("prompt_eval_count")} token prompt, '
                  f'eval_count={body.get("eval_count")} token sinh ra; '
                  f'load_duration={(body.get("load_duration") or 0) / ns:.2f}s (nạp model vào RAM/VRAM), '
                  f'total_duration={(body.get("total_duration") or 0) / ns:.2f}s; tổng {http.get("ms")} ms'))

        # ---------- Bước 6: tách SQL ----------
        sql = ol.extract_sql(raw)
        trace.step(
            '6', 'ollama_request.extract_sql',
            'Bỏ <think>...</think> (nếu model có suy luận), lấy nội dung trong ```sql ... ``` (không có dấu đóng thì '
            'bỏ dấu mở), cắt ở ";" đầu tiên, bỏ khoảng trắng. Rỗng → "SELECT".',
            [('raw_text', raw, 'Output bước 5')],
            sql, output_desc='Câu SQL dự đoán')

    # ---------- Bước 7: dòng ghi vào predict_dev.json ----------
    line = sql + '\t----- bird -----\t' + item['db_id']
    trace.step(
        '7', 'collect_response → save_predictions',
        'Ghép SQL với db_id theo định dạng BIRD rồi ghi vào exp_result/.../predict_dev.json.',
        [('sql', sql, 'Bước 6 (hoặc "SELECT" nếu gọi model lỗi)'), ('db_id', item['db_id'], 'Lấy từ câu dev')],
        {str(args.question_id): line},
        output_desc='1 mục trong predict_dev.json: key = chỉ số câu gốc trong dev.json')

    # ---------- Bước 8: evaluation.py đọc lại ----------
    pred_sql, db_name = line.split('\t----- bird -----\t')
    eval_db = args.db_root_path + db_name + '/' + db_name + '.sqlite'
    gold_sql = item['SQL']
    trace.step(
        '8', 'evaluation.package_sqls',
        'evaluation.py đọc predict_dev.json, tách "sql\\t----- bird -----\\tdb_id" thành SQL và đường dẫn CSDL; '
        'đọc SQL gold từ dev_gold.sql theo cùng thứ tự.',
        [('sql_str', line, 'Giá trị trong predict_dev.json'), ('db_root_path', args.db_root_path, None)],
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
    trace.step('9a', 'cursor.execute(predicted_sql).fetchall()', 'Kết quả chạy SQL dự đoán (để xem; bước 9c chấm).',
               [('predicted_sql', pred_sql, None)], run(pred_sql))
    trace.step('9b', 'cursor.execute(ground_truth).fetchall()', 'Kết quả chạy SQL gold.',
               [('ground_truth', gold_sql, None)], run(gold_sql))
    result = execute_model(pred_sql, gold_sql, eval_db, args.question_id, 30.0)
    trace.step(
        '9c', 'evaluation.execute_model → execute_sql',
        'Chạy cả 2 câu SQL trên cùng CSDL, so set(predicted_res) == set(ground_truth_res) '
        '(không quan tâm thứ tự dòng, bỏ trùng). Quá thời gian hoặc lỗi SQL → 0.',
        [('predicted_sql', pred_sql, None), ('ground_truth', gold_sql, None), ('db_place', eval_db, None),
         ('idx', args.question_id, 'Chỉ số câu, để sắp xếp lại kết quả khi chạy song song'),
         ('meta_time_out', 30.0, 'Giới hạn thời gian (giây) cho mỗi cặp câu (func_timeout)')],
        result, output_desc='res = 1 → đúng (tính vào EX), res = 0 → sai')

    trace.log.info(f'\n[OLLAMA #{args.question_id}] KẾT THÚC — SQL: {sql} — EX res={result["res"]}\n'
                   f'Log đã ghi vào {log_file}\n' + '=' * 100)


if __name__ == '__main__':
    main()
