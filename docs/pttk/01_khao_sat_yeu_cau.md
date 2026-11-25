# 1. Khảo sát và đặc tả yêu cầu — ClubQuery

## 1.1. Bối cảnh

Một câu lạc bộ sinh viên cần quản lý thành viên, sự kiện, điểm danh và thu chi. Hiện dữ liệu nằm trong CSDL quan hệ `student_club` (lấy từ benchmark BIRD, Li et al., NeurIPS 2023), nhưng không có phần mềm nghiệp vụ đi kèm:

- Ghi điểm danh, lập ngân sách, ghi khoản chi đều phải sửa trực tiếp CSDL; không có quy trình duyệt chi, không ai biết ai đã sửa gì.
- Muốn trả lời câu hỏi như *"năm 2020 trung bình mỗi buổi họp có bao nhiêu người tham dự?"* hay *"hạng mục Food còn bao nhiêu ngân sách?"* thì phải viết SQL. Hầu hết ban chủ nhiệm không biết SQL.
- Dữ liệu tài chính và thông tin liên lạc của thành viên không được giới hạn theo người xem.

ClubQuery là **hệ thống thông tin quản lý CLB** có thêm **hỏi đáp dữ liệu bằng ngôn ngữ tự nhiên**. Phần hỏi đáp áp dụng kết quả nghiên cứu bài báo BIRD: LLM chuyển được câu hỏi thành SQL nhưng chưa đủ tin cậy, và tri thức nghiệp vụ (*evidence*) giúp tăng mạnh độ chính xác — trong khảo nghiệm của nhóm, GPT-3.5-Turbo trên toàn bộ 1.534 câu dev tăng từ **31,23% lên 47,78% EX** khi có evidence. Hệ thống hiện thực hoá điều này theo hai đường, cùng đổ vào dòng `-- External Knowledge` của prompt như BIRD: **tri thức ngoài** người hỏi tự cung cấp (gõ tay, hoặc lấy evidence của một trong 158 câu hỏi mẫu BIRD), và **từ điển thuật ngữ** do CLB tự duy trì, được ghép tự động.

Giao diện ứng dụng bằng **tiếng Anh** (thống nhất với câu hỏi, schema và evidence của BIRD); tài liệu này viết bằng tiếng Việt và trích nguyên văn các nhãn tiếng Anh khi cần.

Phần khảo nghiệm BIRD (chạy lại benchmark, chấm EX/VES, các model Ollama) vẫn nằm trong repo nhưng **ở ngoài ứng dụng**.

## 1.2. Dữ liệu

Hệ thống dùng hai CSDL SQLite:

| CSDL | Vai trò |
|---|---|
| `student_club.sqlite` (BIRD) | Dữ liệu gốc, **không bao giờ bị sửa**, chỉ dùng làm dữ liệu mồi |
| `app/data/club.sqlite` | Bản làm việc của CLB, chép từ dữ liệu gốc ở lần chạy đầu. Chức năng quản lý ghi vào đây; hỏi đáp mở nó ở chế độ **chỉ đọc** (`mode=ro`) |
| `app/data/app.sqlite` | Dữ liệu của ứng dụng: tài khoản, cấu hình model, từ điển, câu hỏi mẫu BIRD, nhật ký truy vấn, đánh giá, quy trình duyệt chi, nhật ký thay đổi |
| `dev.json` (BIRD) | 158 câu hỏi dev của `student_club` (146 câu có evidence; 101 simple, 48 moderate, 9 challenging), nạp vào bảng `sample_question` khi khởi tạo |

Dữ liệu mồi của `club.sqlite`:

| Bảng | Số dòng | Nội dung |
|---|---|---|
| `member` | 33 | Thành viên: họ tên, email, chức vụ, size áo, số điện thoại, mã bưu chính, ngành |
| `major` | 113 | Ngành học, khoa, trường |
| `zip_code` | 41.877 | Mã bưu chính, thành phố, quận, bang |
| `event` | 42 | Sự kiện: tên, ngày, loại, địa điểm, trạng thái (18 Closed, 13 Open, 11 Planning) |
| `attendance` | 326 | Điểm danh (quan hệ N–N giữa `member` và `event`) |
| `budget` | 52 | Ngân sách theo sự kiện và hạng mục (Food, Advertisement, Parking, Speaker Gifts, Club T-Shirts) |
| `expense` | 32 | Khoản chi, cột `approved` |
| `income` | 36 | Khoản thu (Dues, Fundraising, Sponsorship, School Appropration) |

