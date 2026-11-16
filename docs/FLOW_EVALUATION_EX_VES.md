# Luồng chấm điểm EX và VES (kèm ví dụ giả định)

Tài liệu này nối tiếp **sau khi benchmark đã sinh xong `predict_dev.json`** (xem log `app/logs/benchmark_ollama_*.log`, bước 7). Hai file chấm của BIRD được dùng nguyên, không sửa:

- [evaluation.py](../src/DAMO-ConvAI/bird/llm/src/evaluation.py): tính **EX** (Execution Accuracy). SQL của model có ra **đúng kết quả** như đáp án không?
- [evaluation_ves.py](../src/DAMO-ConvAI/bird/llm/src/evaluation_ves.py): tính **VES** (Valid Efficiency Score). Câu đã đúng thì SQL của model chạy **nhanh hay chậm** so với đáp án?

Mỗi bước được viết theo dạng log: **hàm → làm gì → input/tham số (giải thích) → output**.

> ⚠️ **Ví dụ giả định.** Để dễ theo dõi, giả sử bộ dev chỉ có **5 câu** của CSDL `student_club`. Câu số 0 lấy SQL thật của Qwen2.5-Coder ở lượt có evidence (câu 1379). Các câu còn lại, cùng mọi kết quả truy vấn và thời gian đo, là **số minh hoạ**, không phải kết quả đã chạy.

---

## 0. Dữ liệu đầu vào (đầu ra của benchmark + đáp án)

**`exp_result/<lượt>/predict_dev.json`**: SQL của model. Mỗi giá trị có dạng `SQL\t----- bird -----\tdb_id`.

```json
{
  "0": "SELECT COUNT(event_id) FROM event WHERE type = 'Meeting' AND event_date LIKE '2020%'\t----- bird -----\tstudent_club",
  "1": "SELECT COUNT(*) FROM event WHERE status = 'closed'\t----- bird -----\tstudent_club",
  "2": "SELECT COUNT(*) FROM member WHERE link_to_major IN (SELECT major_id FROM major WHERE college = 'College of Engineering')\t----- bird -----\tstudent_club",
  "3": "SELECT COUNT(*) FROM event WHERE YEAR(event_date) = 2019\t----- bird -----\tstudent_club",
  "4": "SELECT SUM(cost) FROM expense WHERE approved = 'true'\t----- bird -----\tstudent_club"
}
```

**`data/dev_gold.sql`**: SQL đáp án, mỗi dòng có dạng `SQL<TAB>db_id`, cùng thứ tự câu.

```
SELECT COUNT(event_id) FROM event WHERE type = 'Meeting' AND SUBSTR(event_date, 1, 4) = '2020'	student_club
SELECT COUNT(event_id) FROM event WHERE status = 'Closed'	student_club
SELECT COUNT(T1.member_id) FROM member AS T1 INNER JOIN major AS T2 ON T1.link_to_major = T2.major_id WHERE T2.college = 'College of Engineering'	student_club
SELECT COUNT(event_id) FROM event WHERE SUBSTR(event_date, 1, 4) = '2019'	student_club
SELECT SUM(T1.cost) FROM expense AS T1 INNER JOIN budget AS T2 ON T1.link_to_budget = T2.budget_id WHERE T1.approved = 'true'	student_club
```

**`data/dev.json`**: chỉ dùng trường `difficulty` của từng câu, theo cùng thứ tự.

| Câu | difficulty | Tình huống giả định |
|---|---|---|
| 0 | simple | Đúng (câu 1379 thật) |
| 1 | simple | Sai kết quả: model viết `'closed'` thường, dữ liệu là `'Closed'` |
| 2 | moderate | Đúng nhưng **chậm hơn** đáp án (dùng `IN (subquery)`) |
| 3 | moderate | **Lỗi**: dùng hàm `YEAR()` mà SQLite không có |
| 4 | challenging | Đúng và **nhanh hơn** đáp án (không cần JOIN) |

---

# PHẦN A. EX — `evaluation.py`

```
predict_dev.json ─┐
                  ├─► A1 package_sqls ×2 ─► A2 zip ─► A3 run_sqls_parallel ─► A4 execute_model ─► A5 execute_sql
dev_gold.sql ─────┘                                     (song song)               (timeout)          (so set)
                                                                                     │
dev.json (difficulty) ──────────────────► A7 compute_acc_by_diff ◄── A6 sort_results ┘
                                                     │
                                               A8 print_data ─► bảng EX
```

