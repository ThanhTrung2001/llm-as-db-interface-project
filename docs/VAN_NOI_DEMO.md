# Lời trình bày khi demo: từ prompt đến câu SQL

Lời nói đi kèm mục **"Bên trong model"** trên giao diện ClubQuery. Số liệu lấy từ lần chạy thật câu mẫu **#1379** với **Qwen2.5-Coder 7B trên Ollama**. Mỗi lần chạy, giao diện hiện số liệu của chính lần đó; với câu này, các con số phải khớp với bên dưới.

> Câu hỏi: *How many meeting events were held in 2020?*
> Evidence: *meeting events refers to type = 'Meeting'; held in 2020 refers to YEAR(event_date) = 2020*

---

## Mở đầu (trước khi bấm "Hỏi")

"Ứng dụng của em chỉ gửi **văn bản** cho model và nhận lại **văn bản**. Toàn bộ phần tokenize, embedding, transformer… chạy bên trong Ollama. Để chứng minh em hiểu các bước đó, em đã tự chạy lại chúng bằng chính file model mà Ollama dùng, rồi đối chiếu với kết quả của server. Những chỗ có dấu ✓ trên màn hình là chỗ đã khớp."

## Phía app: dựng prompt (mục "Prompt gửi cho LLM")

"Prompt gồm 3 phần:
1. 8 câu `CREATE TABLE` của CSDL student_club, để model biết có những bảng và cột nào.
2. Evidence và câu hỏi, viết dưới dạng comment SQL `--`.
3. Một câu yêu cầu model chỉ trả về SQL trong khối ` ```sql `.

Tổng cộng 2.600 ký tự. Khuôn prompt này giống hệt script benchmark BIRD, để kết quả demo khớp với điểm EX đã đo. App gửi prompt qua HTTP POST tới `/v1/chat/completions` với `temperature = 0`."

## A. Template

"Ollama không đưa nguyên prompt của em vào model. Nó bọc prompt theo template hội thoại ChatML mà Qwen đã học lúc huấn luyện: thêm câu system *'You are Qwen, created by Alibaba Cloud…'*, đặt prompt vào lượt `<|im_start|>user`, rồi mở sẵn lượt `<|im_start|>assistant`. Chuỗi từ 2.600 thành 2.748 ký tự. Vì lượt assistant đã mở, model hiểu là đến lượt nó trả lời và viết tiếp ngay sau đó."

## B. Tokenize

"Model không đọc chữ, nó chỉ làm việc với số. Tokenizer BPE có bộ từ vựng 152.064 mảnh. Đầu tiên văn bản được tách thô thành từ, số, dấu câu. Sau đó các byte được ghép dần theo 151.387 quy tắc merge (cặp nào hay gặp hơn thì ghép trước). Mỗi mảnh cuối cùng là một token có ID riêng. Ví dụ ` SQLite` (có dấu cách phía trước) là token 28334; `<|im_start|>` luôn là một token đặc biệt, ID 151644. Mỗi chữ số đứng riêng thành một token, nên '2020' là 4 token.

Em tự chạy lại tokenizer bằng bộ từ vựng trong file model và đếm được **606 token**, khớp với con số **606** Ollama báo về (`usage.prompt_tokens`)."

## C. Embedding

"Mỗi token ID được đổi thành một vector **3.584** số thực. Thực chất là tra bảng: ma trận embedding có 152.064 dòng × 3.584 cột, token số bao nhiêu thì lấy dòng đó, chưa có phép tính nào. Ví dụ token ` meeting` (ID 6438) có vector bắt đầu bằng `[0.0204, -0.0210, -0.0072, …]`. Các con số này đọc thẳng từ file model; file lưu nén 4-bit nên em phải giải nén ra.

Vector mang ý nghĩa của token, học được lúc huấn luyện: token gần nghĩa thì vector gần nhau. Em đo thử độ tương đồng cosine: `SELECT` với ` SELECT` là 0,56, còn `SELECT` với ` banana` gần bằng 0. Cả prompt giờ thành một ma trận 606 × 3.584, khoảng 2,17 triệu số. Đây là đầu vào thật sự của mạng neural."

## D. Transformer

"Ma trận đi qua **28 tầng** transformer. Mỗi tầng có 2 phần:
- **Self-attention** với 28 head (dùng chung 4 KV head): mỗi token nhìn lại các token phía trước để lấy thông tin. Chẳng hạn, chữ 'meeting' trong câu hỏi có thể lấy thông tin từ cột `type` trong `CREATE TABLE event` và từ evidence.
- **Feed-forward**: 3.584 → 18.944 → 3.584.

606 token của prompt được tính song song trong một lượt (gọi là *prefill*), và key/value của attention được giữ lại (KV cache). Kích thước ra vẫn là 606 × 3.584, nhưng mỗi vector giờ đã chứa ngữ cảnh. Ollama không xuất giá trị trung gian, nên trên màn hình em chỉ hiện kích thước và thông số."

## E. Decode

"Đến đây mới bắt đầu sinh câu trả lời, và model sinh **từng token một**:
1. Lấy vector của token cuối ở tầng cuối.
2. Nhân với ma trận đầu ra (LM head) để ra 152.064 điểm số, mỗi điểm ứng với một token trong từ vựng.
3. Softmax đổi điểm số thành xác suất.
4. `temperature = 0` nên luôn chọn token có xác suất cao nhất.
5. Nối token đó vào chuỗi, chạy lại qua 28 tầng. Nhờ KV cache, chỉ cần tính cho 1 token mới. Rồi lặp lại.

Bảng trên màn hình là dữ liệu thật server trả (logprobs). Bước đầu tiên model chọn ` ``` ` với 99,6%. Chỗ đáng chú ý là bước 6: model chọn `(event` với **68%**, còn `(*)` có **31%**, tức là nó phân vân giữa `COUNT(event_id)` và `COUNT(*)`. Ở câu này hai cách viết cho cùng kết quả, nhưng ở câu khác, một nhánh như vậy có thể dẫn tới SQL sai. Đó là lý do model không phải lúc nào cũng đúng.

