# 4. Kiểm thử và đánh giá

## 4.1. Kế hoạch kiểm thử

| Mức | Nội dung | File | Số ca |
|---|---|---|---|
| Đơn vị | Lớp an toàn hỏi đáp: BR01 (chỉ SELECT), BR02 (timeout, chỉ đọc), BR03 (phân quyền ở tầng engine theo 4 vai trò), lọc schema theo ma trận quyền | `app/tests/test_guard.py` | 35 |
| Đơn vị | Câu trả lời dựng theo mẫu (UC02f, tiếng Anh): rỗng, một giá trị, một dòng, danh sách, bảng | `app/tests/test_answer.py` | 5 |
| Chức năng | Từng use case qua API theo từng vai trò; tri thức ngoài và câu mẫu BIRD; quy tắc nghiệp vụ BR04–BR13; model được giả lập (không gọi model thật) | `app/tests/test_api.py` | 28 |
| Phân quyền trên câu hỏi thật | Chạy 158 câu SQL do GPT-3.5 sinh trong phần khảo nghiệm cho bộ dev `student_club` qua `guard.execute()` với từng vai trò | script, mục 4.4 | 158 × 4 |
| Giao diện | Đăng nhập từng vai trò, các màn hình, khổ điện thoại | thủ công, ảnh trong `screens/` | 10 màn |
| Tích hợp model thật | Qwen2.5-Coder 7B qua Ollama: câu mẫu BIRD #1379 kèm evidence; bật/tắt thuật ngữ | chạy tay, mục 4.5 | 5 câu |

Mỗi lần chạy, `conftest.py` tạo `app.sqlite` và `club.sqlite` tạm trong thư mục tạm (`CLUBQUERY_APP_DB`, `CLUBQUERY_CLUB_DB`), nên test không đụng dữ liệu làm việc.

Chạy toàn bộ:

```bash
PYTHONIOENCODING=utf-8 ./venv/Scripts/python -m pytest app/tests -q -v
```

Kết quả (26/11/2026): **68 passed in 5,16 s** (35 + 5 + 28).

## 4.2. Ánh xạ ca kiểm thử chức năng (`test_api.py`)

