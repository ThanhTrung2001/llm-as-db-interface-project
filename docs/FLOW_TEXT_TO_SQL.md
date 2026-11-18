# Flow chi tiết: từ câu hỏi đến SQL và điểm số

Tài liệu này mô tả **từng hàm được gọi theo thứ tự**, hàm nhận tham số gì, tham số có ý nghĩa gì, và đầu ra của hàm này được hàm nào dùng tiếp.

Có 2 luồng:

| Luồng | Mục đích | Code |
|---|---|---|
| **A. Benchmark** | Sinh SQL cho cả bộ dev (1.534 câu) rồi chấm EX / VES | `src/DAMO-ConvAI/bird/llm/src/*.py`, `app/scripts/ex_ves_by_category.py` |
| **B. Demo (ClubQuery)** | Người dùng hỏi một câu, hệ thống sinh SQL, chạy và trả lời | `app/backend/*.py` |

Cuối tài liệu (mục C) có ví dụ chạy tay câu **1379** qua cả hai luồng, ghi rõ giá trị ở từng bước.

Quy ước: đường dẫn `bird/` = `src/DAMO-ConvAI/bird/`.

---

## A. Luồng benchmark

```
A1. Sinh SQL                  A2. Chấm EX               A3. Chấm VES              A4. Chấm theo 6 mức
dev.json ─► predict_dev.json ─► evaluation.py ─► EX     evaluation_ves.py ─► VES   ex_ves_by_category.py
                                                                                   (gọi lại hàm của A2, A3)
```

### A1. Sinh SQL: `openai_request.py` / `ollama_request.py`

**Lệnh chạy** (từ thư mục `bird/llm/`):

```bash
# GPT-3.5, có evidence
python src/openai_request.py --model gpt-3.5-turbo \
    --eval_path ../data/dev.json --db_root_path ../data/dev_databases/ \
    --data_output_path ./exp_result/openai_output/predict_dev.json

# GPT-3.5, không evidence
python src/openai_request.py --model gpt-3.5-turbo --no_knowledge \
    --eval_path ../data/dev.json --db_root_path ../data/dev_databases/ \
    --data_output_path ./exp_result/openai_0_output/predict_dev.json

# Ollama (Kaggle), ví dụ Qwen
python src/ollama_request.py --model qwen2.5-coder:7b \
    --eval_path ../data/dev.json --db_root_path ../data/dev_databases/ \
    --data_output_path ./exp_result/ollama_gwen25_output/predict_dev.json
```

| Tham số dòng lệnh | Ý nghĩa |
|---|---|
| `--model` | Tên model gửi cho API (`gpt-3.5-turbo`) hoặc tag Ollama (`qwen2.5-coder:7b`, `deepseek-coder-v2:16b`, `gemma3:12b`) |
| `--eval_path` | File câu hỏi `dev.json` |
| `--db_root_path` | Thư mục chứa 11 CSDL; CSDL của câu hỏi nằm ở `<db_root_path>/<db_id>/<db_id>.sqlite` |
| `--data_output_path` | Nơi ghi kết quả. Quy ước: thư mục có hậu tố `_0` là lượt **không** evidence |
| `--no_knowledge` | (chỉ `openai_request.py`) Bỏ evidence khỏi prompt |
| `--cot` | (chỉ `openai_request.py`) Dùng prompt Chain-of-Thought 1-shot |
| `--limit N` | Chỉ chạy N câu đầu, để thử nhanh |

Bản `openai_request2.py` / `ollama_request2.py` (dùng cho Gap 3) có thêm `--normalize_evidence` (chuẩn hoá evidence), `--ids_file` (chỉ chạy các câu trong file JSON) và `--print_prompts N` (in N prompt đầu để kiểm tra).

**Chuỗi gọi hàm:**

```
main
 ├─1─ json.load(eval_path)                                   → eval_data
 ├─2─ decouple_question_schema(eval_data, db_root_path)      → question_list, db_path_list, knowledge_list
 ├─3─ (--no_knowledge) knowledge_list = [None] * n
 ├─4─ collect_response(client, model, db_path_list, question_list, knowledge_list, ...)
 │      lặp từng câu i:
 │       ├─4.1─ generate_combined_prompts_one(db_path, question, knowledge)  → prompt
 │       │        ├─ generate_schema_prompt(db_path)                         → schema_prompt
 │       │        └─ generate_comment_prompt(question, knowledge)            → comment_prompt
 │       ├─4.2─ call_openai(client, model, prompt) / call_ollama(model, prompt) → raw
 │       ├─4.3─ extract_sql(raw)                                             → sql
 │       └─4.4─ ghép  sql + '\t----- bird -----\t' + db_id                   → 1 phần tử của response_list
 └─5─ generate_sql_file(response_list, output_path)          → predict_dev.json
```

