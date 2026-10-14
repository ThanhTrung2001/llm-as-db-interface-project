# Gap 3 — Chuẩn hoá evidence: runbook

**Mục tiêu:** BIRD evidence dùng hàm giả (`DIVIDE`, `SUBTRACT`, `YEAR`, ...) mà SQLite không có. Model chép nguyên vào SQL nên chạy lỗi `no such function`. Ở đây đo xem việc chuẩn hoá evidence sang cú pháp SQLite hợp lệ **trước khi đưa vào prompt** có làm tăng EX không. SQL do LLM sinh ra được giữ nguyên, không hậu xử lý.

**Nguyên tắc:** DB, `dev.json`, các script gốc (`openai_request.py`, `ollama_request.py`) và bộ chấm (`evaluation.py`, `evaluation_ves.py`) giữ nguyên. Mọi thay đổi nằm trong file mới.

| File (trong `src/DAMO-ConvAI/bird/llm/`) | Vai trò |
|---|---|
| `src/evidence_norm.py` | `normalize_pseudo_sql()`: DIVIDE → `CAST(a AS REAL) / b`, SUBTRACT/MULTIPLY/ADD → toán tử, YEAR/MONTH/DAY → `STRFTIME` |
| `src/test_evidence_norm.py` | Test cho hàm trên |
| `src/openai_request2.py` | Bản 2 của `openai_request.py`, thêm `--normalize_evidence`, `--ids_file`, `--print_prompts` |
| `src/ollama_request2.py` | Bản 2 của `ollama_request.py`, các cờ giống bên trên |
| `src/gap3_tools.py` | Các công cụ offline: `stats`, `merge`, `ex` |
| `gap3-ollama-kaggle.ipynb` (thư mục gốc repo) | Notebook Kaggle chạy phần Ollama |

Khi không bật cờ nào, script bản 2 dựng prompt giống hệt bản gốc, nên dùng luôn được cho lượt chạy đối chứng.

## Các biến thể

| | Mô tả | Gọi LLM? |
|---|---|---|
| A | Baseline: `exp_result/openai_output` (EX 47,78) | đã có |
| A' | Đối chứng: chạy lại prompt gốc trên tập câu có evidence bị đổi, để đo nhiễu do model drift | có |
| C | `--normalize_evidence` trên tập câu có evidence bị đổi | có |

Chỉ cần chạy lại **các câu có evidence bị đổi** (`changed_ids.json`, 182 câu). Với các câu còn lại, prompt giống hệt baseline. Run w/o KG không bị ảnh hưởng nên không chạy lại.

---

## Chạy ở đâu?

| Bước | Ở đâu | Lý do |
|---|---|---|
| 1. Test và thống kê | 💻 Local | Vài giây, không gọi API |
| 2. GPT-3.5: smoke, A', C | 💻 Local | Chỉ gọi OpenAI API, không cần GPU (khoảng 2×182 lời gọi) |
| 3. Ollama: baseline mới, C | ☁️ **Kaggle** | Cần GPU để chạy model |
| 4. Merge và EX/VES | 💻 Local | Chạy SQLite trên DB local |

Mọi lệnh local chạy từ thư mục `src/DAMO-ConvAI/bird/llm/`, bằng Python trong `venv/`.

### 1. 💻 Test và thống kê
```bash
python src/test_evidence_norm.py
python src/gap3_tools.py stats --show 3
```
Lệnh `stats` sinh ra `exp_result/gap3/changed_ids.json` (182 câu) và `malformed_ids.json` (21 evidence tự thân sai cú pháp, không sửa được). Lệnh này cũng in số câu SQL bị chép hàm giả trong các run có sẵn, ở cả w/ KG và w/o KG; đây là số liệu động lực cho báo cáo.

### 2. 💻 GPT-3.5 (cần `OPEN_AI_KEY` trong `.env`)
Dùng **đúng model string đã dùng cho `openai_output`** (`gpt-3.5-turbo`). Alias này có thể đã trỏ sang snapshot mới, và lượt A' tồn tại chính là để đo chênh lệch đó.

