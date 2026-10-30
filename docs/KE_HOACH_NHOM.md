# Kế hoạch nhóm — Text-to-SQL trên BIRD

> Các số liệu dưới đây lấy từ repo: `PROJECT_LOG.md`, `docs/ex_ves_by_category_kaggle.md`, `docs/pttk/data/*.csv`.
> Tên thành viên đang để là **TV1–TV4**, nhóm tự điền tên thật.

---

## 1. Làm rõ tiêu đề paper

### 1.1. Bài báo gốc

**"Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs"**
Li et al., NeurIPS 2023 (Datasets & Benchmarks), https://arxiv.org/abs/2305.03111

| Cụm từ trong tiêu đề | Nghĩa |
|---|---|
| *Can LLM Already Serve as A Database Interface?* | Câu hỏi nghiên cứu: LLM đã đủ tốt để người dùng hỏi CSDL bằng ngôn ngữ tự nhiên thay cho việc viết SQL chưa? |
| *BIg Bench* → **BIRD** | Tên bộ benchmark: 12.751 cặp câu hỏi–SQL, 95 CSDL thật, 37 lĩnh vực, tổng ~33,4 GB |
| *Large-Scale Database* | CSDL lớn, dữ liệu bẩn (giá trị rỗng, định dạng lệch), khác Spider vốn có CSDL nhỏ và sạch |
| *Grounded* | SQL phải chạy được trên dữ liệu thật và ra đúng kết quả, không chỉ đúng cú pháp |
| *Text-to-SQL* | Bài toán: câu hỏi ngôn ngữ tự nhiên → câu SQL |

Hai điểm mới của paper:
- **External knowledge (evidence):** mỗi câu hỏi có gợi ý nghiệp vụ, ví dụ `eligible free rate = Free Meal Count / Enrollment`.
- **Hai độ đo:** **EX** (Execution Accuracy: kết quả chạy SQL sinh ra trùng kết quả SQL đáp án) và **VES** (Valid Efficiency Score: EX có tính thêm tốc độ chạy, `sqrt(t_gold / t_pred)`).

Kết luận gốc: ChatGPT chỉ đạt 40,08% EX, con người 92,96% → LLM **chưa** đủ làm database interface.

### 1.2. Tiêu đề đồ án của nhóm (đề xuất)

**Tiếng Việt:** *Khảo nghiệm lại BIRD-SQL với các LLM hiện nay: đánh giá EX/VES theo 6 mức độ phức tạp truy vấn và tác động của chuẩn hoá evidence*

**Tiếng Anh:** *Revisiting BIRD-SQL with Current LLMs: Query-Complexity-Level EX/VES Evaluation and Evidence Normalization*

Giải thích:
- **Khảo nghiệm lại (Revisiting):** giữ nguyên prompt và bộ chấm `evaluation.py` / `evaluation_ves.py` của paper; chỉ thay các model đã ngừng hoạt động (Codex, các snapshot GPT-3.5 cũ, Claude-2, PaLM-2) bằng model còn dùng được.
- **LLM hiện nay:** GPT-3.5-Turbo (bản alias hiện tại, có trả phí), cùng 3 model mã nguồn mở chạy qua Ollama trên Kaggle: Qwen2.5-Coder 7B, DeepSeek-Coder-V2 16B, Gemma3 12B.
- **6 mức độ phức tạp:** (1) 1 bảng, (2) inner join, (3) union/intersect/except, (4) outer join, (5) group by, (6) phép chia. Paper chỉ chia simple/moderate/challenging theo cảm nhận người gán nhãn; nhóm chia lại theo **cấu trúc SQL** (`app/scripts/sql_category.py`).
- **Chuẩn hoá evidence (Gap 3):** đổi các hàm giả trong evidence (`DIVIDE`, `SUBTRACT`, `YEAR`…) sang SQLite hợp lệ trước khi đưa vào prompt.

### 1.3. Câu hỏi nghiên cứu

