# Kịch bản trình bày demo ClubQuery (liền mạch, từ đầu đến cuối)

Ví dụ xuyên suốt: câu mẫu **#1379**, model **Qwen2.5-Coder 7B** chạy trên **Ollama**, **có tick** evidence.

> Câu hỏi: *How many meeting events were held in 2020?*
> Evidence: *meeting events refers to type = 'Meeting'; held in 2020 refers to YEAR(event_date) = 2020*

Cách đọc file này:
- Đoạn trong ngoặc kép "…" là **lời nói**.
- **[Thao tác]** là việc làm trên màn hình.
- Khối 📘 là **ghi chú cho bạn hiểu**, không cần đọc to.

---

## Phần 0. Mở đầu: bức tranh tổng thể (khoảng 30 giây)

"Bài toán của tụi em là **Text-to-SQL**: người dùng hỏi bằng tiếng Anh tự nhiên, hệ thống tự viết câu SQL, chạy trên CSDL và trả lời.

Toàn bộ luồng gồm 3 giai đoạn:
1. **Trước model**: app chuẩn bị câu hỏi và dựng prompt.
2. **Bên trong model**: model đọc prompt và sinh ra câu SQL.
3. **Sau model**: app tách SQL, chạy trên CSDL, diễn giải kết quả và so với đáp án.

App chỉ gửi **văn bản** cho model và nhận lại **văn bản**. Những gì xảy ra bên trong model, tụi em tự chạy lại bằng chính file model để minh hoạ và đối chiếu với server. Chỗ nào trên màn hình có dấu ✓ là chỗ đã khớp."

> 📘 **LLM là gì, nói gọn:** LLM (Large Language Model) là một chương trình rất lớn, được huấn luyện trên hàng nghìn tỷ chữ, chỉ để làm **một việc**: *đoán mảnh chữ tiếp theo*. Nó giống bàn phím gợi ý từ trên điện thoại, nhưng giỏi hơn rất nhiều. Muốn nó viết SQL, ta đưa một đoạn văn bản (prompt) khiến "mảnh chữ tiếp theo hợp lý nhất" chính là câu SQL.

---

## Phần 1. Đầu vào trên giao diện

**[Thao tác]** Chỉ vào 3 ô nhập.

"Đầu vào của demo gồm 3 thứ:
- **Model**: chọn model sinh SQL (GPT-3.5-Turbo, Qwen2.5-Coder, DeepSeek-Coder, Gemma3…).
- **Câu hỏi**: chọn một trong 158 câu mẫu của bộ dev BIRD thuộc CSDL `student_club`, hoặc tự gõ.
- **Ô tick 'Dùng evidence'**: có đưa tri thức ngoài vào prompt hay không.

Tụi em chọn câu 1379, model Qwen2.5-Coder, có tick evidence."

**[Thao tác]** Bấm **Hỏi**.

"Khi bấm Hỏi, giao diện gửi request `POST /api/ask` lên backend. Hàm `ask()` trong `service.py` nhận request rồi chạy lần lượt từng bước."

---

## Phần 2. Bước 1: lấy câu hỏi và tri thức ngoài

"Lúc server khởi động, app đọc file `dev.json` của BIRD, giữ lại 158 câu thuộc `student_club` và lưu vào bảng `dev_question`. Mỗi câu gồm câu hỏi, evidence, SQL đáp án và độ khó.

Khi bấm Hỏi, hàm `load_question()` truy vấn bảng này theo id câu hỏi. Nếu có tick evidence thì lấy evidence, bỏ tick thì evidence = rỗng. Sau đó `load_model()` đọc cấu hình model: model tên gì, gọi tới địa chỉ nào, dùng API key nào."

> 📘 **Evidence (External Knowledge) là gì?** Là câu giải thích thuật ngữ do người làm bộ dữ liệu BIRD viết sẵn. Ví dụ "meeting" trong câu hỏi tương ứng với giá trị `'Meeting'` ở cột `type`. Không có evidence, model phải tự đoán, và hay đoán sai.

---