#### Bước 1: `json.load(eval_path)`
- Đầu ra `eval_data`: list 1.534 dict, mỗi dict có `question_id`, `db_id`, `question`, `evidence`, `SQL`, `difficulty`.

#### Bước 2: `decouple_question_schema(datasets, db_root_path)`
| Tham số | Ý nghĩa |
|---|---|
| `datasets` | `eval_data` ở bước 1 |
| `db_root_path` | Thư mục chứa các CSDL |

Đầu ra: 3 list cùng độ dài, cùng thứ tự với `dev.json`:
- `question_list[i]` = `datasets[i]['question']`
- `db_path_list[i]` = `<db_root_path>/<db_id>/<db_id>.sqlite`
- `knowledge_list[i]` = `datasets[i]['evidence']`

#### Bước 3: bỏ evidence (nếu có `--no_knowledge`)
`knowledge_list` thành toàn `None`. Bước 4.1 sẽ thấy `knowledge` rỗng và dùng câu nhắc không có External Knowledge.

Ở bản `*_request2.py`, nếu có `--normalize_evidence` thì mỗi evidence được đưa qua `normalize_pseudo_sql(knowledge)` (`evidence_norm.py`) trước khi vào prompt:

| Trong evidence gốc | Sau khi chuẩn hoá |
|---|---|
| `DIVIDE(a, b)` | `CAST(a AS REAL) / b` |
| `SUBTRACT(a, b)` / `MULTIPLY(a, b)` / `ADD(a, b)` | `(a) - (b)` / `(a) * (b)` / `(a) + (b)` |
| `YEAR(x)` / `MONTH(x)` / `DAY(x)` | `CAST(STRFTIME('%Y', x) AS INTEGER)` / `'%m'` / `'%d'` |

Hàm xử lý hàm lồng nhau từ trong ra ngoài. Lời gọi nào sai cú pháp (thiếu ngoặc, sai số tham số) thì được giữ nguyên.

#### Bước 4: `collect_response(...)`
| Tham số | Ý nghĩa |
|---|---|
| `client` | (OpenAI) đối tượng `OpenAI(api_key=...)`, khoá lấy từ `OPEN_AI_KEY` trong `.env` |
| `model` | Tên model |
| `db_path_list`, `question_list`, `knowledge_list` | 3 list từ bước 2–3 |
| `output_path` | Đường dẫn để ghi checkpoint |
| `checkpoint_every` | 50: cứ 50 câu ghi file một lần, phòng trường hợp mất phiên Kaggle |
| `cot` | `True` thì dùng `generate_combined_prompts_cot` và `extract_sql_cot` |

Với từng câu `i`, hàm gọi lần lượt:

**4.1. `generate_combined_prompts_one(db_path, question, knowledge)`**: dựng prompt.

- `generate_schema_prompt(db_path)`: mở CSDL, đọc `sqlite_master`, lấy câu `CREATE TABLE` của mọi bảng (bỏ `sqlite_sequence`), nối bằng dòng trống. Không kèm dữ liệu mẫu.
- `generate_comment_prompt(question, knowledge)`:
  - `knowledge` rỗng → `-- Using valid SQLite, answer the following questions for the tables provided above.\n-- <question>`
  - Có `knowledge` → `-- External Knowledge: <knowledge>\n-- Using valid SQLite and understading External Knowledge, answer ...\n-- <question>`
- Ghép lại, khác nhau ở phần đuôi:

| Script | Prompt |
|---|---|
| `openai_request.py` | `schema + '\n\n' + comment + '\nGenerate the SQL after thinking step by step: ' + '\nSELECT '` (đúng như code gốc của paper) |
| `ollama_request.py` | `schema + '\n\n' + comment + '\nRespond with the final SQLite query only, inside a ```sql code block. Do not add any explanation.'` |

**4.2. Gọi model**