| Ca kiểm thử | UC / quy tắc | Kiểm tra |
|---|---|---|
| `test_login_wrong_password` | UC01 | Sai mật khẩu → 401 |
| `test_requires_login` | UC01, BR05 | Gọi API không có token → 401 |
| `test_me_returns_permissions` | UC01 | Thủ quỹ có `finance.write`, không có `pii.read` |
| `test_change_password` | UC01 | Mật khẩu cũ sai → 422; đổi xong đăng nhập bằng mật khẩu mới |
| `test_ask_uses_glossary_and_role_schema` | UC02, UC02d, BR03 | "How many meetings were held?" → thuật ngữ `meeting` được ghép thành dòng External Knowledge; prompt của Ban sự kiện không có `expense`, `email`; câu trả lời theo mẫu "Result: n." |
| `test_ask_with_external_knowledge_and_sample` | UC02g, UC02h | `/api/sample-questions` trả 158 câu (146 có evidence); hỏi bằng câu mẫu → evidence nằm **nguyên văn** sau `-- External Knowledge:`, `query_log` lưu `evidence`, `sample_id`; tự nhập tri thức + câu chứa `meeting` → hai phần nối bằng `; `; tri thức chỉ có khoảng trắng → không có dòng External Knowledge |
| `test_ask_answer_from_llm` | UC02f | Câu trả lời lấy từ model khi model diễn giải được |
| `test_ask_finance_rejected_for_event_team_and_logged` | BR03, BR04 | Ban sự kiện hỏi tổng chi → `REJECTED_PERMISSION`, có trong `query_log` |
| `test_ask_unsafe_sql_rejected` | BR01 | `DELETE FROM member` → `REJECTED_UNSAFE` |
| `test_ask_llm_failure_logged` | BR04 | Model lỗi → `FAILED_GENERATION`, vẫn có `log_id` |
| `test_ask_inactive_model_rejected` | UC02 E0 | Model không tồn tại → 422 |
| `test_history_feedback_export` | UC03, UC04, UC05 | Lịch sử có câu vừa hỏi; đánh giá lưu được; xuất CSV đúng `text/csv` |
| `test_cannot_export_or_rate_others_question` | UC04, UC05 | Đánh giá/xuất câu của người khác → 404 |
| `test_logs_admin_only` | UC19 | Chủ nhiệm → 403; Quản trị thấy thống kê theo trạng thái |
| `test_member_contact_info_masked` | UC07 | Ban sự kiện không thấy email; Chủ nhiệm thấy |
| `test_member_crud_and_br09` | UC07, BR09, BR10 | Ban sự kiện thêm → 403; zip sai → 422; thêm/sửa/xoá; xoá người đã điểm danh → 409; audit có đủ CREATE, UPDATE, DELETE |
| `test_event_lifecycle_and_attendance` | UC08, UC09, BR11, BR12 | Thủ quỹ tạo sự kiện → 403; tạo ở `Open` → 422; điểm danh khi `Planning` → 409; mở → điểm danh 3 người; đóng → không mở lại (422), không điểm danh (409); xoá sự kiện đã điểm danh → 409 |
| `test_finance_hidden_from_event_team` | BR05 | Ban sự kiện gọi ngân sách, khoản chi, khoản thu, báo cáo tài chính → 403; tổng quan không có khối tài chính |
| `test_expense_approval_updates_budget` | UC11, UC12, BR06 | Chủ nhiệm lập chi → 403; Thủ quỹ duyệt → 403; tổng quan có khoản chờ duyệt; duyệt xong `spent` tăng, `remaining` giảm đúng số tiền; duyệt lại → 409; huỷ khoản đã duyệt → 409 |
| `test_expense_over_budget_cannot_be_approved` | BR07, UC12 | Đề xuất vượt ngân sách có cảnh báo; duyệt → 409; từ chối không lý do → 422; từ chối có lý do → REJECTED, lưu lý do |
| `test_proposer_cannot_approve_own_expense` | BR08, BR13 | Thủ quỹ khác sửa/huỷ đề xuất không phải của mình → 403; người đề xuất được đổi vai trò thành Chủ nhiệm vẫn không tự duyệt được → 409 |
| `test_budget_rules` | UC10 | Ngân sách < đã chi → 422; trùng hạng mục → 409; xoá ngân sách có khoản chi → 409; lập ngân sách cho sự kiện đã đóng → 409 |
| `test_income_crud` | UC13 | Chủ nhiệm ghi thu → 403; Thủ quỹ thêm/sửa/xoá được |
| `test_glossary_crud` | UC06 | Ban sự kiện thêm → 403; trùng không phân biệt hoa thường (có dấu) → 409; sửa, tắt, xoá |
| `test_reports` | UC15 | Báo cáo tham dự đủ 33+ thành viên; báo cáo tài chính có theo sự kiện và theo nguồn thu |
| `test_audit_permission` | UC16 | Thủ quỹ → 403; Chủ nhiệm xem được |
| `test_model_config_admin_only` | UC17 | Chủ nhiệm sửa model → 403; đặt mặc định cho model đang tắt → 422 |
| `test_user_management` | UC18 | Chủ nhiệm xem tài khoản → 403; vai trò `member` cũ → 422; quản trị tự hạ quyền → 422 |

## 4.3. Ca kiểm thử tiêu biểu của lớp an toàn (`test_guard.py`)

