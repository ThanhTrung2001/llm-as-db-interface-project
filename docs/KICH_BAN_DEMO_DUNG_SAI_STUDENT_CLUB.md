# Kịch bản demo live: 1 câu đúng, 1 câu sai (student_club, Qwen2.5-Coder 7B)

> **Model:** `qwen2.5-coder:7b-instruct` qua Ollama, cấu hình **có evidence**, `temperature = 0`.
> **Câu đúng:** #1332 (moderate). **Câu sai:** #1386 (simple), lỗi **schema linking**.
> Mỗi đoạn có 2 phần: **[LÀM]** là gõ hoặc mở gì, **[NÓI]** là lời thoại.
> Đã chạy thử ngày 17/11/2026: kết quả live **trùng 100%** với `exp_result/ollama_gwen25_output/predict_dev.json`.

| # | Phần | Thời lượng |
|---|---|---|
| 0 | Chuẩn bị (trước giờ demo) | — |
| 1 | Giới thiệu 3 bảng và đường nối | 0:40 |
| 2 | Câu đúng #1332: chạy, xem prompt, xem SQL, chấm EX | 1:30 |
| 3 | Câu sai #1386: chạy, xem SQL, lỗi, chấm EX | 1:30 |
| 4 | Soi lỗi trực tiếp trên CSDL | 0:50 |
| 5 | Lỗi này phổ biến cỡ nào + kết luận | 0:30 |

---

## 0. Chuẩn bị (trước giờ demo)

1. Bật Ollama và **làm nóng model** (lần gọi đầu mất thêm thời gian nạp model vào VRAM):
   ```powershell
   ollama serve                      # nếu chưa chạy
   ollama run qwen2.5-coder:7b-instruct "SELECT 1"
   ```
2. Mở terminal ở thư mục gốc repo `d:\AI Learning\Paper\LLM`.
3. Mở sẵn 2 tab terminal SQLite trỏ vào CSDL:
   ```powershell
   sqlite3 "src\DAMO-ConvAI\bird\data\dev_databases\student_club\student_club.sqlite"
   ```
4. Chạy thử 2 lệnh ở bước 2 và 3 một lần. Log cũ sẽ bị ghi đè nên lúc demo vẫn sạch.
5. **Phương án dự phòng:** nếu Ollama lỗi lúc demo, mở 2 file log đã chạy sẵn:
   `app/logs/benchmark_ollama_1332_evidence.log` và `app/logs/benchmark_ollama_1386_evidence.log`.

---

## 1. Giới thiệu 3 bảng và đường nối (0:40)

**[LÀM]** Chiếu sơ đồ (vẽ tay hoặc slide):

```
event (event_id, event_name, ...)
   ▲  budget.link_to_event
budget (budget_id, category, spent, amount, link_to_event)
   ▲  expense.link_to_budget
expense (expense_id, cost, expense_date, link_to_budget, link_to_member)
```

**[NÓI]**
> "Hai câu demo đều xoay quanh 3 bảng của CLB: **event** là sự kiện, **budget** là ngân sách theo từng hạng mục của sự kiện, **expense** là từng khoản chi.
> Quan hệ đi theo chuỗi: một sự kiện có nhiều dòng ngân sách, mỗi dòng ngân sách có nhiều khoản chi.
> Điểm cần nhớ: bảng **expense không nối thẳng với event**. Muốn đi từ sự kiện tới khoản chi thì bắt buộc phải qua budget.
> Câu thứ nhất chỉ cần event với budget, câu thứ hai cần đi hết cả chuỗi. Mình xem model xử lý hai trường hợp này thế nào."

---

## 2. Câu đúng #1332 (1:30)

**[LÀM]** Gõ lệnh:

```powershell
venv\Scripts\python app\scripts\trace_benchmark_ollama.py --question_id 1332
```

Trong lúc chờ khoảng 10 giây, mở `app/logs/benchmark_ollama_1332_evidence.log` và lần lượt chỉ:

**Bước 1: câu hỏi và evidence**
```
question : How much did the Student_Club members spend on food in September Meeting?
evidence : amount spent refers to spent; spend on food in September Meeting refers to
           category = 'Food' where event_name = 'September Meeting'
```

**Bước 4.3: prompt.** Cuộn nhanh qua 8 câu `CREATE TABLE`, dừng ở 3 dòng cuối:
```
-- External Knowledge: amount spent refers to spent; ... category = 'Food' where event_name = 'September Meeting'
-- Using valid SQLite and understading External Knowledge, answer the following questions for the tables provided above.
-- How much did the Student_Club members spend on food in September Meeting?
Respond with the final SQLite query only, inside a ```sql code block. Do not add any explanation.
```

**Bước 6: SQL model sinh ra**
```sql
SELECT SUM(T1.spent) FROM budget AS T1
INNER JOIN event AS T2 ON T1.link_to_event = T2.event_id
WHERE T2.event_name = 'September Meeting' AND T1.category = 'Food'
```

**Bước 9a/9b/9c: chấm điểm**
```
9a  predicted → [(101.94,)]
9b  gold      → [(101.94,)]
9c  set(pred) == set(gold) → res = 1   ✅
```

**[NÓI]**
> "Câu hỏi: CLB đã chi bao nhiêu cho đồ ăn trong buổi September Meeting.
> Evidence chỉ rõ cho model: 'spent' là cột `spent`, 'food' là `category = 'Food'`, tên sự kiện nằm ở `event_name`.
> Model chỉ còn phải tìm xem các cột này nằm ở bảng nào: `spent` và `category` ở **budget**, `event_name` ở **event**. Hai bảng nối trực tiếp qua `budget.link_to_event = event.event_id`, chỉ **một bước join**.
> Kết quả 101,94, trùng với đáp án, nên **EX = 1**.
> Lưu ý: model viết `SUM(spent)`, đáp án viết `spent` và còn lọc thêm theo tháng 9. Câu chữ khác nhau nhưng kết quả chạy giống nhau, nên vẫn tính là đúng. BIRD chấm theo **kết quả chạy**, không so mặt chữ SQL."

---

## 3. Câu sai #1386 (1:30)

**[LÀM]** Gõ lệnh:

```powershell
venv\Scripts\python app\scripts\trace_benchmark_ollama.py --question_id 1386
```

Mở `app/logs/benchmark_ollama_1386_evidence.log`:

**Bước 1: câu hỏi và evidence**
```
question : What is the total expense for the Yearly Kickoff?
evidence : 'Yearly Kickoff' is an event name; total expense refers to SUM(cost)
```

**Bước 6: SQL model sinh ra**
```sql
SELECT SUM(T2.cost) FROM event AS T1
INNER JOIN expense AS T2 ON T1.event_id = T2.link_to_event
WHERE T1.event_name = 'Yearly Kickoff'
```

**Bước 9a/9b/9c: chấm điểm**
```
9a  predicted → LỖI: no such column: T2.link_to_event
9b  gold      → [(449.13,)]
9c  res = 0   ❌
```

**[NÓI]**
> "Câu này còn được BIRD xếp là **simple**: tổng chi cho sự kiện Yearly Kickoff là bao nhiêu.
> Phần hiểu câu hỏi model làm đúng hết: lấy `SUM(cost)` như evidence nói, lọc `event_name = 'Yearly Kickoff'`.
> Nhưng model **nối thẳng expense với event** qua cột `expense.link_to_event`. Cột này **không tồn tại**, nên SQLite báo `no such column` và câu bị chấm 0.
> Đây là **lỗi schema linking**: hiểu đúng câu hỏi nhưng gắn sai vào bảng và cột của CSDL."

---

## 4. Soi lỗi trực tiếp trên CSDL (0:50)

**[LÀM]** Trong tab SQLite, gõ lần lượt:

```sql
-- (a) expense có những cột nào?
PRAGMA table_info(expense);
--  expense_id | expense_description | expense_date | cost | approved | link_to_member | link_to_budget
--  → KHÔNG có link_to_event

