# Nhật ký dự án — Khảo nghiệm lại BIRD-SQL với LLM hiện đại

**Đồ án môn Hệ thống CSDL tiên tiến**
Bài báo gốc: *"Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs"* (BIRD-SQL, NeurIPS 2023) — https://arxiv.org/abs/2305.03111

---

## 1. Mục tiêu đồ án

Dựa trên hướng đã chốt từ đầu: **giữ nguyên phương pháp đánh giá của paper BIRD-SQL, nhưng thay các model LLM năm 2023 (đã lỗi thời/bị khai tử) bằng model hiện tại**, để trả lời lại câu hỏi gốc của paper — *"LLM đã đủ sức làm database interface chưa?"* — với bối cảnh công nghệ mới nhất.

Cấu trúc báo cáo theo yêu cầu đề bài:
1. Tính SOTA
2. Phát triển từ bài báo (What / How / Why)
3. Cài đặt minh họa (code đưa lên GitHub)

---

## 2. Chuẩn bị môi trường & dữ liệu

### 2.1. Thiết lập ban đầu
- Clone `AlibabaResearch/DAMO-ConvAI` (chứa code gốc của paper, MIT License), chỉ dùng phần `bird/`
- Tạo venv Python, cài dependency: `google-genai`, `groq`, `openai`, `python-dotenv`, `sqlparse`, `backoff`, `func_timeout`, `pandas`, `tqdm`
- Dựng git repo riêng cho đồ án, `.gitignore` loại bỏ: database SQLite (346MB, license CC BY-SA không cho phân phối lại), các project không liên quan khác trong DAMO-ConvAI, và **toàn bộ dataset BIRD** (`dev.json`, `dev_gold.sql`...) — mỗi người tự tải theo hướng dẫn trong README, không commit vào git
- Xóa dòng `Co-Authored-By: Claude` khỏi mọi commit theo yêu cầu

### 2.2. Dữ liệu BIRD dev set
- Tải từ `bird-bench.github.io` → giải nén đúng vị trí: `data/dev.json`, `data/dev_databases/` (11 database), `llm/data/dev_gold.sql`
- Xác nhận: **chỉ cần thư mục `bird/llm/`** của repo gốc (không cần `finetuning/`, không cần git submodule nào — kiểm tra kỹ không có `.gitmodules` trong repo)

---

## 3. Phân tích code gốc của paper

Đọc trực tiếp source code (không chỉ dựa README, vì README nhiều chỗ lỗi thời) để nắm chính xác:

- **`gpt_request.py`**: dùng `openai.Completion.create()` (API cũ) với `engine='code-davinci-002'` — API này **đã bị OpenAI khai tử hoàn toàn**
- Công thức prompt: `schema (CREATE TABLE) + comment (question + evidence) + cot_wizard() + '\nSELECT '` — thiết kế riêng cho Completion API (mồi nối chuỗi, model tự tiếp tục văn bản ngay sau `SELECT`)
- Tham số gọi model: `temperature=0`, `max_tokens=256`, `stop=['--', '\n\n', ';', '#']`
- Phát hiện: hàm `few_shot()` (1-shot COT pseudo-example) **được định nghĩa nhưng bị comment-out** trong code thật — mâu thuẫn với mô tả trong paper (Appendix B.4) nói có dùng 1-shot example cho COT
- Phát hiện: cơ chế `@backoff` retry trong `connect_gpt()` **thực chất không hoạt động** — `try/except` bên trong hàm bắt hết exception trước khi decorator kịp thấy, nên không bao giờ retry thật sự (bug có sẵn trong code gốc)
- **`evaluation.py`**: EX = so khớp **tập kết quả thực thi** SQL (không so sánh text), chạy song song bằng `multiprocessing.Pool`
- **`evaluation_ves.py`**: VES = đo hiệu năng tương đối `sqrt(E_gold/E_pred)`, mặc định lặp **100 lần/câu** để ổn định kết quả (đúng theo paper Appendix B.8, không phải tùy tiện)
- **`finetuning/`** (track T5): phụ thuộc `third_party/` (từ framework UnifiedSKG) **không tồn tại trong repo**, và stack dependency rất cũ (`torch==1.7.1`, `transformers==4.9.2`) không cài được trên môi trường hiện đại → kết luận **không khả thi** trong khung thời gian đồ án, trừ khi tự viết fine-tuning script mới (đã thiết kế pipeline thay thế dùng `transformers` hiện đại + schema serialization kiểu "peteshaw" đúng paper, nhưng chưa triển khai thật)