### A0. `evaluation.py` (argparse)

- **Làm gì:** nhận tham số dòng lệnh.

```bash
python src/evaluation.py --predicted_sql_path ./exp_result/ollama_gwen25_output/ \
    --ground_truth_path ../data/ --data_mode dev --db_root_path ../data/dev_databases/ \
    --diff_json_path ../data/dev.json --num_cpus 8 --meta_time_out 30.0
```

| Tham số | Giá trị | Giải thích |
|---|---|---|
| `--predicted_sql_path` | `./exp_result/ollama_gwen25_output/` | Thư mục chứa `predict_dev.json`. `*_output/` là lượt có evidence, `*_0_output/` là lượt không evidence. Phải có `/` ở cuối vì code ghép chuỗi trực tiếp |
| `--ground_truth_path` | `../data/` | Thư mục chứa `dev_gold.sql` |
| `--data_mode` | `dev` | Dùng để ghép tên file: `predict_` + `dev` + `.json`, `dev` + `_gold.sql` |
| `--db_root_path` | `../data/dev_databases/` | Thư mục chứa `<db_id>/<db_id>.sqlite` |
| `--diff_json_path` | `../data/dev.json` | Chỉ để lấy độ khó của từng câu |
| `--num_cpus` | `8` | Số tiến trình chấm song song |
| `--meta_time_out` | `30.0` | Số giây tối đa cho **mỗi cặp câu**. Quá thời gian thì tính sai |
| `--mode_predict` / `--mode_gt` | `gpt` / `gt` | Cách đọc file: `gpt` đọc JSON, `gt` đọc file `.sql` theo dòng |

- **Output:** `args`. Khởi tạo danh sách toàn cục `exec_result = []`.

### A1. `package_sqls(sql_path, db_root_path, mode, data_mode)`: gọi 2 lần

- **Làm gì:** đọc SQL và tạo đường dẫn CSDL cho từng câu.

**Lần 1:** `package_sqls('./exp_result/ollama_gwen25_output/', '../data/dev_databases/', mode='gpt', data_mode='dev')`

| Tham số | Giải thích |
|---|---|
| `sql_path` | Thư mục; file đọc là `sql_path + 'predict_dev.json'` |
| `mode='gpt'` | Đọc JSON, tách mỗi giá trị bằng `'\t----- bird -----\t'`. Giá trị không phải chuỗi thì thay bằng `" "` và CSDL `financial` |

- **Output:**

```python
pred_queries = [
  "SELECT COUNT(event_id) FROM event WHERE type = 'Meeting' AND event_date LIKE '2020%'",
  "SELECT COUNT(*) FROM event WHERE status = 'closed'",
  "SELECT COUNT(*) FROM member WHERE link_to_major IN (SELECT ...)",
  "SELECT COUNT(*) FROM event WHERE YEAR(event_date) = 2019",
  "SELECT SUM(cost) FROM expense WHERE approved = 'true'"]
db_paths = ['../data/dev_databases/student_club/student_club.sqlite'] * 5
```

**Lần 2:** `package_sqls('../data/', '../data/dev_databases/', mode='gt', data_mode='dev')`

- `mode='gt'`: đọc `dev_gold.sql` theo dòng, tách bằng dấu tab.
- **Output:** `gt_queries` (5 SQL đáp án) và `db_paths_gt`. **`db_paths_gt` không được dùng**: cả hai câu SQL đều chạy trên `db_paths` lấy từ file của model.

### A2. `query_pairs = list(zip(pred_queries, gt_queries))`

- **Làm gì:** ghép câu thứ *i* của model với đáp án thứ *i*. Vì vậy **thứ tự** trong hai file phải khớp nhau.
- **Output:** 5 cặp `(SQL model, SQL đáp án)`.

### A3. `run_sqls_parallel(sqls, db_places, num_cpus=8, meta_time_out=30.0)`

- **Làm gì:** tạo `mp.Pool(8)`. Với mỗi cặp, gọi `pool.apply_async(execute_model, ...)`. Hàm `result_callback` thêm kết quả vào `exec_result` **theo thứ tự cặp nào chạy xong trước**.

| Tham số | Giải thích |
|---|---|
| `sqls` | `query_pairs` |
| `db_places` | `db_paths` (bước A1) |
| `num_cpus` | Số tiến trình |
| `meta_time_out` | Chuyển xuống `execute_model` |

