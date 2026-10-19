#!/usr/bin/env python3
"""
EX theo từng CSDL (mặc định student_club) từ các file predict_dev.json đã có.

Chấm bằng chính execute_model() của evaluation.py gốc (so tập kết quả thực thi,
timeout 30s) nên kết quả từng câu khớp với bộ chấm của BIRD.

Xuất:
  app/data/benchmark_<db>.json   kết quả từng câu (để app nạp vào chế độ phát lại)
  docs/pttk/data/ex_<db>.csv     bảng EX theo model × cấu hình × độ khó

Usage:
  python app/scripts/per_db_ex.py
  python app/scripts/per_db_ex.py --db_id financial
"""
import argparse
import csv
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
BIRD = os.path.join(ROOT, 'src', 'DAMO-ConvAI', 'bird')
LLM = os.path.join(BIRD, 'llm')
sys.path.insert(0, os.path.join(LLM, 'src'))
from evaluation import execute_model  # noqa: E402  (bộ chấm gốc)

DEV_JSON = os.path.join(BIRD, 'data', 'dev.json')
GOLD_SQL = os.path.join(LLM, 'data', 'dev_gold.sql')
DB_ROOT = os.path.join(BIRD, 'data', 'dev_databases')
EXP = os.path.join(LLM, 'exp_result')

# (model, cấu hình, thư mục output, ghi chú) — ánh xạ lấy từ evaluation-and-ves-local.ipynb
# và gap3-evaluation-kaggle.ipynb
RUNS = [
    ('GPT-3.5-Turbo', 'no_evidence', 'openai_0_output', 'chính thức'),
    ('GPT-3.5-Turbo', 'evidence', 'openai_output', 'chính thức'),
    ('GPT-3.5-Turbo', 'evidence_norm', 'gap3/turbo_kg_norm_v2', 'Gap 3'),
    ('DeepSeek-Coder-V2', 'no_evidence', 'ollama_deepseekcoder_0_output', 'tạm thời'),
    ('DeepSeek-Coder-V2', 'evidence', 'ollama_deepseekcoder_output', 'tạm thời'),
    ('DeepSeek-Coder-V2', 'evidence_norm', 'gap3/deepseek_kg_norm_v2', 'Gap 3, tạm thời'),
    ('Gemma3', 'no_evidence', 'ollama_gemma3_0_output', 'tạm thời'),
    ('Gemma3', 'evidence', 'ollama_gemma3_output', 'tạm thời'),
    ('Gemma3', 'evidence_norm', 'gap3/gemma3_kg_norm_v2', 'Gap 3, tạm thời'),
    ('Qwen2.5-Coder', 'no_evidence', 'ollama_gwen25_0_output', 'tạm thời'),
    ('Qwen2.5-Coder', 'evidence', 'ollama_gwen25_output', 'tạm thời'),
    ('Qwen2.5-Coder', 'evidence_norm', 'gap3/qwen25_kg_norm_v2', 'Gap 3, tạm thời'),
]
LEVELS = ['simple', 'moderate', 'challenging']


def load_gold():
    with open(GOLD_SQL, encoding='utf-8') as f:
        return [line.strip().split('\t')[0] for line in f]


def load_pred(run_dir):
    path = os.path.join(EXP, run_dir, 'predict_dev.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    return {int(k): (v.split('\t----- bird -----\t')[0] if isinstance(v, str) else ' ')
            for k, v in data.items()}


def pct(xs):
    return round(100 * sum(xs) / len(xs), 2) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db_id', default='student_club')
    ap.add_argument('--timeout', type=float, default=30.0)
    args = ap.parse_args()

    dev = json.load(open(DEV_JSON, encoding='utf-8'))
    gold = load_gold()
    db_path = os.path.join(DB_ROOT, args.db_id, args.db_id + '.sqlite')
    idx = [i for i, q in enumerate(dev) if q['db_id'] == args.db_id]
    print(f'{args.db_id}: {len(idx)} câu')

    questions = [{'question_id': i, 'question': dev[i]['question'], 'evidence': dev[i]['evidence'],
                  'gold_sql': gold[i], 'difficulty': dev[i]['difficulty']} for i in idx]
    runs, rows = [], []
    for model, config, run_dir, note in RUNS:
        if not os.path.exists(os.path.join(EXP, run_dir, 'predict_dev.json')):
            print(f'  bỏ qua {run_dir} (không có file)')
            continue
        pred = load_pred(run_dir)
        items = []
        for i in idx:
            res = execute_model(pred.get(i, ' '), gold[i], db_path, i, args.timeout)['res']
            items.append({'question_id': i, 'predicted_sql': pred.get(i, ' '), 'is_correct': res})
        by_level = {lv: [it['is_correct'] for it, q in zip(items, questions) if q['difficulty'] == lv]
                    for lv in LEVELS}
        row = {'model': model, 'config': config, 'source': run_dir, 'note': note,
               **{lv: pct(by_level[lv]) for lv in LEVELS},
               'total': pct([it['is_correct'] for it in items]), 'n': len(items)}
        rows.append(row)
        runs.append({**{k: row[k] for k in ('model', 'config', 'source', 'note', 'total')}, 'items': items})
        print(f"  {model:18} {config:14} EX={row['total']:6.2f}  ({run_dir})")

    os.makedirs(os.path.join(ROOT, 'app', 'data'), exist_ok=True)
    with open(os.path.join(ROOT, 'app', 'data', f'benchmark_{args.db_id}.json'), 'w', encoding='utf-8') as f:
        json.dump({'db_id': args.db_id, 'questions': questions, 'runs': runs}, f, ensure_ascii=False, indent=1)

    out_csv = os.path.join(ROOT, 'docs', 'pttk', 'data', f'ex_{args.db_id}.csv')
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f'-> {out_csv}')


if __name__ == '__main__':
    main()