-- (b) link_to_event thật ra nằm ở đâu?
PRAGMA table_info(budget);
--  budget_id | category | spent | remaining | amount | event_status | link_to_event   ← ở đây

-- (c) Sửa lại: đi đúng chuỗi event → budget → expense
SELECT SUM(T3.cost)
FROM event AS T1
JOIN budget  AS T2 ON T1.event_id  = T2.link_to_event
JOIN expense AS T3 ON T2.budget_id = T3.link_to_budget
WHERE T1.event_name = 'Yearly Kickoff';
--  449.13   ← khớp đáp án
```

**[NÓI]**
> "`link_to_event` là cột có thật, nhưng nằm ở bảng **budget**. Các khoá ngoại trong CSDL này đều đặt tên kiểu `link_to_...`, nên model 7B **đoán theo mẫu tên** rồi gán nhầm cho bảng expense.
> Điều đáng chú ý: thông tin đúng **đã có sẵn trong prompt**. Câu `CREATE TABLE expense` có ghi rõ `foreign key (link_to_budget) references budget(budget_id)`. Model vẫn bỏ qua và chọn đường tắt.
> Thêm đúng bảng trung gian budget là ra 449,13, khớp đáp án."

---

## 5. Lỗi này phổ biến cỡ nào + kết luận (0:30)

**[LÀM]** Chiếu bảng:

| Qwen2.5-Coder 7B, có evidence, student_club (158 câu) | Số câu | % |
|---|---|---|
| Đúng | 114 | 72,15% |
| Sai do schema linking | 22 | 13,92% (chiếm **50%** số câu sai) |
| Sai logic hoặc giá trị | 21 | 13,29% |
| Lỗi thực thi khác | 1 | 0,63% |

Riêng lỗi `expense.link_to_event` lặp lại ở 8 câu: #1342, #1386, #1389, #1390, #1401, #1448, #1451, #1454.

**[NÓI]**
> "Trên student_club, Qwen đúng 72%. Trong số câu sai, **một nửa là lỗi schema linking**, nhiều nhất so với các nhóm lỗi khác.
> Riêng kiểu lỗi vừa xem, nối thẳng expense với event, lặp lại ở 8 câu, nhiều câu trong đó chỉ là mức simple.
> Kết luận: evidence giúp model hiểu **câu hỏi**, nhưng không giúp model hiểu **cấu trúc nối giữa các bảng**. Hướng cải thiện là nêu rõ đường nối khoá ngoại trong prompt, lọc bớt schema không liên quan, hoặc chạy thử SQL rồi cho model tự sửa khi gặp lỗi `no such column`."

---

## Mẹo khi trình bày

- **Chạy câu đúng trước** để khán giả hiểu luồng, sau đó câu sai chỉ cần chỉ vào bước 6 và bước 9.
- Kết quả live ổn định nhờ `temperature = 0`, nhưng vẫn **giữ sẵn 2 file log** phòng Ollama lỗi.
- **Câu hỏi hay gặp:**
  - *"Model có thấy khoá ngoại không?"* → Có. Prompt chứa nguyên `CREATE TABLE` kèm dòng `foreign key`, xem bước 4.1 của log.
  - *"Sao câu simple lại sai còn câu moderate lại đúng?"* → Độ khó BIRD dựa trên câu hỏi, không dựa trên số bước join. #1386 cần 2 join qua bảng trung gian, #1332 chỉ cần 1 join trực tiếp.
  - *"Không có evidence thì sao?"* → Thêm `--no_knowledge` vào lệnh để chạy lại.
- Số liệu ở phần 5 dùng cách chia nhóm heuristic (dựa vào lỗi `no such column/table` và so tập bảng/cột với gold), chưa gán nhãn thủ công.