- **Output:** không trả về. `exec_result` được điền theo thứ tự chạy xong, ví dụ:

```python
[{'sql_idx': 3, 'res': 0}, {'sql_idx': 0, 'res': 1}, {'sql_idx': 1, 'res': 0},
 {'sql_idx': 4, 'res': 1}, {'sql_idx': 2, 'res': 1}]
```

### A4. `execute_model(predicted_sql, ground_truth, db_place, idx, meta_time_out)`: gọi cho từng cặp

- **Làm gì:** gọi `execute_sql` trong `func_timeout(meta_time_out, ...)`. Quá thời gian → `res = 0`. Mọi lỗi khác (sai cú pháp, không có hàm, không có cột…) → `res = 0`.
- **Output:** `{'sql_idx': idx, 'res': 0 | 1}`.

### A5. `execute_sql(predicted_sql, ground_truth, db_path)`

- **Làm gì:** mở CSDL, chạy SQL model rồi `fetchall()`, chạy SQL đáp án rồi `fetchall()`, so sánh **`set(predicted_res) == set(ground_truth_res)`**. Phép so này không xét thứ tự dòng, bỏ dòng trùng và không xét tên cột. Thứ tự cột trong mỗi dòng thì phải giống.

| Câu | `predicted_res` | `ground_truth_res` | So `set` | `res` |
|---|---|---|---|---|
| 0 | `[(9,)]` | `[(9,)]` | bằng nhau | **1** |
| 1 | `[(0,)]` | `[(15,)]` *(minh hoạ)* | khác | **0** |
| 2 | `[(12,)]` *(minh hoạ)* | `[(12,)]` | bằng nhau | **1** |
| 3 | *(lỗi)* `sqlite3.OperationalError: no such function: YEAR` | không chạy tới | — | **0** (lỗi được `execute_model` bắt) |
| 4 | `[(4250.5,)]` *(minh hoạ)* | `[(4250.5,)]` | bằng nhau | **1** |

### A6. `sort_results(exec_result)`

- **Làm gì:** sắp lại theo `sql_idx`, vì các tiến trình chạy xong không theo thứ tự.
- **Output:** `[{0:1}, {1:0}, {2:1}, {3:0}, {4:1}]` (viết gọn dạng `sql_idx: res`).

### A7. `compute_acc_by_diff(exec_results, diff_json_path)`

- **Làm gì:** đọc `dev.json`. Với câu thứ *i* trong `dev.json`, lấy `exec_results[i]` cho vào nhóm theo `difficulty`. Sau đó tính tỉ lệ đúng của từng nhóm và của toàn bộ.

| Tham số | Giải thích |
|---|---|
| `exec_results` | Danh sách đã sắp xếp ở bước A6 |
| `diff_json_path` | `dev.json`; ghép theo **chỉ số**, nên phải đủ câu và cùng thứ tự |

| Nhóm | Câu | Đúng / tổng | EX |
|---|---|---|---|
| simple | 0, 1 | 1 / 2 | **50.00** |
| moderate | 2, 3 | 1 / 2 | **50.00** |
| challenging | 4 | 1 / 1 | **100.00** |
| total | 0–4 | 3 / 5 | **60.00** |

- **Output:** `(50.0, 50.0, 100.0, 60.0, [2, 2, 1, 5])`.

Công thức: $EX = \dfrac{\text{số câu đúng}}{N} \times 100$

### A8. `print_data(score_lists, count_lists)`

- **Output** (in ra màn hình):

```
                     simple               moderate             challenging          total
count                2                    2                    1                    5
======================================    ACCURACY    =====================================
accuracy             50.00                50.00                100.00               60.00
```

---

# PHẦN B. VES — `evaluation_ves.py`

Các bước đọc dữ liệu giống EX. Khác biệt chỉ nằm ở cách chấm từng cặp (bước B3–B5) và công thức (bước B7).

```
query_pairs ─► B2 run_sqls_parallel ─► B3 execute_model ─► B4 iterated_execute_sql ─┬─ sai/lỗi → R = 0
                                        (timeout × 5)        (so set 1 lần)          └─ đúng → chạy 5 lần
                                                                                          execute_sql (đo giờ)
                                                                                          ratio = t_gold / t_pred
                                                                                     B5 clean_abnormal → R = trung bình
B6 sort_results ─► B7 compute_ves_by_diff → compute_ves (√R × 100) ─► B8 print_data ─► bảng VES
```

