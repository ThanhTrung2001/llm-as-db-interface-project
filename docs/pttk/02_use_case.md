# 2. Mô hình use case

## 2.1. Biểu đồ use case tổng quát

![Use case tổng quát](diagrams/usecase_tong_quat.png)

- Bốn tác nhân nghiệp vụ (Chủ nhiệm, Thủ quỹ, Ban sự kiện, Quản trị hệ thống) đều **tổng quát hoá** thành *Người dùng*, nên đều thực hiện được UC01–UC05, UC14, UC15. Các use case còn lại gắn với quyền cụ thể trong ma trận (mục 1.5 của [01_khao_sat_yeu_cau.md](01_khao_sat_yeu_cau.md)).
- Phần dữ liệu một use case hiển thị cũng phụ thuộc quyền: ví dụ UC14 *Xem tổng quan* chỉ có khối tài chính khi vai trò có `finance.read`; UC07 chỉ hiện email, số điện thoại với Chủ nhiệm.
- Dịch vụ LLM là tác nhân phụ của UC02.

## 2.2. Phân rã UC02 — Hỏi đáp bằng ngôn ngữ tự nhiên

![Phân rã UC02](diagrams/usecase_hoi_dap.png)

- *include*: mọi câu hỏi đều qua **sinh SQL**, **kiểm tra an toàn**, **thực thi chỉ đọc theo quyền** và **ghi nhật ký**.
- *extend*:
  - **Nhập tri thức ngoài** (UC02g) — người dùng tự gõ gợi ý vào ô *External knowledge (optional)*;
  - **Chọn câu hỏi mẫu BIRD** (UC02h) — chọn một trong 158 câu dev của `student_club`, hệ thống điền cả câu hỏi lẫn evidence của câu đó;
  - **Áp dụng thuật ngữ từ điển** (UC02d) khi câu hỏi chứa thuật ngữ đang bật;
  - **Diễn giải kết quả** khi thực thi thành công; **đánh giá** (UC04) và **xuất CSV** (UC05) do người dùng chọn sau khi có kết quả.

Tri thức ngoài chính là *evidence* của BIRD: trong bài báo, mỗi câu hỏi đi kèm một đoạn tri thức do người gán nhãn viết, và nó được đưa vào prompt ở dòng `-- External Knowledge:`. Ứng dụng giữ đúng cơ chế đó, với hai nguồn tri thức: do người hỏi cung cấp (tự gõ hoặc từ câu mẫu, giữ **nguyên văn**) và do CLB duy trì (từ điển, đã chuẩn hoá hàm giả).

## 2.3. Đặc tả use case

### UC02 — Hỏi đáp bằng ngôn ngữ tự nhiên

| Mục | Nội dung |
|---|---|
| Tác nhân chính | Người dùng (mọi vai trò) |
| Tác nhân phụ | Dịch vụ LLM |
| Mô tả | Người dùng hỏi bằng tiếng Anh (có thể kèm tri thức ngoài, hoặc chọn câu hỏi mẫu BIRD); hệ thống ghép tri thức ngoài và thuật ngữ từ điển thành dòng External Knowledge, sinh SQL, kiểm tra, thực thi chỉ đọc theo quyền và trả lời bằng một câu tiếng Anh dễ hiểu kèm bảng dữ liệu |
| Tiền điều kiện | Đã đăng nhập; có ít nhất một model đang bật |
| Hậu điều kiện | Một bản ghi `query_log` với trạng thái kết thúc được tạo (BR04) |
| Quy tắc áp dụng | BR01, BR02, BR03, BR04 |