| Hàm | Tham số | Ý nghĩa |
|---|---|---|
| `call_openai(client, model, prompt, max_retries=5, max_tokens=256)` | `temperature=0` | Luôn chọn token có xác suất cao nhất → kết quả ổn định |
| | `max_tokens=256` | Giới hạn độ dài câu trả lời (giống paper) |
| | `stop=['--', '\n\n', ';', '#']` | Dừng sinh khi gặp các chuỗi này (giống paper) |
| | `max_retries=5` | Gặp lỗi 429 (rate limit) thì chờ rồi thử lại tối đa 5 lần |
| `call_ollama(model, prompt, max_retries=3, timeout=120)` | `temperature=0` | Như trên; gửi POST đến Ollama server trên Kaggle |
| | `timeout=120` | Mỗi lần gọi chờ tối đa 120 giây |

Đầu ra `raw`: chuỗi model trả về.

**4.3. `extract_sql(raw)`**: tách câu SQL ra khỏi `raw`.
- Bản Ollama: bỏ `<think>…</think>` nếu có, lấy nội dung trong khối ```` ```sql … ``` ````, cắt ở dấu `;` đầu tiên.
- Bản OpenAI: tương tự, nhưng bỏ chữ `SELECT` ở đầu (nếu có) rồi thêm lại `SELECT `, mô phỏng cách code gốc ghép `'SELECT' + phần model viết tiếp`.
- Model không trả gì → trả về `"SELECT"`. Câu này sẽ bị tính sai ở bước chấm.

**4.4. Ghép kết quả**: `sql + '\t----- bird -----\t' + db_id`. Chuỗi phân cách này được `package_sqls` ở A2 dùng để tách lại.

Gặp lỗi bất kỳ (mạng, hết lượt thử lại) thì câu đó nhận `sql = "SELECT"`, vòng lặp chạy tiếp.

#### Bước 5: `generate_sql_file(sql_lst, output_path)`
Ghi `predict_dev.json` dạng:

```json
{
    "0": "SELECT ... \t----- bird -----\tcalifornia_schools",
    "1": "SELECT ... \t----- bird -----\tcalifornia_schools"
}
```

Khoá là số thứ tự câu trong `dev.json` (0 → 1533).

---

### A2. Chấm EX: `evaluation.py` (bộ chấm gốc, không sửa)

**Lệnh chạy** (từ `bird/llm/`):

```bash
python src/evaluation.py \
    --predicted_sql_path ./exp_result/openai_output/ \
    --ground_truth_path ./data/ \
    --data_mode dev \
    --db_root_path ../data/dev_databases/ \
    --diff_json_path ../data/dev.json \
    --num_cpus 8 --meta_time_out 30.0
```

| Tham số | Ý nghĩa |
|---|---|
| `--predicted_sql_path` | Thư mục chứa `predict_dev.json` (phải có `/` ở cuối vì code nối chuỗi) |
| `--ground_truth_path` | Thư mục chứa `dev_gold.sql` |
| `--data_mode` | `dev`: dùng để ghép tên file `predict_dev.json`, `dev_gold.sql` |
| `--db_root_path` | Thư mục CSDL (có `/` ở cuối) |
| `--diff_json_path` | `dev.json`, chỉ dùng để lấy độ khó `simple/moderate/challenging` của từng câu |
| `--num_cpus` | Số tiến trình chạy song song |
| `--meta_time_out` | Thời gian tối đa cho mỗi câu (giây); quá thời gian tính là sai |
| `--mode_predict` / `--mode_gt` | `gpt` / `gt`: cách đọc file dự đoán / file đáp án |

**Chuỗi gọi hàm:**

```
main
 ├─1─ package_sqls(predicted_sql_path, db_root_path, mode='gpt', data_mode='dev') → pred_queries, db_paths
 ├─2─ package_sqls(ground_truth_path,  db_root_path, mode='gt',  data_mode='dev') → gt_queries, _
 ├─3─ query_pairs = zip(pred_queries, gt_queries)
 ├─4─ run_sqls_parallel(query_pairs, db_paths, num_cpus, meta_time_out)
 │      mỗi cặp i (song song):
 │       └─ execute_model(predicted_sql, ground_truth, db_place, idx, meta_time_out) → {'sql_idx': i, 'res': 0|1}
 │            └─ execute_sql(predicted_sql, ground_truth, db_path)                  → 0|1
 ├─5─ sort_results(exec_result)                       → kết quả theo đúng thứ tự câu
 ├─6─ compute_acc_by_diff(exec_result, diff_json_path) → EX simple, moderate, challenging, total
 └─7─ print_data(score_lists, count_lists)            → in bảng
```

