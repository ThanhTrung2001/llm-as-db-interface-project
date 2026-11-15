# Luồng Benchmark BIRD và luồng Text-to-SQL — mô tả từng bước

Sơ đồ đi kèm: [diagrams/benchmark_text2sql_flow.drawio](diagrams/benchmark_text2sql_flow.drawio) (mở bằng draw.io / diagrams.net). Số bước trong tài liệu này trùng với số bước trên sơ đồ.

## Bức tranh toàn cảnh

```
 ┌─────────────────────┐     ┌──────────────────────────┐     ┌──────────────────┐     ┌─────────────────┐
 │ PHẦN 1              │     │ PHẦN 2A                  │     │ PHẦN 2B          │     │ PHẦN 2C         │
 │ Chuẩn bị dữ liệu    │ ──► │ Sinh SQL cho 1.534 câu   │ ──► │ Chấm điểm        │ ──► │ Bảng kết quả    │
 │ (tải + phân tích    │     │ (có / không evidence)    │     │ EX  và  VES      │     │ nhiều model     │
 │  tập dev)           │     │ → predict_dev.json       │     │                  │     │                 │
 └─────────────────────┘     └──────────────────────────┘     └──────────────────┘     └─────────────────┘
                                         │ dùng chung phần "dựng prompt → gọi LLM → tách SQL"
                                         ▼
                             ┌──────────────────────────────────────────────────────────────┐
                             │ PHẦN 3 — Text-to-SQL (ứng dụng ClubQuery)                     │
                             │ 1 câu hỏi → SQL → kiểm tra an toàn → chạy → trả lời → so gold │
                             │ → hiển thị lên giao diện                                      │
                             └──────────────────────────────────────────────────────────────┘
```

**Hai khái niệm cần nắm trước:**

- **Evidence (knowledge)**: một câu gợi ý do người làm bộ dữ liệu viết sẵn cho mỗi câu hỏi, cho biết từ ngữ trong câu hỏi ứng với cột / giá trị nào trong CSDL. Ví dụ: *"meeting events refers to type = 'Meeting'"*.
- **With knowledge / Without knowledge**: chạy benchmark **có** đưa evidence vào prompt hay **không**. Paper chạy cả hai để đo xem evidence giúp model được bao nhiêu. Mỗi cách cho ra 2 điểm (EX, VES), nên mỗi model có 4 con số.

**Ví dụ xuyên suốt tài liệu:** câu số **1379** trong tập dev.

| | |
|---|---|
| Câu hỏi | How many meeting events were held in 2020? |
| CSDL | `student_club` |
| Evidence | meeting events refers to type = 'Meeting'; held in 2020 refers to YEAR(event_date) = 2020 |
| SQL đáp án | `SELECT COUNT(event_id) FROM event WHERE type = 'Meeting' AND SUBSTR(event_date, 1, 4) = '2020'` |
| Độ khó | simple |

Quy ước đường dẫn: `bird/` = `src/DAMO-ConvAI/bird/`. Lệnh ở Phần 2 chạy từ thư mục `bird/llm/`.

---

# PHẦN 1. Chuẩn bị dữ liệu

```
 Bước 1            Bước 2                 Bước 3                    Bước 4
 Tải bộ dev  ──►   Xem cấu trúc   ──►     Phân tích, thống kê ──►   Xác định dữ liệu nào
 BIRD              từng file              (số câu, độ khó,           đi vào bước nào
                                           evidence, loại SQL)
```

### Bước 1. Tải bộ dev của BIRD

- **Làm gì:** lấy bộ dữ liệu chuẩn mà paper dùng để chấm.
- **Vào:** file `dev.zip` (bản `dev_20240627`) từ trang BIRD.
- **Xử lý:** giải nén vào `bird/data/`, rồi giải nén tiếp `dev_databases.zip` bên trong.
- **Ra:** 4 thành phần:

| Thành phần | Là gì |
|---|---|
| `dev.json` | 1.534 câu hỏi, mỗi câu kèm evidence, SQL đáp án và độ khó |
| `dev_gold.sql` (ở `bird/llm/data/`) | 1.534 dòng, mỗi dòng là SQL đáp án + tên CSDL, cách nhau bởi dấu tab |
| `dev_databases/` | 11 CSDL SQLite, mỗi CSDL một thư mục `<tên>/<tên>.sqlite` |
| `dev_tables.json` | Mô tả schema dạng JSON (chỉ để tham khảo) |

Không sửa bất kỳ file nào, để kết quả so sánh công bằng được với paper.

### Bước 2. Xem cấu trúc từng file

Mỗi câu trong `dev.json` có dạng:

```json
{
  "question_id": 1379,
  "db_id": "student_club",
  "question": "How many meeting events were held in 2020?",
  "evidence": "meeting events refers to type = 'Meeting'; held in 2020 refers to YEAR(event_date) = 2020",
  "SQL": "SELECT COUNT(event_id) FROM event WHERE type = 'Meeting' AND SUBSTR(event_date, 1, 4) = '2020'",
  "difficulty": "simple"
}
```

Dòng thứ 1379 trong `dev_gold.sql`:

```
SELECT COUNT(event_id) FROM event WHERE type = 'Meeting' AND SUBSTR(event_date, 1, 4) = '2020'	student_club
```

Thứ tự câu được giữ nguyên ở mọi nơi: câu thứ *i* trong `dev.json` = dòng thứ *i* trong `dev_gold.sql` = khoá `"i"` trong file kết quả `predict_dev.json` sau này.

### Bước 3. Phân tích tập dev

- **Làm gì:** hiểu tập dữ liệu trước khi chạy, để thiết kế thí nghiệm và giải thích kết quả sau này.
- **Vào:** `dev.json`, `dev_gold.sql`.
- **Xử lý:** đếm bằng Python (`json`, `collections.Counter`); phân loại SQL đáp án bằng `classify()` trong [app/scripts/sql_category.py](../app/scripts/sql_category.py).
- **Ra:**