### B0. `evaluation_ves.py` (argparse)

```bash
python src/evaluation_ves.py --predicted_sql_path ./exp_result/ollama_gwen25_output/ \
    --ground_truth_path ../data/ --data_mode dev --db_root_path ../data/dev_databases/ \
    --diff_json_path ../data/dev.json --num_cpus 8 --meta_time_out 30.0 --iterate_num 5
```

Các tham số giống A0, thêm một tham số:

| Tham số | Giá trị | Giải thích |
|---|---|---|
| `--iterate_num` | `5` | Số lần chạy lại mỗi câu để đo thời gian. Paper dùng 5; mặc định trong hàm `run_sqls_parallel` là 100 |

### B1. `package_sqls` ×2 → `zip`

Giống hệt A1–A2. Output: 5 cặp và `db_paths`.

### B2. `run_sqls_parallel(sqls, db_places, num_cpus=8, iterate_num=5, meta_time_out=30.0)`

- **Làm gì:** giống A3 nhưng truyền thêm `iterate_num`.
- **Output:** `exec_result` gồm các `{'sql_idx', 'time_ratio'}`, theo thứ tự chạy xong.

### B3. `execute_model(predicted_sql, ground_truth, db_place, idx, iterate_num, meta_time_out)`

- **Làm gì:** gọi `iterated_execute_sql` trong `func_timeout(meta_time_out × iterate_num, ...)`, tức **150 giây** cho cả quá trình đo một câu. Quá thời gian hoặc có lỗi → `time_ratio = 0`.
- **Output:** `{'sql_idx': idx, 'time_ratio': R}`.

### B4. `iterated_execute_sql(predicted_sql, ground_truth, db_path, iterate_num)`

- **Làm gì:**
  1. Chạy hai câu SQL **một lần**, so `set` như EX. **Sai → trả về 0 ngay**, không đo thời gian.
  2. Đúng → lặp `iterate_num` lần. Mỗi lần gọi `execute_sql(predicted_sql)` → `t_pred`, rồi `execute_sql(ground_truth)` → `t_gold`, và ghi lại `t_gold / t_pred`.
  3. Đưa danh sách tỉ lệ qua `clean_abnormal` (bước B5), lấy trung bình → **R**.
- Tỉ lệ **> 1** nghĩa là SQL model nhanh hơn đáp án; **< 1** nghĩa là chậm hơn.

**`execute_sql(sql, db_path)`** (bản của VES): mở kết nối mới, bấm giờ **chỉ quanh `cursor.execute(sql)`** (không đo `fetchall`), trả về số giây.

Ví dụ câu 0 *(thời gian minh hoạ, đơn vị ms)*:

| Lần | `t_pred` | `t_gold` | `t_gold / t_pred` |
|---|---|---|---|
| 1 | 1.00 | 1.02 | 1.02 |
| 2 | 1.02 | 1.00 | 0.98 |
| 3 | 0.99 | 0.99 | 1.00 |
| 4 | 1.00 | 1.01 | 1.01 |
| 5 | 1.01 | 1.00 | 0.99 |

Danh sách tỉ lệ của cả 5 câu:

| Câu | So `set` | `diff_list` (5 tỉ lệ) |
|---|---|---|
| 0 | đúng | `[1.02, 0.98, 1.00, 1.01, 0.99]` |
| 1 | **sai** → trả về 0 | — |
| 2 | đúng | `[0.50, 0.48, 0.52, 0.50, 0.50]` (model chậm gấp đôi) |
| 3 | **lỗi** → `execute_model` bắt lỗi → 0 | — |
| 4 | đúng | `[4.10, 3.90, 4.00, 4.00, 4.00]` (model nhanh gấp 4) |

### B5. `clean_abnormal(input)`

- **Làm gì:** chỉ giữ các giá trị nằm **trong khoảng (trung bình − 3·độ lệch chuẩn, trung bình + 3·độ lệch chuẩn)**, dùng độ lệch chuẩn tổng thể (`np.std`).

| Câu | Trung bình | Độ lệch chuẩn | Khoảng giữ lại | Còn lại | **R** |
|---|---|---|---|---|---|
| 0 | 1.000 | 0.0141 | (0.958, 1.042) | cả 5 | **1.000** |
| 2 | 0.500 | 0.0126 | (0.462, 0.538) | cả 5 | **0.500** |
| 4 | 4.000 | 0.0632 | (3.810, 4.190) | cả 5 | **4.000** |