## 1.3. Ranh giới hệ thống

- **Trong phạm vi:** quản lý dữ liệu CLB (thành viên, sự kiện, điểm danh, ngân sách, khoản chi có quy trình duyệt, khoản thu); tổng quan và báo cáo; hỏi đáp bằng ngôn ngữ tự nhiên; từ điển thuật ngữ; tài khoản, vai trò và ma trận quyền; nhật ký truy vấn và nhật ký thay đổi dữ liệu; cấu hình model.
- **Ngoài phạm vi:** thanh toán thật, gửi email/thông báo, đăng ký tài khoản tự do (tài khoản do quản trị tạo), khảo nghiệm benchmark BIRD. Dịch vụ LLM là hệ thống ngoài.

## 1.4. Tác nhân

| Tác nhân | Mã vai trò | Mô tả |
|---|---|---|
| Chủ nhiệm | `president` | Điều hành CLB: quản lý thành viên, sự kiện, điểm danh; **duyệt khoản chi**; quản lý từ điển; xem nhật ký thay đổi. Người duy nhất xem được email, số điện thoại thành viên |
| Thủ quỹ | `treasurer` | Lập ngân sách, **đề xuất khoản chi**, ghi khoản thu. Không tự duyệt chi |
| Ban sự kiện | `event` | Tạo, cập nhật sự kiện, điểm danh. Không xem dữ liệu tài chính |
| Quản trị hệ thống | `admin` | Quản lý tài khoản, cấu hình model, nhật ký truy vấn; quản lý từ điển; xem tài chính (chỉ đọc) và nhật ký thay đổi |
| Dịch vụ LLM (hệ thống ngoài) | — | Ollama (chạy nội bộ) hoặc Groq (dịch vụ đám mây), gọi qua API chuẩn Chat Completions: nhận prompt, trả SQL; diễn giải kết quả thành câu trả lời |

Mọi vai trò đều là **Người dùng**: đăng nhập, đổi mật khẩu, hỏi đáp, xem lịch sử, xem tổng quan và báo cáo (phần tài chính tuỳ quyền).

## 1.5. Ma trận phân quyền

Một ma trận duy nhất (`config.PERMISSIONS`) dùng chung cho API quản lý và cho bộ kiểm tra quyền của hỏi đáp.

| Quyền | Ý nghĩa | Chủ nhiệm | Thủ quỹ | Ban sự kiện | Quản trị |
|---|---|:-:|:-:|:-:|:-:|
| `member.write` | Thêm, sửa, cho nghỉ thành viên | ✓ | | | |
| `pii.read` | Xem email, số điện thoại thành viên | ✓ | | | |
| `event.write` | Thêm, sửa, đổi trạng thái sự kiện | ✓ | | ✓ | |
| `attendance.write` | Điểm danh | ✓ | | ✓ | |
| `finance.read` | Xem ngân sách, khoản chi, khoản thu | ✓ | ✓ | | ✓ |
| `finance.write` | Lập ngân sách, đề xuất chi, ghi khoản thu | | ✓ | | |
| `expense.approve` | Duyệt hoặc từ chối khoản chi | ✓ | | | |
| `glossary.write` | Quản lý từ điển thuật ngữ | ✓ | | | ✓ |
| `audit.read` | Xem nhật ký thay đổi dữ liệu | ✓ | | | ✓ |
| `system.admin` | Quản lý tài khoản, model, nhật ký truy vấn | | | | ✓ |

**Dữ liệu bị ẩn khi hỏi đáp** (suy ra từ ma trận bằng `config.restrictions(role)`):

| Vai trò | Bảng bị ẩn (thiếu `finance.read`) | Cột bị ẩn (thiếu `pii.read`) |
|---|---|---|
| Chủ nhiệm | — | — |
| Thủ quỹ | — | `member.email`, `member.phone` |
| Ban sự kiện | `budget`, `expense`, `income` | `member.email`, `member.phone` |
| Quản trị | — | `member.email`, `member.phone` |

**Tách nhiệm vụ:** Thủ quỹ đề xuất chi nhưng không duyệt được; Chủ nhiệm duyệt nhưng không lập được khoản chi. Kể cả khi một người được đổi vai trò, hệ thống vẫn chặn người đề xuất tự duyệt khoản của mình (BR08).

## 1.6. Yêu cầu chức năng