| Thống kê | Kết quả |
|---|---|
| Tổng số câu | 1.534 câu, 11 CSDL |
| Theo độ khó | simple 925 · moderate 464 · challenging 145 |
| Theo CSDL | card_games 191 · codebase_community 186 · formula_1 174 · thrombosis_prediction 163 · student_club 158 · toxicology 145 · superhero 129 · european_football_2 129 · financial 106 · california_schools 89 · debit_card_specializing 64 |
| Evidence | 1.386 câu có, 148 câu để trống. Với 148 câu này, chạy "with" hay "without" thì prompt vẫn giống nhau |
| Evidence viết bằng hàm không có trong SQLite (`DIVIDE`, `SUBTRACT`, `YEAR`…) | 192 câu |
| Loại SQL đáp án | Chia 6 mức: 1 một bảng · 2 JOIN · 3 UNION/INTERSECT/EXCEPT · 4 LEFT/RIGHT JOIN · 5 GROUP BY · 6 phép chia (NOT EXISTS lồng nhau) |

### Bước 4. Dữ liệu nào đi vào bước nào

| Dữ liệu | Dùng ở |
|---|---|
| `question`, `evidence`, `db_id` trong `dev.json` | Phần 2A — dựng prompt |
| File `.sqlite` | Phần 2A — đọc cấu trúc bảng; Phần 2B — chạy SQL để chấm |
| `dev_gold.sql` | Phần 2B — đáp án |
| `difficulty` trong `dev.json` | Phần 2B — chia điểm theo độ khó |
| 158 câu của `student_club` | Phần 3 — câu mẫu trong ứng dụng |

---

# PHẦN 2A. Benchmark — sinh SQL cho 1.534 câu

Mục tiêu: với mỗi câu hỏi, nhờ LLM viết một câu SQL, rồi lưu cả 1.534 câu SQL vào file `predict_dev.json`.

```
 Bước 0   Chạy lệnh, chọn model và chọn CÓ / KHÔNG evidence
   │
 Bước 1   Đọc dev.json, tách thành 3 danh sách: câu hỏi · đường dẫn CSDL · evidence
   │      (nếu chạy "without" → xoá hết evidence)
   │
   │   ┌──────────── LẶP CHO TỪNG CÂU i = 0 … 1533 ───────────────────────────┐
   │   │ Bước 2   Lấy cấu trúc các bảng của CSDL (các câu CREATE TABLE)        │
   │   │ Bước 3   Viết phần câu hỏi (+ evidence nếu có)                        │
   │   │ Bước 4   Ghép bước 2 + bước 3 thành prompt hoàn chỉnh                 │
   │   │ Bước 5   Gửi prompt cho LLM, nhận câu trả lời                         │
   │   │ Bước 6   Tách lấy câu SQL ra khỏi câu trả lời                         │
   │   │ Bước 7   Gắn tên CSDL vào sau câu SQL, cất vào danh sách kết quả      │
   │   └───────────────────────────────────────────────────────────────────────┘
   │
 Bước 8   Ghi danh sách 1.534 câu SQL ra file predict_dev.json
```

Code: [bird/llm/src/openai_request.py](../src/DAMO-ConvAI/bird/llm/src/openai_request.py) cho GPT-3.5 (giữ đúng prompt của paper), [ollama_request.py](../src/DAMO-ConvAI/bird/llm/src/ollama_request.py) / `ollama_request2.py` cho các model chạy local (DeepSeek, Qwen, Gemma). Các file này có cùng các bước, chỉ khác ở bước 4, 5, 6.

---

### Bước 0. Chạy lệnh

- **Làm gì:** chọn model và chọn chạy có hay không có evidence.
- **Vào:** lệnh, ví dụ:

```bash
# GPT-3.5, CÓ evidence
python src/openai_request.py --model gpt-3.5-turbo \
    --eval_path ../data/dev.json --db_root_path ../data/dev_databases/ \
    --data_output_path ./exp_result/openai_output/predict_dev.json

# GPT-3.5, KHÔNG evidence: thêm --no_knowledge, đổi thư mục kết quả sang *_0_output
python src/openai_request.py --model gpt-3.5-turbo --no_knowledge \
    --eval_path ../data/dev.json --db_root_path ../data/dev_databases/ \
    --data_output_path ./exp_result/openai_0_output/predict_dev.json
```

| Tham số | Nghĩa |
|---|---|
| `--model` | Model dùng: `gpt-3.5-turbo`, hoặc tên model Ollama như `qwen2.5-coder:7b`, `deepseek-coder-v2:16b`, `gemma3:12b` |
| `--eval_path` | File câu hỏi `dev.json` |
| `--db_root_path` | Thư mục chứa 11 CSDL |
| `--data_output_path` | Nơi ghi kết quả. Quy ước: thư mục có đuôi `_0` là lượt **không** evidence |
| `--no_knowledge` | Bỏ evidence khỏi prompt (với model Ollama dùng `ollama_request2.py`, bản đầu không có cờ này) |
| `--limit N` | Chỉ chạy N câu đầu để thử |

- **Ra:** chương trình bắt đầu chạy, có sẵn kết nối tới model (khoá API của OpenAI đọc từ file `.env`; Ollama thì gọi tới `http://localhost:11434`).

---

### Bước 1. Đọc `dev.json` và tách dữ liệu

*Hàm: `json.load` rồi `decouple_question_schema(datasets, db_root_path)`*

- **Làm gì:** từ file câu hỏi, chuẩn bị đủ 3 thứ mà mỗi câu cần: câu hỏi, CSDL nào, evidence gì.
- **Vào:** file `dev.json` (1.534 câu) và thư mục CSDL.
- **Xử lý:**
  1. Đọc toàn bộ `dev.json` thành một danh sách 1.534 phần tử.
  2. Duyệt từng câu và tách ra 3 danh sách song song:
     - danh sách **câu hỏi** ← trường `question`
     - danh sách **đường dẫn CSDL** ← ghép `thư mục CSDL / db_id / db_id.sqlite`
     - danh sách **evidence** ← trường `evidence`
  3. **Chỗ rẽ nhánh CÓ / KHÔNG evidence:**
     - Chạy **có** evidence: giữ nguyên danh sách evidence.
     - Chạy **không** evidence (`--no_knowledge`): thay toàn bộ danh sách evidence bằng rỗng (`None`).
- **Ra:** 3 danh sách, mỗi danh sách 1.534 phần tử, cùng thứ tự với `dev.json`.

> **Ví dụ câu 1379**
> - câu hỏi = `How many meeting events were held in 2020?`
> - đường dẫn CSDL = `../data/dev_databases/student_club/student_club.sqlite`
> - evidence = `meeting events refers to type = 'Meeting'; held in 2020 refers to YEAR(event_date) = 2020` (chạy "without" thì = `None`)

Sau bước này, chương trình đi vào **vòng lặp** (hàm `collect_response`): lần lượt lấy câu 0, 1, 2, … 1533 và cho mỗi câu đi qua bước 2 → 7.