- **Output** (sau bước B3): `{0: 1.0}`, `{1: 0}`, `{2: 0.5}`, `{3: 0}`, `{4: 4.0}`.

### B6. `sort_results`

Giống A6.

### B7. `compute_ves_by_diff(exec_results, diff_json_path)` → `compute_ves(exec_results)`

- **Làm gì:** chia nhóm theo `difficulty` giống A7. Mỗi câu đóng góp **√R × 100** điểm; VES của một nhóm là **tổng điểm ÷ số câu trong nhóm**. Câu sai đóng góp 0 nhưng **vẫn được tính vào mẫu số**.

| Câu | R | √R × 100 |
|---|---|---|
| 0 | 1.0 | 100.00 |
| 1 | 0 | 0 |
| 2 | 0.5 | 70.71 |
| 3 | 0 | 0 |
| 4 | 4.0 | 200.00 |

| Nhóm | Tính | VES |
|---|---|---|
| simple | (100 + 0) / 2 | **50.00** |
| moderate | (70.71 + 0) / 2 | **35.36** |
| challenging | 200 / 1 | **200.00** |
| total | (100 + 0 + 70.71 + 0 + 200) / 5 | **74.14** |

- **Output:** `(50.0, 35.36, 200.0, 74.14, [2, 2, 1, 5])`.

Công thức: $VES = \dfrac{1}{N}\sum_{n=1}^{N} \mathbb{1}(\text{câu } n \text{ đúng}) \cdot \sqrt{R_n} \times 100$

### B8. `print_data(score_lists, count_lists)`

```
                     simple               moderate             challenging          total
count                2                    2                    1                    5
=========================================    VES   ========================================
ves                  50.00                35.36                200.00               74.14
```

---

## So sánh EX và VES trong ví dụ

| | simple | moderate | challenging | total |
|---|---|---|---|---|
| EX | 50.00 | 50.00 | 100.00 | **60.00** |
| VES | 50.00 | 35.36 | 200.00 | **74.14** |

- **moderate:** VES thấp hơn EX vì câu 2 đúng nhưng chạy chậm gấp đôi đáp án (√0.5 × 100 ≈ 70.7 thay vì 100).
- **challenging:** VES cao hơn EX vì câu 4 nhanh gấp 4 lần (√4 × 100 = 200). Do đó **VES có thể lớn hơn 100**.
- Câu sai (câu 1) và câu lỗi (câu 3) đều được 0 ở cả hai thước đo.

## Lưu ý rút ra từ code

1. **Thứ tự phải khớp ở ba file.** `zip` ở bước A2 và việc ghép theo chỉ số với `dev.json` ở bước A7/B7 đều dựa vào thứ tự. Muốn chấm một tập con (ví dụ 158 câu `student_club`), phải cắt cả ba file theo cùng thứ tự. Nếu một nhóm độ khó không có câu nào, `compute_acc_by_diff` và `compute_ves` sẽ **chia cho 0**.
2. **Timeout khác nhau:** EX cho mỗi cặp 30 giây; VES cho mỗi câu `30 × iterate_num` = 150 giây.
3. **Với `iterate_num = 5`, `clean_abnormal` không bao giờ loại được giá trị nào.** Với *n* mẫu, một giá trị lệch xa nhất cũng chỉ cách trung bình tối đa √(*n*−1) độ lệch chuẩn (bất đẳng thức Samuelson). Với *n* = 5 con số này là 2, luôn nhỏ hơn 3. Muốn bước này có tác dụng thì cần *n* ≥ 10.
4. **Trường hợp hiếm:** nếu mọi tỉ lệ đo được bằng nhau tuyệt đối (độ lệch chuẩn = 0), điều kiện `<` và `>` nghiêm ngặt sẽ loại hết mẫu → chia cho 0 → bị bắt thành lỗi → `time_ratio = 0`. Câu đúng khi đó bị tính 0. Với `iterate_num = 1` thì luôn rơi vào trường hợp này.
5. **VES chỉ đo `cursor.execute`**, không đo `fetchall`, và mỗi lần đo đều mở một kết nối mới. VES phụ thuộc máy và thời điểm chạy, nên mỗi lần chấm có thể lệch nhau một chút; EX thì luôn cho cùng kết quả.
