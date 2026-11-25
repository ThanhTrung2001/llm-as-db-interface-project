# ClubQuery — Hồ sơ phân tích thiết kế

Hệ thống thông tin quản lý câu lạc bộ sinh viên (thành viên, sự kiện, điểm danh, ngân sách, khoản chi có quy trình duyệt, khoản thu, báo cáo) kèm hỏi đáp dữ liệu bằng ngôn ngữ tự nhiên. Phần hỏi đáp áp dụng kết quả nghiên cứu bài báo BIRD (Li et al., NeurIPS 2023, https://arxiv.org/abs/2305.03111): từ điển thuật ngữ của CLB đóng vai trò *evidence* trong prompt.

| Tài liệu | Nội dung |
|---|---|
| [01_khao_sat_yeu_cau.md](01_khao_sat_yeu_cau.md) | Bối cảnh, dữ liệu, ranh giới, tác nhân, ma trận phân quyền, yêu cầu chức năng (UC01–UC19), quy tắc nghiệp vụ BR01–BR13, yêu cầu phi chức năng |
| [02_use_case.md](02_use_case.md) | Biểu đồ use case, phân rã UC02 (gồm tri thức ngoài và câu hỏi mẫu BIRD), đặc tả UC02, UC06, UC07, UC09, UC11, UC12, UC18 và tóm tắt các UC còn lại |
| [03_thiet_ke.md](03_thiet_ke.md) | BFD, hoạt động, tuần tự, lớp phân tích, trạng thái, ERD và từ điển dữ liệu, kiến trúc, an toàn truy vấn, API, giao diện |
| [04_kiem_thu.md](04_kiem_thu.md) | Kế hoạch và kết quả kiểm thử, ánh xạ ca kiểm thử, phân quyền trên câu hỏi thật, kịch bản demo, hạn chế |
| [BAO_CAO.md](BAO_CAO.md) | Báo cáo đầy đủ (nghiên cứu BIRD + phân tích thiết kế); [BAO_CAO.docx](BAO_CAO.docx) dựng bằng `build_docx.py` |
| [data/](data/) | Số liệu khảo nghiệm BIRD (EX theo model × cấu hình × độ khó) — thuộc phần nghiên cứu, không phải dữ liệu của ứng dụng |

## Chạy hệ thống

Cần có bộ dev của BIRD đặt đúng chỗ (README gốc của repo, Bước 3): `student_club.sqlite` và `dev.json`. Lần chạy đầu, app chép CSDL thành `app/data/club.sqlite` và tạo `app/data/app.sqlite`, nạp 158 câu hỏi mẫu `student_club` (kèm evidence) từ `dev.json`. Giao diện ứng dụng bằng tiếng Anh.

```bash
venv/Scripts/python -m pip install fastapi "uvicorn[standard]" openai python-dotenv sqlparse pytest httpx
venv/Scripts/python -m app.backend.appdb            # (tuỳ chọn) tạo lại CẢ app.sqlite và club.sqlite từ dữ liệu gốc
venv/Scripts/python -m uvicorn app.backend.main:app --port 8000
```

Mở http://127.0.0.1:8000. Tài khoản demo:

| Tài khoản | Mật khẩu | Vai trò |
|---|---|---|
| `chunhiem` | `chunhiem123` | Chủ nhiệm (President) |
| `thuquy` | `thuquy123` | Thủ quỹ (Treasurer) |
| `bansukien` | `bansukien123` | Ban sự kiện (Event team) |
| `admin` | `admin123` | Quản trị hệ thống (System admin) |

Hỏi đáp cần một model chạy được: Ollama tại `localhost:11434` (model mặc định `qwen2.5-coder:7b`; `deepseek-coder-v2:16b`, `gemma3:12b` tuỳ chọn), hoặc `GROQ_API_KEY` trong `.env` để dùng GPT-OSS-20B qua Groq. Gói `openai` chỉ được dùng làm thư viện client cho API Chat Completions của Ollama/Groq. Các chức năng quản lý không cần model.

Kiểm thử (không gọi model thật, dùng CSDL tạm): `PYTHONIOENCODING=utf-8 venv/Scripts/python -m pytest app/tests -q` → 68 passed.

## Vẽ lại diagram

```bash
curl -L -o tools/plantuml.jar https://repo1.maven.org/maven2/net/sourceforge/plantuml/plantuml/1.2024.7/plantuml-1.2024.7.jar
cd docs/pttk/diagrams && java -jar ../../../tools/plantuml.jar -charset UTF-8 -tpng [0-9]*.puml
```

Tên file PNG lấy theo tên sau `@startuml` / `@startwbs` (vd. `04_activity_duyet_chi.puml` → `activity_duyet_chi.png`).