---

### Bước 2. Lấy cấu trúc các bảng của CSDL

*Hàm: `generate_schema_prompt(db_path)`*

- **Làm gì:** cho model biết CSDL có những bảng nào, cột nào. Model không nhìn thấy dữ liệu, chỉ thấy cấu trúc.
- **Vào:** đường dẫn CSDL của câu đang xét.
- **Xử lý:**
  1. Mở file `.sqlite`.
  2. Hỏi bảng hệ thống `sqlite_master` để lấy danh sách tên bảng (bỏ bảng nội bộ `sqlite_sequence`).
  3. Với mỗi bảng, lấy nguyên văn câu lệnh `CREATE TABLE` đã tạo ra bảng đó.
  4. Nối các câu `CREATE TABLE` lại, mỗi câu cách nhau một dòng trống.
- **Ra:** một đoạn văn bản gồm toàn bộ các câu `CREATE TABLE` (gọi là `schema_prompt`).

> **Ví dụ câu 1379** — CSDL `student_club` có 8 bảng, đoạn đầu:
> ```sql
> CREATE TABLE event (
>     event_id   TEXT constraint event_pk primary key,
>     event_name TEXT,
>     event_date TEXT,
>     type       TEXT,
>     ...
> )
>
> CREATE TABLE major ( ... )
> ... (còn zip_code, attendance, budget, expense, income, member)
> ```

---

### Bước 3. Viết phần câu hỏi (kèm evidence nếu có)

*Hàm: `generate_comment_prompt(question, knowledge)`*

- **Làm gì:** viết phần "đề bài" cho model: câu hỏi, và evidence nếu đang chạy "with".
- **Vào:** câu hỏi và evidence của câu đang xét (evidence có thể là `None`).
- **Xử lý:** chọn 1 trong 2 mẫu câu:
  - **Không có evidence** → 2 dòng:
    ```
    -- Using valid SQLite, answer the following questions for the tables provided above.
    -- <câu hỏi>
    ```
  - **Có evidence** → 3 dòng, thêm dòng `External Knowledge` lên đầu:
    ```
    -- External Knowledge: <evidence>
    -- Using valid SQLite and understading External Knowledge, answer the following questions for the tables provided above.
    -- <câu hỏi>
    ```
- **Ra:** đoạn "đề bài" (gọi là `comment_prompt`).

**Đây chính là chỗ tạo ra sự khác nhau giữa "with knowledge" và "without knowledge".** Mọi bước khác giống hệt nhau.

> **Ví dụ câu 1379, chạy CÓ evidence:**
> ```
> -- External Knowledge: meeting events refers to type = 'Meeting'; held in 2020 refers to YEAR(event_date) = 2020
> -- Using valid SQLite and understading External Knowledge, answer the following questions for the tables provided above.
> -- How many meeting events were held in 2020?
> ```
> **Chạy KHÔNG evidence:**
> ```
> -- Using valid SQLite, answer the following questions for the tables provided above.
> -- How many meeting events were held in 2020?
> ```
> Không có evidence, model phải tự đoán "meeting events" là cột `type` có giá trị `'Meeting'`, và "held in 2020" là lọc theo năm của `event_date`.

---

### Bước 4. Ghép thành prompt hoàn chỉnh

*Hàm: `generate_combined_prompts_one(db_path, question, knowledge)`*

- **Làm gì:** tạo văn bản cuối cùng gửi cho model.
- **Vào:** cấu trúc bảng (bước 2) và đề bài (bước 3).
- **Xử lý:** nối theo thứ tự: **cấu trúc bảng** + dòng trống + **đề bài** + **một câu dặn ở cuối**. Câu dặn khác nhau tuỳ script:
  - GPT-3.5 (`openai_request.py`, giữ đúng paper): `Generate the SQL after thinking step by step:` rồi xuống dòng viết sẵn chữ `SELECT `, để model viết tiếp phần còn lại.
  - Model Ollama (`ollama_request.py`): `Respond with the final SQLite query only, inside a ```sql code block. Do not add any explanation.`. Model chạy local hay giải thích dài dòng, nên phải dặn chỉ trả về SQL nằm trong khối code.
- **Ra:** `prompt`, một chuỗi văn bản.

> **Ví dụ câu 1379 (bản Ollama, có evidence)** — prompt đầy đủ:
> ```
> CREATE TABLE event ( ... )
> CREATE TABLE major ( ... )
> ... (8 bảng)
>
> -- External Knowledge: meeting events refers to type = 'Meeting'; held in 2020 refers to YEAR(event_date) = 2020
> -- Using valid SQLite and understading External Knowledge, answer the following questions for the tables provided above.
> -- How many meeting events were held in 2020?
> Respond with the final SQLite query only, inside a ```sql code block. Do not add any explanation.
> ```

---

### Bước 5. Gửi prompt cho LLM

*Hàm: `call_openai(...)` hoặc `call_ollama(...)`*

- **Làm gì:** nhờ model viết SQL.
- **Vào:** prompt (bước 4) và tên model.
- **Xử lý:**
  - Gửi prompt cho model dưới dạng một tin nhắn của người dùng.
  - Cài đặt cố định:
    - `temperature = 0`: model luôn chọn phương án chắc chắn nhất, nên chạy lại vẫn ra cùng kết quả.
    - GPT-3.5: tối đa 256 token; dừng khi gặp `--`, dòng trống, `;` hoặc `#` (giống paper), tức là dừng ngay khi viết xong câu SQL.
  - Lỗi mạng hoặc bị giới hạn tốc độ: chờ rồi thử lại (GPT tối đa 5 lần, Ollama tối đa 3 lần).