**Luồng chính:**
1. Người dùng mở màn **Ask AI**, chọn model (mặc định là model đánh dấu mặc định), nhập câu hỏi (3–500 ký tự); tuỳ chọn gõ gợi ý vào ô **External knowledge (optional)** (≤ 2000 ký tự) (UC02g); bấm **Ask**.
2. Hệ thống tìm các thuật ngữ **đang bật** xuất hiện trong câu hỏi (không phân biệt hoa thường) (UC02d).
3. Hệ thống dựng tri thức: tri thức ngoài người dùng nhập **giữ nguyên văn** (như evidence trong benchmark BIRD), nối `; ` với định nghĩa thuật ngữ dạng `<term> refers to <definition>` (phần này được chuẩn hoá hàm giả `DIVIDE`, `YEAR`… sang SQLite hợp lệ). Kết quả là dòng `-- External Knowledge: …` của prompt.
4. Hệ thống dựng prompt theo khuôn BIRD: các câu `CREATE TABLE` **chỉ gồm bảng/cột vai trò được xem**, rồi tri thức, rồi câu hỏi.
5. Hệ thống gửi prompt tới Dịch vụ LLM (`temperature = 0`) và tách SQL khỏi văn bản trả về (UC02a).
6. Hệ thống kiểm tra SQL là đúng một câu `SELECT`/`WITH` (UC02b, BR01).
7. Hệ thống thực thi trên `club.sqlite` mở ở chế độ chỉ đọc, kèm authorizer theo vai trò và hạn chót 10 giây (UC02c, BR02, BR03).
8. Hệ thống gửi câu hỏi và tối đa 30 dòng đầu kết quả cho Dịch vụ LLM để diễn giải thành 1–3 câu trả lời **tiếng Anh** (UC02f).
9. Hệ thống ghi `query_log` (câu hỏi, model, câu mẫu, tri thức ngoài, thuật ngữ đã dùng, SQL, câu trả lời, trạng thái, độ trễ, số dòng) (UC02e).
10. Hệ thống hiển thị thẻ kết quả: dòng *Knowledge added to the prompt* (nhãn `external knowledge` và các thuật ngữ), câu trả lời, biểu đồ (nếu kết quả có dạng nhãn–số), *Data table*, mục thu gọn *External knowledge sent to the model* và SQL (thu gọn).

**Luồng thay thế:**
- **A1 — Không có tri thức** (bước 2–3): ô tri thức ngoài trống và không thuật ngữ nào khớp → prompt **không có** dòng External Knowledge, đúng như prompt "không evidence" của BIRD.
- **A5 — Chọn câu hỏi mẫu BIRD** (UC02h, thay bước 1): người dùng bấm **BIRD sample questions (158)**, tìm theo nội dung câu hỏi/evidence, lọc theo độ khó (*All / Simple / Moderate / Challenging*), chọn một câu. Hệ thống điền câu hỏi và evidence của câu đó vào ô tri thức ngoài, hiện nhãn *BIRD sample #id · difficulty* (bấm *Clear* để bỏ); kèm nhãn *evidence attached*, hoặc *no evidence in BIRD* với 12 câu mà BIRD để trống evidence — khi đó ô tri thức ngoài để trống và prompt không có dòng `-- External Knowledge:`. Người dùng có thể sửa tự do trước khi hỏi; mã câu mẫu được ghi vào `query_log.sample_id`. 146/158 câu có evidence.
- **A6 — Hỏi lại**: nút **Ask again** trên thẻ kết quả, hoặc hỏi lại từ **Question history**, gửi lại cả tri thức ngoài đã dùng.
- **A2 — Kết quả quá 1000 dòng** (bước 10): chỉ trả 1000 dòng đầu, có cờ `truncated`.
- **A3 — Diễn giải không dùng được model** (bước 8): model lỗi hoặc trả rỗng → câu trả lời dựng theo mẫu từ kết quả, ví dụ "Result: 9.", "2 results: Law, Business.", "No matching data was found.".
- **A4 — Đánh giá, xuất CSV**: sau bước 10 người dùng có thể bấm **Correct** / **Wrong** (UC04) hoặc **CSV** (UC05).

**Luồng ngoại lệ:**

