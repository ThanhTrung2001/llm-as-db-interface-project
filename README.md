# LLM as a Database Interface — Re-evaluation on BIRD-SQL

Đồ án môn Hệ thống CSDL tiên tiến.

Based on the paper **"Can LLM Already Serve as A Database Interface? A BIg Bench for
Large-Scale Database Grounded Text-to-SQLs" (BIRD-SQL, NeurIPS 2023)**
— https://arxiv.org/abs/2305.03111.

The original paper evaluates older-generation LLMs (`code-davinci-002`, `text-davinci-003`,
`gpt-3.5-turbo`) on the BIRD-SQL benchmark and finds a large gap versus human performance.
This project re-runs the benchmark against current models to see how much that gap has closed.

## Structure

```
src/DAMO-ConvAI/bird/          # curated subset of AlibabaResearch/DAMO-ConvAI (MIT License)
  data/                        # NOT included in this repo — download separately, see below
  data/dev_databases/          # NOT included in this repo
  llm/data/dev_gold.sql        # NOT included in this repo
  llm/src/gpt_request.py       # original inference script from the paper (legacy OpenAI Completion API)
  llm/src/evaluation.py        # Execution Accuracy (EX)
  llm/src/evaluation_ves.py    # Valid Efficiency Score (VES)
  llm/exp_result/              # prediction outputs (turbo_output* are the sample baseline shipped upstream)
Notebook.ipynb                 # experiment notebook
```

> **The full BIRD dev set (databases + json + gold SQL) is not committed to this repo.** The
> data is licensed CC BY-SA 4.0 by the BIRD-SQL authors — download it yourself following the
> instructions below instead of pulling it from git.

## Setup

1. Create a virtualenv and install dependencies (already set up locally under `venv/`, not
   committed to git):
   ```
   pip install google-generativeai google-genai groq pandas tqdm python-dotenv sqlparse backoff func_timeout
   ```
2. Download the `dev` set from https://bird-bench.github.io/ (Dev Set section), unzip it, and
   copy the files into place:
   ```
   dev.json               -> src/DAMO-ConvAI/bird/data/dev.json
   dev_tables.json         -> src/DAMO-ConvAI/bird/data/dev_tables.json
   dev_tied_append.json    -> src/DAMO-ConvAI/bird/data/dev_tied_append.json
   dev.sql                 -> src/DAMO-ConvAI/bird/llm/data/dev_gold.sql
   dev_databases.zip       -> unzip into src/DAMO-ConvAI/bird/data/dev_databases/
   ```
3. Create a `.env` file at the project root:
   ```
   GEMINI_API_KEY=...
   FREE_API_KEY=...   # Groq API key
   ```

## Evaluation (Execution Accuracy / VES)

```bash
cd src/DAMO-ConvAI/bird/llm
sh run/run_evaluation.sh
```

## Credits

Code under `src/DAMO-ConvAI/bird/` comes from
[AlibabaResearch/DAMO-ConvAI](https://github.com/AlibabaResearch/DAMO-ConvAI) (MIT License).
The BIRD-SQL dataset is licensed CC BY-SA 4.0 — see https://bird-bench.github.io/.