- **Ra:** câu trả lời thô của model (`raw`). Có thể kèm khối ```` ```sql ````, lời giải thích, hoặc đoạn suy nghĩ `<think>…</think>`.

> **Ví dụ câu 1379** (minh hoạ):
> ````
> ```sql
> SELECT COUNT(*) FROM event WHERE type = 'Meeting' AND STRFTIME('%Y', event_date) = '2020';
> ```
> ````

---

### Bước 6. Tách lấy câu SQL

*Hàm: `extract_sql(raw)`*

- **Làm gì:** lấy riêng câu SQL sạch từ câu trả lời thô, để chạy được trên CSDL.
- **Vào:** câu trả lời thô (bước 5).
- **Xử lý:**
  1. Xoá đoạn `<think>…</think>` nếu có.
  2. Nếu có khối ```` ```sql … ``` ```` thì chỉ lấy phần bên trong.
  3. Cắt tại dấu `;` đầu tiên (chỉ giữ một câu lệnh), bỏ khoảng trắng thừa.
  4. Riêng GPT-3.5: bảo đảm câu bắt đầu bằng `SELECT`, vì prompt đã viết sẵn chữ `SELECT` và model chỉ viết tiếp phần sau.
  5. Không lấy được gì thì trả về `"SELECT"`. Câu này sẽ bị chấm sai.
- **Ra:** một câu SQL sạch, không có dấu `;`.

> **Ví dụ câu 1379:**
> `SELECT COUNT(*) FROM event WHERE type = 'Meeting' AND STRFTIME('%Y', event_date) = '2020'`

Nếu bước 5 hoặc 6 bị lỗi (mạng, hết lượt thử lại…), câu đó nhận SQL `"SELECT"` và vòng lặp chạy tiếp câu sau, không dừng cả chương trình.

---

### Bước 7. Gắn tên CSDL và cất vào danh sách

- **Làm gì:** lưu kết quả của câu này, ghi kèm câu SQL thuộc CSDL nào để bước chấm biết chạy ở đâu.
- **Vào:** câu SQL (bước 6) và tên CSDL.
- **Xử lý:**
  - Tạo chuỗi `<SQL>` + `\t----- bird -----\t` + `<tên CSDL>`. Chuỗi phân cách đặc biệt này giúp bước chấm tách lại chính xác.
  - Thêm chuỗi vào danh sách kết quả.
  - Cứ sau 50 câu thì ghi tạm danh sách ra file, phòng khi phiên Kaggle bị ngắt giữa chừng.
- **Ra:** danh sách kết quả có thêm 1 phần tử. Quay lại **bước 2** với câu tiếp theo.

> **Ví dụ câu 1379:**
> `SELECT COUNT(*) FROM event WHERE type = 'Meeting' AND STRFTIME('%Y', event_date) = '2020'\t----- bird -----\tstudent_club`

---

### Bước 8. Ghi file `predict_dev.json`

*Hàm: `generate_sql_file(sql_lst, output_path)`*

- **Làm gì:** lưu kết quả cuối cùng của cả lượt chạy.
- **Vào:** danh sách 1.534 chuỗi kết quả, đường dẫn file.
- **Xử lý:** đánh số từng phần tử từ 0 đến 1533, ghi ra file JSON.
- **Ra:** file `predict_dev.json`:

```json
{
    "0":    "SELECT ... \t----- bird -----\tcalifornia_schools",
    "1379": "SELECT COUNT(*) FROM event WHERE type = 'Meeting' AND STRFTIME('%Y', event_date) = '2020'\t----- bird -----\tstudent_club",
    "1533": "..."
}
```

**Điều kiện sang Phần 2B:** file có đủ 1.534 khoá (câu lỗi vẫn có khoá, với SQL `"SELECT"`). Mỗi model có 2 file: một ở thư mục `*_output/` (có evidence), một ở `*_0_output/` (không evidence).

---

# PHẦN 2B. Chấm điểm EX và VES

Có 2 file chấm có sẵn của BIRD, dùng nguyên, không sửa:

| File | Tính gì | Câu hỏi nó trả lời |
|---|---|---|
| [evaluation.py](../src/DAMO-ConvAI/bird/llm/src/evaluation.py) | **EX** — Execution Accuracy | SQL của model có ra **đúng kết quả** như đáp án không? |
| [evaluation_ves.py](../src/DAMO-ConvAI/bird/llm/src/evaluation_ves.py) | **VES** — Valid Efficiency Score | Đã đúng rồi thì SQL của model chạy **nhanh hay chậm** so với đáp án? |

**"With" hay "without" do thư mục mình đưa vào quyết định:**

```
 exp_result/openai_output/predict_dev.json   ──► evaluation.py      ──► EX  with knowledge
                                             ──► evaluation_ves.py  ──► VES with knowledge

 exp_result/openai_0_output/predict_dev.json ──► evaluation.py      ──► EX  without knowledge
                                             ──► evaluation_ves.py  ──► VES without knowledge
```

Hai file chấm không biết lượt chạy có evidence hay không. Chúng chỉ so SQL trong `predict_dev.json` với đáp án.

## 2B-1. Chấm EX — `evaluation.py`

```
 Bước 1  Chạy lệnh
   │
 Bước 2  Đọc 1.534 SQL của model (predict_dev.json) và 1.534 SQL đáp án (dev_gold.sql)
   │
 Bước 3  Ghép thành 1.534 cặp (SQL model, SQL đáp án)
   │
   │   ┌──── CHẤM SONG SONG NHIỀU CẶP CÙNG LÚC ──────────────────────────────┐
   │   │ Bước 4  Với mỗi cặp: chạy cả 2 câu SQL trên cùng CSDL                │
   │   │ Bước 5  So 2 tập kết quả: giống nhau → 1 điểm, khác / lỗi / quá giờ → 0│
   │   └──────────────────────────────────────────────────────────────────────┘
   │
 Bước 6  Sắp xếp lại kết quả đúng thứ tự câu
   │
 Bước 7  Tính tỉ lệ câu đúng theo từng độ khó và toàn bộ → in bảng EX
```

### Bước 1. Chạy lệnh

```bash
python src/evaluation.py \
    --predicted_sql_path ./exp_result/openai_output/ \
    --ground_truth_path  ./data/ \
    --data_mode dev \
    --db_root_path ../data/dev_databases/ \
    --diff_json_path ../data/dev.json \
    --num_cpus 8 --meta_time_out 30.0