| Mã | Điều kiện | Xử lý | Trạng thái log |
|---|---|---|---|
| E0 | Model không tồn tại hoặc đang tắt; câu hỏi rỗng/quá ngắn; tri thức ngoài quá 2000 ký tự | Báo lỗi 422 (vd. "The model does not exist or is disabled"), **không** tạo log | — |
| E1 | Gọi model lỗi (Ollama chưa chạy/model chưa pull, mạng, thiếu khoá Groq) | Báo không sinh được SQL, kèm lý do | `FAILED_GENERATION` |
| E2 | Model trả văn bản không phải SQL | Báo không sinh được truy vấn | `FAILED_GENERATION` |
| E3 | SQL có nhiều câu lệnh, hoặc là lệnh ghi/DDL | Từ chối, không thực thi | `REJECTED_UNSAFE` |
| E4 | SQL đọc bảng/cột vai trò không được xem | Từ chối, nêu dữ liệu bị cấm | `REJECTED_PERMISSION` |
| E5 | Quá 10 giây | Ngắt truy vấn | `TIMEOUT` |
| E6 | Lỗi cú pháp, sai tên cột | Hiện thông báo lỗi của SQLite | `EXEC_ERROR` |

### UC11 — Đề xuất khoản chi

| Mục | Nội dung |
|---|---|
| Tác nhân | Thủ quỹ (quyền `finance.write`) |
| Mô tả | Lập đề xuất chi gắn với một ngân sách (sự kiện + hạng mục); đề xuất chờ Chủ nhiệm duyệt |
| Tiền điều kiện | Đã đăng nhập; đã có ngân sách cho sự kiện; sự kiện chưa `Closed` |
| Hậu điều kiện | `expense` mới với `approved = 'pending'`; `expense_review` lưu người và thời điểm đề xuất; `audit_log` ghi `CREATE` — cùng một giao dịch (BR10) |
| Quy tắc | BR05, BR07 (cảnh báo), BR10, BR13 |

**Luồng chính:**
1. Thủ quỹ mở **Finance** → tab **Expenses**, bấm **Propose expense**.
2. Thủ quỹ chọn ngân sách, nhập mô tả (2–200 ký tự), ngày (`YYYY-MM-DD`), số tiền (> 0), người chi (*Paid by member*, tuỳ chọn) và lưu.
3. Hệ thống kiểm tra quyền, ngân sách tồn tại, sự kiện chưa đóng, người chi tồn tại.
4. Hệ thống ghi khoản chi ở trạng thái chờ duyệt, ghi người đề xuất và nhật ký thay đổi, rồi commit.
5. Hệ thống hiển thị khoản chi trong danh sách ở trạng thái chờ duyệt (`PENDING`); thẻ *Pending approval* của Chủ nhiệm tăng.

**Luồng thay thế:**
- **A1 — Vượt ngân sách còn lại** (bước 4): vẫn lưu đề xuất nhưng trả kèm cảnh báo "Chủ nhiệm sẽ không duyệt được nếu chưa tăng ngân sách" (BR07).
- **A2 — Sửa đề xuất**: khi còn `PENDING`, **người đã đề xuất** sửa nội dung (BR13); hệ thống kiểm tra lại như bước 3 và ghi `audit_log UPDATE`.
- **A3 — Huỷ đề xuất**: khi còn `PENDING`, **người đã đề xuất** huỷ (BR13); hệ thống xoá `expense` và `expense_review`, ghi `audit_log DELETE`.

**Ngoại lệ:** không có quyền → 403; sửa/huỷ đề xuất của người khác → 403 (BR13); ngân sách/thành viên không tồn tại → 422; sự kiện đã `Closed` → 409; sửa/huỷ khoản đã duyệt hoặc đã từ chối → 409.

### UC12 — Duyệt khoản chi

| Mục | Nội dung |
|---|---|
| Tác nhân | Chủ nhiệm (quyền `expense.approve`) |
| Mô tả | Duyệt hoặc từ chối khoản chi đang chờ duyệt; duyệt thì ngân sách được tính lại |
| Tiền điều kiện | Có khoản chi ở trạng thái `PENDING` |
| Hậu điều kiện | Duyệt: `approved = 'true'`, `budget.spent`/`remaining` được tính lại. Từ chối: `approved = 'false'`, lưu lý do. Cả hai: `expense_review` lưu người duyệt, thời điểm, ghi chú; `audit_log` ghi `APPROVE`/`REJECT`. Tất cả trong **một giao dịch** trên hai CSDL |
| Quy tắc | BR05, BR06, BR07, BR08, BR10 |