---

## 4. Xác định model nào trong paper còn gọi được

| Model gốc trong paper | Trạng thái (kiểm chứng trực tiếp qua API) |
|---|---|
| `code-davinci-002` (Codex) | ❌ Khai tử vĩnh viễn |
| `gpt-3.5-turbo-0301/-0613/-1106` (mọi snapshot cố định) | ❌ Tất cả đã deprecated (test trực tiếp, lỗi 404 "has been deprecated") |
| `gpt-3.5-turbo` (alias trôi) | ✅ Còn gọi được — **duy nhất lựa chọn còn lại cho dòng ChatGPT** |
| `gpt-4-32k` | ❌ Không còn trong danh sách model của OpenAI (xác nhận qua `client.models.list()`) |
| `gpt-4-0613` | ✅ Còn tồn tại (snapshot cố định duy nhất còn sống của dòng GPT-4), nhưng **giá rất cao** ($30/$60 mỗi 1M token) |
| `gpt-4` (alias trôi) | ✅ Còn gọi được |
| Claude-2 | ❌ Anthropic đã ngừng |
| Palm-2 | ❌ Google đã thay bằng Gemini |

**Quyết định:** thay thế bằng model hiện tại theo đúng công ty gốc khi có thể (Google → Gemini, OpenAI → giữ nguyên nhưng alias mới), bổ sung thêm model mã nguồn mở miễn phí để mở rộng phạm vi khảo nghiệm.

---

## 5. Các script inference đã viết

Tất cả đều tái sử dụng logic build prompt (`generate_schema_prompt`, `generate_comment_prompt`) giống hệt bản gốc, chỉ thay tầng gọi model:

| File | Model gọi | Ghi chú |
|---|---|---|
| `gemini_request.py` | Gemini (`gemini-3.6-flash`) | Free tier **rate limit rất chặt** (5 req/phút thực tế còn tệ hơn do quota cộng dồn) → không chạy full được, phải tạm hoãn |
| `groq_request.py` | Model mã nguồn mở qua Groq (`openai/gpt-oss-20b`, `gpt-oss-120b`) | Free, rate limit rộng rãi hơn (1000 req / 8000 token/phút) → **chạy full thành công** |
| `ollama_request.py` | Model local qua Ollama (`qwen2.5-coder:7b`, `deepseek-coder-v2:16b`, `gemma3:12b`) | Chạy trên Kaggle (GPU T4 free), cần copy database ra `/kaggle/working` (tránh lỗi đọc sqlite qua mount mạng `/kaggle/input`) |
| `openai_request.py` | `gpt-3.5-turbo`, có thêm biến thể `--cot` | Đã trả phí nạp tài khoản OpenAI để chạy |

### 5.1. Phát hiện quan trọng: độ trung thành với prompt gốc ảnh hưởng khác nhau theo model

Khi sửa `openai_request.py` để khớp **chính xác** tham số gốc (`cot_wizard()+'\nSELECT '`, `max_tokens=256`, có `stop`), áp dụng y hệt sang `ollama_request.py` thì **gây lỗi nghiêm trọng**: EX tụt xuống gần 0% cho `qwen2.5-coder`/`deepseek-coder-v2`.

**Nguyên nhân:** kỹ thuật "mồi nối chuỗi" (`'\nSELECT '` ở cuối prompt) chỉ hiệu quả với Completion API đời cũ. Model chat đã instruction-tuned (Qwen, DeepSeek) hiểu nhầm đây là câu hỏi dang dở, trả lời kiểu giải thích ("To find X, we need to follow these steps:") thay vì viết SQL — khiến `extract_sql()` gắn nhầm "SELECT" vào đầu đoạn văn giải thích, tạo ra SQL vô nghĩa.

