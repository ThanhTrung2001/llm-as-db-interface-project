# LLM as a Database Interface — BIRD-SQL và ứng dụng ClubQuery

Dự án gồm hai phần, cùng dựa trên bài báo **"Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs" (BIRD-SQL, NeurIPS 2023)** — https://arxiv.org/abs/2305.03111:

1. **Khảo nghiệm lại BIRD-SQL** (đồ án môn Hệ thống CSDL tiên tiến): giữ nguyên prompt và bộ chấm của bài báo, thay các model đã ngừng hoạt động bằng model hiện tại; thêm thí nghiệm chuẩn hoá evidence (Gap 3). Nhật ký chi tiết: [PROJECT_LOG.md](PROJECT_LOG.md).
2. **ClubQuery** (đồ án môn Phân tích thiết kế hệ thống thông tin): hệ thống hỏi đáp dữ liệu câu lạc bộ sinh viên bằng ngôn ngữ tự nhiên trên CSDL `student_club` của BIRD, có phân quyền, nhật ký, từ điển nghiệp vụ, dashboard benchmark. Báo cáo: [docs/pttk/BAO_CAO.docx](docs/pttk/BAO_CAO.docx) (nguồn Markdown: [docs/pttk/BAO_CAO.md](docs/pttk/BAO_CAO.md)).

## Cấu trúc

```
app/                           # ClubQuery
  backend/                     #   FastAPI: main.py (API, phân quyền), service.py (luồng hỏi đáp),
                               #   guard.py (chỉ SELECT, authorizer theo vai trò, timeout), prompt.py,
                               #   llm.py, answer.py (diễn giải câu trả lời), appdb.py (app.sqlite)
  frontend/                    #   index.html, app.js, style.css
  scripts/per_db_ex.py         #   chấm EX theo CSDL bằng evaluation.py gốc -> dữ liệu phát lại
  tests/                       #   pytest
docs/pttk/                     # báo cáo, diagram PlantUML (.puml + .png), ảnh màn hình
src/DAMO-ConvAI/bird/          # phần BIRD lấy từ AlibabaResearch/DAMO-ConvAI (MIT License)
  data/                        #   KHÔNG có trong repo — tự tải, xem Bước 3
  llm/data/dev_gold.sql        #   KHÔNG có trong repo
  llm/src/                     #   script gọi model (openai/groq/ollama/gemini_request.py), evaluation.py (EX),
                               #   evaluation_ves.py (VES), evidence_norm.py (Gap 3)
  llm/exp_result/              #   SQL do các model sinh (predict_dev.json) — đã có sẵn trong repo
*.ipynb                        # notebook chạy benchmark / chấm điểm (local và Kaggle)
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

Chế độ **phát lại** không cần khoá và không cần mạng.

### Bước 5 — Chấm điểm và tạo dữ liệu phát lại

```powershell
.\venv\Scripts\python app\scripts\per_db_ex.py
```

Script chấm 12 lượt (4 model × 3 cấu hình) × 158 câu bằng `evaluation.py` gốc, rồi ghi ra:

- `app\data\benchmark_student_club.json`: dữ liệu cho chế độ phát lại và dashboard.
- `docs\pttk\data\ex_student_club.csv`: bảng EX.

### Bước 6 — (Tuỳ chọn) Kiểm thử

```powershell
.\venv\Scripts\python -m pytest app\tests -q      # mong đợi: 52 passed (không gọi model thật)
```

### Bước 7 — Chạy app

```powershell
.\venv\Scripts\python -m uvicorn app.backend.main:app --port 8000
```

Mở http://127.0.0.1:8000. Lần chạy đầu, app tự tạo `app\data\app.sqlite`: tài khoản demo, model, từ điển, và nạp dữ liệu từ Bước 5.

| Tài khoản | Mật khẩu | Vai trò |
|---|---|---|
| `thuquy` | `thuquy123` | Ban chủ nhiệm: xem được tài chính, dashboard, xuất CSV |
| `thanhvien` | `thanhvien123` | Thành viên: câu hỏi về tài chính, email, số điện thoại bị chặn |
| `admin` | `admin123` | Quản trị: nhật ký, model, tài khoản, nhập benchmark |

Hai chế độ hỏi đáp:

- **Phát lại benchmark:** chọn lượt benchmark và câu hỏi mẫu, bấm **Hỏi**. Dùng SQL model đã sinh lúc benchmark, kèm đáp án chuẩn và nhãn đúng/sai.
- **Hỏi trực tiếp:** chọn model GPT-3.5-Turbo, gõ câu hỏi (tiếng Anh cho kết quả ổn định nhất), bấm **Hỏi**. Model sinh SQL; hệ thống kiểm tra rồi chạy SQL trên `student_club.sqlite` ở chế độ chỉ đọc; model diễn giải kết quả thành câu tiếng Việt.

Tắt app: **Ctrl+C** trong cửa sổ đang chạy server.

### Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| Danh sách "Lượt benchmark" trống | Chưa chạy Bước 5. Chạy xong thì xoá `app\data\app.sqlite` rồi chạy lại app, hoặc nhập file JSON ở tab Quản trị |
| "Chưa cấu hình khoá API" | Thiếu `OPEN_AI_KEY` trong `.env` |
| Model Ollama báo "Lỗi gọi model" | Cài Ollama, chạy `ollama serve` và `ollama pull qwen2.5-coder:7b` (tương tự với `deepseek-coder-v2:16b`, `gemma3:12b`). Không dùng thì chọn GPT-3.5-Turbo |
| Cổng 8000 đang bận | Chạy với `--port 8001` |
| Muốn làm mới dữ liệu ứng dụng | `.\venv\Scripts\python -m app.backend.appdb` (xoá nhật ký và tài khoản tạo thêm) |

## Khảo nghiệm BIRD-SQL (benchmark)

Cần dữ liệu ở Bước 3, cùng các thư viện của script gọi model:

```powershell
.\venv\Scripts\python -m pip install google-genai groq pandas backoff
```

- Sinh SQL: các script `src/DAMO-ConvAI/bird/llm/src/*_request.py`. Model Ollama được chạy trên Kaggle bằng `llm-as-db-interface-ollama-kaggle.ipynb`.
- Chấm EX và VES trên toàn bộ 1.534 câu: `evaluation-and-ves-local.ipynb`, hoặc
  ```bash
  cd src/DAMO-ConvAI/bird/llm
  sh run/run_evaluation.sh
  ```
- Gap 3 (chuẩn hoá evidence): xem [docs/gap3_runbook.md](docs/gap3_runbook.md).
## Nguồn

Code trong `src/DAMO-ConvAI/bird/` lấy từ [AlibabaResearch/DAMO-ConvAI](https://github.com/AlibabaResearch/DAMO-ConvAI) (MIT License).
Bộ dữ liệu BIRD-SQL theo giấy phép CC BY-SA 4.0 — https://bird-bench.github.io/.