**Luồng chính (duyệt):**
1. Chủ nhiệm mở Tài chính → Khoản chi; các khoản chờ duyệt xếp đầu, kèm ngân sách còn lại của hạng mục.
2. Chủ nhiệm bấm **Approve** (có thể nhập ghi chú).
3. Hệ thống kiểm tra: khoản chi đang `PENDING`; người duyệt khác người đề xuất (BR08); số tiền ≤ ngân sách còn lại (BR07).
4. Hệ thống đặt `approved = 'true'`, cập nhật `expense_review`, tính lại `spent` và `remaining` của ngân sách (BR06), ghi `audit_log APPROVE`, rồi commit.
5. Danh sách hiển thị khoản chi "Đã duyệt"; ngân sách còn lại giảm tương ứng.

**Luồng thay thế:**
- **A1 — Từ chối** (bước 2): Chủ nhiệm bấm **Reject** và nhập lý do (*Reason for rejection*); hệ thống kiểm tra BR08 và lý do không rỗng, đặt `approved = 'false'`, lưu lý do, ghi `audit_log REJECT`. Ngân sách không đổi.

**Ngoại lệ:**

| Điều kiện | Xử lý |
|---|---|
| Vai trò không có `expense.approve` (vd. Thủ quỹ) | 403 |
| Khoản chi đã được xử lý | 409 "This expense has already been reviewed" |
| Người duyệt chính là người đề xuất (BR08) | 409 "You cannot review an expense you proposed" |
| Số tiền vượt ngân sách còn lại (BR07) | 409, nêu số tiền và số còn lại; Chủ nhiệm từ chối hoặc chờ Thủ quỹ tăng ngân sách |
| Từ chối mà không có lý do | 422 |
| Lỗi giữa chừng | Không commit → mọi thay đổi trên cả hai CSDL bị huỷ |

### UC09 — Điểm danh

| Mục | Nội dung |
|---|---|
| Tác nhân | Chủ nhiệm, Ban sự kiện (quyền `attendance.write`) |
| Mô tả | Ghi danh sách thành viên tham dự một sự kiện |
| Tiền điều kiện | Sự kiện đang ở trạng thái `Open` (BR12) |
| Hậu điều kiện | Danh sách `attendance` của sự kiện được thay bằng danh sách mới; `audit_log` ghi số người, số thêm, số bớt và danh sách trước/sau |
| Quy tắc | BR05, BR10, BR12 |

**Luồng chính:**
1. Người dùng mở **Events & attendance**, chọn một sự kiện đang `Open`; hộp chi tiết sự kiện hiện danh sách điểm danh.
2. Hệ thống hiển thị danh sách thành viên, đánh dấu sẵn người đã điểm danh.
3. Người dùng đánh dấu/bỏ đánh dấu (có ô *Search members…*, *Select all*, *Clear*) rồi bấm **Save attendance**.
4. Hệ thống kiểm tra quyền, trạng thái sự kiện và sự tồn tại của từng thành viên.
5. Hệ thống xoá điểm danh cũ của sự kiện, ghi danh sách mới, ghi `audit_log` rồi commit trong một giao dịch.
6. Hệ thống báo số người tham dự.

**Hướng dẫn trên giao diện:** với sự kiện `Planning`, hộp chi tiết nhắc người có quyền `event.write`: "click **Open event** below, tick the members who came, then **Save attendance**".

**Ngoại lệ:** sự kiện `Planning` hoặc `Closed` → 409 "Attendance can only be recorded while the event is Open."; danh sách có thành viên không tồn tại → 422; vai trò Thủ quỹ/Quản trị → 403.

### UC07 — Quản lý thành viên

| Mục | Nội dung |
|---|---|
| Tác nhân | Xem: mọi vai trò. Thêm, sửa, xoá: Chủ nhiệm (`member.write`) |
| Mô tả | Tra cứu danh sách và chi tiết thành viên (ngành, số sự kiện đã tham dự); thêm, sửa, xoá hoặc cho nghỉ |
| Hậu điều kiện | Bảng `member` được cập nhật; `audit_log` ghi `CREATE`/`UPDATE`/`DELETE` kèm giá trị trước/sau |
| Quy tắc | BR05, BR09, BR10; che email, số điện thoại khi thiếu `pii.read` |