**Kết luận:** `gpt-3.5-turbo` (được RLHF trên khối lượng lớn, "đoán ý" tốt hơn) chịu được kỹ thuật cũ (dù điểm vẫn giảm nhẹ: 49.61%→47.78%), nhưng model mở nhỏ thì không. → **Giữ `openai_request.py` khớp đúng gốc** (vì đây đại diện đúng dòng model paper test), **revert `ollama_request.py` về prompt tường minh** ("Respond with SQL only, in code block") — chấp nhận không khớp 100% với `gpt_request.py` vì các model này vốn là **model thay thế tự chọn**, không phải đối tượng gốc của paper.

### 5.2. Chain-of-Thought (`--cot` trong `openai_request.py`)

Khôi phục đúng logic `few_shot()`/`few_shot_no_kg()` bị comment trong code gốc (copy verbatim, kể cả token `</s>` cuối chuỗi dù không còn ý nghĩa với Chat API), viết thêm `extract_sql_cot()` port từ `post_process_cot.py` để tách phần suy luận khỏi SQL cuối cùng (`split(': SELECT')`).

---

## 6. Hạ tầng chạy — Local vs Kaggle

- **Local máy:** chạy tốt cho Gemini/Groq/OpenAI (chỉ cần gọi API, không cần GPU)
- **Kaggle (GPU T4 free):** bắt buộc cho Ollama (máy cá nhân không đủ VRAM, bị chia tải CPU/GPU 55/45 → quá chậm, ~2 phút/câu; trên Kaggle full GPU → ~2-4s/câu)
- Bài học rút ra:
  - Phải copy database + script `evaluation.py`/`evaluation_ves.py` ra `/kaggle/working/` (ghi được) thay vì đọc trực tiếp `/kaggle/input/` (read-only, mount mạng chậm — từng gây lỗi "unable to open database file" và treo hàng giờ)
  - `evaluation.py` dùng `multiprocessing.Pool` → trên Windows phải gọi qua `subprocess` (process độc lập) thay vì `import` thẳng vào kernel Jupyter (tránh lỗi spawn); trên Kaggle (Linux) không bị vấn đề này nhưng vẫn giữ cách gọi subprocess cho đồng nhất
  - Checkpoint (`checkpoint_every=50`) để tránh mất dữ liệu khi session Kaggle bị ngắt giữa chừng

---

## 7. Phát hiện quan trọng về Model Drift & Dataset Drift

### 7.1. Model drift — "gpt-3.5-turbo" hôm nay không phải "gpt-3.5-turbo" của 2023
Xác nhận bằng cách gọi trực tiếp API: mọi snapshot cố định đã chết, chỉ còn alias trôi — nghĩa là mô hình đứng sau cái tên này đã được OpenAI âm thầm cập nhật nhiều lần.

### 7.2. Dataset drift — chính BIRD dev set cũng đã "trôi" theo thời gian
Trích dẫn trực tiếp từ `bird-bench.github.io`:

| Ngày | Thay đổi |
|---|---|
| 14/07/2023 | Sửa tên schema CSV + vấn đề "tied results" trong `ORDER BY ... LIMIT 1` |
| 25/09/2023 | *"We have released a cleaner version of dev set... fixed all errors that we found."* — ChatGPT EX: 37.22%→42.24% |
| 13/11/2025 | Phát hành `bird-sql-dev-1106` (HuggingFace) — **không chỉ sửa lỗi mà viết lại nhiều câu hỏi phức tạp hơn hẳn** (xác nhận bằng so sánh nội dung trực tiếp, không chỉ ngày tháng) |

Bản `dev.json` dùng trong đồ án (thư mục gốc `dev_20240627`) nằm **giữa 2 lần dọn lớn** — đã có bản sửa 09/2023, **chưa có** bản viết lại 11/2025. Quyết định: **giữ nguyên bản đang dùng**, vì bản 11/2025 đã đổi bản chất độ khó câu hỏi, không còn so sánh công bằng với Table 2 gốc của paper.

### 7.3. Human Performance cao bất thường — lý do cụ thể
- Annotator đã qua sàng lọc ≥90% chính xác (Appendix B.2)
- Được "luyện tập" qua 8/10 batch có chuyên gia sửa lỗi trước khi "thi" ở 2 batch cuối (Appendix B.9)
- **Bất đối xứng thông tin quan trọng:** con người được xem `Database Description File` (giải thích tên cột/giá trị), nhưng **prompt gửi cho model hoàn toàn không có** nội dung này — chỉ có CREATE TABLE schema + evidence