1. Sau 3 năm, LLM hiện nay đạt EX/VES bao nhiêu trên BIRD dev, so với số của paper?
2. Evidence giúp bao nhiêu (có so với không có knowledge)?
3. EX giảm thế nào khi truy vấn phức tạp hơn (theo 6 mức)?
4. Chuẩn hoá evidence có làm EX tăng không, và tăng có ý nghĩa thống kê không?

### 1.4. Phạm vi và giới hạn

- Dữ liệu: BIRD dev (bản `dev_20240627`, 1.534 câu, 11 CSDL). Không dùng bản dev viết lại 11/2025 vì độ khó câu hỏi đã khác, không còn so được với paper.
- Chấm theo 6 mức chủ yếu trên CSDL `student_club` (158 câu). **Giới hạn cần nêu trong báo cáo:** BIRD gần như không có câu thuộc mức 3, 4, 6. Trên toàn bộ 1.534 câu: mức 3 có 1 câu, mức 4 có 1 câu, mức 6 có 0 câu. Trên `student_club` thì cả 3 mức này đều có 0 câu.
- Không làm phần fine-tune T5 của paper: code thiếu `third_party/` và chỉ chạy được trên torch 1.7.

---

## 2. Phân công công việc (4 người)

| Người | Vai trò | Phần phụ trách |
|---|---|---|
| **TV1** | Trưởng nhóm, Benchmark | Sinh SQL bằng các model, chấm EX/VES toàn tập, tổng hợp bảng kết quả chính |
| **TV2** | Phân loại 6 mức, Gap 3 | `sql_category.py`, chấm EX/VES theo mức, thí nghiệm chuẩn hoá evidence, kiểm định thống kê |
| **TV3** | Ứng dụng demo | App ClubQuery (FastAPI + frontend), hỏi trực tiếp, phát lại, phân quyền, kiểm thử |
| **TV4** | Báo cáo, slide, video | Viết báo cáo, vẽ biểu đồ, làm slide, quay và dựng video 5 phút |

### Danh sách task chi tiết

| # | Task | Người | Đầu ra | Phụ thuộc | Trạng thái |
|---|---|---|---|---|---|
| T1 | Tải BIRD dev, đặt đúng thư mục, kiểm tra 158 câu `student_club` | TV1 | `data/dev.json`, `dev_databases/`, `llm/data/dev_gold.sql` | — | Xong |
| T2 | Đọc code gốc, ghi lại prompt và tham số (`temperature=0`, `max_tokens=256`, `stop`) | TV1 | Mục 3 trong `PROJECT_LOG.md` | T1 | Xong |
| T3 | Chạy GPT-3.5-Turbo, có và không knowledge | TV1 | `exp_result/openai_output`, `openai_0_output` | T2 | Xong |
| T4 | Chạy lại 6 lượt Ollama (3 model × có/không knowledge) với prompt đã sửa | TV1 | 6 file `predict_dev.json` | T2 | **Còn lại** |
| T5 | Chấm EX + VES toàn tập 1.534 câu, xuất `summary_ex.csv` và `summary_ves.csv` | TV1 | 2 file CSV | T3, T4 | **Còn lại** |
| T6 | Viết bộ phân loại 6 mức, gán nhãn cả tập dev | TV2 | `sql_category.py`, `sql_category_*.csv` | T1 | Xong |
| T7 | Chấm EX/VES theo 6 mức (Kaggle) | TV2 | `ex_ves_by_category_student_club.xlsx` | T4, T6 | Có EX; **cần chạy lại** khi xong T4 |
| T8 | Gap 3: chạy ctrl/norm trên 182 câu, chấm, kiểm định McNemar | TV2 | `exp_result/gap3/summary_gap3_ex_ves.csv` | T3, T4 | Có số; số toàn tập Ollama **còn tạm** |
| T9 | Backend: `/api/ask`, guard chỉ cho SELECT, authorizer theo vai trò | TV3 | `app/backend/*` | T1 | Xong |
| T10 | Chế độ phát lại benchmark và dashboard | TV3 | `per_db_ex.py`, `benchmark_student_club.json` | T5 | Xong (nạp lại sau T5) |
| T11 | Chạy `pytest` (mong đợi 52 passed), dựng sẵn bộ câu hỏi dùng cho demo | TV3 | Log test, danh sách câu demo | T9 | Cần kiểm lại |
| T12 | Báo cáo: SOTA → Phát triển từ bài báo (What/How/Why) → Cài đặt minh hoạ | TV4 | `BAO_CAO.docx` / PDF | T5, T7, T8 | Đang viết |
| T13 | Biểu đồ: EX theo model, EX theo mức, ΔEX của Gap 3 | TV4 | PNG trong báo cáo/slide | T5, T7, T8 | **Còn lại** |
| T14 | Slide thuyết trình (10–12 slide) | TV4 | `.pptx` | T12 | **Còn lại** |
| T15 | Quay, dựng video demo ~5 phút (kịch bản ở mục 4) | TV4 (+TV3 thao tác app) | `.mp4` | T11, T14 | **Còn lại** |
| T16 | Đưa code lên GitHub, kiểm tra README chạy được từ đầu trên một máy khác | TV1 | Link repo | Tất cả | **Còn lại** |