Sau 27 token, model sinh token `<|im_end|>` (ID 151645), nghĩa là nó tự quyết định dừng. Vì vậy server báo 28 token sinh ra."

## F. Detokenize

"Dãy 27 ID `[73594, 3544, 198, 4858, …]` được đổi ngược về chữ bằng cùng bộ từ vựng: mỗi ID ra chuỗi byte của nó, nối lại, giải mã UTF-8. Em tự ghép lại và ra **đúng văn bản server trả về** ✓.

Ở đây **không có 'embedding ngược'**: đầu ra của model là xác suất trên các token (bước E), chọn ra token rồi tra ngược ID → chữ."

## Phía app: tách SQL, chạy và trả lời

"Văn bản thô vẫn còn ` ```sql `, nên app lấy phần bên trong khối code rồi cắt ở dấu `;` đầu tiên, giống hệt code benchmark. Kết quả là:

```sql
SELECT COUNT(event_id) FROM event WHERE type = 'Meeting' AND event_date LIKE '2020%'
```

App chạy câu này trên CSDL ở chế độ chỉ đọc và được 9. Sau đó app so với SQL đáp án của BIRD theo đúng cách tính EX (so tập kết quả). Cuối cùng app gửi kết quả cho model diễn giải thành câu trả lời: *'In 2020, 9 meeting events were held.'*"

---

## Câu hỏi giáo viên có thể hỏi

**Embedding có phải là app làm không?**
Không. App chỉ gửi văn bản. Tokenize và embedding chạy trong Ollama; em chạy lại để minh hoạ và đối chiếu.

**Sao biết tokenizer em viết đúng?**
Số token tự đếm (606) khớp với `usage.prompt_tokens` server trả về. Ghép ngược các ID model sinh ra cũng ra đúng văn bản server trả về.

**Sao cùng câu hỏi lần nào cũng ra cùng SQL?**
`temperature = 0` nên mỗi bước luôn chọn token xác suất cao nhất (greedy), không có ngẫu nhiên.

**Model có "hiểu" CSDL không?**
Model chỉ thấy schema qua 8 câu `CREATE TABLE` trong prompt. Attention giúp nó nối từ trong câu hỏi với tên bảng/cột. Nếu không có evidence, model dễ hiểu sai thuật ngữ (ví dụ 'meeting' là giá trị nào của cột `type`).

**Vì sao model đôi khi sai?**
Ở những bước xác suất gần nhau (như 68% và 31% ở bước 6), chỉ cần lệch một token là cả câu SQL đi theo hướng khác. Model chọn cái có xác suất cao nhất, không kiểm tra SQL có đúng hay không.

**Bước nào tốn thời gian nhất?**
Transformer: mỗi token đi qua 28 tầng với 7,6 tỷ tham số. Prefill tính cả prompt một lượt; decode thì phải lặp lại cho từng token sinh ra.