| Nhóm | Mã | Chức năng | Tác nhân |
|---|---|---|---|
| Hệ thống | UC01 | Đăng nhập, đăng xuất, đổi mật khẩu, xem quyền của mình | Tất cả |
| Hỏi đáp | UC02 | Hỏi đáp bằng ngôn ngữ tự nhiên (tiếng Anh): kèm tri thức ngoài tuỳ chọn hoặc chọn câu hỏi mẫu BIRD; sinh SQL, kiểm tra, thực thi chỉ đọc theo quyền, diễn giải | Tất cả |
| | UC03 | Xem lịch sử câu hỏi của mình | Tất cả |
| | UC04 | Đánh giá câu trả lời đúng/sai | Người đặt câu hỏi |
| | UC05 | Xuất kết quả ra CSV (chạy lại với quyền hiện tại) | Người đặt câu hỏi |
| | UC06 | Quản lý từ điển thuật ngữ (thêm, sửa, bật/tắt, xoá) | Xem: tất cả; ghi: Chủ nhiệm, Quản trị |
| Thành viên | UC07 | Quản lý thành viên (tra cứu, thêm, sửa, xoá hoặc cho nghỉ) | Xem: tất cả (che liên lạc); ghi: Chủ nhiệm |
| Sự kiện | UC08 | Quản lý sự kiện (tra cứu, thêm, sửa, xoá, đổi trạng thái Planning → Open → Closed) | Xem: tất cả; ghi: Chủ nhiệm, Ban sự kiện |
| | UC09 | Điểm danh | Chủ nhiệm, Ban sự kiện |
| Tài chính | UC10 | Quản lý ngân sách theo sự kiện và hạng mục | Xem: Chủ nhiệm, Thủ quỹ, Quản trị; ghi: Thủ quỹ |
| | UC11 | Đề xuất khoản chi (người đề xuất sửa, huỷ khi còn chờ duyệt) | Thủ quỹ |
| | UC12 | Duyệt / từ chối khoản chi | Chủ nhiệm |
| | UC13 | Quản lý khoản thu | Xem: Chủ nhiệm, Thủ quỹ, Quản trị; ghi: Thủ quỹ |
| Tổng quan, báo cáo | UC14 | Xem tổng quan (thành viên, sự kiện, tham dự; tài chính nếu có quyền) | Tất cả |
| | UC15 | Xem báo cáo tham dự theo thành viên/sự kiện; báo cáo tài chính theo sự kiện | Tham dự: tất cả; tài chính: có `finance.read` |
| Quản trị | UC16 | Xem nhật ký thay đổi dữ liệu | Chủ nhiệm, Quản trị |
| | UC17 | Cấu hình model LLM (model tag, địa chỉ, bật/tắt, model mặc định) | Quản trị |
| | UC18 | Quản lý tài khoản và vai trò | Quản trị |
| | UC19 | Xem nhật ký truy vấn toàn hệ thống, thống kê theo trạng thái | Quản trị |

## 1.7. Quy tắc nghiệp vụ

| Mã | Quy tắc | Cách cài đặt |
|---|---|---|
| BR01 | Hỏi đáp chỉ thực thi đúng một câu `SELECT` (hoặc `WITH … SELECT`) | `guard.check_select()` dùng `sqlparse`; authorizer chặn tiếp lệnh ghi giấu trong CTE |
| BR02 | Mỗi truy vấn hỏi đáp tối đa 10 giây; trả về tối đa 1000 dòng | `set_progress_handler` với hạn chót; cắt dòng khi trả kết quả |
| BR03 | Hỏi đáp chỉ đọc được bảng/cột vai trò được phép (mục 1.5) | Hai lớp: schema trong prompt bỏ bảng/cột bị cấm; `sqlite3.set_authorizer` từ chối `SQLITE_READ` trên bảng/cột đó (bắt được cả `COUNT(*)`, `SELECT *`) |
| BR04 | Mọi câu hỏi đều được ghi nhật ký, kể cả khi bị từ chối hoặc lỗi | `service.ask()` ghi `query_log` trong khối `finally` |
| BR05 | Mọi API kiểm tra đăng nhập và quyền theo ma trận | Dependency `need(quyền)` trong `deps.py` (403 nếu thiếu quyền) |
| BR06 | `budget.spent` = tổng các khoản chi **đã duyệt**; `remaining = amount − spent` | `recompute_budget()` chạy khi duyệt/từ chối chi và khi sửa ngân sách |
| BR07 | Không duyệt được khoản chi vượt ngân sách còn lại; cảnh báo ngay khi đề xuất | Kiểm tra `cost > remaining` khi duyệt (409); khi đề xuất trả `warning` |
| BR08 | Người đề xuất không được tự duyệt/từ chối khoản chi của mình | So `expense_review.proposed_by` với người duyệt (409) |
| BR09 | Thành viên đã có điểm danh, khoản chi hoặc khoản thu thì không xoá được, chỉ chuyển chức vụ sang `Inactive` | Đếm tham chiếu trước khi xoá (409) |
| BR10 | Mọi thay đổi dữ liệu được ghi `audit_log` trong cùng giao dịch | `appdb.audit()` gọi trước `commit()`; `club.sqlite` được ATTACH vào cùng kết nối với `app.sqlite` |
| BR11 | Trạng thái sự kiện chỉ đi một chiều: Planning → Open → Closed (Planning → Closed được phép) | Bảng chuyển trạng thái `EVENT_TRANSITIONS` (422 nếu đi lùi) |
| BR12 | Chỉ điểm danh được khi sự kiện đang `Open` | Kiểm tra trạng thái (409) |
| BR13 | Chỉ người đề xuất mới được sửa hoặc huỷ khoản chi của mình (khi còn chờ duyệt) | So `expense_review.proposed_by` với người thao tác (403); giao diện ẩn nút Sửa/Huỷ với người khác |

