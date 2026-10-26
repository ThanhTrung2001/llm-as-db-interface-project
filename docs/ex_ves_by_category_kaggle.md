# Chạy EX & VES theo 6 mức truy vấn (student_club) trên Kaggle

Notebook: [`ex-ves-by-category-kaggle.ipynb`](../ex-ves-by-category-kaggle.ipynb) (thư mục gốc repo).

## Notebook làm gì

1. Lấy 158 câu `student_club` trong BIRD dev (question_id 1312–1469).
2. Phân loại gold SQL của từng câu vào 6 tập bằng `app/scripts/sql_category.py`:

   | Tập | Nội dung | Số câu (student_club) |
   |---|---|---|
   | 1 | Truy vấn 1 bảng | 33 |
   | 2 | Kết bảng (inner join) | 114 |
   | 3 | Union / Intersect / Except | 0 |
   | 4 | Kết ngoài (outer join) | 0 |
   | 5 | Group by | 11 |
   | 6 | Phép chia | 0 |

3. Chấm **EX** và **VES** cho 4 model × (có / không knowledge) trên từng tập:
   DeepSeek-Coder-V2, Gemma3, Qwen2.5-Coder, GPT-3.5-Turbo.
4. Mỗi tập ra 2 bảng:
   - `Model | EX_wo_knowledge | EX_w_knowledge`
   - `Model | VES_wo_knowledge | VES_w_knowledge`

Việc chấm dùng lại hàm của bộ chấm gốc BIRD: `package_sqls`, `execute_model` trong `evaluation.py`, và `execute_model`, `compute_ves` trong `evaluation_ves.py`. Vì vậy cách tính giống hệt khi chấm cả tập dev.

## Cần chuẩn bị

| Thứ | Lấy ở đâu |
|---|---|
| Tài khoản Kaggle | — |
| `bird-category-eval.zip` | Thư mục gốc repo (~350 KB, chứa 8 file `predict_dev.json`) |
| `ex-ves-by-category-kaggle.ipynb` | Thư mục gốc repo |
| Dataset BIRD trên Kaggle (`bird-sql`) | Dataset nhóm đang dùng cho các notebook trước. Cần có `data/dev.json`, `data/dev_databases/`, `llm/src/evaluation.py`, `llm/src/evaluation_ves.py`, `llm/data/dev_gold.sql` |

Trong `bird-category-eval.zip`, mỗi model có 2 thư mục, mỗi thư mục chứa 1 file `predict_dev.json`:

| Model | Có knowledge | Không knowledge |
|---|---|---|
| DeepSeek-Coder-V2 | `ollama_deepseekcoder_output` | `ollama_deepseekcoder_0_output` |
| Gemma3 | `ollama_gemma3_output` | `ollama_gemma3_0_output` |
| Qwen2.5-Coder | `ollama_gwen25_output` | `ollama_gwen25_0_output` |
| GPT-3.5-Turbo | `openai_output` | `openai_0_output` |

## Các bước

### Bước 1 — Tạo dataset kết quả (làm 1 lần)
1. Vào kaggle.com → **Datasets** → **New Dataset**.
2. Kéo thả `bird-category-eval.zip` vào. Kaggle tự giải nén.
3. Đặt tên `bird-category-eval`, chọn **Private**, bấm **Create**.

### Bước 2 — Import notebook
**Code** → **New Notebook** → **File** → **Import Notebook** → chọn `ex-ves-by-category-kaggle.ipynb`.

### Bước 3 — Gắn dữ liệu và cấu hình
1. Panel phải → **Add Input**, gắn **cả 2** dataset:
   - `bird-category-eval` (vừa tạo)
   - dataset BIRD (`bird-sql`)
2. **Settings**:
   - **Accelerator: None**. Không cần GPU vì chỉ chạy SQLite.
   - **Internet: On**. Cell đầu cần mạng để `pip install func_timeout`.

### Bước 4 — Chạy
Bấm **Run All**. Kiểm tra các cell sau:

| Cell | Kết quả đúng |
|---|---|
| Tìm BIRD | In `BIRD_ROOT = /kaggle/input/...`, `dev_databases exists: True`, `DBs copied: 11` |
| Tìm kết quả | `EXP_DIR = /kaggle/input/bird-category-eval/...`, cả **8 dòng OK** |
| Chạy chính | In EX của từng lượt, sau đó in bảng EX/VES của từng tập. Mất vài phút |
| Hiển thị | Mỗi tập có 1 bảng EX và 1 bảng VES; tập không có câu nào ghi "Không có câu nào thuộc tập này" |