## Phần 3. Bước 2: dựng prompt

**[Thao tác]** Mở mục **"Prompt gửi cho LLM"**.

"Prompt là toàn bộ văn bản gửi cho model. Nó gồm 4 phần, ghép theo đúng khuôn của script benchmark BIRD để kết quả demo khớp với điểm đã đo.

**Phần 1, Schema:** 8 câu `CREATE TABLE` của CSDL, cho model biết có những bảng và cột nào. App không tự viết các câu này. Nó chạy `SELECT name, sql FROM sqlite_master WHERE type='table'`. `sqlite_master` là bảng hệ thống có sẵn trong mọi file SQLite, lưu **nguyên văn câu `CREATE TABLE` gốc** lúc tạo bảng. Nếu mở file bằng DB Browser thì cột *Schema* chính là các câu này. Điều kiện `type='table'` để chỉ lấy bảng, bỏ qua index, view, trigger.

**Phần 2, Tri thức ngoài:** dòng `-- External Knowledge: …`, chỉ có khi tick evidence.

**Phần 3, Câu hỏi:** dòng `-- Using valid SQLite … answer the following questions…` và dòng `-- How many meeting events were held in 2020?`. Hai dòng này viết dạng comment SQL `--` cho giống một file SQL.

**Phần 4, Câu chặn cuối:** yêu cầu model *chỉ trả về SQL trong khối ```sql*, không giải thích gì thêm.

Tổng cộng khoảng **2.600 ký tự**. App gửi prompt qua HTTP tới `/v1/chat/completions` với `temperature = 0`."

> 📘 **Vì sao phải đưa schema vào prompt?** Model không truy cập được CSDL. Nó chỉ biết những gì nằm trong prompt. Không có schema, nó không biết bảng `event` có cột `type`.
>
> 📘 **temperature = 0 là gì?** Ở mỗi bước, model luôn chọn mảnh chữ có xác suất cao nhất, không chọn ngẫu nhiên. Vì vậy cùng một câu hỏi lần nào cũng ra cùng một kết quả, và demo lặp lại được.

---

## Phần 4. Bên trong model: từ chữ thành số, rồi từ số lại thành chữ

**[Thao tác]** Mở mục **"Bên trong model"**.

"Đến đây prompt đã vào Ollama. Model là một mạng neural, nó **chỉ tính toán được với số**, không đọc được chữ. Vì vậy cả quá trình bên trong là: **biến chữ thành số → tính toán → biến số ngược lại thành chữ**. Có 6 bước, từ A đến F."

### A. Template: bọc prompt thành một đoạn hội thoại

"Ollama không đưa nguyên prompt vào model. Qwen được huấn luyện trên dữ liệu hội thoại có định dạng riêng gọi là **ChatML**: mỗi lượt nói mở bằng `<|im_start|>` kèm vai trò (system, user, assistant) và đóng bằng `<|im_end|>`.

Ollama làm 3 việc: thêm câu system *'You are Qwen, created by Alibaba Cloud…'*, đặt prompt của tụi em vào lượt **user**, rồi **mở sẵn lượt assistant** mà không đóng lại. Model thấy lượt assistant đang bỏ ngỏ nên hiểu là đến lượt nó trả lời. Chuỗi tăng từ 2.600 lên **2.748 ký tự**."

> 📘 Giống như đưa cho model một kịch bản hội thoại còn thiếu câu cuối, và model sẽ viết tiếp câu đó.

### B. Tokenize: cắt chữ thành mảnh và đánh số

"Bước đầu tiên để biến chữ thành số là **tokenize**. Văn bản được cắt thành các mảnh nhỏ gọi là **token**, và mỗi token có một số thứ tự gọi là **token ID**. Qwen có bộ từ vựng **152.064 token**.

Cách cắt gọi là **BPE**. Đầu tiên tách văn bản thành từ, số, dấu câu. Sau đó ghép dần các ký tự đi cạnh nhau, cặp nào hay gặp hơn thì ghép trước, theo **151.387 quy tắc ghép** học được từ dữ liệu. Từ phổ biến như ` SELECT` thành 1 token, còn từ hiếm bị cắt thành nhiều mảnh.

Vài ví dụ trên màn hình:
- ` SQLite`, có dấu cách phía trước, là token **28334**. Dấu cách dính vào đầu từ, nên ` SELECT` và `SELECT` là hai token khác nhau.
- `<|im_start|>` luôn là **một** token đặc biệt, ID **151644**.
- Mỗi chữ số là một token riêng, nên `2020` là 4 token.

Tụi em tự viết lại tokenizer, dùng bộ từ vựng đọc từ file model, và đếm được **606 token**. Con số này khớp với **606** mà Ollama báo về ✓."

> 📘 **Vì sao không cắt theo từng chữ cái hoặc từng từ?** Theo chữ cái thì chuỗi quá dài, model xử lý chậm. Theo từ thì bộ từ vựng phải chứa mọi từ trên đời. Token nằm ở giữa: từ phổ biến là 1 token, từ lạ thì ghép từ vài mảnh.

### C. Embedding: mỗi số thành một vector ý nghĩa

"Token ID chỉ là số thứ tự, bản thân nó không mang ý nghĩa. Số 6438 không 'gần' số 6439 về nghĩa. Vì vậy mỗi ID được đổi thành một **vector 3.584 số thực**, gọi là **embedding**.

Cách làm rất đơn giản: trong model có một bảng lớn **152.064 dòng × 3.584 cột**, mỗi dòng ứng với một token. Token số bao nhiêu thì **lấy đúng dòng đó**. Đây là tra bảng, chưa có phép tính nào. Ví dụ token ` meeting` (ID 6438) có vector bắt đầu bằng `[0.0204, -0.0210, -0.0072, …]`. Tụi em đọc thẳng các con số này từ file model. File lưu nén 4-bit để tiết kiệm dung lượng nên phải giải nén ra.

Các con số này học được lúc huấn luyện: token gần nghĩa thì vector gần nhau. Tụi em đo thử: `SELECT` và ` SELECT` có độ tương đồng **0,56**, còn `SELECT` và ` banana` gần bằng **0**.

Sau bước này, cả prompt thành một ma trận **606 × 3.584**, khoảng 2,17 triệu số. Đây là đầu vào thật sự của mạng neural."

> 📘 Hãy hình dung mỗi token là một điểm trong không gian 3.584 chiều. Những từ có nghĩa giống nhau nằm gần nhau, như các thành phố gần nhau trên bản đồ.

### D. Transformer: "đọc hiểu" cả prompt

"Ma trận đi qua **28 tầng transformer**. Đây là phần 'bộ não' và tốn tính toán nhất, với khoảng **7,6 tỷ tham số**. Mỗi tầng có 2 phần:

1. **Self-attention**: mỗi token **nhìn lại các token đứng trước nó** để lấy thông tin. Ví dụ chữ 'meeting' trong câu hỏi có thể chú ý tới cột `type` trong `CREATE TABLE event` và tới dòng evidence nói `type = 'Meeting'`. Nhờ vậy vector của 'meeting' không còn mang nghĩa chung chung nữa, mà mang nghĩa *'meeting trong ngữ cảnh CSDL này'*. Qwen có 28 'đầu' attention chạy song song, mỗi đầu chú ý một kiểu quan hệ khác nhau.
2. **Feed-forward**: mỗi vector đi qua một mạng nhỏ (3.584 → 18.944 → 3.584) để xử lý thêm thông tin vừa thu được.

606 token của prompt được tính **song song trong một lượt** (gọi là *prefill*). Kết quả vẫn là ma trận 606 × 3.584, nhưng mỗi vector giờ đã 'hiểu' ngữ cảnh. Ollama không xuất các giá trị trung gian, nên trên màn hình tụi em chỉ hiện kích thước và thông số của model."

> 📘 Attention giống cách người đọc: gặp chữ "nó" thì nhìn lại phía trước để biết "nó" là ai. Model làm việc này cho mọi token, ở mọi tầng.

### E. Decode: sinh câu trả lời từng token một

"Đến đây model mới bắt đầu **viết**, và nó viết **từng token một**, theo vòng lặp:
1. Lấy vector của **token cuối cùng** ở tầng cuối. Vector này đã tổng hợp thông tin của cả prompt.
2. Nhân với ma trận đầu ra để ra **152.064 điểm số**, mỗi điểm ứng với một token trong từ vựng.
3. Hàm **softmax** đổi điểm số thành **xác suất**, tổng cộng bằng 100%.
4. Vì temperature = 0, chọn token có **xác suất cao nhất**.
5. Nối token đó vào cuối chuỗi rồi quay lại bước 1. Nhờ **KV cache**, model nhớ phần đã tính, nên mỗi vòng chỉ tính thêm cho 1 token mới.

**[Thao tác]** Chỉ vào bảng decode.

Bảng này là dữ liệu thật server trả về, gồm 5 ứng viên mạnh nhất ở mỗi bước:
- Bước 1: model chọn ` ``` ` với **99,6%**, gần như chắc chắn, vì prompt yêu cầu trả SQL trong khối code.
- **Bước 6 là chỗ đáng chú ý** (dòng tô vàng): model chọn `(event` với **68%**, còn `(*)` có **31%**. Tức là nó phân vân giữa `COUNT(event_id)` và `COUNT(*)`. Ở câu này hai cách cho cùng kết quả. Nhưng ở câu khác, chỉ cần lệch một token như vậy là cả câu SQL đi theo hướng sai. **Đây là lý do LLM không phải lúc nào cũng đúng**: nó chọn cái có xác suất cao nhất, chứ không kiểm tra SQL có đúng hay không.