```

| Tham số | Nghĩa |
|---|---|
| `--predicted_sql_path` | Thư mục chứa `predict_dev.json` của model. **Đổi thư mục này để chấm "with" (`*_output/`) hay "without" (`*_0_output/`)**. Phải có `/` ở cuối |
| `--ground_truth_path` | Thư mục chứa `dev_gold.sql` |
| `--data_mode dev` | Dùng để ghép tên file: `predict_dev.json`, `dev_gold.sql` |
| `--db_root_path` | Thư mục 11 CSDL (có `/` cuối) |
| `--diff_json_path` | `dev.json`, chỉ để biết câu nào thuộc độ khó nào |
| `--num_cpus` | Số câu chấm song song cùng lúc |
| `--meta_time_out` | Mỗi câu được chạy tối đa bao nhiêu giây. Quá giờ thì tính sai |

### Bước 2. Đọc SQL của model và SQL đáp án

*Hàm: `package_sqls(...)`, gọi 2 lần*

- **Vào:** `predict_dev.json` và `dev_gold.sql`.
- **Xử lý:**
  - Với `predict_dev.json`: mỗi chuỗi được tách bằng `\t----- bird -----\t` thành (SQL, tên CSDL).
  - Với `dev_gold.sql`: mỗi dòng được tách bằng dấu tab thành (SQL, tên CSDL).
  - Từ tên CSDL tạo đường dẫn tới file `.sqlite`.
- **Ra:** danh sách 1.534 SQL của model, danh sách 1.534 SQL đáp án, danh sách đường dẫn CSDL.

### Bước 3. Ghép cặp

- **Xử lý:** ghép câu thứ *i* của model với đáp án thứ *i*.
- **Ra:** 1.534 cặp `(SQL model, SQL đáp án)`.

### Bước 4–5. Chạy và so sánh từng cặp

*Hàm: `run_sqls_parallel` → `execute_model` → `execute_sql`*

- **Làm gì:** biết từng câu đúng hay sai.
- **Vào:** một cặp SQL và đường dẫn CSDL.
- **Xử lý:**
  1. `run_sqls_parallel` chia 1.534 cặp cho nhiều tiến trình (`--num_cpus`) chạy cùng lúc cho nhanh.
  2. Với mỗi cặp, `execute_model` bấm giờ và gọi `execute_sql`:
     - Mở CSDL, chạy SQL của model, lấy toàn bộ kết quả.
     - Chạy SQL đáp án, lấy toàn bộ kết quả.
     - **So sánh hai tập kết quả** (`set(kết quả model) == set(kết quả đáp án)`):
       - giống nhau → **1** (đúng)
       - khác nhau → **0** (sai)
  3. Các trường hợp cũng bị tính **0**:
     - SQL của model lỗi (sai tên cột, sai cú pháp, dùng hàm SQLite không có…)
     - chạy quá `--meta_time_out` giây
     - SQL là `"SELECT"` (do lỗi ở bước sinh)
- **Ra:** mỗi câu một kết quả `{số thứ tự câu, 0 hoặc 1}`.

**So "tập kết quả" nghĩa là:** không quan tâm thứ tự các dòng, không quan tâm tên cột; chỉ cần các dòng dữ liệu giống nhau. Thứ tự các cột trong mỗi dòng thì phải giống.

> **Ví dụ câu 1379:**
> - SQL model: `SELECT COUNT(*) FROM event WHERE type = 'Meeting' AND STRFTIME('%Y', event_date) = '2020'` → kết quả `[(n,)]`
> - SQL đáp án: `SELECT COUNT(event_id) FROM event WHERE type = 'Meeting' AND SUBSTR(event_date, 1, 4) = '2020'` → kết quả `[(n,)]`
> - Hai câu viết khác nhau nhưng cùng ra một con số → **đúng (1)**.

### Bước 6. Sắp xếp lại

- Các tiến trình chạy song song nên xong theo thứ tự lộn xộn. `sort_results` sắp lại theo số thứ tự câu 0 → 1533.

### Bước 7. Tính điểm EX

*Hàm: `compute_acc_by_diff` → `print_data`*

- **Vào:** 1.534 kết quả 0/1 và độ khó của từng câu (từ `dev.json`).
- **Xử lý:**
  - Chia các câu thành 3 nhóm simple / moderate / challenging.
  - Mỗi nhóm: **EX = số câu đúng ÷ số câu trong nhóm × 100**.
  - Toàn bộ: **EX = số câu đúng ÷ 1.534 × 100**.
- **Ra:** bảng in ra màn hình:

```
                     simple    moderate   challenging   total
count                925       464        145           1534
accuracy             ...       ...        ...           47.78
```

Công thức: $EX = \dfrac{\text{số câu đúng}}{N} \times 100$, với $N = 1534$.

## 2B-2. Chấm VES — `evaluation_ves.py`

VES chấm giống EX, nhưng **câu đúng được thêm điểm nếu SQL của model chạy nhanh hơn đáp án, và bị trừ điểm nếu chạy chậm hơn**. Câu sai vẫn là 0.

```
 Bước 1–3  Giống EX (chạy lệnh, đọc SQL, ghép cặp)
   │
   │   ┌──── CHẤM SONG SONG ──────────────────────────────────────────────────┐
   │   │ Bước 4  Chạy 2 câu một lần, so kết quả. Sai → tỉ lệ = 0, dừng.        │
   │   │ Bước 5  Đúng → chạy lại mỗi câu 5 lần, mỗi lần đo thời gian,          │
   │   │         tính tỉ lệ = thời gian đáp án ÷ thời gian model               │
   │   │ Bước 6  Bỏ các lần đo bất thường, lấy trung bình → tỉ lệ R của câu    │
   │   └──────────────────────────────────────────────────────────────────────┘
   │
 Bước 7  Sắp xếp lại
   │
 Bước 8  Mỗi câu đóng góp √R × 100; VES = trung bình trên mọi câu → in bảng VES
```

### Bước 1. Chạy lệnh

Như EX, đổi tên file và thêm `--iterate_num 5`:

```bash
python src/evaluation_ves.py --predicted_sql_path ./exp_result/openai_output/ \
    --ground_truth_path ./data/ --data_mode dev --db_root_path ../data/dev_databases/ \
    --diff_json_path ../data/dev.json --num_cpus 8 --meta_time_out 30.0 --iterate_num 5