| Hàm | Tham số và ý nghĩa | Đầu ra |
|---|---|---|
| `package_sqls(sql_path, db_root_path, mode, data_mode)` | `mode='gpt'`: đọc `predict_dev.json`, tách mỗi dòng bằng `'\t----- bird -----\t'` thành (sql, db_name). `mode='gt'`: đọc `dev_gold.sql`, mỗi dòng tách bằng `\t` | `clean_sqls` (list SQL), `db_path_list` (list đường dẫn CSDL) |
| `run_sqls_parallel(sqls, db_places, num_cpus, meta_time_out)` | `sqls`: list cặp (pred, gold); `db_places`: CSDL của từng câu | Không trả về; kết quả được `result_callback` thêm vào biến toàn cục `exec_result` |
| `execute_model(predicted_sql, ground_truth, db_place, idx, meta_time_out)` | Bọc `execute_sql` trong `func_timeout`. Hết giờ hoặc SQL lỗi → `res = 0` | `{'sql_idx': idx, 'res': 0 hoặc 1}` |
| `execute_sql(predicted_sql, ground_truth, db_path)` | Chạy cả hai câu trên cùng CSDL, `fetchall()` | `1` nếu `set(kết quả pred) == set(kết quả gold)`, ngược lại `0` |
| `compute_acc_by_diff(exec_results, diff_json_path)` | Chia kết quả theo `difficulty` trong `dev.json` | `simple_acc, moderate_acc, challenging_acc, all_acc` (đơn vị %), `count_lists` |

Lưu ý về cách so: EX so **tập** kết quả, nên không phân biệt thứ tự dòng và số dòng trùng nhau. Tên cột không được so.

---

### A3. Chấm VES: `evaluation_ves.py` (bộ chấm gốc, không sửa)

Lệnh chạy giống A2, đổi tên script và thêm `--iterate_num 5`.

Chuỗi gọi hàm giống A2, khác ở các hàm sau:

| Hàm | Tham số và ý nghĩa | Đầu ra |
|---|---|---|
| `execute_model(predicted_sql, ground_truth, db_place, idx, iterate_num, meta_time_out)` | Thời gian tối đa = `meta_time_out × iterate_num` | `{'sql_idx': idx, 'time_ratio': số thực}` |
| `iterated_execute_sql(predicted_sql, ground_truth, db_path, iterate_num)` | Chạy hai câu một lần để so kết quả. **Sai → `time_ratio = 0`**. Đúng → chạy lại mỗi câu `iterate_num` lần, mỗi lần lấy `t_gold / t_pred` | Trung bình các tỉ lệ sau khi `clean_abnormal` |
| `execute_sql(sql, db_path)` | Đo thời gian chạy một câu SQL | Số giây |
| `clean_abnormal(input)` | Loại các giá trị nằm ngoài khoảng trung bình ± 3 độ lệch chuẩn | List đã lọc |
| `compute_ves(exec_results)` | `VES = Σ sqrt(time_ratio) × 100 / tổng số câu` | Số điểm VES |
| `compute_ves_by_diff(exec_results, diff_json_path)` | Như `compute_acc_by_diff` | VES theo 3 độ khó và tổng |

Ý nghĩa: câu sai đóng góp 0 điểm. Câu đúng và chạy nhanh bằng gold đóng góp 100. Câu đúng mà chạy nhanh gấp 4 lần gold đóng góp 200, chạy chậm gấp 4 lần thì được 50. Vì VES phụ thuộc thời gian chạy, số liệu dao động nhẹ giữa các lần chấm.

`iterate_num` phải ≥ 2. Nếu bằng 1, `clean_abnormal` có thể loại hết mẫu và VES về 0.

---

### A4. Chấm theo 6 mức: `app/scripts/ex_ves_by_category.py`

**Lệnh chạy:** `python app/scripts/ex_ves_by_category.py [--db_id student_club|all] [--group level|tag] [--skip_ves]`