Sau **27 token**, model sinh token đặc biệt `<|im_end|>` (ID 151645), nghĩa là nó **tự quyết định dừng**. Vì vậy server báo tổng cộng 28 token sinh ra."

> 📘 Đây chính là "đoán mảnh chữ tiếp theo" ở Phần 0. Cả câu SQL chỉ là 27 lần đoán liên tiếp.

### F. Detokenize: số trở lại thành chữ

"Model sinh ra một dãy ID: `[73594, 3544, 198, 4858, …]`. Bước cuối đổi ngược mỗi ID về mảnh chữ của nó bằng cùng bộ từ vựng, rồi nối lại. Tụi em tự ghép lại và ra **đúng văn bản server trả về** ✓.

Ở đây **không có 'embedding ngược'**. Đầu ra của model là xác suất trên các token (bước E), từ đó chọn ra ID, rồi tra ngược ID thành chữ."

> 📘 Tóm tắt Phần 4 trong một dòng: **chữ → token ID → vector → 28 tầng hiểu ngữ cảnh → xác suất → chọn token → lặp → ID → chữ.**

---

## Phần 5. Sau model: tách SQL, chạy và trả lời

**[Thao tác]** Mở mục **"Văn bản thô model trả về"** và **"Tách SQL"**.

"Văn bản model trả về vẫn còn ký hiệu ` ```sql ` bao quanh. App tách SQL theo đúng code của script benchmark: bỏ đoạn suy luận `<think>` nếu có, lấy phần trong khối ` ```sql … ``` `, rồi cắt ở dấu `;` đầu tiên. Kết quả:

```sql
SELECT COUNT(event_id) FROM event WHERE type = 'Meeting' AND event_date LIKE '2020%'
```

**Chạy SQL:** câu này chạy trên `student_club.sqlite` với 3 lớp bảo vệ: mở CSDL **chỉ đọc**, nên lệnh xoá hay sửa đều bị từ chối; mỗi lần chỉ chạy **một** câu lệnh; quá **10 giây** thì ngắt. Kết quả là **9**.

**Diễn giải:** app gửi câu hỏi và kết quả cho model, nhờ viết câu trả lời ngắn: *'In 2020, 9 meeting events were held.'* Nếu model lỗi thì app dùng câu mẫu có sẵn.

**So với đáp án:** đây là câu mẫu nên có SQL đáp án của BIRD. Đáp án viết `SUBSTR(event_date,1,4) = '2020'`, còn model viết `LIKE '2020%'`. Hai câu khác nhau nhưng cùng ra 9. Cách chấm **EX** (Execution Accuracy) của BIRD so **kết quả chạy**, không so câu chữ, nên câu này tính là **đúng** ✓."

---

## Phần 6. Kết thúc và so sánh có / không evidence (nếu còn thời gian)

**[Thao tác]** Bỏ tick evidence, bấm Hỏi lại câu 1379.