```

`--iterate_num`: số lần chạy lại mỗi câu để đo thời gian (paper dùng 5). Chạy nhiều lần để giảm sai số đo. Không được để bằng 1, vì khi đó bước 6 có thể loại hết số đo và VES về 0.

### Bước 2–3. Đọc SQL, ghép cặp

Giống hệt EX.

### Bước 4. Kiểm tra đúng / sai trước

*Hàm: `execute_model` → `iterated_execute_sql`*

- Chạy SQL model và SQL đáp án một lần, so tập kết quả như EX.
- **Sai** (hoặc lỗi, hoặc quá thời gian `meta_time_out × iterate_num`) → tỉ lệ **R = 0**, không đo thời gian nữa.
- **Đúng** → sang bước 5.

### Bước 5. Đo thời gian

*Hàm: `execute_sql(sql, db_path)`, gọi nhiều lần*

- Lặp `iterate_num` lần (5 lần). Mỗi lần:
  - chạy SQL model, đo số giây → `t_model`
  - chạy SQL đáp án, đo số giây → `t_đáp_án`
  - ghi lại tỉ lệ `t_đáp_án ÷ t_model`
- Tỉ lệ > 1: SQL model chạy nhanh hơn đáp án. Tỉ lệ < 1: chậm hơn.

### Bước 6. Bỏ số đo bất thường, lấy trung bình

*Hàm: `clean_abnormal`*

- Bỏ những lần đo lệch quá xa so với trung bình (ngoài khoảng trung bình ± 3 độ lệch chuẩn), ví dụ một lần máy bị chậm đột ngột.
- Lấy trung bình các tỉ lệ còn lại → **R** của câu đó.

### Bước 7. Sắp xếp lại

Giống EX.

### Bước 8. Tính điểm VES

*Hàm: `compute_ves_by_diff` → `compute_ves` → `print_data`*

- Mỗi câu đóng góp **√R × 100** điểm.
- **VES = tổng điểm các câu ÷ số câu**, tính cho từng độ khó và cho toàn bộ.

| Trường hợp của một câu | R | Điểm đóng góp |
|---|---|---|
| Sai / lỗi / quá giờ | 0 | 0 |
| Đúng, nhanh bằng đáp án | 1 | 100 |
| Đúng, nhanh gấp 4 lần đáp án | 4 | 200 |
| Đúng, chậm gấp 4 lần đáp án | 0,25 | 50 |

Công thức: $VES = \dfrac{1}{N}\sum_{n=1}^{N} \mathbb{1}(\text{câu } n \text{ đúng}) \cdot \sqrt{R_n} \times 100$

Hệ quả:
- VES có thể **cao hơn** EX nếu nhiều câu đúng chạy nhanh hơn đáp án.
- VES phụ thuộc thời gian chạy thật, nên mỗi lần chấm lệch nhau một chút.

> **Ví dụ câu 1379:** đúng ở bước 4; 5 lần đo cho tỉ lệ xấp xỉ 1 → R ≈ 1 → đóng góp ≈ 100 điểm.

---

# PHẦN 2C. Chạy nhiều model và lập bảng kết quả

```
 Với mỗi model ∈ { GPT-3.5-Turbo, DeepSeek-Coder-V2, Qwen2.5-Coder, Gemma3, ... }:

     Phần 2A (có evidence)    ──► *_output/predict_dev.json   ──► evaluation.py ─► EX  w/ KG
                                                              ──► evaluation_ves.py ─► VES w/ KG
     Phần 2A (--no_knowledge) ──► *_0_output/predict_dev.json ──► evaluation.py ─► EX  w/o KG
                                                              ──► evaluation_ves.py ─► VES w/o KG

     → ghi 4 con số vào exp_result/summary_ex_ves.csv
```

| Model | Script sinh SQL | Thư mục có evidence | Thư mục không evidence |
|---|---|---|---|
| GPT-3.5-Turbo (như paper) | `openai_request.py` | `openai_output/` | `openai_0_output/` |
| DeepSeek-Coder-V2 | `ollama_request2.py --model deepseek-coder-v2:16b` | `ollama_deepseekcoder_output/` | `ollama_deepseekcoder_0_output/` |
| Qwen2.5-Coder | `ollama_request2.py --model qwen2.5-coder:7b` | `ollama_gwen25_output/` | `ollama_gwen25_0_output/` |
| Gemma3 | `ollama_request2.py --model gemma3:12b` | `ollama_gemma3_output/` | `ollama_gemma3_0_output/` |

**Bảng kết quả (tập dev, 1.534 câu):**

| Model | EX w/o KG | EX w/ KG | VES w/o KG | VES w/ KG |
|---|---|---|---|---|
| ChatGPT — số trong paper BIRD | — | 37,22 | — | — |
| **GPT-3.5-Turbo — chạy lại** | **31,23** | **47,78** | **33,88** | **53,88** |
| DeepSeek-Coder-V2 | … | 42,11 | … | 45,80 |
| Qwen2.5-Coder | … | 53,85 | … | 59,83 |
| Gemma3 | … | 48,70 | … | 54,86 |

- `…` = chưa có, điền sau khi chấm các thư mục `*_0_output/`.
- Số "w/ KG" của 3 model Ollama lấy từ lượt đối chứng (ctrl) trong `exp_result/gap3/summary_gap3_ex_ves.csv`.
- Paper ghi 37,22; BIRD công bố 42,24 sau khi sửa lỗi tập dev (09/2023). Số chạy lại cao hơn một phần vì model GPT-3.5 đã được cập nhật.
- Đọc bảng: với GPT-3.5, có evidence tăng **+16,55 điểm EX** và **+20,00 điểm VES**. Evidence là yếu tố quyết định.

**Mở rộng:** [app/scripts/ex_ves_by_category.py](../app/scripts/ex_ves_by_category.py) tính EX/VES riêng cho từng mức trong 6 loại SQL (Phần 1, bước 3). Script này dùng lại đúng các hàm chấm của `evaluation.py` và `evaluation_ves.py`.

---

# PHẦN 3. Luồng Text-to-SQL — ứng dụng ClubQuery

Đây là luồng **một câu hỏi** của người dùng thật. Phần đầu giống Phần 2A (dựng prompt → gọi LLM → tách SQL). Khác ở chỗ: có SQL rồi thì **không ghi vào `predict_dev.json`**, mà kiểm tra an toàn, chạy thật trên CSDL, viết câu trả lời, so với đáp án (nếu là câu mẫu), rồi **hiển thị lên giao diện**.

```
 Bước 1   Người dùng nhập câu hỏi trên giao diện, bấm "Hỏi"
   │
 Bước 2   Backend nhận yêu cầu, kiểm tra đăng nhập, biết người hỏi có vai trò gì
   │
 Bước 3   Nếu chọn câu mẫu BIRD → lấy câu hỏi, evidence, SQL đáp án của câu đó
   │
 Bước 4   Lấy câu SQL ─┬─ 4a. Chế độ PHÁT LẠI: lấy SQL đã sinh sẵn lúc benchmark
   │                   └─ 4b. Chế độ TRỰC TIẾP:
   │                          4b.1 chọn model
   │                          4b.2 ghép evidence + từ điển nghiệp vụ
   │                          4b.3 dựng prompt (schema lọc theo vai trò)   ← giống bước 2–4 Phần 2A
   │                          4b.4 gọi LLM + tách SQL                       ← giống bước 5–6 Phần 2A
   │
 Bước 5   Kiểm tra an toàn: chỉ cho đúng 1 câu SELECT
   │
 Bước 6   Chạy SQL trên CSDL ở chế độ chỉ đọc, chặn bảng/cột không được xem
   │
 Bước 7   Viết câu trả lời tiếng Việt từ kết quả
   │
 Bước 8   (Nếu là câu mẫu) chạy SQL đáp án, so kết quả → Đúng / Sai   ← giống cách chấm EX
   │
 Bước 9   Ghi nhật ký
   │
 Bước 10  Trả kết quả về, hiển thị lên giao diện
