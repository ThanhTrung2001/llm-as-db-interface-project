# LLM as a Database Interface — BIRD-SQL và ứng dụng ClubQuery

Dự án gồm hai phần, cùng dựa trên bài báo **"Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs" (BIRD-SQL, NeurIPS 2023)** — https://arxiv.org/abs/2305.03111:

1. **Khảo nghiệm lại BIRD-SQL** (đồ án môn Hệ thống CSDL tiên tiến): giữ nguyên prompt và bộ chấm của bài báo, thay các model đã ngừng hoạt động bằng model hiện tại; thêm thí nghiệm chuẩn hoá evidence (Gap 3). Nhật ký chi tiết: [PROJECT_LOG.md](PROJECT_LOG.md).
2. **ClubQuery** (đồ án môn Phân tích thiết kế hệ thống thông tin): demo hỏi đáp Text-to-SQL trên CSDL `student_club` của BIRD, dùng đúng prompt và cách tách SQL của luồng benchmark. Phần phân quyền, nhật ký, tài khoản của đồ án PTTK đã gỡ khỏi code. Báo cáo cũ: [docs/pttk/BAO_CAO.docx](docs/pttk/BAO_CAO.docx) (nguồn Markdown: [docs/pttk/BAO_CAO.md](docs/pttk/BAO_CAO.md)).

## Cấu trúc

```
app/                           # ClubQuery
  backend/                     #   main.py (API), service.py (luồng hỏi đáp + chạy SQL chỉ đọc),
                               #   prompt.py (schema + comment + câu chặn), llm.py (gọi LLM, tách SQL),
                               #   answer.py (diễn giải câu trả lời), appdb.py (app.sqlite: model + câu hỏi mẫu)
  frontend/                    #   index.html, app.js, style.css
  scripts/                     #   phân tích kết quả benchmark (không dùng trong app)
    per_db_ex.py               #   chấm EX theo CSDL bằng evaluation.py gốc
    sql_category.py            #   phân loại SQL vào 6 mức (1 bảng, join, set-op, outer join, group by, phép chia)
    ex_by_category.py          #   EX theo 6 mức
    ex_ves_by_category.py      #   EX + VES theo 6 mức (local hoặc Kaggle)
  tests/                       #   pytest
docs/
  FLOW_*.md                    #   giải thích luồng benchmark, sinh SQL, chấm EX/VES
  ex_ves_by_category_kaggle.md #   hướng dẫn chấm theo 6 mức trên Kaggle
  gap3_runbook.md              #   hướng dẫn thí nghiệm Gap 3
  pttk/                        #   báo cáo, diagram PlantUML (.puml + .png), ảnh màn hình
src/DAMO-ConvAI/bird/          # phần BIRD lấy từ AlibabaResearch/DAMO-ConvAI (MIT License)
  data/                        #   KHÔNG có trong repo — tự tải, xem Bước 3
  llm/data/dev_gold.sql        #   KHÔNG có trong repo
  llm/src/                     #   script gọi model (openai/groq/ollama/gemini_request.py), evaluation.py (EX),
                               #   evaluation_ves.py (VES), evidence_norm.py (Gap 3)
  llm/run/                     #   script chạy hàng loạt (run_ollama_eval.ps1, *.sh của bản gốc)
  llm/exp_result/              #   SQL do các model sinh (predict_dev.json) — đã có sẵn trong repo
*.ipynb                        # notebook chạy benchmark / chấm điểm (local và Kaggle)
bird-*.zip                     # gói kết quả để upload làm dataset Kaggle
```

> **Bộ dữ liệu BIRD (CSDL, `dev.json`, SQL đáp án) không có trong repo.** Dữ liệu theo giấy phép CC BY-SA 4.0 của nhóm tác giả BIRD — tự tải theo Bước 3.

## Chạy ClubQuery từ đầu (Windows, PowerShell)

### Bước 1 — Mở thư mục dự án

```powershell
cd "D:\AI Learning\Paper\LLM"      # hoặc git clone repo rồi cd vào thư mục đó
```

Yêu cầu: Python 3.11 trở lên.

### Bước 2 — Tạo môi trường Python

```powershell
python -m venv venv
.\venv\Scripts\python -m pip install fastapi "uvicorn[standard]" openai python-dotenv sqlparse func_timeout requests tqdm pytest httpx
```

### Bước 3 — Tải bộ dev của BIRD (chứa CSDL `student_club`)

1. Vào https://bird-bench.github.io/, mục **Dev Set**, tải file zip.
2. Giải nén vào `src\dev` (bên trong có thư mục `dev_20240627`).
3. Chép các file vào đúng chỗ:

```powershell
Expand-Archive .\dev.zip -DestinationPath .\src\dev        # đổi tên nếu file tải về tên khác

$DEV  = ".\src\dev\dev_20240627"
$BIRD = ".\src\DAMO-ConvAI\bird"
New-Item -ItemType Directory -Force "$BIRD\llm\data" | Out-Null
Copy-Item "$DEV\dev.json" "$BIRD\data\dev.json"
Copy-Item "$DEV\dev.sql"  "$BIRD\llm\data\dev_gold.sql"
Expand-Archive "$DEV\dev_databases.zip" -DestinationPath "$BIRD\data" -Force
```

`dev_databases.zip` đã có sẵn thư mục `dev_databases/` bên trong, nên giải nén vào `bird\data` sẽ ra đúng `bird\data\dev_databases\student_club\student_club.sqlite`.

Kiểm tra (phải in `True` và `158`):

```powershell
Test-Path "$BIRD\data\dev_databases\student_club\student_club.sqlite"
.\venv\Scripts\python -c "import json;print(sum(q['db_id']=='student_club' for q in json.load(open(r'src\DAMO-ConvAI\bird\data\dev.json',encoding='utf-8'))))"
```

### Bước 4 — Khoá API (chỉ cần cho chế độ hỏi trực tiếp)

Tạo file `.env` ở thư mục gốc:

```
OPEN_AI_KEY=sk-...      # model GPT-3.5-Turbo
GROQ_API_KEY=...        # tuỳ chọn, model GPT-OSS-20B (Groq)
```

Các model chạy qua Ollama (Qwen2.5-Coder — mặc định, DeepSeek-Coder-V2, Gemma3) không cần khoá, chỉ cần Ollama chạy trên máy:

```powershell
ollama serve                          # nếu Ollama chưa tự chạy
ollama pull qwen2.5-coder:7b          # model app dùng; tuỳ chọn thêm deepseek-coder-v2:16b, gemma3:12b
```

### Bước 5 — (Tuỳ chọn) Kiểm thử

```powershell
.\venv\Scripts\python -m pytest app\tests -q      # mong đợi: 24 passed (không gọi model thật)
```

### Bước 6 — Chạy app

```powershell
.\venv\Scripts\python -m uvicorn app.backend.main:app --port 8000
```

Mở http://127.0.0.1:8000 (không cần đăng nhập). Lần chạy đầu, app tự tạo `app\data\app.sqlite`: danh sách model và 158 câu hỏi mẫu của `student_club` (đọc từ `dev.json` ở Bước 3).

Chọn model (mặc định Qwen2.5-Coder qua Ollama; GPT-3.5-Turbo / GPT-OSS-20B nếu có khoá), gõ câu hỏi (tiếng Anh cho kết quả ổn định nhất) hoặc chọn câu mẫu của BIRD, bấm **Hỏi**. Kết quả hiện câu trả lời, bảng dữ liệu, và có thể mở xem prompt gửi LLM, văn bản thô model trả về, SQL đã chạy, SQL đáp án.

Luồng xử lý một câu hỏi — `service.ask()` gọi lần lượt:

| Bước | Hàm | Làm gì |
|---|---|---|
| 1 | `service.load_question` | Câu mẫu BIRD: lấy câu hỏi, evidence, SQL đáp án từ bảng `dev_question`. Câu tự gõ: dùng nguyên câu hỏi |
| 2 | `service.load_model` | Đọc cấu hình model (provider, model_tag, base_url) |
| 3 | `prompt.build_prompt` | `build_schema_part()` (các câu CREATE TABLE) + `"\n\n"` + `build_question_part()` (External Knowledge nếu có, câu dẫn, câu hỏi) + `build_instruction_part()` (câu chặn) — đúng khuôn `generate_combined_prompts_one()` của benchmark |
| 4 | `llm.call_llm_for_sql` | Gửi prompt cho LLM (temperature = 0, tham số như lúc benchmark), nhận văn bản thô |
| 5 | `llm.extract_sql` | Tách SQL: `extract_sql_chat()` (chép từ `ollama_request.py`) hoặc `extract_sql_openai()` (chép từ `openai_request.py`) |
| 6 | `service.execute_sql` | Chạy SQL trên `student_club.sqlite` ở chế độ chỉ đọc, có timeout |
| 7 | `answer.make_answer` | Nhờ model diễn giải kết quả thành câu trả lời (model lỗi thì dựng câu theo mẫu) |
| 8 | `service.compare_with_gold` | Câu mẫu: chạy SQL đáp án, so `set(kết quả) == set(đáp án)` như `evaluation.py` |

Tắt app: **Ctrl+C** trong cửa sổ đang chạy server.

### Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| App báo lỗi không tìm thấy `dev.json` / `student_club.sqlite` | Chưa làm Bước 3 |
| "Chưa cấu hình khoá API" | Thiếu `OPEN_AI_KEY` trong `.env` |
| Model Ollama báo "Lỗi gọi model" | Cài Ollama, chạy `ollama serve` và `ollama pull qwen2.5-coder:7b` (tương tự với `deepseek-coder-v2:16b`, `gemma3:12b`). Không dùng thì chọn GPT-3.5-Turbo |
| Cổng 8000 đang bận | Chạy với `--port 8001` |
| Muốn làm mới dữ liệu ứng dụng | `.\venv\Scripts\python -m app.backend.appdb` (tạo lại `app.sqlite`: danh sách model + 158 câu hỏi mẫu từ `dev.json`) |

## Khảo nghiệm BIRD-SQL (benchmark)

Cần dữ liệu ở Bước 3, cùng các thư viện của script gọi model và bộ chấm:

```powershell
.\venv\Scripts\python -m pip install google-genai groq pandas backoff openpyxl
```

Luồng gồm 2 việc: **sinh SQL** cho 1.534 câu dev → `exp_result/<lượt>/predict_dev.json`, rồi **chấm EX/VES** so với `dev_gold.sql`. Mỗi model chạy 2 lượt: có evidence (`*_output`) và không evidence (`*_0_output`). Giải thích chi tiết: [docs/FLOW_TEXT_TO_SQL.md](docs/FLOW_TEXT_TO_SQL.md), [docs/FLOW_EVALUATION_EX_VES.md](docs/FLOW_EVALUATION_EX_VES.md).

Các lượt đã chạy có sẵn trong `src/DAMO-ConvAI/bird/llm/exp_result/`:

| Model | Có evidence | Không evidence |
|---|---|---|
| GPT-3.5-Turbo | `openai_output` | `openai_0_output` |
| Qwen2.5-Coder 7B | `ollama_gwen25_output` | `ollama_gwen25_0_output` |
| DeepSeek-Coder-V2 16B | `ollama_deepseekcoder_output` | `ollama_deepseekcoder_0_output` |
| Gemma3 12B | `ollama_gemma3_output` | `ollama_gemma3_0_output` |

> Mọi lệnh trong mục này chạy từ thư mục `src\DAMO-ConvAI\bird\llm`. Các tham số đường dẫn phải **có dấu `\` ở cuối** vì code gốc ghép chuỗi trực tiếp. Không dùng `run/run_evaluation.sh` của bản gốc: script đó gọi `python3` và trỏ `./data/dev_databases/` (sai chỗ với cấu trúc repo này).

```powershell
cd "src\DAMO-ConvAI\bird\llm"
$PY = "..\..\..\..\venv\Scripts\python"
```

### 1. Sinh SQL ở local (tuỳ chọn — kết quả đã có sẵn)

```powershell
# Ollama (cần ollama serve + ollama pull qwen2.5-coder:7b-instruct). Bỏ --limit để chạy đủ 1.534 câu
& $PY src\ollama_request2.py --model qwen2.5-coder:7b-instruct `
    --eval_path ..\data\dev.json --db_root_path ..\data\dev_databases\ `
    --data_output_path exp_result\thu_nghiem_output\predict_dev.json --limit 3
# thêm --no_knowledge để chạy lượt không evidence
```

GPT dùng `src\openai_request.py` với cùng các tham số (cần `OPEN_AI_KEY` trong `.env`). Chạy đủ 1.534 câu bằng model local trên máy không có GPU mạnh mất nhiều giờ, nên các lượt Ollama được chạy trên Kaggle (xem mục 4).

### 2. Chấm EX và VES ở local (toàn bộ 1.534 câu)

Chấm một lượt:

```powershell
# EX
& $PY src\evaluation.py --predicted_sql_path exp_result\ollama_gwen25_output\ `
    --ground_truth_path data\ --data_mode dev --db_root_path ..\data\dev_databases\ `
    --diff_json_path ..\data\dev.json --num_cpus 4 --meta_time_out 30.0

# VES (chạy mỗi câu đúng 5 lần để đo thời gian, lâu hơn EX nhiều)
& $PY src\evaluation_ves.py --predicted_sql_path exp_result\ollama_gwen25_output\ `
    --ground_truth_path data\ --data_mode dev --db_root_path ..\data\dev_databases\ `
    --diff_json_path ..\data\dev.json --num_cpus 4 --meta_time_out 30.0 --iterate_num 5