**Luồng chính (thêm):**
1. Chủ nhiệm mở **Members**, bấm **Add member**.
2. Nhập họ, tên (bắt buộc), email, số điện thoại, chức vụ (President, Vice President, Secretary, Treasurer, Member, Inactive), size áo, mã bưu chính, ngành; lưu.
3. Hệ thống kiểm tra: chức vụ và size áo thuộc danh mục, email đúng định dạng, mã bưu chính và ngành tồn tại.
4. Hệ thống sinh mã thành viên (dạng `rec` + 14 ký tự như dữ liệu gốc), lưu, ghi `audit_log` và commit.

**Luồng thay thế:**
- **A1 — Tra cứu:** mọi vai trò xem danh sách (thành viên `Inactive` xếp cuối) và chi tiết; với vai trò không có `pii.read`, email và số điện thoại trả về rỗng.
- **A2 — Sửa:** như bước 2–4, ghi `audit_log UPDATE`.
- **A3 — Xoá:** nếu thành viên chưa có điểm danh, khoản chi, khoản thu thì xoá và ghi `audit_log DELETE`.

**Ngoại lệ:** dữ liệu không hợp lệ → 422 (nêu trường lỗi); xoá thành viên đã có dữ liệu liên quan → 409, gợi ý chuyển chức vụ sang `Inactive` (BR09); vai trò khác Chủ nhiệm thêm/sửa/xoá → 403.

### UC06 — Quản lý từ điển thuật ngữ

| Mục | Nội dung |
|---|---|
| Tác nhân | Xem: mọi vai trò. Thêm, sửa, bật/tắt, xoá: Chủ nhiệm, Quản trị (`glossary.write`) |
| Mô tả | Duy trì thuật ngữ nghiệp vụ và định nghĩa SQL tương ứng. Thuật ngữ đang bật được ghép tự động vào prompt như *evidence* của BIRD |
| Hậu điều kiện | `glossary_term` được cập nhật (người và thời điểm sửa); `audit_log` ghi thay đổi; câu hỏi sau đó dùng từ điển mới |
| Quy tắc | BR05, BR10; thuật ngữ duy nhất, không phân biệt hoa thường (kể cả chữ có dấu) |

**Luồng chính:** (1) Mở màn **Glossary** → (2) bấm **Add term**, nhập thuật ngữ (2–80 ký tự) và định nghĩa (2–500 ký tự) → (3) hệ thống kiểm tra quyền và tính duy nhất → (4) lưu, ghi nhật ký, làm mới danh sách.
**Luồng thay thế:** sửa định nghĩa; tắt thuật ngữ (giữ lại nhưng không ghép vào prompt); xoá thuật ngữ.
**Ngoại lệ:** thuật ngữ đã tồn tại (vd. "TIỆC CUỐI NĂM" khi đã có "tiệc cuối năm") → 409 "This term already exists"; vai trò không có quyền → 403, giao diện ẩn nút thêm/sửa.

### UC18 — Quản lý tài khoản

| Mục | Nội dung |
|---|---|
| Tác nhân | Quản trị hệ thống (`system.admin`) |
| Mô tả | Thêm tài khoản, đổi họ tên, vai trò, khoá/mở, đặt lại mật khẩu |
| Quy tắc | Tên đăng nhập 3–40 ký tự (chữ, số, `_`, `.`) và duy nhất; vai trò ∈ {president, treasurer, event, admin}; mật khẩu ≥ 6 ký tự, lưu dạng băm PBKDF2; quản trị không tự hạ quyền hoặc tự khoá mình |