"Bây giờ tụi em bỏ tick evidence. Trong prompt sẽ mất dòng `-- External Knowledge`. Model phải tự đoán 'meeting' là giá trị nào và '2020' nằm ở cột nào. Đây là minh hoạ trực tiếp cho vai trò của tri thức ngoài mà tụi em đã đo trong benchmark."

"Tóm lại toàn bộ luồng là: **chọn câu hỏi → lấy câu hỏi và evidence → dựng prompt 4 phần → bên trong model: chữ thành số, tính toán, số thành chữ → tách SQL → chạy trên CSDL chỉ đọc → diễn giải → so đáp án**. Mỗi bước đều hiện dữ liệu thật trên giao diện. Em xin hết phần demo."

---

## Câu hỏi giáo viên có thể hỏi

**Embedding có phải app làm không?**
Không. App chỉ gửi văn bản, tokenize và embedding chạy trong Ollama. Tụi em chạy lại để minh hoạ và đối chiếu kết quả.

**Sao biết tokenizer tụi em viết là đúng?**
Số token tự đếm (606) khớp với số server báo. Ghép ngược các ID model sinh ra cũng ra đúng văn bản server trả về.

**Sao lần nào hỏi cũng ra cùng một SQL?**
Vì temperature = 0: mỗi bước luôn chọn token có xác suất cao nhất, không có ngẫu nhiên.

**Model có "hiểu" CSDL không?**
Model chỉ thấy CSDL qua 8 câu `CREATE TABLE` trong prompt. Attention giúp nó nối các từ trong câu hỏi với tên bảng và tên cột. Không có evidence, model dễ hiểu sai thuật ngữ.

**Vì sao model đôi khi sai?**
Ở những bước xác suất gần nhau (như 68% và 31% ở bước 6), chỉ cần lệch một token là cả câu SQL đi hướng khác. Model không chạy thử SQL để kiểm tra.

**Bước nào tốn thời gian nhất?**
Transformer: mỗi token đi qua 28 tầng với 7,6 tỷ tham số. Prompt được tính một lượt (prefill), còn khi sinh câu trả lời thì phải lặp lại cho từng token.

**Model có thể xoá dữ liệu không?**
Không. CSDL mở ở chế độ chỉ đọc, và mỗi lần chỉ chạy được một câu lệnh.

---

## Bảng thuật ngữ (để bạn ôn)

| Thuật ngữ | Hiểu đơn giản |
|---|---|
| Prompt | Toàn bộ văn bản gửi cho model |
| Token | Mảnh chữ nhỏ (một từ, một phần từ, một dấu câu) |
| Token ID | Số thứ tự của token trong bộ từ vựng |
| Embedding | Vector số thực đại diện cho ý nghĩa của một token |
| Transformer | Kiến trúc mạng neural gồm nhiều tầng attention + feed-forward |
| Attention | Cơ chế để mỗi token "nhìn" các token khác và lấy ngữ cảnh |
| Prefill | Tính toàn bộ prompt trong một lượt |
| Decode | Sinh từng token một, lặp lại tới khi dừng |
| KV cache | Bộ nhớ phần đã tính, để không phải tính lại từ đầu |
| Softmax | Hàm đổi điểm số thành xác suất, tổng bằng 100% |
| Temperature | Mức ngẫu nhiên khi chọn token; bằng 0 là luôn chọn cao nhất |
| Logprobs | Xác suất của từng token mà server trả về |
| EX | Execution Accuracy: SQL đúng nếu kết quả chạy giống đáp án |