### Bước 5 — Lấy kết quả
Tab **Output** → tải thư mục `/kaggle/working/ex_ves_by_category_level/`. Muốn lưu lâu dài thì bấm **Save Version** → **Save & Run All** rồi tải ở trang version.

| File | Nội dung |
|---|---|
| `summary_ex_ves_by_category_student_club.csv` | Bảng gọn (tập × model × 4 chỉ số), để dán vào báo cáo |
| `ex_ves_by_category_student_club.csv` | Như trên, có cả các tập rỗng |
| `ex_ves_by_category_student_club.xlsx` | Mỗi tập 2 sheet: `<tập>_EX`, `<tập>_VES` |
| `per_question_student_club.csv` | Từng câu × từng lượt: `ex` (0/1), `time_ratio` (dùng để tính VES) |

## Tuỳ chọn (cell chạy chính)

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `GROUP` | `'level'` | `'level'`: mỗi câu vào đúng 1 tập, tổng = 158. `'tag'`: mỗi câu được tính vào mọi nhãn nó có |
| `ITERATE_NUM` | `5` | Số lần chạy lại SQL để đo thời gian khi tính VES (như paper). **Phải ≥ 2** |
| `DB_ID` | `'student_club'` | Đổi sang CSDL khác của BIRD dev, hoặc `'all'` để chấm cả 1.534 câu (rất lâu) |

## Cách phân loại (đọc trước khi so số liệu)

- Một câu SQL có thể có nhiều nhãn. Với `GROUP = 'level'`, câu được xếp vào **nhãn có số lớn nhất**. Vì vậy:
  - **1322, 1323** dùng `EXCEPT` (mức 3) nhưng có cả `GROUP BY … HAVING` (mức 5), nên vào **mức 5**. Do đó mức 3 có 0 câu. Với `GROUP = 'tag'` thì tập 3 có 2 câu này.
  - **1402, 1444** chỉ dùng 1 bảng nhưng có `GROUP BY`, nên vào **mức 5**.
- Câu có truy vấn lồng `(SELECT …)` được xếp theo phần truy vấn bên ngoài: **1343, 1406** vào mức 1, **1453, 1457** vào mức 2.
- Danh sách nhãn của từng câu: [`docs/pttk/data/sql_category_student_club.csv`](pttk/data/sql_category_student_club.csv).

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân / cách xử lý |
|---|---|
| `Không tìm thấy bird/data/dev.json` | Chưa gắn dataset BIRD |
| Dòng `MISSING` ở cell tìm kết quả | Chưa gắn `bird-category-eval`. Thiếu thư mục nào thì lượt đó bị bỏ qua, nên cột tương ứng trống |
| `ModuleNotFoundError: func_timeout` | Chưa bật Internet. Bật lên rồi chạy lại cell `pip install` |
| Toàn bộ VES = 0 | `ITERATE_NUM = 1`. Với 1 lần đo, hàm `clean_abnormal` của bộ chấm gốc loại hết mẫu. Đặt `ITERATE_NUM` từ 2 trở lên |
| Số VES lệch nhẹ giữa các lần chạy | Bình thường, vì VES đo theo thời gian chạy. Chỉ so sánh số trong cùng một lần chạy |
| EX lệch nhẹ so với số chấm local | Vài câu chạy sát giới hạn timeout 30s. Dùng số của cùng một môi trường |

## Chạy local (không dùng Kaggle)

Từ thư mục gốc repo:

```bash
python app/scripts/ex_ves_by_category.py                # student_club, đủ EX + VES, ghi vào docs/pttk/data/
python app/scripts/ex_ves_by_category.py --skip_ves     # chỉ EX (nhanh)
python app/scripts/ex_ves_by_category.py --group tag    # chia theo nhãn
```

## Khi sửa code

Notebook đã nhúng sẵn **bản sao** của `app/scripts/sql_category.py` và `app/scripts/ex_ves_by_category.py`, qua 2 cell `%%writefile`. Nếu sửa 2 file này trong repo thì phải cập nhật lại 2 cell đó, nếu không Kaggle vẫn chạy code cũ.