| Tham số | Mặc định | Ý nghĩa |
|---|---|---|
| `--bird_root` | tự tìm | Thư mục `bird/` (trên Kaggle tự tìm trong `/kaggle/input`) |
| `--eval_src` | `<bird>/llm/src` | Nơi import `evaluation.py`, `evaluation_ves.py` |
| `--db_root_path` | `<bird>/data/dev_databases` | Thư mục CSDL |
| `--exp_dir` | `<bird>/llm/exp_result` | Thư mục chứa các lượt `predict_dev.json` |
| `--db_id` | `student_club` | Chỉ chấm câu thuộc CSDL này; `all` = cả 1.534 câu |
| `--group` | `level` | `level`: mỗi câu thuộc đúng 1 mức (mức cao nhất). `tag`: câu được tính vào mọi nhãn nó có |
| `--num_cpus` | 4 | Số tiến trình |
| `--meta_time_out` | 30 | Như A2 |
| `--iterate_num` | 5 | Như A3 |
| `--skip_ves` | tắt | Chỉ chấm EX |
| `--out_dir` | `docs/pttk/data` | Nơi ghi kết quả |

**Chuỗi gọi hàm:**

```
main
 ├─1─ find_bird_root()                                            → đường dẫn bird/
 ├─2─ import evaluation, evaluation_ves                           (bộ chấm gốc)
 ├─3─ evaluation.package_sqls(<bird>/llm/data/, ..., mode='gt')   → gold_sqls
 ├─4─ với mỗi câu i thuộc db_id:  classify(gold_sqls[i])          → {'tags', 'level', ...}
 ├─5─ categories(questions, group)                                → [(key, tên mức, [chỉ số câu])]
 ├─6─ với mỗi model × {có, không} evidence (MODEL_FOLDERS):
 │       score_run(evaluation, evaluation_ves, pred_dir, idxs, gold_sqls, args)
 │         ├─ evaluation.package_sqls(pred_dir, ..., mode='gpt')   → preds, pred_dbs
 │         ├─ evaluation.execute_model(...)      cho mọi câu       → res (EX)
 │         └─ evaluation_ves.execute_model(...)  cho mọi câu       → time_ratio (VES)
 │       → {idx: (res, time_ratio)}
 ├─7─ ghi per_question_<db>.csv
 ├─8─ với mỗi mức: EX = 100 × số câu đúng / số câu;  VES = evaluation_ves.compute_ves(...)
 └─9─ ghi ex_ves_by_category_<db>.csv và .xlsx (mỗi mức 2 sheet: EX, VES)
```

**`classify(sql)`** (`app/scripts/sql_category.py`): tách SQL đáp án thành token rồi gắn nhãn.

| Nhãn | Mức | Điều kiện |
|---|---|---|
| `SINGLE_TABLE` | 1 | Không có JOIN và chỉ đọc 1 bảng |
| `JOIN` | 2 | Có `JOIN` (không phải LEFT/RIGHT/FULL) hoặc kết ngầm `FROM a, b` |
| `SET_OP` | 3 | Có `UNION` / `INTERSECT` / `EXCEPT` / `MINUS` |
| `OUTER_JOIN` | 4 | Có `LEFT` / `RIGHT` / `FULL [OUTER] JOIN` |
| `GROUP_BY` | 5 | Có `GROUP BY` |
| `DIVISION` | 6 | Có ≥ 2 `NOT EXISTS`, hoặc `NOT EXISTS` + `EXCEPT`, hoặc `HAVING COUNT(...) = (SELECT COUNT ...)` |
| `NESTED` | (phụ) | Có `(SELECT ...)` lồng bên trong |

Đầu ra: `{'tags': [...], 'level': mức lớn nhất trong các nhãn (0 nếu không có nhãn nào), 'tables': [...], 'nested': bool}`.

`score_run` gọi thẳng `execute_model` thay vì chạy cả `evaluation.py`, vì `compute_acc_by_diff` gốc chia cho số câu của từng độ khó. Một tập con thiếu hẳn một độ khó sẽ gây lỗi chia cho 0.

---

## B. Luồng demo ClubQuery

```
Trình duyệt (app.js)
   │  POST /api/ask  {question, mode, model_id, run_id, dev_question_id, use_evidence, use_glossary}
   ▼
main.ask(body, user, conn)
   ▼
service.ask(conn, user, question, mode, ...)
   ├─1─ đọc câu dev (nếu chọn câu mẫu)
   ├─2─ lấy SQL
   │     ├─ replay: đọc predicted_sql đã lưu
   │     └─ live:   match_glossary → normalize_pseudo_sql → prompt.build_prompt → llm.generate_sql
   ├─3─ guard.check_select(sql)
   ├─4─ guard.execute(sql, role)                       → columns, rows
   ├─5─ answer.make_answer(question, columns, rows, model) → câu trả lời tiếng Việt
   ├─6─ (có câu dev) chạy gold SQL, same_result       → is_correct
   └─7─ ghi query_log
   ▼
JSON trả về trình duyệt → renderResult()
```