```

Kết quả in ra bảng theo độ khó simple / moderate / challenging / total. Đổi `exp_result\...\` để chấm lượt khác.

Chấm nhiều lượt một lần:

- `run\run_ollama_eval.ps1`: EX + VES cho 3 lượt Ollama có evidence. Sửa biến `$PY` ở đầu file nếu repo không nằm ở `D:\AI Learning\Paper\LLM`.
- [evaluation-and-ves-local.ipynb](evaluation-and-ves-local.ipynb): mở Jupyter **từ thư mục gốc repo**, chạy cả 8 lượt, ghi `exp_result\summary_ex.csv` và `summary_ves.csv`.

VES đo thời gian thật nên mỗi lần chấm lệch nhau một chút; chỉ so số trong cùng một lần chạy.

### 3. Chấm theo 6 mức truy vấn (student_club)

Chạy từ **thư mục gốc repo**:

```powershell
.\venv\Scripts\python app\scripts\ex_by_category.py                 # EX theo 6 mức, đọc kết quả có sẵn (nhanh)
.\venv\Scripts\python app\scripts\ex_ves_by_category.py --skip_ves  # EX bằng bộ chấm gốc
.\venv\Scripts\python app\scripts\ex_ves_by_category.py             # EX + VES (lâu hơn)
```

Kết quả ghi vào `docs\pttk\data\`. Cách phân loại: `app\scripts\sql_category.py`.

### 4. Chạy trên Kaggle

Dùng Kaggle khi cần GPU để chạy model Ollama, hoặc để chấm VES trên máy ổn định hơn. Notebook nằm ở thư mục gốc repo; import bằng **Code → New Notebook → File → Import Notebook**.

| Notebook | Việc | Accelerator | Dataset cần gắn (Add Input) |
|---|---|---|---|
| `llm-as-db-interface-ollama-kaggle.ipynb` | Sinh SQL bằng Ollama cho 1.534 câu | **GPU T4** | Dataset BIRD (`bird-sql`) |
| `run-evaluation-kaggle.ipynb` | Chấm EX + VES cho 3 model Ollama × 2 cấu hình | None | Dataset BIRD có kèm `llm/exp_result/` |
| `ex-ves-by-category-kaggle.ipynb` | EX + VES theo 6 mức (student_club) | None | `bird-sql` + `bird-category-eval` |
| `gap3-ollama-kaggle.ipynb`, `gap3-evaluation-kaggle.ipynb` | Thí nghiệm Gap 3 | GPU T4 / None | `bird-sql` + `bird-gap3-src` / `bird-gap3-eval` |

**Chuẩn bị dataset (làm 1 lần):** Kaggle → **Datasets → New Dataset**, chọn **Private**.

- Dataset BIRD: upload thư mục `src\DAMO-ConvAI\bird` **sau khi làm Bước 3** (phải có `data/dev.json`, `data/dev_databases/`, `llm/src/`, `llm/data/dev_gold.sql`; muốn chấm thì có cả `llm/exp_result/`). Notebook tự tìm thư mục chứa `data/dev.json` trong `/kaggle/input`, nên tên dataset không quan trọng.
- Các gói kết quả: upload nguyên file `bird-category-eval.zip`, `bird-gap3-src.zip`, `bird-gap3-eval.zip` ở thư mục gốc repo, Kaggle tự giải nén.

**Sinh SQL với Ollama** (`llm-as-db-interface-ollama-kaggle.ipynb`):

1. Settings: **Accelerator GPU T4**, **Internet On** (cần để cài Ollama và tải model).
2. Cell 3: bỏ comment dòng `ollama pull` của model muốn chạy.
3. Cell cuối: bỏ comment lời gọi `collect_response(...)` tương ứng, đặt `OUTPUT_PATH` (ví dụ `/kaggle/working/exp_result/ollama_gwen25_output/predict_dev.json`). Dùng `knowledge_list` cho lượt có evidence, `knowledge_list_nokg` cho lượt không evidence. Script ghi tạm sau mỗi 50 câu; nếu bị ngắt thì chạy tiếp theo đoạn (`chunk = eval_data[512:1024]`...).
4. **Run All**, xong thì tải `predict_dev.json` ở tab **Output** về đặt vào `src\DAMO-ConvAI\bird\llm\exp_result\<lượt>\`, rồi chấm ở local (mục 2) hoặc trên Kaggle.

**Chấm trên Kaggle:** gắn dataset, Accelerator None, **Run All**, tải file CSV ở tab **Output**. Riêng `ex-ves-by-category-kaggle.ipynb` cần bật **Internet On** vì cell đầu chạy `pip install func_timeout`. Chi tiết từng cell: [docs/ex_ves_by_category_kaggle.md](docs/ex_ves_by_category_kaggle.md).

### 5. Gap 3 (chuẩn hoá evidence)

Xem [docs/gap3_runbook.md](docs/gap3_runbook.md).

## Nguồn

Code trong `src/DAMO-ConvAI/bird/` lấy từ [AlibabaResearch/DAMO-ConvAI](https://github.com/AlibabaResearch/DAMO-ConvAI) (MIT License).
Bộ dữ liệu BIRD-SQL theo giấy phép CC BY-SA 4.0 — https://bird-bench.github.io/.