Thứ tự gợi ý: **T4 → T5 → T7, T8 → T13 → T12, T14 → T15 → T16**. T4 tốn thời gian nhất (Kaggle GPU) nên chạy trước; trong lúc chờ, TV3 làm T11, TV4 dựng khung báo cáo và slide.

---

## 3. Kịch bản thực hiện

### 3.1. Dataset

| Thành phần | Nội dung |
|---|---|
| Nguồn | https://bird-bench.github.io/ → Dev Set (`dev_20240627`) |
| `data/dev.json` | 1.534 câu; mỗi câu có `question_id`, `db_id`, `question`, `evidence`, `SQL`, `difficulty` |
| `data/dev_databases/` | 11 CSDL SQLite (mỗi CSDL kèm `database_description/*.csv`) |
| `llm/data/dev_gold.sql` | SQL đáp án, mỗi dòng `SQL \t db_id` |
| Tập con demo | `student_club`: 158 câu (question_id 1312–1469) |

Phân bố theo 6 mức (`GROUP='level'`, mỗi câu thuộc đúng 1 mức):

| Mức | `student_club` | Toàn bộ dev |
|---|---|---|
| 0. Khác (nhiều bảng qua truy vấn lồng) | 0 | 32 |
| 1. Một bảng | 33 | 340 |
| 2. Inner join | 114 | 1.040 |
| 3. Union / Intersect / Except | 0 | 1 |
| 4. Outer join | 0 | 1 |
| 5. Group by | 11 | 120 |
| 6. Phép chia | 0 | 0 |

### 3.2. Input / Output của thực nghiệm

**Input của mỗi câu** (prompt, giống paper):

```
<CREATE TABLE ... của mọi bảng trong CSDL>
-- External Knowledge: <evidence>              ← bỏ dòng này ở cấu hình "không knowledge"
-- Using valid SQLite and understading External Knowledge, answer the following questions for the tables provided above.
-- <question>
Generate the SQL after thinking step by step:
SELECT
```

**Output của bước sinh SQL:** `exp_result/<lượt>/predict_dev.json`, dạng `{"0": "SELECT ...\t----- bird -----\tdb_id", ...}`

**Output của bước chấm:**

| File | Nội dung |
|---|---|
| `summary_ex.csv`, `summary_ves.csv` | Model × (có/không knowledge) × (simple / moderate / challenging / total) |
| `ex_ves_by_category_student_club.csv` / `.xlsx` | Mỗi mức 2 bảng: `Model | EX_wo | EX_w` và `Model | VES_wo | VES_w` |
| `per_question_student_club.csv` | Từng câu × từng lượt: `ex` (0/1), `time_ratio` |
| `exp_result/gap3/summary_gap3_ex_ves.csv` | EX/VES ctrl và norm, ΔEX, ΔVES |

