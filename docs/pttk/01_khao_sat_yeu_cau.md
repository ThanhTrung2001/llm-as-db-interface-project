# 1. Khảo sát và đặc tả yêu cầu — ClubQuery

## 1.1. Bối cảnh

Một câu lạc bộ sinh viên lưu dữ liệu hoạt động trong CSDL quan hệ `student_club` (lấy từ benchmark BIRD, Li et al., NeurIPS 2023): thành viên, ngành học, sự kiện, điểm danh, ngân sách, khoản chi, khoản thu. Muốn trả lời các câu hỏi như *"năm 2020 trung bình mỗi buổi họp có bao nhiêu người tham dự?"* hay *"tổng chi cho hạng mục Food là bao nhiêu?"*, người dùng phải viết SQL. Hầu hết thành viên ban chủ nhiệm không biết SQL.

Bài báo BIRD cho thấy LLM đã chuyển được câu hỏi tự nhiên thành SQL trên CSDL thực tế, nhưng độ chính xác còn xa con người (ChatGPT 37–42% EX so với 92,96% của con người), và tri thức nghiệp vụ (*evidence*) giúp tăng mạnh độ chính xác. ClubQuery đưa kết quả nghiên cứu đó vào một hệ thống có người dùng, phân quyền và kiểm soát.

## 1.2. Dữ liệu nguồn

| Bảng | Số dòng | Nội dung |
|---|---|---|
| `member` | 33 | Thành viên: họ tên, email, chức vụ, size áo, số điện thoại, mã bưu chính, ngành |
| `major` | 113 | Ngành học, khoa, trường |
| `zip_code` | 41.877 | Mã bưu chính, thành phố, quận, bang |
| `event` | 42 | Sự kiện: tên, ngày, loại (Meeting, Election, Game…), địa điểm, trạng thái |
| `attendance` | 326 | Điểm danh (quan hệ N–N giữa `member` và `event`) |
| `budget` | 52 | Ngân sách theo sự kiện và hạng mục |
| `expense` | 32 | Khoản chi, cờ đã duyệt |
| `income` | 36 | Khoản thu (Dues, Fundraising, Sponsorship…) |

## 1.3. Ranh giới hệ thống

- **Trong phạm vi:** hỏi đáp bằng ngôn ngữ tự nhiên trên CSDL nguồn; người dùng và vai trò; nhật ký truy vấn; đánh giá câu trả lời; từ điển nghiệp vụ; cấu hình model; nhập và xem kết quả benchmark.
- **Ngoài phạm vi:** thêm, sửa, xoá dữ liệu CLB. CSDL nguồn được mở ở chế độ **chỉ đọc**. Dịch vụ LLM là hệ thống ngoài.

## 1.4. Tác nhân

| Tác nhân | Mô tả | Quyền dữ liệu |
|---|---|---|
| Thành viên (`member`) | Thành viên CLB tra cứu sự kiện, điểm danh, thành viên | Không được đọc `budget`, `expense`, `income`, cột `member.email`, `member.phone` |
| Ban chủ nhiệm / Thủ quỹ (`board`) | Kế thừa Thành viên, được tra cứu tài chính, xuất CSV, xem dashboard | Toàn bộ, chỉ đọc |
| Quản trị viên (`admin`) | Kế thừa Ban chủ nhiệm, quản trị hệ thống | Toàn bộ, chỉ đọc |
| Dịch vụ LLM (hệ thống ngoài) | OpenAI, Groq hoặc Ollama, nhận prompt và trả SQL | — |

## 1.5. Yêu cầu chức năng

| Mã | Chức năng | Tác nhân |
|---|---|---|
| UC01 | Đăng nhập, đăng xuất | Tất cả |
| UC02 | Đặt câu hỏi bằng ngôn ngữ tự nhiên, gồm hai chế độ: hỏi trực tiếp (gọi model) và phát lại benchmark (dùng SQL model đã sinh) | Thành viên trở lên |
| UC03 | Xem lịch sử câu hỏi của mình | Thành viên trở lên |
| UC04 | Đánh giá câu trả lời đúng/sai | Thành viên trở lên |
| UC05 | Xuất kết quả ra CSV | Ban chủ nhiệm trở lên |
| UC06 | Quản lý từ điển nghiệp vụ (thêm, sửa, bật/tắt, xoá) | Quản trị viên |
| UC07 | Cấu hình model LLM (model tag, địa chỉ, bật/tắt) | Quản trị viên |
| UC08 | Nhập kết quả benchmark | Quản trị viên |
| UC09 | Xem dashboard benchmark (EX theo model, cấu hình, độ khó) | Ban chủ nhiệm trở lên |
| UC10 | Xem nhật ký truy vấn toàn hệ thống, thống kê theo trạng thái | Quản trị viên |
| UC11 | Quản lý tài khoản và vai trò | Quản trị viên |

## 1.6. Quy tắc nghiệp vụ

| Mã | Quy tắc | Cách cài đặt |
|---|---|---|
| BR01 | Chỉ thực thi đúng một câu `SELECT` (hoặc `WITH … SELECT`) | `guard.check_select()` dùng `sqlparse`; tầng engine chặn tiếp bằng authorizer |
| BR02 | Mỗi truy vấn tối đa 10 giây; hiển thị tối đa 1000 dòng | `set_progress_handler` với hạn chót; cắt dòng khi trả về |
| BR03 | Thành viên không đọc được dữ liệu tài chính và thông tin liên lạc | Hai lớp: (1) schema trong prompt bỏ bảng/cột bị cấm; (2) `sqlite3.set_authorizer` từ chối `SQLITE_READ` trên bảng/cột đó, bắt được cả `COUNT(*)` và `SELECT *` |
| BR04 | Mọi câu hỏi đều được ghi nhật ký, kể cả khi bị từ chối hoặc lỗi | `service.ask()` ghi `query_log` trong khối `finally` |
| BR05 | Chỉ quản trị viên được sửa từ điển, model, tài khoản, nhập benchmark | Dependency `require('admin')` trên từng API |

## 1.7. Yêu cầu phi chức năng

| Mã | Yêu cầu | Chỉ tiêu | Kết quả đo |
|---|---|---|---|
| NFR1 | Độ chính xác | Báo cáo EX trên 158 câu `student_club`, chấm giống `evaluation.py` của BIRD | Khớp 1896/1896 lượt chấm (xem [04_kiem_thu.md](04_kiem_thu.md)) |
| NFR2 | Độ trễ | Phát lại < 1 giây; trực tiếp ghi `latency_ms` theo model | Phát lại 1–7 ms; gpt-3.5-turbo trực tiếp ≈ 4,8 giây |
| NFR3 | Chạy được offline | Chế độ phát lại không cần mạng | Đạt |
| NFR4 | An toàn dữ liệu | CSDL nguồn không thể bị sửa | Mở `mode=ro` cộng authorizer; có test |
| NFR5 | Bảo mật tài khoản | Mật khẩu không lưu dạng rõ | PBKDF2-SHA256, 100.000 vòng, có salt |
| NFR6 | Giao diện | Dùng được trên điện thoại (rộng 390px) | Không tràn ngang (kiểm tra bằng Playwright) |