Ràng buộc bổ sung trong mã:

- Sự kiện mới phải ở trạng thái `Planning`; sự kiện đã có điểm danh hoặc ngân sách thì không xoá được (gợi ý chuyển `Closed`).
- Mỗi sự kiện chỉ có một ngân sách cho mỗi hạng mục; không lập ngân sách mới cho sự kiện đã `Closed`; số tiền ngân sách không nhỏ hơn số đã chi; ngân sách đã có khoản chi thì không xoá được.
- Chỉ khoản chi đang **chờ duyệt** mới sửa hoặc huỷ được; từ chối bắt buộc nhập lý do; không đề xuất chi cho sự kiện đã `Closed`.
- Thành viên ẩn email/số điện thoại với vai trò không có `pii.read` (cả ở API quản lý lẫn hỏi đáp).
- Mật khẩu ≥ 6 ký tự; quản trị không tự hạ quyền hoặc tự khoá mình; model mặc định phải đang bật.

## 1.8. Yêu cầu phi chức năng

| Mã | Yêu cầu | Chỉ tiêu | Kết quả |
|---|---|---|---|
| NFR1 | Toàn vẹn dữ liệu | Một thao tác nghiệp vụ (vd. duyệt chi: sửa khoản chi, tính lại ngân sách, ghi duyệt, ghi nhật ký) thành công hoặc huỷ trọn vẹn | Một giao dịch SQLite trên hai file đã ATTACH |
| NFR2 | An toàn khi hỏi đáp | SQL do model sinh không sửa được dữ liệu, không đọc được dữ liệu bị cấm | `mode=ro` + authorizer; có test |
| NFR3 | Bảo vệ dữ liệu gốc | `student_club.sqlite` không bao giờ bị sửa | Chỉ được chép sang `club.sqlite` |
| NFR4 | Bảo mật tài khoản | Mật khẩu không lưu dạng rõ; khoá API không lưu trong CSDL | PBKDF2-SHA256, 100.000 vòng, có salt; `model_config` chỉ lưu tên biến môi trường |
| NFR5 | Truy vết | Biết ai đã thay đổi gì, ai đã hỏi gì | `audit_log` (giá trị trước/sau), `query_log` |
| NFR6 | Độ trễ hỏi đáp | Ghi lại độ trễ từng câu để theo dõi theo model | `query_log.latency_ms`; thống kê trung bình ở nhật ký truy vấn. Đo thật với Qwen2.5-Coder 7B chạy cục bộ: khoảng 11–55 giây/câu (mục 4.5 của [04_kiem_thu.md](04_kiem_thu.md)) |
| NFR7 | Tối thiểu dữ liệu gửi ra ngoài | Bước diễn giải chỉ gửi tối đa 30 dòng kết quả đã qua kiểm tra quyền | `answer.MAX_ROWS_TO_LLM = 30`; model mặc định chạy nội bộ qua Ollama, dữ liệu không rời máy chủ |
| NFR8 | Giao diện | Tiếng Anh, thống nhất; dùng được trên điện thoại (rộng 390px) | Ảnh `09_mobile.png` |