### 3.3. Flow benchmark

> Chuỗi gọi hàm chi tiết (hàm nào gọi hàm nào, tham số, ý nghĩa, ví dụ câu 1379): xem [FLOW_TEXT_TO_SQL.md](FLOW_TEXT_TO_SQL.md).

```
dev.json + dev_databases
        │
        ▼
[1] Sinh SQL ── openai_request.py / ollama_request.py
        │       (có knowledge / --no_knowledge; bản *_request2.py có thêm --normalize_evidence)
        ▼
exp_result/<lượt>/predict_dev.json
        │
        ├──► [2] evaluation.py      → EX theo độ khó của paper
        ├──► [3] evaluation_ves.py  → VES
        ├──► [4] sql_category.py + ex_ves_by_category.py → EX/VES theo 6 mức
        └──► [5] Gap 3: ctrl vs norm trên 182 câu → ΔEX + McNemar
        │
        ▼
CSV / XLSX  →  bảng, biểu đồ trong báo cáo  →  benchmark_student_club.json (nạp vào app)
```

**Bước 1: Sinh SQL** (`src/DAMO-ConvAI/bird/llm/src/`)

| Hàm | Việc làm |
|---|---|
| `generate_schema_prompt(db_path)` | Đọc `sqlite_master`, ghép CREATE TABLE của mọi bảng |
| `generate_comment_prompt(question, knowledge)` | Ghép evidence và câu hỏi thành comment SQL |
| `generate_combined_prompts_one(...)` | Prompt đầy đủ = schema + comment + đuôi. Đuôi của OpenAI: `cot_wizard()` + `\nSELECT `; của Ollama: yêu cầu trả về khối ```` ```sql ```` |
| `call_openai(...)` / `call_ollama(...)` | Gọi model, có retry |
| `extract_sql(raw)` | Tách SQL ra khỏi câu trả lời (code block, thêm `SELECT` nếu thiếu) |
| `collect_response(...)` | Chạy hết danh sách câu, có checkpoint |
| `generate_sql_file(...)` | Ghi `predict_dev.json` |
| `normalize_pseudo_sql(text)` (`evidence_norm.py`) | Gap 3: `DIVIDE(a,b)` → `CAST(a AS REAL)/b`, `YEAR(x)` → `CAST(STRFTIME('%Y',x) AS INTEGER)`… |

| Tham số | Giá trị | Ghi chú |
|---|---|---|
| `--model` | `gpt-3.5-turbo`, `qwen2.5-coder:7b`, `deepseek-coder-v2:16b`, `gemma3:12b` | |
| `--eval_path` | `./data/dev.json` | |
| `--db_root_path` | `./data/dev_databases/` | |
| `--data_output_path` | `./exp_result/<lượt>/predict_dev.json` | Hậu tố `_0` = không knowledge |
| `--no_knowledge` | bật/tắt | Cấu hình w/o KG |
| `--cot` | tuỳ chọn | 1-shot CoT (khôi phục từ `few_shot()` bị comment trong code gốc) |
| `--normalize_evidence` | tuỳ chọn | Gap 3, chỉ có ở `openai_request2.py` / `ollama_request2.py` |
| `--limit` | N | Chạy thử N câu đầu |
| `temperature` / `max_tokens` / `stop` | 0 / 256 / `['--','\n\n',';','#']` | Giữ như paper (GPT) |

**Bước 2–3: Chấm EX, VES** (bộ chấm gốc, không sửa)

| Hàm | Việc làm |
|---|---|
| `package_sqls(sql_path, db_root_path, mode)` | Đọc SQL dự đoán / SQL đáp án và đường dẫn CSDL |
| `execute_sql(pred, gold, db_path)` | Chạy 2 câu, so **tập kết quả**: `set(pred_res) == set(gold_res)` → 1 / 0 |
| `run_sqls_parallel(..., num_cpus, meta_time_out)` | Chạy song song, mỗi câu timeout 30 giây |
| `compute_acc_by_diff(...)` | Tính EX theo simple / moderate / challenging |
| `iterated_execute_sql(..., iterate_num)` | Chạy lặp để đo thời gian, `clean_abnormal` loại giá trị bất thường |
| `compute_ves(...)` | VES = `Σ sqrt(t_gold / t_pred) × 100 / tổng số câu`; câu sai tính 0 |

| Tham số | Giá trị |
|---|---|
| `--num_cpus` | 4 (Kaggle) / 8 (local) |
| `--meta_time_out` | 30.0 |
| `--iterate_num` | 5 (**phải ≥ 2**, nếu không VES = 0) |

**Bước 4: Theo 6 mức** (`app/scripts/`)

| Hàm / lệnh | Việc làm |
|---|---|
| `classify(sql)` | Trả `{'tags', 'level', 'tables', 'nested'}`; mức chính = nhãn có số lớn nhất |
| `categories(questions, group)` | Gom câu theo mức (`level`) hoặc theo nhãn (`tag`) |
| `score_run(...)` | Gọi lại `execute_model` của bộ chấm gốc cho từng tập |
| `python app/scripts/ex_ves_by_category.py [--skip_ves] [--group tag] [--db_id all]` | Chạy local |
| `ex-ves-by-category-kaggle.ipynb` | Chạy trên Kaggle (xem `docs/ex_ves_by_category_kaggle.md`) |

**Bước 5: Gap 3**: xem `docs/gap3_runbook.md`, gồm `gap3-ollama-kaggle.ipynb` và `gap3-evaluation-kaggle.ipynb`.

### 3.4. Kết quả hiện có (để kiểm tra khi chạy lại)

EX toàn tập 1.534 câu, có knowledge (lượt ctrl của Gap 3, Kaggle):

| Model | EX | VES |
|---|---|---|
| GPT-3.5-Turbo | 47,91 | 56,58 |
| DeepSeek-Coder-V2 | 42,11* | 45,80* |
| Gemma3 | 48,70* | 54,86* |
| Qwen2.5-Coder | 53,85* | 59,83* |

\* Số tạm, sẽ cập nhật sau T4/T5. Paper gốc: ChatGPT có knowledge đạt 37,22% (bản dev cũ) / 42,24% (bản dev đã sửa).

EX theo mức trên `student_club` (không knowledge → có knowledge):

| Model | Mức 1 (33) | Mức 2 (114) | Mức 5 (11) | Tổng (158) |
|---|---|---|---|---|
| GPT-3.5-Turbo | 33,3 → 60,6 | 41,2 → 49,1 | 18,2 → 27,3 | 38,0 → 50,0 |
| DeepSeek-Coder-V2 | 42,4 → 66,7 | 34,2 → 50,0 | 36,4 → 27,3 | 36,1 → 51,9 |
| Gemma3 | 45,5 → 78,8 | 51,8 → 72,8 | 36,4 → 36,4 | 49,4 → 71,5 |
| Qwen2.5-Coder | 39,4 → 78,8 | 49,1 → 71,9 | 45,5 → 54,5 | 46,8 → 72,2 |

Nhận xét chính: evidence giúp nhiều ở mức 1–2 (+17 đến +33 điểm) nhưng gần như không giúp ở mức 5 (Group by). Group by là mức khó nhất với mọi model.

Gap 3 (182 câu, ΔEX): GPT-3.5 +1,6 (p=0,68), DeepSeek **+9,3 (p=0,009)**, Gemma3 **+7,1 (p=0,015)**, Qwen +2,7 (p=0,30).

### 3.5. Flow demo Text-to-SQL (ClubQuery)

> Chi tiết từng hàm và tham số: mục B của [FLOW_TEXT_TO_SQL.md](FLOW_TEXT_TO_SQL.md).

```
Người dùng (đăng nhập theo vai trò)
     │  câu hỏi tiếng Anh / chọn câu dev
     ▼
