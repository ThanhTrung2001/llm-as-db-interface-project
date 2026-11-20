# Kịch bản demo luồng Benchmark BIRD — 5 phút

> Ví dụ xuyên suốt: **câu 1379** (`student_club`, simple).
> Mỗi đoạn có 2 phần: **[MÀN HÌNH]** = mở cái gì, **[NÓI]** = lời thoại (đọc gần nguyên văn được).
> Số giờ chạy Kaggle: điền vào các chỗ `__h__` trước khi demo (xem tab *Version / Logs* của notebook).

| # | Phần | Thời lượng | Mốc |
|---|---|---|---|
| 0 | Mở đầu — bức tranh tổng | 0:30 | 0:00 → 0:30 |
| 1 | Đọc `dev.json` → lấy 1 câu | 0:40 | 0:30 → 1:10 |
| 2 | **Dựng prompt (core)** | 1:30 | 1:10 → 2:40 |
| 3 | Gọi LLM → tách SQL → `predict_dev.json` | 0:30 | 2:40 → 3:10 |
| 4 | Chấm EX | 0:35 | 3:10 → 3:45 |
| 5 | Chấm VES | 0:35 | 3:45 → 4:20 |
| 6 | Kết quả Kaggle + kết luận | 0:40 | 4:20 → 5:00 |

---

## 0. Mở đầu (0:30)

**[MÀN HÌNH]** Drawio, trang tổng quan. Chỉ tay theo 4 khối: ① → ② → ③ → ④.

**[NÓI]**
> "Bài toán là Text-to-SQL: cho câu hỏi tiếng Anh và một CSDL, model phải viết ra SQL. Benchmark BIRD đo việc này bằng 1.534 câu hỏi trên 11 CSDL.
> Luồng có 4 bước: **chuẩn bị dữ liệu → sinh SQL cho từng câu → chấm điểm EX và VES → lập bảng**.
> Điểm quan trọng nhất của BIRD là mỗi câu có kèm **evidence**, tức tri thức ngoài. Nên mỗi model chạy 2 lần: **có** evidence và **không** evidence, để đo xem tri thức ngoài giúp được bao nhiêu.
> Em sẽ đi qua luồng bằng đúng một câu ví dụ là câu 1379."

---

## 1. Đọc `dev.json` → lấy 1 câu (0:40)

**[MÀN HÌNH]** Khối ① rồi hình thoi "Cấu hình evidence?". Mở sẵn 1 phần tử JSON:

```json
{
  "question_id": 1379,
  "db_id": "student_club",
  "question": "How many meeting events were held in 2020?",
  "evidence": "meeting events refers to type = 'Meeting'; held in 2020 refers to YEAR(event_date) = 2020",
  "SQL": "SELECT COUNT(event_id) FROM event WHERE type = 'Meeting' AND SUBSTR(event_date, 1, 4) = '2020'",
  "difficulty": "simple"
}
```

**[NÓI]**
> "Mỗi câu trong `dev.json` có 5 thứ: câu hỏi, tên CSDL, evidence, SQL đáp án và độ khó.
> Hàm `decouple_question_schema` tách ra 3 danh sách song song: **câu hỏi**, **đường dẫn file .sqlite** ghép từ `db_id`, và **evidence**.
> SQL đáp án **không** đưa vào prompt — nó chỉ dùng lúc chấm điểm.
> Đến hình thoi: nếu chạy cờ `--no_knowledge` thì toàn bộ evidence bị thay bằng `None`; còn lại thì dùng nguyên văn. Đây là **chỗ rẽ nhánh duy nhất** giữa hai cấu hình."

---

## 2. Dựng prompt — phần core (1:30)

**[MÀN HÌNH]** Khối ② bước 2→4. Mở `openai_request.py` / `ollama_request.py`, cuộn tới 3 hàm `generate_schema_prompt`, `generate_comment_prompt`, `generate_combined_prompts_one`. Sau đó chiếu **prompt hoàn chỉnh** bên dưới (có tô màu 3 phần nếu kịp).

Prompt thật của câu 1379 (bản Ollama, có evidence):