### B0. Trình duyệt gửi yêu cầu

Khi người dùng bấm **Hỏi**, `app.js` gửi `POST /api/ask`. Body là `AskIn` (`main.py`):

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `question` | str | Câu hỏi tự gõ. Bỏ trống nếu chọn câu mẫu |
| `mode` | `live` / `replay` | `live` = gọi model ngay; `replay` = dùng SQL đã sinh lúc benchmark |
| `model_id` | int | (live) Model trong bảng `model_config` |
| `run_id` | int | (replay) Lượt benchmark (model × cấu hình evidence) |
| `dev_question_id` | int | `question_id` của câu mẫu trong BIRD dev (1312–1469) |
| `use_evidence` | bool | Ô "Dùng evidence của câu mẫu" |
| `evidence` | str | Evidence tự nhập (khi không chọn câu mẫu) |
| `use_glossary` | bool | Ô "Áp dụng từ điển nghiệp vụ" |

Header `Authorization` mang token đăng nhập. `current_user()` đọc token và trả về `user` (gồm `id`, `role`).

### B1. `main.ask(body, user, conn)`
- Không có `question` lẫn `dev_question_id` → lỗi 422.
- Gọi `service.ask(conn, user, body.question or '', body.mode, body.model_id, body.run_id, body.dev_question_id, body.use_evidence, body.evidence, body.use_glossary)`.
- `ValueError` (model không tồn tại, câu dev không có…) → lỗi 422.

### B2. `service.ask(...)`

| Tham số | Ý nghĩa |
|---|---|
| `conn` | Kết nối tới `app/data/app.sqlite` (dữ liệu ứng dụng: người dùng, model, câu dev, benchmark, nhật ký) |
| `user` | Người đang hỏi; `user['role']` ∈ `member`, `board`, `admin` |
| Các tham số còn lại | Như bảng ở B0 |

Hàm tạo dict `out` (kết quả trả về), rồi làm lần lượt:

**Bước 1. Đọc câu dev.** Nếu có `dev_question_id`: đọc dòng trong bảng `dev_question` (có `question`, `evidence`, `gold_sql`); `question` được thay bằng câu hỏi gốc.

**Bước 2a. `mode = 'replay'`.** Đọc `benchmark_item.predicted_sql` của lượt `run_id` và câu `dev_question_id`. Không gọi model.

**Bước 2b. `mode = 'live'`.**

1. Đọc model trong `model_config` (`is_active = 1`). Mỗi model có: `provider`, `model_tag` (ví dụ `gpt-3.5-turbo`), `base_url` (Ollama: `http://localhost:11434/v1`), `api_key_env` (ví dụ `OPEN_AI_KEY`).
2. Ghép phần knowledge `parts`:
   - Có câu dev và `use_evidence` → thêm `dev_q['evidence']`.
   - Không có câu dev nhưng có `evidence` tự nhập → thêm evidence đó.
   - `use_glossary` → `match_glossary(conn, question)`: lấy các thuật ngữ đang bật trong `glossary_term` có xuất hiện trong câu hỏi (so chữ thường). Mỗi thuật ngữ thêm thành `"<term> refers to <definition>"`.
3. `knowledge = normalize_pseudo_sql('; '.join(parts))` (giống A1 bước 3). Lưu vào `out['evidence_used']`. Không có phần nào thì `knowledge = None`.
4. `prompt.build_prompt(question, knowledge, role)`:
   - `schema_prompt(role)`: đọc `CREATE TABLE` từ `student_club.sqlite`, **bỏ bảng và cột vai trò không được xem** (vai trò `member`: bỏ bảng `budget`, `expense`, `income`, bỏ cột `member.email`, `member.phone`). Có cache theo vai trò.
   - `comment_prompt(question, knowledge)`: giống `generate_comment_prompt` ở A1.
   - Ghép `schema + '\n\n' + comment + '\nRespond with the final SQLite query only, inside a ```sql code block. Do not add any explanation.'` (giống `ollama_request.py`).