POST /api/ask ──► service.ask()
     │
     ├─ mode = 'replay' : lấy predicted_sql đã lưu từ lượt benchmark
     │
     └─ mode = 'live'   :
          match_glossary()            → tra từ điển nghiệp vụ
          normalize_pseudo_sql()      → chuẩn hoá evidence (Gap 3)
          prompt.build_prompt()       → schema đã lọc theo vai trò + evidence + câu hỏi
          llm.generate_sql()          → gọi GPT-3.5 / Ollama
     ▼
guard.check_select()   → chỉ cho 1 câu SELECT, chặn INSERT/UPDATE/DROP/PRAGMA…
guard.execute()        → chạy read-only, authorizer chặn cột/bảng theo vai trò, có timeout
     ▼
answer.make_answer()   → LLM diễn giải kết quả thành câu tiếng Việt (lỗi thì dùng template)
same_result()          → (khi chọn câu dev, cả live lẫn replay) so với gold SQL → nhãn Đúng/Sai
     ▼
Ghi nhật ký (query_log) → trả về: SQL, bảng kết quả, câu trả lời, trạng thái
```

| Thành phần | File | Ghi chú |
|---|---|---|
| API, phân quyền | `app/backend/main.py` | `/api/login`, `/api/ask`, `/api/benchmark/summary`, `/api/glossary`, `/api/logs`, `/api/export/{id}` |
| Luồng hỏi đáp | `app/backend/service.py` | `ask(conn, user, question, mode, model_id, run_id, dev_question_id, use_evidence, evidence, use_glossary)` |
| An toàn SQL | `app/backend/guard.py` | `check_select`, `_authorizer(role, denied)`, `execute(sql, role, timeout_s)` |
| Prompt | `app/backend/prompt.py` | `schema_prompt(role)` ẩn cột nhạy cảm với vai trò thành viên |
| Cấu hình | `app/backend/config.py`, `.env` | `OPEN_AI_KEY`, `GROQ_API_KEY`, `MAX_ROWS`, timeout |

Chạy demo:

```powershell
.\venv\Scripts\python app\scripts\per_db_ex.py                 # tạo dữ liệu phát lại
.\venv\Scripts\python -m pytest app\tests -q                   # 52 passed
.\venv\Scripts\python -m uvicorn app.backend.main:app --port 8000
```

Tài khoản: `thuquy/thuquy123` (ban chủ nhiệm), `thanhvien/thanhvien123` (thành viên), `admin/admin123`.

### 3.6. App sinh SQL có giống code benchmark của BIRD không?

App dùng lại khuôn prompt của **`ollama_request.py`**, không dùng khuôn của `openai_request.py`.

| Điểm so sánh | `ollama_request.py` (benchmark Ollama) | `openai_request.py` (benchmark GPT-3.5) | App ClubQuery (`prompt.py`, `llm.py`) |
|---|---|---|---|
| Schema | CREATE TABLE mọi bảng | như bên trái | Giống, **trừ vai trò thành viên**: ẩn bảng `budget`, `expense`, `income` và cột `email`, `phone` |
| Comment có/không knowledge | `generate_comment_prompt` | giống | `comment_prompt`: chép y nguyên |
| Đuôi prompt | "Respond with the final SQLite query only, inside a \\`\\`\\`sql code block…" | `cot_wizard()` + `\nSELECT ` (đúng như code gốc của paper) | **Giống Ollama** |
| `temperature` / `max_tokens` / `stop` | 0 / không giới hạn / không có | 0 / 256 / `['--','\n\n',';','#']` | 0 / 512 / không có |
| Tách SQL | `extract_sql` của Ollama | `extract_sql` riêng (thêm lại `SELECT`) | Import đúng `extract_sql` của `ollama_request.py` |
| Evidence | Nguyên bản (hoặc `--normalize_evidence`) | như bên trái | **Luôn** qua `normalize_pseudo_sql`, tương đương cấu hình `evidence_norm` |
| Từ điển nghiệp vụ | không có | không có | Nếu tick "Áp dụng từ điển nghiệp vụ", thêm thuật ngữ vào evidence |

