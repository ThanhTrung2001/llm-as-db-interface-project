# ClubQuery — Hồ sơ phân tích thiết kế

Hệ thống hỏi đáp dữ liệu câu lạc bộ sinh viên bằng ngôn ngữ tự nhiên, xây trên kết quả nghiên cứu bài báo BIRD (Li et al., NeurIPS 2023, https://arxiv.org/abs/2305.03111).

| Tài liệu | Nội dung |
|---|---|
| [01_khao_sat_yeu_cau.md](01_khao_sat_yeu_cau.md) | Bối cảnh, dữ liệu, ranh giới, tác nhân, yêu cầu chức năng, quy tắc nghiệp vụ, yêu cầu phi chức năng |
| [02_use_case.md](02_use_case.md) | Biểu đồ use case, đặc tả UC02, UC06, UC08, UC09, UC11 |
| [03_thiet_ke.md](03_thiet_ke.md) | Hoạt động, tuần tự, lớp, trạng thái, ERD và từ điển dữ liệu, kiến trúc, API, giao diện |
| [04_kiem_thu.md](04_kiem_thu.md) | Kế hoạch và kết quả kiểm thử, kết quả benchmark, kịch bản demo, hạn chế |
| [data/ex_student_club.csv](data/ex_student_club.csv) | EX theo model × cấu hình × độ khó |

## Chạy hệ thống

Cần có bộ dữ liệu BIRD dev đặt đúng chỗ như trong README gốc của repo.

```bash
venv/Scripts/python -m pip install fastapi "uvicorn[standard]" pytest httpx
venv/Scripts/python app/scripts/per_db_ex.py        # chấm EX student_club -> app/data/benchmark_student_club.json
venv/Scripts/python -m app.backend.appdb            # (tuỳ chọn) khởi tạo lại app.sqlite
venv/Scripts/python -m uvicorn app.backend.main:app --port 8000
```

Mở http://127.0.0.1:8000. Tài khoản demo: `admin/admin123`, `thuquy/thuquy123`, `thanhvien/thanhvien123`.

- Chế độ **phát lại** không cần mạng.
- Hỏi **trực tiếp** cần `OPEN_AI_KEY` hoặc `GROQ_API_KEY` trong `.env`, hoặc Ollama chạy tại `localhost:11434`.

Kiểm thử: `venv/Scripts/python -m pytest app/tests -q`

## Vẽ lại diagram

```bash
curl -L -o tools/plantuml.jar https://repo1.maven.org/maven2/net/sourceforge/plantuml/plantuml/1.2024.7/plantuml-1.2024.7.jar
cd docs/pttk/diagrams && java -jar ../../../tools/plantuml.jar -charset UTF-8 -tpng [0-9]*.puml
```
