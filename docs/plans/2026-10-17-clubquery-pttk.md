# Plan: ClubQuery — đồ án PTTK (làm ngay, 1 người)

Hệ thống hỏi đáp dữ liệu CLB sinh viên (`student_club` của BIRD) bằng ngôn ngữ tự nhiên.
CSDL nguồn chỉ đọc; hệ thống quản lý người dùng/vai trò, nhật ký truy vấn, từ điển nghiệp vụ, model, kết quả benchmark.

## Bước

| # | Việc | Sản phẩm | Xong khi |
|---|---|---|---|
| 1 | EX riêng `student_club` từ output có sẵn | `app/scripts/per_db_ex.py`, `docs/pttk/data/ex_student_club.csv` | Có bảng EX theo model × có/không evidence × độ khó |
| 2 | Backend FastAPI | `app/backend/` (guard, authorizer theo vai trò, ask live/replay, log, glossary, benchmark, auth) + `tests/` | `pytest` xanh; BR01–BR05 có test |
| 3 | Frontend 1 trang (HTML+JS, FastAPI phục vụ) | `app/frontend/` | 4 màn: đăng nhập, hỏi đáp+lịch sử, benchmark, quản trị |
| 4 | Tài liệu PTTK + diagram PlantUML | `docs/pttk/*.md`, `docs/pttk/diagrams/*.puml` → `.png` | Đủ D1–D12 |
| 5 | Kiểm thử nghiệm thu | `docs/pttk/06_kiem_thu.md` | EX phát lại trong app = EX của `evaluation.py` trên 158 câu; demo chạy offline |

## Quy tắc nghiệp vụ
- BR01 chỉ 1 câu SELECT · BR02 timeout 10s, ≤1000 dòng · BR03 vai trò `member` không đọc `budget`/`expense`/`income`, `member.email`/`member.phone` (chặn bằng `sqlite3.set_authorizer`) · BR04 mọi câu hỏi đều ghi log · BR05 chỉ admin sửa từ điển/model.

## Cắt khi thiếu thời gian (theo thứ tự)
Live Ollama → feedback/CSV → màn cấu hình model. Không cắt: use case, đặc tả, phân quyền, phát lại, kiểm thử.