Kết luận:
- Với tài khoản `thuquy`/`admin`, **bỏ tick từ điển nghiệp vụ**, thì app sinh prompt giống hệt `ollama_request.py`: tick evidence tương ứng cấu hình `evidence_norm`, bỏ tick evidence tương ứng `no_evidence`.
- Với GPT-3.5, prompt của app **khác** prompt đã dùng để chạy benchmark GPT-3.5 (`openai_output`, `openai_0_output`). Vì vậy SQL mà app sinh trực tiếp có thể khác SQL ở chế độ Phát lại cho cùng câu hỏi.

---

## 4. Kịch bản video demo (~5 phút): chuyển câu hỏi thành SQL

Mục tiêu của video: cho người xem thấy **một câu hỏi tiếng Anh được chuyển thành SQL như thế nào**, SQL chạy ra kết quả gì, khi nào đúng, khi nào sai. Video không trình bày bảng số liệu benchmark; phần đó để trong báo cáo và slide.

Công cụ dùng trong video: app ClubQuery, chế độ **Hỏi trực tiếp**, model GPT-3.5-Turbo, CSDL `student_club`.

### 4.1. Bộ câu hỏi dùng trong video

Các câu dưới đây đã được chọn theo kết quả benchmark của GPT-3.5: **không có evidence thì sai, có evidence thì đúng**. Riêng câu 1402 là câu model luôn sai, dùng để chỉ ra điểm yếu.