```

Code: [app/frontend/app.js](../app/frontend/app.js) → [main.py](../app/backend/main.py) → [service.py](../app/backend/service.py) (điều phối) → [prompt.py](../app/backend/prompt.py), [llm.py](../app/backend/llm.py), [guard.py](../app/backend/guard.py), [answer.py](../app/backend/answer.py).

Ứng dụng dùng 2 CSDL:
- `student_club.sqlite`: dữ liệu câu lạc bộ, chính là CSDL trong BIRD; được truy vấn ở chế độ chỉ đọc.
- `app/data/app.sqlite`: dữ liệu của ứng dụng (tài khoản, danh sách model, câu mẫu, kết quả benchmark đã nạp, từ điển nghiệp vụ, nhật ký).

---

### Bước 1. Người dùng đặt câu hỏi

*`app.js`*

- **Làm gì:** người dùng nhập câu hỏi và các lựa chọn.
- **Vào (trên màn hình):**
  - gõ câu hỏi, **hoặc** chọn một câu mẫu BIRD của `student_club`
  - chọn chế độ: **Trực tiếp** (gọi model ngay) hay **Phát lại** (dùng SQL đã sinh lúc benchmark)
  - chọn model (trực tiếp) hoặc lượt benchmark (phát lại)
  - tick "Dùng evidence của câu mẫu", tick "Áp dụng từ điển nghiệp vụ"
- **Xử lý:** bấm **Hỏi** → trình duyệt gửi yêu cầu `POST /api/ask` kèm mã đăng nhập.
- **Ra:** yêu cầu gồm `question, mode, model_id, run_id, dev_question_id, use_evidence, evidence, use_glossary`.

### Bước 2. Backend nhận yêu cầu

*`main.py`: `current_user` → `ask`*

- **Làm gì:** biết ai đang hỏi và có quyền gì.
- **Xử lý:**
  - Từ mã đăng nhập tìm ra người dùng và **vai trò**: `member` (thành viên), `board` (ban điều hành), `admin`. Sai mã → báo lỗi 401.
  - Không có câu hỏi lẫn câu mẫu → báo lỗi 422.
  - Chuyển mọi thứ cho `service.ask`, nơi xử lý các bước 3–9.
- **Ra:** thông tin người dùng (có vai trò) và nội dung yêu cầu.

### Bước 3. Lấy thông tin câu mẫu (nếu có)

*`service.ask`*

- **Xử lý:** bắt đầu bấm giờ. Nếu người dùng chọn câu mẫu, đọc từ bảng `dev_question` 3 thứ: **câu hỏi**, **evidence**, **SQL đáp án**.
- **Ra:** câu hỏi cần trả lời; evidence và SQL đáp án (nếu là câu mẫu).

> **Ví dụ:** chọn câu 1379 → câu hỏi `How many meeting events were held in 2020?`, evidence và SQL đáp án như ở đầu tài liệu.

### Bước 4. Lấy câu SQL

#### 4a. Chế độ Phát lại

- **Làm gì:** xem lại SQL mà model đã sinh lúc chạy benchmark, không gọi model.
- **Xử lý:** tìm trong bảng `benchmark_item` SQL của lượt benchmark đã chọn, cho câu mẫu đã chọn. Các SQL này được nạp từ các file `predict_dev.json` của Phần 2A (qua script `per_db_ex.py` rồi màn hình Nhập benchmark).
- **Ra:** câu SQL. Chuyển sang bước 5.

#### 4b. Chế độ Trực tiếp

**4b.1. Chọn model**
- Đọc cấu hình model trong bảng `model_config`: tên model, địa chỉ API, khoá API. Ví dụ `gpt-3.5-turbo`, hoặc `qwen2.5-coder:7b` tại `http://localhost:11434/v1`.

**4b.2. Ghép evidence** (tương đương chỗ rẽ nhánh có/không evidence ở Phần 2A)
- Tick "Dùng evidence" và đang ở câu mẫu → lấy evidence của câu mẫu. Hoặc lấy evidence người dùng tự gõ.
- Tick "Từ điển nghiệp vụ" → tìm các thuật ngữ trong từ điển có xuất hiện trong câu hỏi, thêm dạng `<thuật ngữ> refers to <định nghĩa>`.
- Nối tất cả lại, và đổi các hàm không có trong SQLite sang cú pháp SQLite (ví dụ `YEAR(event_date)` → `CAST(STRFTIME('%Y', event_date) AS INTEGER)`).
- Không tick gì → không có evidence, giống chạy `--no_knowledge`.

> **Ví dụ câu 1379, có tick evidence:**
> `meeting events refers to type = 'Meeting'; held in 2020 refers to CAST(STRFTIME('%Y', event_date) AS INTEGER) = 2020`

**4b.3. Dựng prompt** (*`prompt.build_prompt`*, giống bước 2–4 của Phần 2A)
- Lấy các câu `CREATE TABLE` của `student_club`, **nhưng bỏ đi những bảng/cột mà vai trò của người hỏi không được xem**. Ví dụ thành viên thường không thấy bảng `budget`, `expense`, `income` và cột email, số điện thoại. Benchmark không có bước lọc này.
- Viết đề bài: dòng evidence (nếu có) + câu hỏi, cùng mẫu câu như bước 3 Phần 2A.
- Thêm câu dặn "chỉ trả về SQL trong khối ```sql".
- Kết quả: prompt. Với vai trò được xem đủ schema, prompt giống hệt prompt của benchmark.

**4b.4. Gọi LLM và tách SQL** (*`llm.generate_sql`*, giống bước 5–6 của Phần 2A)
- Gửi prompt cho model với `temperature = 0`.
- Tách SQL bằng **chính hàm `extract_sql` của benchmark**, import thẳng từ `ollama_request.py`.
- Model lỗi → trạng thái `FAILED_GENERATION`.

