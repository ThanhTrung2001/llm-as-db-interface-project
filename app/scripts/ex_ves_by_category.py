#!/usr/bin/env python3
"""
EX và VES theo 6 mức truy vấn (sql_category.py) cho từng model, có / không knowledge.

Mỗi mức (tập câu hỏi) cho ra 2 bảng:
  EX : Model | EX_wo_knowledge  | EX_w_knowledge
  VES: Model | VES_wo_knowledge | VES_w_knowledge

Chấm bằng chính bộ chấm gốc của BIRD (llm/src/evaluation.py, evaluation_ves.py):
  - package_sqls()   đọc predict_dev.json / dev_gold.sql
  - execute_model()  EX: so tập kết quả;  VES: tỉ lệ thời gian gold/pred (iterate_num lần)
  - compute_ves()    VES = trung bình sqrt(time_ratio) * 100
Không gọi thẳng 2 script gốc trên từng tập con vì chúng chia cho số câu
simple/moderate/challenging -> tập con thiếu một độ khó sẽ lỗi chia cho 0.

Chạy trên Kaggle (xem ex-ves-by-category-kaggle.ipynb) hoặc local:
  python app/scripts/ex_ves_by_category.py                         # student_club, local
  python app/scripts/ex_ves_by_category.py --group tag             # theo nhãn (một câu nhiều nhãn)
  python app/scripts/ex_ves_by_category.py --skip_ves              # chỉ EX (nhanh)
  python ex_ves_by_category.py --bird_root /kaggle/input/.../bird \\
      --eval_src /kaggle/working/src --db_root_path /kaggle/working/dev_databases \\
      --out_dir /kaggle/working/ex_ves_by_category

Xuất (trong --out_dir):
  per_question_<db>.csv         kết quả từng câu × từng lượt (res EX, time_ratio VES)
  ex_ves_by_category_<db>.csv   bảng dài: mức, model, n, 4 cột EX/VES
  ex_ves_by_category_<db>.xlsx  mỗi mức 2 sheet (EX, VES) — nếu có openpyxl
"""
import argparse
import json
import multiprocessing as mp
import os
import sys

import pandas as pd

# Windows console (cp1258/cp1252) không in được tiếng Việt -> ép UTF-8
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sql_category import LEVEL_NAME, TAG_ORDER, classify  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
LOCAL_BIRD = os.path.join(ROOT, 'src', 'DAMO-ConvAI', 'bird')

# model hiển thị -> (thư mục w/ knowledge, thư mục w/o knowledge) — giống evaluation-and-ves-local.ipynb
MODEL_FOLDERS = {
    'DeepSeek-Coder-V2': ('ollama_deepseekcoder_output', 'ollama_deepseekcoder_0_output'),
    'Gemma3':            ('ollama_gemma3_output',        'ollama_gemma3_0_output'),
    'Qwen2.5-Coder':     ('ollama_gwen25_output',        'ollama_gwen25_0_output'),
    'GPT-3.5-Turbo':     ('openai_output',               'openai_0_output'),
}

TAG_NAME = {
    'SINGLE_TABLE': '1. Đơn bảng',
    'JOIN': '2. Join',
    'SET_OP': '3. Union / Intersect / Except',
    'OUTER_JOIN': '4. Outer join',
    'GROUP_BY': '5. Group by',
    'DIVISION': '6. Phép chia',
}

COLS = ['EX_wo_knowledge', 'EX_w_knowledge', 'VES_wo_knowledge', 'VES_w_knowledge']


def find_bird_root():
    """Kaggle: tìm thư mục cha của data/dev.json trong /kaggle/input; local: src/DAMO-ConvAI/bird."""
    if os.path.isdir('/kaggle/input'):
        for root, _dirs, files in os.walk('/kaggle/input'):
            if 'dev.json' in files and os.path.basename(root) == 'data':
                return os.path.dirname(root)
    return LOCAL_BIRD