5. `llm.generate_sql(model, prompt, timeout_s=120)`:
   - `llm.complete(model, prompt, max_tokens=512, timeout_s=120)`: tạo `OpenAI(api_key, base_url)` và gọi `chat.completions.create(model=model_tag, messages=[{'role':'user','content':prompt}], temperature=0, max_tokens=512)`. Cùng một client dùng cho cả OpenAI, Groq và Ollama vì cả ba đều có API tương thích OpenAI.
   - `extract_sql(raw)`: **import từ `ollama_request.py`**, tức là cùng hàm tách SQL với benchmark Ollama.
   - Lỗi gọi model → `LLMError` → trạng thái `FAILED_GENERATION`.

**Bước 3. `guard.check_select(sql)`** (lớp kiểm tra thứ nhất, kiểm tra trên chuỗi):
- Dùng `sqlparse.split` tách câu. Rỗng → `FAILED_GENERATION`. Nhiều hơn 1 câu → `REJECTED_UNSAFE`.
- Từ đầu tiên thuộc `INSERT, UPDATE, DELETE, DROP, ALTER, PRAGMA, ATTACH…` → `REJECTED_UNSAFE`.
- Từ đầu tiên không phải `SELECT` hoặc `WITH` → `FAILED_GENERATION`.
- Đầu ra: câu SQL đã bỏ dấu `;` cuối.

**Bước 4. `guard.execute(sql, role, timeout_s=10)`** (lớp kiểm tra thứ hai, chặn ngay trong SQLite):
- `connect_readonly()`: mở `student_club.sqlite` với `?mode=ro` (chỉ đọc).
- `conn.set_authorizer(_authorizer(role, denied))`: SQLite hỏi hàm này trước **mọi** thao tác. Chỉ cho `SELECT`, `READ`, `FUNCTION`, `RECURSIVE`. Đọc bảng hoặc cột bị cấm theo vai trò → từ chối.
- `conn.set_progress_handler(...)`: quá `QUERY_TIMEOUT_S = 10` giây thì ngắt truy vấn.
- Đầu ra: `(columns, rows)`. Lỗi được đổi thành trạng thái:

| Trạng thái | Khi nào |
|---|---|
| `REJECTED_PERMISSION` | Đọc bảng/cột vai trò không được xem |
| `REJECTED_UNSAFE` | Thao tác không phải đọc |
| `TIMEOUT` | Chạy quá 10 giây |
| `EXEC_ERROR` | SQL sai (sai tên cột, sai cú pháp…) |

Thành công: `status = 'EXECUTED'`. Chỉ trả về tối đa `MAX_ROWS = 1000` dòng (`truncated = True` nếu nhiều hơn).

**Bước 5. `answer.make_answer(question, columns, rows, model)`**:
- Live: `llm_answer(model, question, columns, rows)` gửi tối đa 30 dòng đầu cho model, yêu cầu trả lời 1–3 câu tiếng Việt, chỉ dựa trên dữ liệu. Nguồn ghi là `llm`.
- Replay, hoặc model lỗi: `template_answer(columns, rows)` dựng câu theo mẫu (`Kết quả: 12.`, `Có 5 kết quả: …`). Nguồn ghi là `template`.

**Bước 6. So với đáp án** (chỉ khi có câu dev, ở cả live lẫn replay):
- `guard.execute(dev_q['gold_sql'], 'admin', timeout_s=30)` chạy SQL đáp án với quyền admin.
- `same_result(rows, gold_rows)` = `set(rows) == set(gold_rows)`, **cùng tiêu chí với `execute_sql` của `evaluation.py`**.
- `is_correct = 1/0`. Bị chặn vì phân quyền thì `is_correct = None` (không phải lỗi của model). Các lỗi khác tính là sai, giống BIRD.

**Bước 7. Ghi nhật ký.** Mọi câu hỏi, kể cả bị từ chối, đều ghi vào bảng `query_log`: người hỏi, câu hỏi, chế độ, model, evidence đã dùng, thuật ngữ đã dùng, SQL, câu trả lời, trạng thái, lỗi, thời gian xử lý (`latency_ms`), số dòng, `is_correct`.

### B3. Kết quả trả về trình duyệt

