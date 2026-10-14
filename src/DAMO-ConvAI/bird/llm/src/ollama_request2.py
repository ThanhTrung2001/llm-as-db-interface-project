#!/usr/bin/env python3
"""
Gap 3 variant of ollama_request.py — same prompt / Ollama call, plus evidence normalization.
Flags are the same as openai_request2.py (--normalize_evidence, --ids_file).

ollama_request.py is left untouched: with no new flag set, this script builds exactly the same prompt.

Usage (Kaggle, after `ollama serve` + `ollama pull`):
  python ollama_request2.py --model deepseek-coder-v2:16b --eval_path <bird>/data/dev.json \
      --db_root_path /kaggle/working/dev_databases/ --ids_file changed_ids.json --normalize_evidence \
      --data_output_path /kaggle/working/exp_result/gap3/deepseek_kg_norm178/predict_dev.json
"""
import argparse
import json
import os
from typing import List, Optional

from tqdm import tqdm

from evidence_norm import normalize_pseudo_sql
from ollama_request import call_ollama, extract_sql, generate_combined_prompts_one


def save_predictions(preds: dict, output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(preds, f, indent=4)


def collect_response(model: str, eval_data: List[dict], ids: List[int], db_root_path: str,
                      use_knowledge: bool, normalize_evidence: bool,
                      output_path: Optional[str] = None, checkpoint_every: int = 50,
                      print_prompts: int = 0) -> dict:
    preds = {}
    for n, i in enumerate(tqdm(ids)):
        item = eval_data[i]
        db_path = os.path.join(db_root_path, item['db_id'], item['db_id'] + '.sqlite')
        knowledge = item['evidence'] if use_knowledge else None
        if normalize_evidence:
            knowledge = normalize_pseudo_sql(knowledge)
        prompt = generate_combined_prompts_one(db_path, item['question'], knowledge)
        try:
            sql = extract_sql(call_ollama(model, prompt))
        except Exception as e:
            print(f'  [warn] question {i}: {e}')
            sql = "SELECT"
        if n < print_prompts:
            print(f'\n===== [{i}] prompt (tail) =====\n...{prompt[-600:]}\n----- SQL -----\n{sql}')

        preds[str(i)] = sql + '\t----- bird -----\t' + item['db_id']
        if output_path and (n + 1) % checkpoint_every == 0:
            save_predictions(preds, output_path)
    return preds


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=str, default='qwen2.5-coder:7b-instruct')
    parser.add_argument('--eval_path', type=str, default='./data/dev.json')
    parser.add_argument('--db_root_path', type=str, default='./data/dev_databases/')
    parser.add_argument('--data_output_path', type=str, required=True)
    parser.add_argument('--limit', type=int, default=None, help='only run the first N selected questions (smoke test)')
    parser.add_argument('--ids_file', type=str, default=None, help='JSON list of question indices to run')
    parser.add_argument('--no_knowledge', action='store_true', help='run w/o external knowledge (evidence)')
    parser.add_argument('--normalize_evidence', action='store_true')
    parser.add_argument('--print_prompts', type=int, default=0, help='print the first N prompts/SQL for inspection')
    args = parser.parse_args()

    eval_data = json.load(open(args.eval_path, 'r', encoding='utf-8'))
    ids = json.load(open(args.ids_file)) if args.ids_file else list(range(len(eval_data)))
    if args.limit:
        ids = ids[:args.limit]

    preds = collect_response(args.model, eval_data, ids, args.db_root_path,
                             use_knowledge=not args.no_knowledge, normalize_evidence=args.normalize_evidence,
                             output_path=args.data_output_path,
                             print_prompts=args.print_prompts)
    save_predictions(preds, args.data_output_path)
    print(f'Done. {len(preds)} predictions -> {args.data_output_path}')