| # | question_id | Mức | Câu hỏi | Evidence | Mục đích |
|---|---|---|---|---|---|
| Q1 | 1379 | 1. Một bảng | How many meeting events were held in 2020? | `type = 'Meeting'`; `YEAR(event_date) = 2020` | Vai trò của evidence; evidence có hàm giả `YEAR()` được đổi sang `STRFTIME` |
| Q2 | 1319 | 2. Inner join | Which college is the vice president of the Student_Club from? | Vice President is a position of the Student Club | SQL phải JOIN `member` với `major` |
| Q3 | 1367 | 5. Group by | Which college do most of the members go to? | `MAX(COUNT(major.college))` | SQL có `GROUP BY … ORDER BY COUNT … LIMIT 1` |
| Q4 | 1402 | 5. Group by | What is the most popular size of t-shirt ordered by the club members? | (có) | Câu model sai cả khi có evidence → giới hạn hiện tại |
| Q5 | — | tự nhập | Which event had the highest total expense? | không | Câu hỏi ngoài bộ dev, không có đáp án chuẩn |

> GPT-3.5 hiện tại có thể trả kết quả khác lúc chạy benchmark. **Phải chạy thử từng câu trước khi quay**; câu nào không cho kết quả như mong muốn thì đổi sang câu khác cùng mức (gợi ý: mức 1 → 1344, 1362, 1377; mức 2 → 1356, 1364; mức 5 → 1444).

### 4.2. Timeline

Chuẩn bị: app chạy sẵn ở `http://127.0.0.1:8000`, `.env` có `OPEN_AI_KEY`, đăng nhập sẵn `thuquy`, **bỏ tick "Áp dụng từ điển nghiệp vụ"** để prompt giống code benchmark (mục 3.6), zoom trình duyệt 125%, VS Code mở sẵn `app/backend/prompt.py` và `app/backend/guard.py`.

