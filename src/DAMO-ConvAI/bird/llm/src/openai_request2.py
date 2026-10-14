#!/usr/bin/env python3
"""
Gap 3 variant of openai_request.py — same prompt / API call, plus evidence normalization.

openai_request.py is left untouched: with no new flag set, this script builds exactly the same
prompt, so it doubles as the control run.

New flags:
  --normalize_evidence  rewrite pseudo-functions in the evidence (DIVIDE -> CAST(..) / ..) before prompting
  --ids_file            JSON list of question indices to run (e.g. exp_result/gap3/changed_ids.json);
                        output keys keep the original indices so the run can be merged into a full baseline

Usage:
  python src/openai_request2.py --model gpt-3.5-turbo --eval_path ../data/dev.json \
      --db_root_path ../data/dev_databases/ --ids_file exp_result/gap3/changed_ids.json \
      --normalize_evidence --data_output_path exp_result/gap3/turbo_kg_norm178/predict_dev.json
"""
import argparse
import json
import os
from typing import List, Optional

from tqdm import tqdm

from evidence_norm import normalize_pseudo_sql
from openai_request import (call_openai, extract_sql, extract_sql_cot, generate_combined_prompts_cot,
                            generate_combined_prompts_one)


def save_predictions(preds: dict, output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(preds, f, indent=4)


def collect_response(client, model: str, eval_data: List[dict], ids: List[int], db_root_path: str,
                      use_knowledge: bool, normalize_evidence: bool, cot: bool,
                      output_path: Optional[str] = None, checkpoint_every: int = 50,
                      print_prompts: int = 0) -> dict:
    preds = {}
    for n, i in enumerate(tqdm(ids)):
        item = eval_data[i]
        db_path = os.path.join(db_root_path, item['db_id'], item['db_id'] + '.sqlite')
        knowledge = item['evidence'] if use_knowledge else None
        if normalize_evidence:
            knowledge = normalize_pseudo_sql(knowledge)
        try:
            if cot:
                prompt = generate_combined_prompts_cot(db_path, item['question'], knowledge)
                sql = extract_sql_cot(call_openai(client, model, prompt, max_tokens=1024))
            else:
                prompt = generate_combined_prompts_one(db_path, item['question'], knowledge)
                sql = extract_sql(call_openai(client, model, prompt))
            if n < print_prompts:
                print(f'\n===== [{i}] prompt (tail) =====\n...{prompt[-600:]}\n----- SQL -----\n{sql}')
        except Exception as e:
            print(f'  [warn] question {i}: {e}')
            sql = "SELECT"

        preds[str(i)] = sql + '\t----- bird -----\t' + item['db_id']
        if output_path and (n + 1) % checkpoint_every == 0:
            save_predictions(preds, output_path)
    return preds


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=str, default='gpt-3.5-turbo')
    parser.add_argument('--eval_path', type=str, default='./data/dev.json')
    parser.add_argument('--db_root_path', type=str, default='./data/dev_databases/')
    parser.add_argument('--data_output_path', type=str, required=True)
    parser.add_argument('--limit', type=int, default=None, help='only run the first N selected questions (smoke test)')
    parser.add_argument('--ids_file', type=str, default=None, help='JSON list of question indices to run')
    parser.add_argument('--no_knowledge', action='store_true', help='run w/o external knowledge (evidence)')
    parser.add_argument('--cot', action='store_true')
    parser.add_argument('--normalize_evidence', action='store_true')
    parser.add_argument('--print_prompts', type=int, default=0, help='print the first N prompts/SQL for inspection')
    args = parser.parse_args()

    api_key = os.environ.get('OPEN_AI_KEY') or os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise SystemExit('OPEN_AI_KEY not set in .env')

    eval_data = json.load(open(args.eval_path, 'r', encoding='utf-8'))
    ids = json.load(open(args.ids_file)) if args.ids_file else list(range(len(eval_data)))
    if args.limit:
        ids = ids[:args.limit]

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    preds = collect_response(client, args.model, eval_data, ids, args.db_root_path,
                             use_knowledge=not args.no_knowledge, normalize_evidence=args.normalize_evidence,
                             cot=args.cot, output_path=args.data_output_path,
                             print_prompts=args.print_prompts)
    save_predictions(preds, args.data_output_path)
    print(f'Done. {len(preds)} predictions -> {args.data_output_path}')
