#!/usr/bin/env python3
"""
Gap 3 offline tools (no LLM calls). Run from the llm/ directory.

  stats   evidence statistics + pseudo-function leaks in existing runs; writes changed_ids.json
  merge   put a subset run (e.g. 182 questions) back into a full 1534-question baseline file
  ex      execution accuracy of several runs, on the full set and on a subset (--ids_file)

Examples:
  python src/gap3_tools.py stats
  python src/gap3_tools.py merge --base openai_output \
      --sub exp_result/gap3/turbo_kg_norm182/predict_dev.json --out exp_result/gap3/turbo_kg_norm/predict_dev.json
  python src/gap3_tools.py ex --runs openai_output gap3/turbo_kg_norm --ids_file exp_result/gap3/changed_ids.json

Official full-set EX/VES numbers should still come from evaluation.py / evaluation_ves.py;
`ex` re-implements the same comparison (set equality, 30s timeout, error = 0) so it can also
report the subset.
"""
import argparse
import json
import multiprocessing as mp
import os
import sqlite3
import threading

from evidence_norm import has_pseudo_fn, normalize_pseudo_sql

EXP = './exp_result'
GAP3 = os.path.join(EXP, 'gap3')
SEP = '\t----- bird -----\t'

# (w/ KG run, w/o KG run) pairs that exist in exp_result/
RUN_PAIRS = {
    'GPT-3.5-Turbo (openai_output)': ('openai_output', 'openai_0_output'),
    'GPT-3.5-Turbo (openai_output1)': ('openai_output1', 'openai_0_output1'),
    'DeepSeek-Coder-V2': ('ollama_deepseekcoder_output', 'ollama_deepseekcoder_0_output'),
    'Gemma3': ('ollama_gemma3_output', 'ollama_gemma3_0_output'),
    'Qwen2.5-Coder': ('ollama_gwen25_output', 'ollama_gwen25_0_output'),
}


def load_preds(path: str) -> dict:
    """{str(idx): raw value}; path is a run folder name under exp_result/ or a .json file."""
    if not path.endswith('.json'):
        path = os.path.join(EXP, path, 'predict_dev.json')
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def pred_sql(value) -> str:
    # evaluation.py turns non-string entries into " " (always wrong); do the same
    return value.split(SEP)[0] if isinstance(value, str) else ' '


def save_preds(preds: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # evaluation.py zips predictions with gold by dict order, so keep keys in index order
    ordered = {k: preds[k] for k in sorted(preds, key=int)}
    with open(path, 'w') as f:
        json.dump(ordered, f, indent=4)


# ---------------- stats ----------------

def cmd_stats(args):
    data = json.load(open(args.eval_path, encoding='utf-8'))
    n = len(data)
    with_fn = [i for i, x in enumerate(data) if has_pseudo_fn(x['evidence'])]
    changed = [i for i in with_fn if normalize_pseudo_sql(data[i]['evidence']) != data[i]['evidence']]
    leftover = [i for i in with_fn if has_pseudo_fn(normalize_pseudo_sql(data[i]['evidence']))]

    print(f'Questions: {n}')
    print(f'Evidence containing pseudo-functions : {len(with_fn)}')
    print(f'Evidence changed by normalization    : {len(changed)}  -> changed_ids.json')
    print(f'Evidence still containing pseudo-fn  : {len(leftover)} (malformed: bad parens / wrong separators)')

    os.makedirs(GAP3, exist_ok=True)
    json.dump(changed, open(os.path.join(GAP3, 'changed_ids.json'), 'w'))
    json.dump(leftover, open(os.path.join(GAP3, 'malformed_ids.json'), 'w'))

    print('\nPredicted SQL containing pseudo-functions (guaranteed "no such function" error):')
    print(f'{"model":34} {"w/ KG":>8} {"w/o KG":>8} {"w/ KG, in changed_ids":>22}')
    changed_set = set(changed)
    for name, (kg, nokg) in RUN_PAIRS.items():
        row = []
        for run in (kg, nokg):
            try:
                preds = load_preds(run)
                row.append(sum(has_pseudo_fn(pred_sql(v)) for v in preds.values()))
            except FileNotFoundError:
                row.append('-')
        try:
            preds = load_preds(kg)
            in_changed = sum(has_pseudo_fn(pred_sql(v)) for k, v in preds.items() if int(k) in changed_set)
        except FileNotFoundError:
            in_changed = '-'
        print(f'{name:34} {row[0]:>8} {row[1]:>8} {in_changed:>22}')

    if args.show:
        for i in changed[:args.show]:
            print(f'\n[{i}] - {data[i]["evidence"]}\n[{i}] + {normalize_pseudo_sql(data[i]["evidence"])}')


# ---------------- merge ----------------

def cmd_merge(args):
    base, sub = load_preds(args.base), load_preds(args.sub)
    missing = set(sub) - set(base)
    if missing:
        raise SystemExit(f'sub has indices not in base: {sorted(missing)[:5]}...')
    merged = dict(base)
    merged.update(sub)
    save_preds(merged, args.out)
    print(f'{len(sub)} of {len(base)} predictions replaced -> {args.out}')


# ---------------- ex ----------------

def _exec(task):
    idx, pred, gold, db_path, timeout = task
    conn = sqlite3.connect(db_path)
    timer = threading.Timer(timeout, conn.interrupt)
    timer.start()
    try:
        pred_res = conn.execute(pred).fetchall()
        gold_res = conn.execute(gold).fetchall()
        return idx, int(set(pred_res) == set(gold_res))
    except Exception:
        return idx, 0
    finally:
        timer.cancel()
        conn.close()


def cmd_ex(args):
    data = json.load(open(args.eval_path, encoding='utf-8'))
    subset = json.load(open(args.ids_file)) if args.ids_file else None
    db = lambda i: os.path.join(args.db_root_path, data[i]['db_id'], data[i]['db_id'] + '.sqlite')

    print(f'{"run":45} {"EX full":>9} {"EX subset":>10}  (subset n={len(subset) if subset else "-"})')
    with mp.Pool(args.num_cpus) as pool:
        for run in args.runs:
            preds = load_preds(run)
            ids = range(len(data)) if args.full or subset is None else subset
            tasks = [(i, pred_sql(preds.get(str(i))), data[i]['SQL'], db(i), args.timeout) for i in ids]
            res = dict(pool.map(_exec, tasks, chunksize=4))
            full = f'{100 * sum(res.values()) / len(data):.2f}' if len(res) == len(data) else '-'
            sub = f'{100 * sum(res[i] for i in subset) / len(subset):.2f}' if subset else '-'
            print(f'{run:45} {full:>9} {sub:>10}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--eval_path', default='../data/dev.json')
    sp = parser.add_subparsers(dest='cmd', required=True)

    p = sp.add_parser('stats')
    p.add_argument('--show', type=int, default=0, help='print N before/after evidence examples')
    p.set_defaults(func=cmd_stats)

    p = sp.add_parser('merge')
    p.add_argument('--base', required=True)
    p.add_argument('--sub', required=True)
    p.add_argument('--out', required=True)
    p.set_defaults(func=cmd_merge)

    p = sp.add_parser('ex')
    p.add_argument('--runs', nargs='+', required=True)
    p.add_argument('--ids_file', default=None)
    p.add_argument('--full', action='store_true', help='also compute full-set EX (slower)')
    p.add_argument('--db_root_path', default='../data/dev_databases/')
    p.add_argument('--num_cpus', type=int, default=8)
    p.add_argument('--timeout', type=float, default=30.0)
    p.set_defaults(func=cmd_ex)

    args = parser.parse_args()
    args.func(args)