def categories(questions, group):
    """[(key, tên, [question_id...])] — 'level': 6 tập rời nhau theo mức chính; 'tag': theo nhãn."""
    if group == 'level':
        cats = [(str(lv), LEVEL_NAME[lv], [q['question_id'] for q in questions if q['level'] == lv])
                for lv in range(1, 7)]
        other = [q['question_id'] for q in questions if q['level'] == 0]
        if other:
            cats.append(('0', LEVEL_NAME[0], other))
    else:
        cats = [(t, TAG_NAME[t], [q['question_id'] for q in questions if t in q['tags']])
                for t in TAG_ORDER if t in TAG_NAME]
    cats.append(('ALL', 'Tổng', [q['question_id'] for q in questions]))
    return cats


def score_run(evaluation, evaluation_ves, pred_dir, idxs, gold_sqls, args):
    """Chấm 1 lượt (1 thư mục predict_dev.json) trên các câu idxs. Trả {idx: (res, time_ratio)}."""
    preds, pred_dbs = evaluation.package_sqls(pred_dir + '/', args.db_root_path, mode='gpt', data_mode='dev')
    with mp.Pool(processes=args.num_cpus) as pool:
        ex = pool.starmap(evaluation.execute_model,
                          [(preds[i], gold_sqls[i], pred_dbs[i], i, args.meta_time_out) for i in idxs])
        if args.skip_ves:
            ves = [{'sql_idx': i, 'time_ratio': None} for i in idxs]
        else:
            ves = pool.starmap(evaluation_ves.execute_model,
                               [(preds[i], gold_sqls[i], pred_dbs[i], i, args.iterate_num, args.meta_time_out)
                                for i in idxs])
    ratio = {r['sql_idx']: r['time_ratio'] for r in ves}
    return {r['sql_idx']: (r['res'], ratio[r['sql_idx']]) for r in ex}