| Trường | Ý nghĩa |
|---|---|
| `status` | `EXECUTED` hoặc một trạng thái lỗi ở trên |
| `sql` | SQL model sinh ra (hoặc SQL phát lại) |
| `columns`, `rows`, `row_count`, `truncated` | Bảng kết quả |
| `answer`, `answer_source` | Câu trả lời tiếng Việt, nguồn `llm` / `template` |
| `evidence_used`, `glossary_used` | Evidence thực sự đã đưa vào prompt (sau khi chuẩn hoá), các thuật ngữ đã áp dụng |
| `gold_sql`, `is_correct` | SQL đáp án và nhãn Đúng/Sai (khi có câu dev) |
| `error` | Thông báo lỗi |
| `latency_ms`, `log_id` | Thời gian xử lý, mã nhật ký |

`renderResult()` trong `app.js` hiển thị các trường này.

---

## C. Ví dụ: câu 1379 đi qua hai luồng

Câu hỏi: `How many meeting events were held in 2020?` (CSDL `student_club`, độ khó `simple`, mức 1 – một bảng)

| Bước | Hàm | Giá trị |
|---|---|---|
| A1-2 | `decouple_question_schema` | `question` = câu trên; `db_path` = `../data/dev_databases/student_club/student_club.sqlite`; `knowledge` = `meeting events refers to type = 'Meeting'; held in 2020 refers to YEAR(event_date) = 2020` |
| A1-3 | `normalize_pseudo_sql` (chỉ khi `--normalize_evidence`) | `... held in 2020 refers to CAST(STRFTIME('%Y', event_date) AS INTEGER) = 2020` |
| A1-4.1 | `generate_combined_prompts_one` | Prompt khoảng 2.600 ký tự: 8 câu `CREATE TABLE` (event, major, zip_code, attendance, budget, expense, income, member) + phần dưới đây |
| A1-4.2 | `call_ollama` / `call_openai` | `raw` = ví dụ ```` ```sql\nSELECT COUNT(*) FROM event WHERE type = 'Meeting' AND STRFTIME('%Y', event_date) = '2020';\n``` ```` |
| A1-4.3 | `extract_sql` | `SELECT COUNT(*) FROM event WHERE type = 'Meeting' AND STRFTIME('%Y', event_date) = '2020'` |
| A1-4.4 | ghép | `"1379": "SELECT COUNT(*) ... = '2020'\t----- bird -----\tstudent_club"` |
| A2 | `execute_sql` | Gold: `SELECT COUNT(event_id) FROM event WHERE type = 'Meeting' AND SUBSTR(event_date, 1, 4) = '2020'`. Hai câu cùng ra một con số → `res = 1` |
| A3 | `iterated_execute_sql` | Chạy mỗi câu 5 lần, `time_ratio` ≈ 1 → đóng góp ≈ 100 vào VES |
| A4 | `classify(gold)` | `{'tags': ['SINGLE_TABLE'], 'level': 1, 'tables': ['event']}` → tính vào mức 1 |
| B2-2b | `service.ask` (live, `thuquy`, tick evidence, bỏ tick từ điển) | `evidence_used` = evidence đã chuẩn hoá như dòng A1-3 |
| B2-2b | `prompt.build_prompt` | Giống hệt prompt A1-4.1 của `ollama_request.py` khi có `--normalize_evidence` |
| B2-3, 4 | `check_select`, `execute` | `status = EXECUTED`, `columns = ['COUNT(*)']`, `rows = [[n]]` |
| B2-5 | `make_answer` | Ví dụ: "Năm 2020 câu lạc bộ đã tổ chức n buổi họp." |
| B2-6 | `same_result` | So với kết quả gold → `is_correct = 1` |

Phần cuối của prompt (sau các câu `CREATE TABLE`):

```
-- External Knowledge: meeting events refers to type = 'Meeting'; held in 2020 refers to CAST(STRFTIME('%Y', event_date) AS INTEGER) = 2020
-- Using valid SQLite and understading External Knowledge, answer the following questions for the tables provided above.
-- How many meeting events were held in 2020?
Respond with the final SQLite query only, inside a ```sql code block. Do not add any explanation.
```

Không có evidence (bỏ tick, hoặc `--no_knowledge`) thì dòng `External Knowledge` biến mất, câu nhắc đổi thành `-- Using valid SQLite, answer the following questions for the tables provided above.` Khi đó model phải tự đoán "meeting events" ứng với cột nào, giá trị nào.

> Câu trả lời của model ở bảng trên chỉ là ví dụ minh hoạ, không phải kết quả đã chạy. Khi demo, lấy SQL thật trên màn hình.