```
CREATE TABLE event                     ┐
(                                      │
    event_id   TEXT constraint event_pk primary key,
    event_name TEXT,                   │  PHẦN A — Schema
    event_date TEXT,                   │  generate_schema_prompt(db_path)
    type       TEXT,                   │  = CREATE TABLE của cả 8 bảng
    ...                                │    lấy thẳng từ sqlite_master
)                                      │
CREATE TABLE major ( ... )             │
... (8 bảng, ~2.200 ký tự)             ┘

-- External Knowledge: meeting events refers to type = 'Meeting'; held in 2020 refers to YEAR(event_date) = 2020    ┐ PHẦN B — Đề bài
-- Using valid SQLite and understading External Knowledge, answer the following questions for the tables provided above. │ generate_comment_prompt
-- How many meeting events were held in 2020?                                                                          ┘ (question, knowledge)
Respond with the final SQLite query only, inside a ```sql code block. Do not add any explanation.   ← PHẦN C — Câu dặn cuối
```

Không evidence thì phần B chỉ còn 2 dòng:

```
-- Using valid SQLite, answer the following questions for the tables provided above.
-- How many meeting events were held in 2020?
```

**[NÓI]**
> "Đây là phần quan trọng nhất. Prompt gồm **3 phần ghép nối**:
>
> **Phần A — schema.** Hàm `generate_schema_prompt` mở file .sqlite, đọc bảng hệ thống `sqlite_master` và lấy nguyên câu `CREATE TABLE` của **mọi bảng**. Với `student_club` là 8 bảng. Model chỉ được thấy tên bảng, tên cột, kiểu dữ liệu và khoá — **không** thấy dữ liệu mẫu, **không** thấy file mô tả cột.
>
> **Phần B — đề bài**, viết dưới dạng **comment SQL** bắt đầu bằng `--`, để model hiểu đây là ngữ cảnh SQL. Hàm `generate_comment_prompt` có hai nhánh:
> - Có evidence: thêm dòng `-- External Knowledge: ...` lên đầu, và câu lệnh đổi thành 'Using valid SQLite **and understanding External Knowledge**'.
> - Không evidence: chỉ còn câu lệnh và câu hỏi.
>
> Nhìn evidence của câu này: nó nói thẳng 'meeting events' là `type = 'Meeting'`, và 'năm 2020' là lấy năm của `event_date`. Không có dòng này, model phải **tự đoán** chữ 'meeting' ứng với cột nào, giá trị viết hoa hay thường — rất dễ sai.
>
> **Phần C — câu dặn cuối**, khác nhau theo model:
> - GPT-3.5 giữ đúng paper: 'Generate the SQL after thinking step by step:' rồi **viết sẵn chữ `SELECT`** để model viết tiếp.
> - Model chạy local qua Ollama thì em đổi thành 'Chỉ trả về SQL trong khối code'. Lý do: em thử dùng mồi `SELECT` cho Qwen và DeepSeek thì model trả lời bằng đoạn văn giải thích, EX tụt gần 0%.
>
> Ba phần nối lại bằng `generate_combined_prompts_one` thành **một tin nhắn duy nhất** gửi cho model. Hai cấu hình có/không evidence **chỉ khác đúng phần B**, mọi thứ khác giống hệt — nên chênh lệch điểm chính là giá trị của tri thức ngoài."

---

## 3. Gọi LLM → tách SQL → `predict_dev.json` (0:30)

**[MÀN HÌNH]** Khối ② bước 5→8 và tờ giấy vàng `predict_dev.json`.

**[NÓI]**
> "Prompt được gửi với `temperature = 0` để chạy lại vẫn ra cùng kết quả. GPT-3.5 thêm giới hạn 256 token và dừng khi gặp `;`, dòng trống hoặc `--`, giống paper.
> Hàm `extract_sql` bóc câu SQL ra khỏi khối ```sql, bỏ đoạn `<think>` nếu có, cắt tại dấu `;` đầu tiên. Lỗi gì thì câu đó nhận SQL rỗng `"SELECT"` và **chạy tiếp câu sau**, không dừng cả lượt.
> Mỗi SQL được gắn tên CSDL bằng chuỗi phân cách `----- bird -----`, cứ 50 câu ghi tạm ra file một lần phòng Kaggle bị ngắt. Kết thúc ta có `predict_dev.json` đủ 1.534 khoá.
> Câu 1379 model trả về: `SELECT COUNT(*) FROM event WHERE type = 'Meeting' AND STRFTIME('%Y', event_date) = '2020'`."

---

## 4. Chấm EX — `evaluation.py` (0:35)

**[MÀN HÌNH]** Khối ③ CHẤM EX. Đặt 2 SQL cạnh nhau:

```
Model : SELECT COUNT(*)        FROM event WHERE type='Meeting' AND STRFTIME('%Y', event_date) = '2020'   → [(n,)]
Gold  : SELECT COUNT(event_id) FROM event WHERE type='Meeting' AND SUBSTR(event_date,1,4)      = '2020'   → [(n,)]
                                                                                       set(...) == set(...) → 1
```

**[NÓI]**
> "EX là **Execution Accuracy**. BIRD **không so chữ** của SQL — vì một câu hỏi có nhiều cách viết đúng. Nó **chạy cả hai câu** trên cùng CSDL rồi so **tập kết quả**: `set(kết quả model) == set(kết quả gold)`. Bằng nhau được 1, khác được 0. SQL lỗi cú pháp, sai tên cột, hoặc chạy quá 30 giây cũng là 0.
> Ví dụ câu 1379: model dùng `STRFTIME`, đáp án dùng `SUBSTR`, viết khác hẳn nhưng ra cùng một con số → **đúng**.
> 1.534 cặp được chấm song song nhiều tiến trình, rồi tính **EX = số câu đúng / tổng số câu × 100**, tách theo 3 độ khó simple / moderate / challenging."

---

## 5. Chấm VES — `evaluation_ves.py` (0:35)

**[MÀN HÌNH]** Khối ③ CHẤM VES. Bảng nhỏ:

| Câu | R = t_gold / t_pred | Điểm đóng góp √R × 100 |
|---|---|---|
| Sai / lỗi / timeout | 0 | 0 |
| Đúng, nhanh bằng gold | 1 | 100 |
| Đúng, nhanh gấp 4 | 4 | 200 |
| Đúng, chậm gấp 4 | 0,25 | 50 |

**[NÓI]**
> "VES là **Valid Efficiency Score** — đã đúng thì còn xét **chạy nhanh hay chậm**.
> Đầu tiên kiểm tra đúng/sai y như EX. Câu sai thì 0 điểm, không đo nữa.
> Câu đúng thì chạy lại cả hai SQL **5 lần**, mỗi lần đo thời gian, lấy tỉ lệ **thời gian gold chia thời gian model**. Bỏ các lần đo bất thường ngoài ±3 độ lệch chuẩn rồi lấy trung bình được R.
> Mỗi câu đóng góp **căn R nhân 100**, VES là trung bình trên tất cả câu. Nên VES **có thể cao hơn EX** nếu SQL của model chạy nhanh hơn đáp án. Vì đo theo thời gian thật nên mỗi lần chấm lệch nhau một chút — chỉ so số trong cùng một lần chạy."

---

## 6. Kết quả Kaggle + kết luận (0:40)

**[MÀN HÌNH]** Lần lượt 3 tab Kaggle (mở sẵn từ trước):
1. Cell code chạy `ollama_request2.py` / `evaluation.py` (chỉ lướt 3 giây).
2. Thanh tiến độ / log thời gian: **mỗi lượt sinh SQL ≈ `__h__` giờ, chấm EX+VES ≈ `__h__` giờ** trên GPU T4.
3. Bảng kết quả:

| Model | EX w/o KG | EX w/ KG | VES w/o KG | VES w/ KG |
|---|---|---|---|---|
| ChatGPT (paper BIRD) | — | 37,22 | — | — |
| **GPT-3.5-Turbo (chạy lại)** | **31,23** | **47,78** | **33,88** | **53,88** |
| DeepSeek-Coder-V2 | … | 42,11 | … | 45,80 |
| Qwen2.5-Coder | … | 53,85 | … | 59,83 |
| Gemma3 | … | 48,70 | … | 54,86 |

> Cập nhật các ô `…` nếu đã chấm xong thư mục `*_0_output/`.

**[NÓI]**
> "Đây là bảng sau khi chạy trên Kaggle. Mỗi model chạy 2 lượt sinh SQL, mỗi lượt khoảng __ giờ, rồi chấm EX và VES.
> Ba điều rút ra:
> 1. **Evidence là yếu tố quyết định**: GPT-3.5 tăng từ 31 lên gần 48 điểm EX, tức **+16,5 điểm**, chỉ nhờ thêm đúng một dòng External Knowledge vào prompt.
> 2. GPT-3.5 chạy lại cao hơn số trong paper, một phần vì model đã được OpenAI cập nhật và tập dev đã được sửa lỗi.
> 3. Model mã nguồn mở nhỏ chạy local như **Qwen2.5-Coder 7B** đạt EX ngang hoặc hơn GPT-3.5.
> Cùng cách dựng prompt này được dùng lại trong ứng dụng ClubQuery ở trang 3 — em xin chuyển sang phần đó."

---

## Mẹo khi trình bày

- **Chuẩn bị trước:** 3 tab Kaggle (code, log thời gian, bảng kết quả), file prompt 1379 đã tô màu A/B/C, drawio mở trang tổng quan. Không chạy live trên Kaggle.
- **Phần 2 là trọng tâm** — nếu bị hỏi dồn, cắt bớt phần 3 và 5 (VES chỉ cần nói câu "đúng rồi mới so tốc độ, √(t_gold/t_pred)").
- **Câu hỏi hay gặp:**
  - *"Sao không so text SQL?"* → nhiều cách viết đúng; câu 1379 là ví dụ `STRFTIME` vs `SUBSTR`.
  - *"Model có thấy dữ liệu không?"* → không, chỉ thấy `CREATE TABLE` + evidence + câu hỏi.
  - *"Sao prompt GPT và Ollama khác nhau?"* → mồi `SELECT` chỉ hợp với GPT; model local trả lời bằng văn xuôi, EX tụt về ~0.
  - *"Sao VES > EX được?"* → câu đúng mà nhanh hơn gold được trên 100 điểm.

## Gợi ý chỉnh drawio (nếu kịp)

1. Khối ② nên tách **bước 2–4 thành một khối con "Dựng prompt"** có 3 ô màu A (schema) / B (đề bài + evidence) / C (câu dặn) — hiện 8 bước đang dồn một danh sách, khó chỉ tay.
2. Khối ③ CHẤM EX: thêm 1 dòng ví dụ `STRFTIME` vs `SUBSTR` → cùng `[(n,)]` → 1.
3. Khối ③ CHẤM VES: ghi rõ "chỉ câu đúng mới đo; lặp 5 lần; R = t_gold / t_pred; bỏ ngoài ±3σ; điểm = √R × 100".
4. Khối ④: thêm số giờ chạy Kaggle cho mỗi lượt.