def main():
    ap = argparse.ArgumentParser(description='EX & VES theo 6 mức truy vấn, có / không knowledge')
    ap.add_argument('--bird_root', help='thư mục chứa data/ và llm/ (mặc định tự tìm)')
    ap.add_argument('--eval_src', help='thư mục chứa evaluation.py, evaluation_ves.py (mặc định <bird>/llm/src)')
    ap.add_argument('--db_root_path', help='thư mục dev_databases (mặc định <bird>/data/dev_databases)')
    ap.add_argument('--exp_dir', help='thư mục exp_result (mặc định <bird>/llm/exp_result)')
    ap.add_argument('--db_id', default='student_club', help="tên CSDL, hoặc 'all'")
    ap.add_argument('--group', choices=['level', 'tag'], default='level',
                    help='level: 6 tập rời nhau theo mức chính (mặc định); tag: theo nhãn')
    ap.add_argument('--num_cpus', type=int, default=4)
    ap.add_argument('--meta_time_out', type=float, default=30.0)
    ap.add_argument('--iterate_num', type=int, default=5, help='số lần chạy lại SQL khi đo VES (paper: 5)')
    ap.add_argument('--skip_ves', action='store_true', help='chỉ chấm EX')
    ap.add_argument('--out_dir', help='mặc định docs/pttk/data')
    args = ap.parse_args()

    bird = args.bird_root or find_bird_root()
    eval_src = args.eval_src or os.path.join(bird, 'llm', 'src')
    args.db_root_path = os.path.join(args.db_root_path or os.path.join(bird, 'data', 'dev_databases'), '')
    exp_dir = args.exp_dir or os.path.join(bird, 'llm', 'exp_result')
    out_dir = args.out_dir or os.path.join(ROOT, 'docs', 'pttk', 'data')
    os.makedirs(out_dir, exist_ok=True)
    print('BIRD_ROOT =', bird)

    sys.path.insert(0, eval_src)
    import evaluation       # noqa: E402  (bộ chấm gốc)
    import evaluation_ves   # noqa: E402

    dev = json.load(open(os.path.join(bird, 'data', 'dev.json'), encoding='utf-8'))
    gold_sqls, _ = evaluation.package_sqls(os.path.join(bird, 'llm', 'data', ''), args.db_root_path,
                                           mode='gt', data_mode='dev')
    questions = []
    for i, q in enumerate(dev):
        if args.db_id != 'all' and q['db_id'] != args.db_id:
            continue
        c = classify(gold_sqls[i])
        questions.append({'question_id': i, 'difficulty': q['difficulty'], 'level': c['level'], 'tags': c['tags']})
    if not questions:
        sys.exit(f'Không có câu nào với db_id={args.db_id}')
    idxs = [q['question_id'] for q in questions]
    cats = categories(questions, args.group)
    print(f'{args.db_id}: {len(questions)} câu; phân loại theo {args.group}:')
    for key, name, ids in cats:
        print(f'  {name:40} {len(ids):5}')

    # ---- chấm từng lượt: model × (có / không knowledge) ----
    results = {}  # (model, 'w'|'wo') -> {idx: (res, time_ratio)}
    for model, (kg_dir, nokg_dir) in MODEL_FOLDERS.items():
        for label, d in [('wo', nokg_dir), ('w', kg_dir)]:
            pred_dir = os.path.join(exp_dir, d)
            if not os.path.exists(os.path.join(pred_dir, 'predict_dev.json')):
                print(f'  bỏ qua {model} ({label} knowledge): không có {pred_dir}/predict_dev.json')
                continue
            print(f'\n===== {model} ({label} knowledge): {d} =====')
            results[(model, label)] = score_run(evaluation, evaluation_ves, pred_dir, idxs, gold_sqls, args)
            r = results[(model, label)]
            print(f'  EX = {100 * sum(v[0] for v in r.values()) / len(r):.2f}')

    if not results:
        sys.exit('Không có lượt nào để chấm.')

    # ---- từng câu ----
    qmap = {q['question_id']: q for q in questions}
    per_q = pd.DataFrame([
        {'question_id': i, 'difficulty': qmap[i]['difficulty'], 'level': qmap[i]['level'],
         'tags': '|'.join(qmap[i]['tags']), 'model': model, 'knowledge': label,
         'ex': res, 'time_ratio': ratio}
        for (model, label), r in results.items() for i, (res, ratio) in r.items()])
    per_q.to_csv(os.path.join(out_dir, f'per_question_{args.db_id}.csv'), index=False, encoding='utf-8-sig')

    # ---- gom theo mức: EX = % đúng; VES = compute_ves() gốc ----
    rows = []
    for key, name, ids in cats:
        for model in MODEL_FOLDERS:
            row = {'category': key, 'category_name': name, 'n': len(ids), 'model': model}
            for label in ('wo', 'w'):
                r = results.get((model, label))
                ex = ves = None
                if r is not None and ids:
                    ex = round(100 * sum(r[i][0] for i in ids) / len(ids), 2)
                    if not args.skip_ves:
                        ves = round(evaluation_ves.compute_ves([{'time_ratio': r[i][1]} for i in ids]), 2)
                row[f'EX_{label}_knowledge'] = ex
                row[f'VES_{label}_knowledge'] = ves
            rows.append(row)
    long = pd.DataFrame(rows)[['category', 'category_name', 'n', 'model'] + COLS]
    out_csv = os.path.join(out_dir, f'ex_ves_by_category_{args.db_id}.csv')
    long.to_csv(out_csv, index=False, encoding='utf-8-sig')

    # ---- in bảng: mỗi mức 1 bảng EX + 1 bảng VES ----
    sheets = {}
    for key, name, ids in cats:
        part = long[long['category'] == key].set_index('model')
        ex_tbl = part[['EX_wo_knowledge', 'EX_w_knowledge']]
        ves_tbl = part[['VES_wo_knowledge', 'VES_w_knowledge']]
        sheets[f'{key}_EX'], sheets[f'{key}_VES'] = ex_tbl, ves_tbl
        print(f'\n######## {name} — {len(ids)} câu ########')
        if not ids:
            print('  (không có câu nào thuộc tập này)')
            continue
        print('EX (%)\n' + ex_tbl.to_string(na_rep='-'))
        if not args.skip_ves:
            print('VES\n' + ves_tbl.to_string(na_rep='-'))

    try:
        out_xlsx = os.path.join(out_dir, f'ex_ves_by_category_{args.db_id}.xlsx')
        with pd.ExcelWriter(out_xlsx) as w:
            for sheet, tbl in sheets.items():
                tbl.to_excel(w, sheet_name=sheet[:31])
        print(f'\n-> {out_xlsx}')
    except ImportError:
        print('\n(không có openpyxl -> bỏ qua file .xlsx)')
    print(f'-> {out_csv}')


if __name__ == '__main__':
    main()
