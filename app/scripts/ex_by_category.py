#!/usr/bin/env python3
"""
EX (execution accuracy) của từng lượt benchmark, tách theo 6 mức truy vấn
(xem sql_category.py): 1 bảng / kết bảng / union-intersect-except / outer join /
group by / phép chia.

Nguồn kết quả đúng/sai từng câu:
  - Mặc định: đọc app/data/benchmark_<db>.json (do per_db_ex.py tạo) -> không cần chạy lại SQL.
  - --rescore, hoặc --db_id all, hoặc chưa có file JSON: chấm lại bằng execute_model()
    của evaluation.py gốc trên các predict_dev.json trong exp_result/ (giống per_db_ex.py).

Xuất:
  docs/pttk/data/ex_by_category_<db>.csv   dạng dài: model, config, nhóm, hạng mục, n, đúng, EX
  và in bảng tóm tắt ra màn hình.

Usage:
  python app/scripts/ex_by_category.py                          # student_club, đọc JSON có sẵn
  python app/scripts/ex_by_category.py --db_id all              # toàn bộ dev (chạy lại SQL, lâu)
  python app/scripts/ex_by_category.py --db_id all --model Qwen # chỉ các lượt có tên chứa "Qwen"
"""
import argparse
import csv
import json
import os
import sys

# Windows console (cp1258/cp1252) không in được tiếng Việt -> ép UTF-8
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sql_category import (LEVEL_NAME, TAG_ORDER, classify,  # noqa: E402
                          load_dev_with_gold)

ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
DB_ROOT = os.path.join(ROOT, 'src', 'DAMO-ConvAI', 'bird', 'data', 'dev_databases')

TAG_NAME = {
    'SINGLE_TABLE': '1.Đơn bảng',
    'JOIN': '2.Join',
    'SET_OP': '3.SetOp',
    'OUTER_JOIN': '4.Outer',
    'GROUP_BY': '5.GroupBy',
    'DIVISION': '6.Chia',
    'NESTED': '(Lồng)',
}


def results_from_json(db_id, model_filter):
    path = os.path.join(ROOT, 'app', 'data', f'benchmark_{db_id}.json')
    if not os.path.exists(path):
        return None
    data = json.load(open(path, encoding='utf-8'))
    runs = []
    for r in data['runs']:
        if model_filter and model_filter.lower() not in r['model'].lower():
            continue
        runs.append({'model': r['model'], 'config': r['config'], 'source': r['source'],
                     'correct': {it['question_id']: it['is_correct'] for it in r['items']}})
    print(f'Đọc kết quả từ {os.path.relpath(path, ROOT)} ({len(runs)} lượt)')
    return runs


def results_by_rescoring(questions, model_filter, timeout):
    import per_db_ex  # dùng chung RUNS, load_pred và execute_model của bộ chấm gốc
    try:
        from tqdm import tqdm
    except ImportError:
        def tqdm(x, **_):
            return x

    runs = []
    for model, config, run_dir, _note in per_db_ex.RUNS:
        if model_filter and model_filter.lower() not in model.lower():
            continue
        if not os.path.exists(os.path.join(per_db_ex.EXP, run_dir, 'predict_dev.json')):
            print(f'  bỏ qua {run_dir} (không có file)')
            continue
        pred = per_db_ex.load_pred(run_dir)
        correct = {}
        for q in tqdm(questions, desc=f'{model} / {config}', leave=False):
            i = q['question_id']
            db_path = os.path.join(DB_ROOT, q['db_id'], q['db_id'] + '.sqlite')
            correct[i] = per_db_ex.execute_model(pred.get(i, ' '), q['gold_sql'], db_path, i, timeout)['res']
        print(f'  chấm xong {model} / {config}: EX={100 * sum(correct.values()) / len(correct):.2f}')
        runs.append({'model': model, 'config': config, 'source': run_dir, 'correct': correct})
    return runs


def ex(values):
    return round(100 * sum(values) / len(values), 2) if values else None


def main():
    ap = argparse.ArgumentParser(description='EX theo 6 mức truy vấn')
    ap.add_argument('--db_id', default='student_club', help="tên CSDL, hoặc 'all'")
    ap.add_argument('--model', help='chỉ lấy các lượt có tên model chứa chuỗi này')
    ap.add_argument('--rescore', action='store_true', help='chấm lại SQL thay vì đọc benchmark JSON')
    ap.add_argument('--timeout', type=float, default=30.0)
    ap.add_argument('--out', help='đường dẫn CSV (mặc định docs/pttk/data/ex_by_category_<db>.csv)')
    args = ap.parse_args()

    questions = load_dev_with_gold()
    if args.db_id != 'all':
        questions = [q for q in questions if q['db_id'] == args.db_id]
    if not questions:
        sys.exit(f'Không có câu nào với db_id={args.db_id}')
    for q in questions:
        c = classify(q['gold_sql'])
        q['level'], q['tags'] = c['level'], c['tags']

    runs = None
    if not args.rescore and args.db_id != 'all':
        runs = results_from_json(args.db_id, args.model)
    if runs is None:
        print(f'Chấm lại {len(questions)} câu cho mỗi lượt (timeout {args.timeout}s/câu)...')
        runs = results_by_rescoring(questions, args.model, args.timeout)
    if not runs:
        sys.exit('Không có lượt benchmark nào để chấm.')

    # hạng mục: theo NHÃN (multi-label) và theo MỨC CHÍNH (mỗi câu 1 mức)
    groups = [('tag', t, TAG_NAME[t], [q for q in questions if t in q['tags']]) for t in TAG_ORDER]
    groups += [('level', str(lv), LEVEL_NAME[lv], [q for q in questions if q['level'] == lv])
               for lv in sorted(LEVEL_NAME)]
    groups.append(('total', 'ALL', 'Tổng', questions))

    rows = []
    for r in runs:
        for kind, key, name, qs in groups:
            vals = [r['correct'].get(q['question_id'], 0) for q in qs]
            rows.append({'model': r['model'], 'config': r['config'], 'source': r['source'],
                         'group': kind, 'category': key, 'category_name': name,
                         'n': len(vals), 'correct': sum(vals), 'ex': ex(vals)})

    out = args.out or os.path.join(ROOT, 'docs', 'pttk', 'data', f'ex_by_category_{args.db_id}.csv')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ---- bảng tóm tắt: EX (%) theo nhãn ----
    tag_groups = [g for g in groups if g[0] == 'tag'] + [groups[-1]]
    head = f"{'Model':18} {'Cấu hình':14}" + ''.join(f'{g[2]:>10}' for g in tag_groups)
    print(f'\nEX (%) theo nhãn — {args.db_id}, {len(questions)} câu (một câu có thể thuộc nhiều nhãn)')
    print(head)
    print(f"{'(số câu)':33}" + ''.join(f'{len(g[3]):>10}' for g in tag_groups))
    print('-' * len(head))
    for r in runs:
        cells = []
        for g in tag_groups:
            v = ex([r['correct'].get(q['question_id'], 0) for q in g[3]])
            cells.append(f"{'-' if v is None else f'{v:.1f}':>10}")
        print(f"{r['model']:18} {r['config']:14}" + ''.join(cells))

    empty = [g[2] for g in tag_groups if not g[3]]
    if empty:
        print(f'\nLưu ý: không có câu nào thuộc: {", ".join(empty)} -> cần tự tạo thêm dữ liệu cho các mức này.')
    print(f'\n-> {out}')


if __name__ == '__main__':
    main()
