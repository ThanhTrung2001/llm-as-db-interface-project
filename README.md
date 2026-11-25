# LLM as a Database Interface — BIRD-SQL và ứng dụng ClubQuery

Dự án gồm hai phần, cùng dựa trên bài báo **"Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs" (BIRD-SQL, NeurIPS 2023)** — https://arxiv.org/abs/2305.03111:

1. **Khảo nghiệm lại BIRD-SQL** (đồ án môn Hệ thống CSDL tiên tiến): giữ nguyên prompt và bộ chấm của bài báo, thay các model đã ngừng hoạt động bằng model hiện tại; thêm thí nghiệm chuẩn hoá evidence (Gap 3). Nhật ký chi tiết: [PROJECT_LOG.md](PROJECT_LOG.md).
2. **ClubQuery** (đồ án môn Phân tích thiết kế hệ thống thông tin): hệ thống thông tin quản lý câu lạc bộ sinh viên (thành viên, sự kiện, điểm danh, ngân sách, khoản chi có quy trình duyệt, khoản thu, báo cáo) kèm hỏi đáp dữ liệu bằng ngôn ngữ tự nhiên; dữ liệu mồi là CSDL `student_club` của BIRD. Có 4 vai trò (Chủ nhiệm, Thủ quỹ, Ban sự kiện, Quản trị) dùng chung một ma trận quyền, nhật ký thay đổi, nhật ký truy vấn; hỏi đáp kèm tri thức ngoài (*evidence* của BIRD, tự nhập hoặc lấy từ 158 câu hỏi mẫu BIRD) và từ điển thuật ngữ. Giao diện ứng dụng bằng tiếng Anh. Báo cáo: [docs/pttk/BAO_CAO.docx](docs/pttk/BAO_CAO.docx) (nguồn Markdown: [docs/pttk/BAO_CAO.md](docs/pttk/BAO_CAO.md)).

## Cấu trúc