```bash
# smoke: 5 câu, in prompt ra kiểm tra (phải thấy CAST(... AS REAL) / ..., không còn DIVIDE()
python src/openai_request2.py --model gpt-3.5-turbo --eval_path ../data/dev.json --db_root_path ../data/dev_databases/ \
  --ids_file exp_result/gap3/changed_ids.json --limit 5 --normalize_evidence --print_prompts 5 \
  --data_output_path exp_result/gap3/smoke/predict_dev.json

# A' — đối chứng (prompt gốc)
python src/openai_request2.py --model gpt-3.5-turbo --eval_path ../data/dev.json --db_root_path ../data/dev_databases/ \
  --ids_file exp_result/gap3/changed_ids.json \
  --data_output_path exp_result/gap3/turbo_kg_ctrl182/predict_dev.json

# C — evidence đã chuẩn hoá
python src/openai_request2.py --model gpt-3.5-turbo --eval_path ../data/dev.json --db_root_path ../data/dev_databases/ \
  --ids_file exp_result/gap3/changed_ids.json --normalize_evidence \
  --data_output_path exp_result/gap3/turbo_kg_norm182/predict_dev.json
```

### 3. ☁️ Ollama trên Kaggle (tuỳ chọn)
1. Upload thành một Kaggle dataset (ví dụ `bird-gap3-src`) 4 file: `src/ollama_request.py`, `src/ollama_request2.py`, `src/evidence_norm.py`, `exp_result/gap3/changed_ids.json`.
2. Mở `gap3-ollama-kaggle.ipynb` trên Kaggle, attach dataset trên và dataset BIRD, bật GPU và Internet.
3. Chạy lần lượt: smoke → baseline full w/ KG (`deepseek_kg_base`) → C (`deepseek_kg_norm182`).
4. Tải `gap3_results.zip` về, giải nén vào `src/DAMO-ConvAI/bird/llm/`.

### 4. 💻 Merge và đánh giá
```bash
# ghép các câu đã chạy lại vào baseline 1534 câu
python src/gap3_tools.py merge --base openai_output --sub exp_result/gap3/turbo_kg_ctrl182/predict_dev.json \
  --out exp_result/gap3/turbo_kg_ctrl_v2/predict_dev.json
python src/gap3_tools.py merge --base openai_output --sub exp_result/gap3/turbo_kg_norm182/predict_dev.json \
  --out exp_result/gap3/turbo_kg_norm_v2/predict_dev.json

# bảng EX: toàn tập và tập con 182 câu
python src/gap3_tools.py ex --full --ids_file exp_result/gap3/changed_ids.json \
  --runs openai_output gap3/turbo_kg_ctrl_v2 gap3/turbo_kg_norm_v2
```
Với Ollama: tương tự, dùng `--base exp_result/gap3/deepseek_kg_base/predict_dev.json`.

Số chính thức trên toàn tập lấy từ bộ chấm gốc:
```bash
python src/evaluation.py --db_root_path ../data/dev_databases/ --predicted_sql_path exp_result/gap3/turbo_kg_norm_v2/ \
  --data_mode dev --ground_truth_path ./data/ --num_cpus 8 --mode_gt gt --mode_predict gpt \
  --diff_json_path ../data/dev.json --meta_time_out 30.0
# VES: thay bằng src/evaluation_ves.py, thêm --iterate_num 5
```

## Cách đọc kết quả
- **Hiệu ứng của chuẩn hoá = C − A'** (không phải C − A), vì A' và C được chạy cùng thời điểm và cùng snapshot model.
- Báo cáo cả tập con 182 câu (hiệu ứng rõ) lẫn toàn tập 1534 câu (con số so được với paper).
- Phân tích lỗi trên các câu C vẫn sai: còn chép hàm giả, chia nguyên, sai cột (thuộc Gap 2), hay nằm trong `malformed_ids.json`.