| Ca | Đầu vào | Mong đợi | Kết quả |
|---|---|---|---|
| Lệnh ghi | `DELETE FROM member`, `DROP TABLE`, `UPDATE`, `ATTACH`, `PRAGMA` | `REJECTED_UNSAFE` | Đạt |
| Nhiều câu lệnh | `SELECT 1; DROP TABLE member` | `REJECTED_UNSAFE` | Đạt |
| Lệnh ghi giấu trong CTE | `WITH x AS (SELECT 1) DELETE FROM member` | Authorizer chặn, `REJECTED_UNSAFE` | Đạt |
| Hàm hợp lệ trùng từ khoá | `WITH … REPLACE(first_name, …)`; `SELECT 'a;b'` | Cho phép | Đạt |
| Không phải SQL | chuỗi rỗng, văn bản giải thích, chỉ có comment | `FAILED_GENERATION` | Đạt |
| Ban sự kiện đọc tài chính | `COUNT(*) FROM expense`, `SUM(amount) FROM income`, JOIN với `expense` | `REJECTED_PERMISSION` | Đạt |
| Ban sự kiện đọc liên lạc | `SELECT email`, `SELECT *`, `WHERE phone LIKE …` | `REJECTED_PERMISSION` | Đạt |
| Chỉ Chủ nhiệm đọc liên lạc | `SELECT email`/`SELECT *` với Thủ quỹ, Quản trị | `REJECTED_PERMISSION`; Chủ nhiệm chạy được | Đạt |
| Vai trò có `finance.read` | `SUM(cost) FROM expense` với Chủ nhiệm, Thủ quỹ, Quản trị | Có kết quả | Đạt |
| Vai trò lạ | `nobody` đọc `income` | Bị hạn chế nhiều nhất | Đạt |
| Schema theo ma trận | `schema_prompt('event' / 'treasurer' / 'president')` | Ẩn đúng bảng/cột | Đạt |
| Truy vấn vô hạn | CTE đệ quy không điểm dừng, timeout 0,5 giây | `TIMEOUT` | Đạt |
| Ghi vào `club.sqlite` qua kết nối hỏi đáp | `UPDATE member …` | Lỗi readonly | Đạt |
| Sai tên cột | `SELECT no_such_col FROM member` | `EXEC_ERROR` | Đạt |

## 4.4. Phân quyền trên câu hỏi thật

Lấy 158 câu SQL mà GPT-3.5-Turbo (có evidence) đã sinh cho các câu hỏi dev của `student_club` trong phần khảo nghiệm, chạy qua `guard.execute()` hiện tại với từng vai trò (CSDL gốc, chế độ chỉ đọc):

| Vai trò | Chạy được | Bị chặn quyền | Lỗi thực thi |
|---|---|---|---|
| Chủ nhiệm | 131 | 0 | 27 |
| Thủ quỹ | 123 | 9 | 26 |
| Quản trị | 123 | 9 | 26 |
| Ban sự kiện | 65 | **76** | 17 |

Gần một nửa số câu hỏi thực tế chạm tới dữ liệu tài chính hoặc thông tin liên lạc, nên phân quyền khi hỏi đáp là yêu cầu thật. 9 câu bị chặn với Thủ quỹ/Quản trị là các câu đọc `email`/`phone`. (Một câu bị chặn thì không còn chạy tới chỗ lỗi, nên cột lỗi thực thi giảm theo.)

## 4.5. Thử nghiệm với model thật: tác dụng của tri thức (evidence)

Các lần chạy dưới đây dùng **Qwen2.5-Coder 7B qua Ollama** (model mặc định), tài khoản Chủ nhiệm.

### 4.5.1. Câu hỏi mẫu BIRD kèm evidence (giao diện hiện tại)

Chọn câu mẫu **#1379** (simple) trong hộp *BIRD sample questions*: *"How many meeting events were held in 2020?"*. Hệ thống điền evidence của BIRD vào ô *External knowledge*: `meeting events refers to type = 'Meeting'; held in 2020 refers to YEAR(event_date) = 2020`. Câu hỏi còn chứa thuật ngữ `meeting` của từ điển, nên dòng tri thức gửi cho model là:

```
-- External Knowledge: meeting events refers to type = 'Meeting'; held in 2020 refers to YEAR(event_date) = 2020; meeting refers to event.type = 'Meeting'
```

| SQL model sinh | Trạng thái | Câu trả lời | Độ trễ |
|---|---|---|---|
| `SELECT COUNT(event_id) FROM event WHERE type = 'Meeting' AND event_date LIKE '2020%'` | `EXECUTED` | "In 2020, 9 meeting events were held." | ≈ 31,8 giây |

- Evidence của câu mẫu được truyền **nguyên văn**, giống hệt cách benchmark BIRD đưa evidence vào prompt; vì vậy nó vẫn chứa hàm giả `YEAR()` mà SQLite không có (vấn đề "Gap 3" trong phần nghiên cứu). Ở lần chạy này model không chép `YEAR()` mà tự dùng `LIKE '2020%'`; với model khác hoặc câu khác, chép nguyên hàm giả sẽ gây `EXEC_ERROR`. Phần thuật ngữ từ điển thì đã được chuẩn hoá bằng `normalize_pseudo_sql`.
- Thẻ kết quả hiện nhãn *BIRD sample #1379*, dòng *Knowledge added to the prompt* (nhãn `external knowledge` và `meeting`) và mục *External knowledge sent to the model* với đúng dòng ở trên, nên người dùng thấy model đã nhận tri thức gì.