> **Ví dụ:** `SELECT COUNT(*) FROM event WHERE type = 'Meeting' AND STRFTIME('%Y', event_date) = '2020'`

### Bước 5. Kiểm tra an toàn (lớp 1)

*`guard.check_select`*

- **Làm gì:** không để model (hoặc người dùng) chạy lệnh phá dữ liệu. Benchmark không có bước này vì chỉ chạy trên bản sao để chấm điểm.
- **Xử lý:** đọc câu SQL dạng văn bản:
  - rỗng → `FAILED_GENERATION`
  - nhiều hơn 1 câu lệnh → `REJECTED_UNSAFE`
  - bắt đầu bằng `INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, PRAGMA, ATTACH…` → `REJECTED_UNSAFE`
  - không bắt đầu bằng `SELECT` hoặc `WITH` → `FAILED_GENERATION`
- **Ra:** câu SQL đã được chấp nhận.

### Bước 6. Chạy SQL (lớp 2)

*`guard.execute`*

- **Làm gì:** chạy câu SQL thật để lấy dữ liệu, và chặn thêm một lần nữa ngay trong CSDL.
- **Xử lý:**
  - Mở `student_club.sqlite` ở chế độ **chỉ đọc**.
  - Gắn bộ kiểm tra quyền: SQLite hỏi bộ này trước mọi thao tác; đọc bảng/cột mà vai trò không được xem → `REJECTED_PERMISSION`.
  - Chạy quá 10 giây → `TIMEOUT`. SQL sai (sai tên cột…) → `EXEC_ERROR`.
  - Lấy tên cột và các dòng kết quả (tối đa 1.000 dòng).
- **Ra:** tên cột + các dòng dữ liệu, trạng thái `EXECUTED`.

> **Ví dụ:** cột `COUNT(*)`, một dòng `[n]`.

**Nếu bước 4–6 có lỗi:** bỏ qua bước 7; với câu mẫu thì tính **Sai** (riêng lỗi do phân quyền thì không chấm, vì không phải lỗi của model); vẫn ghi nhật ký (bước 9) và hiển thị lỗi (bước 10).

| Trạng thái | Nghĩa |
|---|---|
| `EXECUTED` | Chạy thành công |
| `FAILED_GENERATION` | Model không sinh được SQL hợp lệ |
| `REJECTED_UNSAFE` | SQL có lệnh ghi/xoá hoặc nhiều câu lệnh |
| `REJECTED_PERMISSION` | SQL đọc dữ liệu mà người hỏi không được xem |
| `TIMEOUT` | Chạy quá 10 giây |
| `EXEC_ERROR` | SQL sai, CSDL báo lỗi |

### Bước 7. Viết câu trả lời

*`answer.make_answer`*

- **Làm gì:** biến bảng số liệu thành câu nói dễ hiểu.
- **Xử lý:**
  - Chế độ trực tiếp: gửi câu hỏi + tối đa 30 dòng kết quả đầu cho model, yêu cầu trả lời 1–3 câu tiếng Việt, chỉ dựa trên dữ liệu.
  - Chế độ phát lại, hoặc model lỗi: dùng câu mẫu có sẵn, ví dụ "Kết quả: 12." hoặc "Có 5 kết quả: …".
- **Ra:** câu trả lời và nguồn (`llm` hoặc `template`).

> **Ví dụ:** "Năm 2020 câu lạc bộ đã tổ chức n buổi họp."

### Bước 8. So với đáp án (chỉ khi là câu mẫu BIRD)

- **Làm gì:** cho người dùng biết model trả lời đúng hay sai, **cùng cách chấm EX** ở Phần 2B.
- **Xử lý:**
  - Chạy SQL đáp án (quyền admin, tối đa 30 giây).
  - So tập kết quả của model với tập kết quả của đáp án: giống → **Đúng**, khác → **Sai**.
  - Nếu chính SQL đáp án không chạy được → không chấm.
- **Ra:** SQL đáp án và nhãn Đúng / Sai / không chấm.

> **Ví dụ câu 1379:** đáp án cũng ra `[n]` → **Đúng**.

### Bước 9. Ghi nhật ký

- **Xử lý:** dừng bấm giờ; ghi vào bảng `query_log`: ai hỏi, câu hỏi, chế độ, model, evidence đã dùng, thuật ngữ đã dùng, SQL, câu trả lời, trạng thái, lỗi, thời gian xử lý, số dòng, Đúng/Sai. **Mọi câu hỏi đều được ghi, kể cả câu bị chặn.**
- **Ra:** mã nhật ký, thời gian xử lý.

### Bước 10. Hiển thị lên giao diện

*`renderResult()` trong `app.js`*

Backend trả kết quả về trình duyệt, màn hình hiển thị:

| Hiển thị | Lấy từ |
|---|---|
| Nhãn trạng thái (thành công / loại lỗi) | bước 5, 6 |
| Câu SQL model sinh ra | bước 4 |
| Bảng kết quả (tối đa 1.000 dòng) | bước 6 |
| Câu trả lời tiếng Việt | bước 7 |
| Evidence và thuật ngữ đã đưa vào prompt | bước 4b.2 |
| SQL đáp án + nhãn **Đúng / Sai** | bước 8 |
| Thời gian xử lý; nút phản hồi / xuất CSV | bước 9 |

---

## So sánh hai luồng

| | Benchmark (Phần 2) | Text-to-SQL (Phần 3) |
|---|---|---|
| Số câu mỗi lần chạy | 1.534 câu, chạy hàng loạt | 1 câu |
| Evidence | Có, hoặc không (`--no_knowledge`) | Evidence câu mẫu / tự gõ + từ điển nghiệp vụ |
| Cấu trúc bảng trong prompt | Toàn bộ | Lọc theo vai trò người hỏi |
| Dựng prompt, gọi LLM, tách SQL | Bước 2–6 | Bước 4b — cùng cách làm, cùng hàm `extract_sql` |
| Có SQL rồi thì | Ghi vào `predict_dev.json` | Kiểm tra an toàn → chạy chỉ đọc → viết câu trả lời |
| Chấm đúng/sai | `evaluation.py` (EX) + `evaluation_ves.py` (VES) cho cả tập | So tập kết quả từng câu (cùng cách EX) |
| Kết quả cuối | Điểm EX, VES | Câu trả lời + bảng dữ liệu + Đúng/Sai trên giao diện |
