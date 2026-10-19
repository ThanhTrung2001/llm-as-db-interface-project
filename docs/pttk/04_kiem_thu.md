# 4. Kiểm thử và đánh giá

## 4.1. Kế hoạch kiểm thử

| Mức | Nội dung | File | Số ca |
|---|---|---|---|
| Đơn vị | Lớp an toàn: BR01 (chỉ SELECT), BR02 (timeout, chỉ đọc), BR03 (phân quyền tầng engine), lọc schema theo vai trò | `app/tests/test_guard.py` | 29 |
| Chức năng | Từng use case qua API, theo từng vai trò; model được giả lập để kiểm luồng lỗi | `app/tests/test_api.py` | 15 |
| Nghiệm thu | Chấm lại 12 lượt × 158 câu qua luồng phát lại của hệ thống; so với bộ chấm gốc của BIRD | `app/tests/test_acceptance.py` | 1 (1896 phép so) |
| Giao diện | Playwright: đăng nhập 3 vai trò, hỏi, dashboard, quản trị, khổ điện thoại | thủ công có ghi ảnh, `screens/` | 7 màn |
| Tích hợp model thật | Một câu hỏi trực tiếp qua gpt-3.5-turbo | chạy tay | 1 |

Chạy toàn bộ: `venv/Scripts/python -m pytest app/tests -q` → **45 passed**.

## 4.2. Kết quả nghiệm thu NFR1

`test_acceptance.py` đưa 1896 cặp (lượt chạy, câu hỏi) qua đúng luồng `service.ask()` của hệ thống: kiểm tra an toàn, thực thi chỉ đọc, so tập kết quả với SQL gold. Kết quả đúng/sai **trùng 1896/1896** với giá trị do `execute_model()` trong `evaluation.py` gốc tính ra. Vậy con số EX trên dashboard là EX theo đúng định nghĩa của BIRD.

## 4.3. Kết quả trên `student_club` (158 câu: 101 simple, 48 moderate, 9 challenging)

| Model | Không evidence | Có evidence | Evidence chuẩn hoá | Toàn dev, có evidence |
|---|---|---|---|---|
| GPT-3.5-Turbo | 37,97 | 50,00 | 51,90 | 47,78 |
| DeepSeek-Coder-V2* | 36,08 | 51,90 | 53,80 | — |
| Gemma3* | 49,37 | 71,52 | 70,89 | — |
| Qwen2.5-Coder* | 46,84 | 72,15 | 73,42 | 53,85 |

\* Số tạm thời, đo trước khi sửa lỗi prompt (PROJECT_LOG mục 5.1).

Nhận xét:
- **Evidence tăng EX ở mọi model, từ 12 đến 25 điểm**, cùng chiều với kết luận của bài báo BIRD. Đây là lý do hệ thống có từ điển nghiệp vụ (UC06): từ điển chính là evidence do tổ chức tự duy trì.
- **`student_club` dễ hơn mức trung bình của bộ dev.** Ví dụ Qwen2.5-Coder đạt 72,15% ở đây nhưng 53,85% trên toàn dev. Không được lấy số của một CSDL để kết luận cho cả benchmark.
- Với 158 câu, sai số khoảng ±8 điểm, nên chênh lệch giữa Gemma3 và Qwen2.5 (dưới 1 điểm) hay giữa các cấu hình evidence (dưới 2 điểm) **không có ý nghĩa**.
- Phân tích lượt GPT-3.5 có evidence: 79 câu đúng, 52 câu chạy được nhưng sai kết quả, 27 câu lỗi thực thi.

## 4.4. Kiểm thử phân quyền trên dữ liệu thật

Phát lại 158 câu của lượt GPT-3.5 có evidence bằng tài khoản **Thành viên**: 76 câu bị chặn (`REJECTED_PERMISSION`), 65 câu chạy được, 17 câu lỗi thực thi. Gần một nửa số câu hỏi của bộ dev chạm tới dữ liệu tài chính hoặc thông tin liên lạc, nên phân quyền là yêu cầu thật, không phải chi tiết trang trí.

## 4.5. Kịch bản demo đề xuất (7–10 phút)

| # | Tài khoản | Thao tác | Điều muốn chứng minh |
|---|---|---|---|
| 1 | thuquy | Phát lại GPT-3.5 có evidence, câu #1312 "What's Angela Sanders's major?" | Luồng chuẩn: SQL, kết quả, đúng đáp án, 7 ms |
| 2 | thuquy | Phát lại câu #1324 "average attendance of meetings in 2020" | **Câu sai, cả 4 model đều sai.** Evidence gợi ý `DIVIDE(COUNT(event_id), COUNT(DISTINCT event_name))`, tức là đếm sự kiện chứ không đếm lượt điểm danh. GPT-3.5 làm theo nguyên văn và bỏ qua bảng `attendance`; các model khác lồng `AVG(COUNT(...))` hoặc dùng `YEAR()`, hàm SQLite không có. Đây là nhóm lỗi "hiểu sai evidence" của BIRD (17,6%) |
| 3 | thuquy | Phát lại câu #1318 "event that has the highest attendance" | GPT-3.5 trả thêm cột `event_id`, `attendance_count` nên bị chấm sai dù ý đúng: EX so khớp tập kết quả rất chặt |
| 4 | thanhvien | Chọn câu hỏi về khoản chi | Bị chặn ở tầng engine (BR03), vẫn được ghi log |
| 5 | thanhvien | Hỏi trực tiếp "How many meeting events were held in 2020?" | Thuật ngữ "meeting" tự ghép vào prompt; trả 9 |
| 6 | admin | Tab Benchmark → Quản trị → Nhật ký | EX theo model; nhật ký có cả các lần bị từ chối |

Tỉ lệ đúng tổng thể phải nêu cùng lúc với các câu demo (GPT-3.5 có evidence: 50%). Trong 158 câu có 51 câu cả 4 model đều đúng và 30 câu cả 4 model đều sai.

## 4.6. Hạn chế

- Số của 3 model Ollama là tạm thời; cần chạy lại sau khi sửa prompt.
- Câu hỏi của BIRD bằng tiếng Anh. Hệ thống nhận được tiếng Việt, nhưng độ chính xác với tiếng Việt chưa được đo.
- Phiên đăng nhập lưu trong bộ nhớ tiến trình (khởi động lại máy chủ thì phải đăng nhập lại). Đủ cho demo, chưa đủ cho triển khai thật.
- Từ điển khớp thuật ngữ theo chuỗi con, chưa xử lý từ đồng nghĩa.