### 4.5.2. Bật/tắt một thuật ngữ từ điển (đo trước khi chuyển giao diện sang tiếng Anh)

Lần đo này thực hiện ở phiên bản trước, khi giao diện, câu hỏi và từ điển còn bằng tiếng Việt: câu hỏi *"Có bao nhiêu thành viên đang hoạt động?"*, thuật ngữ `thành viên đang hoạt động` = `member.position <> 'Inactive'` (nay thuật ngữ này có tên tiếng Anh là `active member`, định nghĩa không đổi). Giữ lại như một phép đo lịch sử vì nó tách riêng đúng một biến: có hay không có tri thức.

| Thuật ngữ | Dòng tri thức trong prompt | SQL model sinh | Trạng thái | Câu trả lời |
|---|---|---|---|---|
| **Bật** | `-- External Knowledge: thành viên đang hoạt động refers to member.position <> 'Inactive'` | `SELECT COUNT(*) FROM member WHERE position != 'Inactive'` | `EXECUTED` | "Có 30 thành viên đang hoạt động." (đúng: 33 − 3 Inactive) |
| **Tắt** | (không có) | `SELECT COUNT(*) FROM member WHERE status = 'active'` | `EXEC_ERROR` (no such column: status) | Không có |

Khi không có tri thức, model **đoán** một cột `status` không tồn tại trong bảng `member` — đúng nhóm lỗi "hiểu sai nội dung CSDL" mà BIRD mô tả. Một dòng định nghĩa do CLB tự viết là đủ để biến câu hỏi từ lỗi thành đúng. Đây là minh hoạ trực tiếp nhất cho phát hiện của bài báo (evidence tăng mạnh độ chính xác) khi đưa vào hệ thống thật.

Các quan sát khác trong cùng đợt (phiên bản tiếng Việt, khi đó prompt diễn giải yêu cầu trả lời cùng ngôn ngữ với câu hỏi; nay luôn trả lời tiếng Anh):

| Câu hỏi | Kết quả | Độ trễ |
|---|---|---|
| Có bao nhiêu thành viên đang hoạt động? (thuật ngữ bật) | 1 dòng | ≈ 11 giây |
| Mỗi loại sự kiện có bao nhiêu sự kiện? | 8 dòng, giao diện tự vẽ biểu đồ cột | ≈ 21 giây |
| Tổng đã chi theo từng hạng mục là bao nhiêu? | 5 dòng, kèm biểu đồ cột | ≈ 55 giây |

Độ trễ cao do model 7B chạy cục bộ trên máy thử nghiệm và mỗi câu gọi model hai lần (sinh SQL, diễn giải). Đây là hạn chế về hạ tầng, không phải của thiết kế; có thể giảm bằng GPU mạnh hơn hoặc chọn model qua Groq.

## 4.6. Liên hệ với kết quả nghiên cứu

Tri thức ngoài và từ điển thuật ngữ là cách hệ thống áp dụng phát hiện chính của BIRD: *evidence* tăng mạnh độ chính xác. Trong khảo nghiệm của nhóm, GPT-3.5-Turbo trên 1.534 câu dev đạt 31,23% EX khi không có evidence và 47,78% khi có; trên 158 câu `student_club`, evidence tăng EX 12–25 điểm ở cả 4 model (chi tiết ở báo cáo, chương 2 và mục 8.4). Hộp *BIRD sample questions* cho phép chạy lại chính các câu đó, với chính evidence đó, trên ứng dụng. Phần khảo nghiệm (chấm EX) chạy bằng script riêng, không thuộc ứng dụng.

## 4.7. Kịch bản demo (8–10 phút)

Chuẩn bị: `python -m app.backend.appdb` để có dữ liệu sạch; Ollama chạy `qwen2.5-coder:7b` (model mặc định), hoặc `GROQ_API_KEY` trong `.env` để dùng GPT-OSS-20B qua Groq. Với model 7B chạy cục bộ, mỗi câu hỏi mất 10–60 giây — nên hỏi trước vài câu để có sẵn trong *Question history*.