| Thời gian | Người | Màn hình | Thao tác và lời thoại |
|---|---|---|---|
| 0:00–0:20 | TV1 | Slide tiêu đề, sơ đồ bảng của `student_club` (member, major, event, attendance, budget, expense, income, zip_code) | Bài toán: người dùng hỏi bằng ngôn ngữ tự nhiên, hệ thống tự viết SQL. Dữ liệu demo là CSDL câu lạc bộ sinh viên của BIRD |
| 0:20–0:50 | TV1 | Sơ đồ flow ở mục 3.5, sau đó VS Code mở `prompt.py` | Câu hỏi đi qua 4 bước: **ghép prompt → LLM sinh SQL → kiểm tra an toàn → chạy và trả lời**. Prompt gồm CREATE TABLE của các bảng, evidence và câu hỏi, kết thúc bằng `SELECT` để model viết tiếp |
| 0:50–1:40 | TV2 | App, Hỏi trực tiếp, chọn **Q1**. Lần 1 **bỏ tick** "Dùng evidence" → Hỏi. Lần 2 **tick** → Hỏi | Lần 1: model không biết "meeting events" là `type = 'Meeting'` → kết quả sai, nhãn **Sai**. Lần 2: mở "Evidence đưa vào prompt" để thấy `YEAR(event_date)` đã được đổi thành `STRFTIME('%Y', event_date)`; SQL chạy đúng, nhãn **Đúng**, so với SQL đáp án (gold) |
| 1:40–2:20 | TV2 | Chọn **Q2**, có evidence → Hỏi | Chỉ vào SQL sinh ra: `member JOIN major ON link_to_major = major_id`, lọc theo `position` là Vice President. Model phải tự tìm khoá nối giữa 2 bảng. Bảng kết quả và câu trả lời tiếng Việt |
| 2:20–3:00 | TV3 | Chọn **Q3** → Hỏi; sau đó chọn **Q4** → Hỏi | Q3: SQL nối `member` với `major`, rồi `GROUP BY … ORDER BY COUNT(...) DESC LIMIT 1` → đúng. Q4: mở SQL gold để so, chỉ ra chỗ model sai (gom nhóm sai cột hoặc thiếu điều kiện). Nói ngắn: câu càng phức tạp (gom nhóm) thì model càng hay sai |
| 3:00–3:40 | TV3 | Chọn "— tự nhập câu hỏi —", gõ **Q5** → Hỏi | Câu hỏi không có trong bộ dev, không có evidence. Model vẫn sinh được SQL nối `event`, `budget`, `expense` và cộng `SUM(cost)`. Không có gold nên không có nhãn Đúng/Sai; người dùng tự đọc SQL để kiểm tra |
| 3:40–4:20 | TV4 | Đăng xuất, đăng nhập `thanhvien`. Hỏi *"List the email of all members"*, rồi hỏi *"Delete all members"* | Câu 1: bị chặn vì vai trò thành viên không được xem email (authorizer trong `guard.py`). Câu 2: dù model có sinh `DELETE`, guard chỉ cho phép một câu `SELECT` → bị từ chối. CSDL mở ở chế độ chỉ đọc |
| 4:20–4:45 | TV4 | Tab Lịch sử, sau đó chế độ **Phát lại**: chọn Q3, đổi qua lại lượt GPT-3.5 / Qwen / DeepSeek / Gemma3 | Mọi câu hỏi đều được ghi lại. Cùng một câu, mỗi model viết SQL khác nhau; có model đúng, có model sai |
| 4:45–5:00 | TV1 | Slide kết luận | LLM chuyển câu hỏi đơn giản sang SQL khá tốt, nhất là khi có evidence. Câu có gom nhóm vẫn hay sai. Vì vậy hệ thống luôn hiện SQL cho người dùng kiểm tra và chặn mọi lệnh không phải SELECT |

### 4.3. Lưu ý khi quay

- Quay từng đoạn riêng rồi ghép (OBS hoặc Xbox Game Bar; cắt bằng Clipchamp hoặc CapCut).
- Mỗi lần gọi GPT-3.5 mất vài giây: cắt bớt đoạn chờ khi dựng.
- Khi SQL hiện lên, phóng to hoặc tô sáng phần quan trọng (JOIN, WHERE, GROUP BY) và thêm phụ đề giải thích.
- Câu "Delete all members" phụ thuộc vào model: có lúc model từ chối viết SQL thay vì sinh `DELETE`. Nếu vậy, cả hai trường hợp đều nói được là hệ thống không xoá dữ liệu.
- Tổng thời lượng không quá 5:15. Nếu dài, bỏ Q4 trước, sau đó rút ngắn đoạn Phát lại.