---

## 8. Kết quả thực nghiệm (tính tới thời điểm hiện tại)

| Model | EX w/o KG | EX w/ KG | VES w/o KG | VES w/ KG | Trạng thái |
|---|---|---|---|---|---|
| GPT-3.5-Turbo (OpenAI, bản khớp gốc) | 31.23% | 47.78% | 33.88% | 53.88% | ✅ Hoàn chỉnh |
| DeepSeek-Coder-V2 (Ollama, free) | — | 41.98-42.24%* | — | 45.52-45.86%* | ⚠️ Cần chạy lại với prompt đã sửa |
| Gemma3 (Ollama, free) | — | 48.31-48.50%* | — | 50.90-51.06%* | ⚠️ Cần chạy lại với prompt đã sửa |
| Qwen2.5-Coder (Ollama, free) | — | 53.85%* | — | 60.19-60.36%* | ⚠️ Cần chạy lại với prompt đã sửa |
| Gemini (gemini-3.6-flash) | — | — | — | — | ❌ Tạm hoãn (rate limit free tier quá chặt) |
| Groq gpt-oss-20b/120b | đã test, chưa tổng hợp bảng | | | | ⚠️ Cần chạy full + eval |

*Số liệu đo trước khi phát hiện bug prompt (mục 5.1) — **cần chạy lại** với `ollama_request.py` đã sửa để có số liệu cuối cùng đáng tin cậy.

So với paper gốc (ChatGPT w/ KG dev: 37.22% gốc / 42.24% đã cập nhật) — GPT-3.5-Turbo hiện tại (47.78%) **vượt cả 2 mốc**, một phần do model đã cải tiến (model drift), một phần do dataset đã sạch hơn (dataset drift).

---

## 9. Việc còn lại (chưa hoàn thành)

1. **Chạy lại full 6 lượt Ollama** (3 model × w/kg, w/o kg) với `ollama_request.py` đã sửa prompt
2. Chạy evaluation (EX + VES) cho toàn bộ kết quả Ollama mới
3. Tổng hợp bảng `summary_ex.csv` / `summary_ves.csv` cuối cùng (2 file CSV riêng)
4. Quyết định có chạy thêm Groq `gpt-oss-120b` full + eval không (đã test smoke, chưa chạy full)
5. Quyết định cuối cùng về Claude (Anthropic) — không có phương án free, cân nhắc bỏ qua hoặc trả ~$8 qua OpenRouter
6. Viết báo cáo 5-7 trang theo cấu trúc: Tính SOTA → Phát triển từ bài báo (What/How/Why) → Cài đặt minh họa, dùng nội dung đã soạn ở các phần trước trong hội thoại
7. Đẩy code lên GitHub (repo đã dựng sẵn, chưa push)

---

## 10. Cấu trúc code cuối cùng

```
src/DAMO-ConvAI/bird/llm/src/
  gpt_request.py          # gốc paper, giữ nguyên để tham chiếu
  gemini_request.py        # Gemini — tạm hoãn do rate limit
  groq_request.py          # Groq (gpt-oss-20b/120b) — free, chạy full được
  ollama_request.py        # Ollama local (qwen2.5-coder, deepseek-coder-v2, gemma3) — chạy trên Kaggle
  openai_request.py        # OpenAI (gpt-3.5-turbo), có flag --cot, khớp tham số gốc
  evaluation.py / evaluation_ves.py   # gốc paper, tái sử dụng nguyên vẹn

evaluation-and-ves-local.ipynb   # Notebook tổng hợp EX/VES local, xuất CSV
run-evaluation.ipynb             # Phiên bản chạy trên Kaggle
llm-as-db-interface-ollama-kaggle.ipynb   # Notebook chạy Ollama trên Kaggle
```

---

*Tài liệu này được tổng hợp lại từ toàn bộ quá trình làm việc, dùng làm tài liệu tham chiếu khi viết báo cáo chính thức.*