```
app/                           # ClubQuery
  backend/                     #   FastAPI: main.py (đăng nhập, hỏi đáp, lịch sử, model, tài khoản, nhật ký truy vấn),
                               #   club_api.py (thành viên, sự kiện, điểm danh, ngân sách, khoản chi + duyệt, khoản thu,
                               #   tổng quan, báo cáo, từ điển, nhật ký thay đổi), deps.py (phiên, kiểm tra quyền),
                               #   config.py (vai trò, ma trận quyền), service.py (luồng hỏi đáp), guard.py (chỉ SELECT,
                               #   authorizer theo vai trò, timeout), prompt.py, llm.py, answer.py, appdb.py (2 CSDL)
  frontend/                    #   giao diện một trang (HTML, JS, CSS)
  data/                        #   club.sqlite (dữ liệu CLB) và app.sqlite (dữ liệu ứng dụng) — tự tạo lần chạy đầu
  scripts/                     #   công cụ của phần nghiên cứu (per_db_ex.py: EX theo CSDL; thống kê theo loại SQL)
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

ClubQuery dùng `student_club.sqlite` làm dữ liệu mồi: lần chạy đầu, app chép nó thành `app\data\club.sqlite` (file gốc không bao giờ bị sửa), và nạp 158 câu hỏi `student_club` kèm evidence từ `dev.json` làm câu hỏi mẫu BIRD trên màn Ask AI.

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

### Bước 4 — Model cho hỏi đáp

Các chức năng quản lý không cần model. Hỏi đáp cần **một** trong hai:

- **Ollama** (model mặc định `Qwen2.5-Coder`): cài Ollama, chạy `ollama serve` và `ollama pull qwen2.5-coder:7b`.
- **Groq** (dịch vụ đám mây): thêm khoá vào file `.env` ở thư mục gốc, rồi chọn model GPT-OSS-20B trên màn **Ask AI** (hoặc đặt làm mặc định ở **Administration → AI models**):

```
GROQ_API_KEY=...        # model GPT-OSS-20B (Groq)
```

Ứng dụng không dùng dịch vụ OpenAI; gói Python `openai` chỉ là thư viện client cho API Chat Completions của Ollama/Groq.

### Bước 5 — (Tuỳ chọn) Kiểm thử

```powershell
$env:PYTHONIOENCODING = "utf-8"
.\venv\Scripts\python -m pytest app\tests -q      # mong đợi: 68 passed (không gọi model thật, dùng CSDL tạm)
```

### Bước 6 — Chạy app

```powershell
.\venv\Scripts\python -m uvicorn app.backend.main:app --port 8000
```

Mở http://127.0.0.1:8000. Lần chạy đầu, app tự tạo `app\data\club.sqlite` (chép từ `student_club.sqlite`) và `app\data\app.sqlite` (tài khoản demo, model, từ điển thuật ngữ).

| Tài khoản | Mật khẩu | Vai trò |
|---|---|---|
| `chunhiem` | `chunhiem123` | Chủ nhiệm (President): thành viên (thấy email, SĐT), sự kiện, điểm danh, **duyệt chi**, từ điển, nhật ký thay đổi |
| `thuquy` | `thuquy123` | Thủ quỹ (Treasurer): ngân sách, **đề xuất chi**, khoản thu |
| `bansukien` | `bansukien123` | Ban sự kiện (Event team): sự kiện, điểm danh; không xem tài chính |
| `admin` | `admin123` | Quản trị hệ thống (System admin): tài khoản, model, nhật ký truy vấn, từ điển; xem tài chính |

Giao diện bằng tiếng Anh. Các module: Dashboard, Ask AI, Question history, Members, Events & attendance, Finance (budgets, expenses, income), Reports, Glossary, Change log, Administration. Mọi thay đổi dữ liệu nghiệp vụ được ghi vào Change log.

**Ask AI (hỏi đáp):** gõ câu hỏi tiếng Anh, tuỳ chọn thêm gợi ý vào ô **External knowledge (optional)**, hoặc bấm **BIRD sample questions (158)** để chọn một câu hỏi dev của BIRD (điền sẵn câu hỏi và evidence), rồi bấm **Ask**. Tri thức ngoài (nguyên văn, như evidence của BIRD) và các thuật ngữ trong **Glossary** xuất hiện trong câu hỏi được ghép vào dòng `-- External Knowledge` của prompt; model sinh SQL; hệ thống kiểm tra rồi chạy SQL trên `club.sqlite` ở chế độ chỉ đọc, chỉ với bảng/cột vai trò được xem; model diễn giải kết quả thành câu trả lời.

Tắt app: **Ctrl+C** trong cửa sổ đang chạy server.

### Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| "Không thấy CSDL nguồn … student_club.sqlite" | Chưa làm Bước 3 |
| "Chưa cấu hình khoá API" | Chọn model Groq nhưng thiếu `GROQ_API_KEY` trong `.env` |
| Model Ollama báo "Lỗi gọi model" | Chạy `ollama serve` và `ollama pull qwen2.5-coder:7b` (tương tự với `deepseek-coder-v2:16b`, `gemma3:12b`), hoặc chọn GPT-OSS-20B (Groq) khi đã có `GROQ_API_KEY` |
| Cổng 8000 đang bận | Chạy với `--port 8001` |
| Muốn làm mới dữ liệu | `.\venv\Scripts\python -m app.backend.appdb` — tạo lại cả `app.sqlite` và `club.sqlite` từ dữ liệu gốc (mất mọi thay đổi, nhật ký, tài khoản tạo thêm) |

## Khảo nghiệm BIRD-SQL (benchmark)

Cần dữ liệu ở Bước 3, cùng các thư viện của script gọi model. Script GPT-3.5-Turbo (`openai_request.py`) cần `OPEN_AI_KEY=sk-...` trong `.env` (Groq: `GROQ_API_KEY`; Gemini: khoá tương ứng của script):

```powershell
.\venv\Scripts\python -m pip install google-genai groq pandas backoff
```

- Sinh SQL: các script `src/DAMO-ConvAI/bird/llm/src/*_request.py`. Model Ollama được chạy trên Kaggle bằng `llm-as-db-interface-ollama-kaggle.ipynb`.
- Chấm EX và VES trên toàn bộ 1.534 câu: `evaluation-and-ves-local.ipynb`, hoặc
  ```bash
  cd src/DAMO-ConvAI/bird/llm
  sh run/run_evaluation.sh
  ```
- EX theo từng CSDL (mặc định `student_club`, 4 model × 3 cấu hình × độ khó): `.\venv\Scripts\python app\scripts\per_db_ex.py` → `docs\pttk\data\ex_student_club.csv`.
- Gap 3 (chuẩn hoá evidence): xem [docs/gap3_runbook.md](docs/gap3_runbook.md).

## Báo cáo và diagram

- Dựng lại file Word từ Markdown:
  ```powershell
  .\venv\Scripts\python -m pip install pypandoc_binary python-docx
  .\venv\Scripts\python docs\pttk\build_docx.py
  ```
  Sau đó mở `BAO_CAO.docx` bằng Word và cập nhật mục lục (chuột phải → Update Field).
- Vẽ lại diagram (cần Java):
  ```powershell
  curl.exe -L -o tools\plantuml.jar https://repo1.maven.org/maven2/net/sourceforge/plantuml/plantuml/1.2024.7/plantuml-1.2024.7.jar
  cd docs\pttk\diagrams; java -jar ..\..\..\tools\plantuml.jar -charset UTF-8 -tpng (Get-ChildItem [0-9]*.puml).Name
  ```

## Nguồn

Code trong `src/DAMO-ConvAI/bird/` lấy từ [AlibabaResearch/DAMO-ConvAI](https://github.com/AlibabaResearch/DAMO-ConvAI) (MIT License).
Bộ dữ liệu BIRD-SQL theo giấy phép CC BY-SA 4.0 — https://bird-bench.github.io/.