| # | Tài khoản | Thao tác | Điều muốn chứng minh |
|---|---|---|---|
| 1 | `bansukien / bansukien123` | Mở **Dashboard** | Không có khối tài chính; menu không có **Finance** |
| 2 | bansukien | **Events & attendance** → **Create event** "Git Workshop" → mở sự kiện | Sự kiện mới ở `Planning`; điểm danh bị chặn (BR12) |
| 3 | bansukien | Chuyển sự kiện sang `Open`, điểm danh 3 người (**Save attendance**); thử chuyển về `Planning` | Điểm danh được; không đi lùi trạng thái (BR11) |
| 4 | bansukien | **Ask AI**: "How many meetings were held in 2020?" | Thuật ngữ `meeting` tự ghép vào prompt (nhãn trong *Knowledge added to the prompt*); trả lời một câu tiếng Anh, kèm SQL |
| 5 | bansukien | Hỏi "How much has been spent in each budget category?" | `REJECTED_PERMISSION` ở tầng engine (BR03), vẫn ghi log (BR04) |
| 6 | `thuquy / thuquy123` | **Finance** → **Expenses** → **Propose expense** một khoản nhỏ và một khoản vượt ngân sách còn lại | Cả hai chờ duyệt; khoản thứ hai có cảnh báo (BR07); Thủ quỹ không có nút **Approve** |
| 7 | `chunhiem / chunhiem123` | **Dashboard** → thẻ *Pending approval* → **Approve** khoản nhỏ | Ngân sách còn lại giảm đúng số tiền (BR06) |
| 8 | chunhiem | **Approve** khoản vượt ngân sách → bị chặn → **Reject** kèm lý do | BR07; từ chối bắt buộc có lý do |
| 9 | chunhiem | **Members** → xoá một thành viên đã từng điểm danh → chuyển sang `Inactive` | BR09; Chủ nhiệm thấy email, số điện thoại |
| 10 | chunhiem | **Ask AI** → **BIRD sample questions** → lọc *Simple* → chọn #1379 → **Ask** | Evidence của BIRD được điền vào *External knowledge* và gửi nguyên văn; xem *External knowledge sent to the model* |
| 11 | chunhiem | **Glossary** → **Add term** `year-end party` = `event.type = 'Social'` → hỏi "How many year-end party events are there?" | Tri thức nghiệp vụ do CLB tự duy trì đi thẳng vào prompt |
| 12 | chunhiem | **Change log** | Mọi thao tác ở bước 2–11 có người, thời điểm, giá trị trước/sau (BR10) |
| 13 | `admin / admin123` | **Administration** → **Query log**, **AI models**, **Accounts**, **Permissions** | Thống kê theo trạng thái có cả lần bị chặn; đổi model mặc định; khoá/mở tài khoản; ma trận quyền |

## 4.8. Hạn chế

- Giao diện, câu hỏi gợi ý, từ điển và câu trả lời đều bằng tiếng Anh (thống nhất với BIRD); hỏi bằng tiếng Việt vẫn chạy được nhưng độ chính xác chưa được đo.
- Evidence của câu mẫu BIRD được gửi nguyên văn, kể cả hàm giả như `YEAR()`, `DIVIDE()`; chỉ thuật ngữ từ điển được chuẩn hoá.
- Phiên đăng nhập lưu trong bộ nhớ tiến trình: khởi động lại máy chủ thì phải đăng nhập lại; chưa có hết hạn phiên.
- Từ điển khớp thuật ngữ theo chuỗi con, chưa xử lý từ đồng nghĩa, biến thể.
- Thay đổi tài khoản, cấu hình model và đổi mật khẩu chưa được ghi vào `audit_log` (nhật ký thay đổi hiện chỉ bao phủ dữ liệu nghiệp vụ và từ điển).
- Hỏi đáp chạy trên dữ liệu làm việc nên kết quả thay đổi theo dữ liệu; chưa có bộ câu hỏi chuẩn cho dữ liệu đã chỉnh sửa.
- Kiểm thử giao diện còn thủ công.
- Độ trễ hỏi đáp cao khi chạy model 7B cục bộ (11–55 giây/câu đo được, gồm hai lần gọi model: sinh SQL và diễn giải); muốn nhanh hơn cần GPU mạnh hơn hoặc dùng Groq.