**Luồng chính:** (1) Mở **Administration** → tab **Accounts** → (2) nhập tên đăng nhập, họ tên, vai trò, mật khẩu, bấm Thêm → (3) hệ thống kiểm tra, băm mật khẩu, lưu → (4) danh sách cập nhật.
**Luồng thay thế:** sửa tài khoản có sẵn (họ tên, vai trò, trạng thái; nhập mật khẩu mới nếu muốn đặt lại). Tài khoản bị khoá không đăng nhập được, phiên đang mở bị từ chối (401) ngay ở yêu cầu kế tiếp. Đổi vai trò có hiệu lực ngay vì quyền được tra lại ở mỗi yêu cầu.
**Ngoại lệ:** trùng tên đăng nhập → 409; vai trò không hợp lệ hoặc mật khẩu ngắn → 422; tự hạ quyền/tự khoá → 422; tài khoản không tồn tại → 404.

### Các use case còn lại (tóm tắt)

| UC | Luồng chính | Ngoại lệ chính |
|---|---|---|
| UC01 Đăng nhập, đổi mật khẩu | Nhập tên, mật khẩu → nhận token phiên và danh sách quyền; đổi mật khẩu cần mật khẩu cũ | Sai thông tin hoặc tài khoản khoá → 401; mật khẩu cũ sai → 422 |
| UC03 Lịch sử | Màn **Question history**: 200 câu hỏi gần nhất của chính mình, kèm trạng thái, đánh giá; hỏi lại một câu (kèm tri thức ngoài đã dùng) | — |
| UC04 Đánh giá | Bấm **Correct** (1) hoặc **Wrong** (−1), có thể kèm nhận xét; đánh giá lại thì ghi đè | Câu hỏi của người khác → 404 |
| UC05 Xuất CSV | Chạy lại SQL đã lưu **với quyền hiện tại** của người dùng, tải file CSV (UTF-8 BOM) | Câu không thành công/của người khác → 404; quyền đã bị thu hồi → 409 |
| UC08 Quản lý sự kiện | Thêm (luôn ở `Planning`), sửa, đổi trạng thái theo một chiều, xoá | Đi lùi trạng thái → 422 (BR11); xoá sự kiện đã có điểm danh/ngân sách → 409 |
| UC10 Ngân sách | Lập ngân sách cho (sự kiện, hạng mục) ở **Finance → Budgets → Create budget**, hoặc nút **Add budget** trong hộp chi tiết sự kiện (Thủ quỹ; form chọn sẵn sự kiện); sửa số tiền; xoá. Chủ nhiệm thấy dòng nhắc "Budgets are created by the Treasurer" | Sự kiện đã `Closed` → 409; trùng hạng mục → 409; số tiền < đã chi → 422; đã có khoản chi → 409 |
| UC13 Khoản thu | Ghi, sửa, xoá khoản thu (ngày, số tiền, nguồn, người nộp) | Nguồn không hợp lệ → 422 |
| UC14 Tổng quan | Số thành viên hoạt động/nghỉ/ban điều hành, sự kiện theo trạng thái và loại, sự kiện sắp tới, tham dự trung bình, top tham dự; tài chính (tổng ngân sách, đã chi, còn lại, thu, chờ duyệt, chi theo hạng mục, thu theo nguồn, thu chi theo tháng) nếu có `finance.read` | — |
| UC15 Báo cáo | Tỉ lệ tham dự từng thành viên (trên số sự kiện không còn `Planning`), số người từng sự kiện; tài chính theo sự kiện và thu theo nguồn | Báo cáo tài chính khi thiếu `finance.read` → 403 |
| UC16 Nhật ký thay đổi | Xem 500 thay đổi gần nhất (ai, lúc nào, hành động, đối tượng, tóm tắt, chi tiết trước/sau), lọc theo đối tượng | Thiếu `audit.read` → 403 |
| UC17 Cấu hình model | Sửa model tag, địa chỉ, bật/tắt, đặt mặc định (chỉ một model mặc định); nhà cung cấp ∈ {ollama, groq, openrouter} | Đặt mặc định cho model đang tắt → 422 |
| UC19 Nhật ký truy vấn | Xem 500 câu hỏi gần nhất của mọi người, lọc theo trạng thái; thống kê số lượng và độ trễ trung bình theo trạng thái; thống kê đánh giá | Không phải quản trị → 403 |
