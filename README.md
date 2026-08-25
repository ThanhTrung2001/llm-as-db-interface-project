# LLM as a Database Interface — Re-evaluation on BIRD-SQL

Đồ án môn Hệ thống CSDL tiên tiến. Dựa trên bài báo **"Can LLM Already Serve as A Database
Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs" (BIRD-SQL, NeurIPS 2023)**
— https://arxiv.org/abs/2305.03111.

Bài báo gốc đánh giá các LLM đời cũ (`code-davinci-002`, `text-davinci-003`, `gpt-3.5-turbo`) trên
benchmark BIRD-SQL và kết luận vẫn còn khoảng cách lớn so với con người. Đồ án này chạy lại
benchmark với một số model hiện tại (Gemini, các model mã nguồn mở qua Groq) để khảo nghiệm xem
khoảng cách đó đã thu hẹp đến đâu.

## Cấu trúc

```
src/DAMO-ConvAI/bird/          # subset của repo gốc AlibabaResearch/DAMO-ConvAI (MIT License)
  data/                        # KHÔNG có trong repo — toàn bộ dev set tải riêng, xem bên dưới
  data/dev_databases/          # KHÔNG có trong repo
  llm/data/dev_gold.sql        # KHÔNG có trong repo
  llm/src/gpt_request.py       # script inference gốc của paper (OpenAI Completion API, để tham chiếu)
  llm/src/modern_llm_request.py# script inference MỚI: gọi Gemini (google-genai) và Groq
  llm/src/evaluation.py        # Execution Accuracy (EX)
  llm/src/evaluation_ves.py    # Valid Efficiency Score (VES)
  llm/exp_result/              # kết quả dự đoán (turbo_output* là baseline mẫu có sẵn từ repo gốc)
Notebook.ipynb                 # notebook chạy thử nghiệm
```

> **Toàn bộ BIRD dev set (database + json + gold sql) không được commit vào repo này** — dữ liệu
> thuộc giấy phép CC BY-SA 4.0 của BIRD-SQL, mỗi người cần tự tải về theo hướng dẫn dưới đây thay
> vì lấy từ git.

## Thiết lập

1. Tạo virtualenv và cài dependency (đã có sẵn trong `venv/`, không commit lên git):
   ```
   pip install google-generativeai google-genai groq pandas tqdm python-dotenv sqlparse backoff func_timeout
   ```
2. Tải bộ `dev` từ https://bird-bench.github.io/ (mục Dev Set), giải nén rồi copy vào đúng vị trí:
   ```
   dev.json               -> src/DAMO-ConvAI/bird/data/dev.json
   dev_tables.json         -> src/DAMO-ConvAI/bird/data/dev_tables.json
   dev_tied_append.json    -> src/DAMO-ConvAI/bird/data/dev_tied_append.json
   dev.sql                 -> src/DAMO-ConvAI/bird/llm/data/dev_gold.sql
   dev_databases.zip       -> giải nén vào src/DAMO-ConvAI/bird/data/dev_databases/
   ```
3. Tạo file `.env` ở gốc dự án:
   ```
   GEMINI_API_KEY=...
   FREE_API_KEY=...   # Groq API key
   ```

## Chạy inference

```bash
cd src/DAMO-ConvAI/bird/llm
python src/modern_llm_request.py --provider gemini --model gemini-2.5-flash \
  --use_knowledge True --data_output_path ./exp_result/gemini_output/

python src/modern_llm_request.py --provider groq --model llama-3.3-70b-versatile \
  --use_knowledge True --data_output_path ./exp_result/groq_output/
```

## Đánh giá (Execution Accuracy / VES)

```bash
cd src/DAMO-ConvAI/bird/llm
sh run/run_evaluation.sh
```

## Ghi công

Code trong `src/DAMO-ConvAI/bird/` (trừ `modern_llm_request.py`) được lấy từ
[AlibabaResearch/DAMO-ConvAI](https://github.com/AlibabaResearch/DAMO-ConvAI) (MIT License).
Bộ dữ liệu BIRD-SQL thuộc giấy phép CC BY-SA 4.0 — xem https://bird-bench.github.io/.
