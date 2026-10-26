#!/usr/bin/env python3
"""
Phân loại câu SQL theo 6 mức truy vấn (khung trên lớp):

  1. Dễ — truy vấn 1 bảng
  2. Kết 2+ bảng (INNER JOIN, kể cả kết ngầm "FROM a, b")
  3. Phép tập hợp: UNION / INTERSECT / EXCEPT (MINUS)
  4. Kết ngoài: LEFT / RIGHT / FULL OUTER JOIN
  5. Gom nhóm: GROUP BY
  6. Phép chia (relational division): NOT EXISTS lồng NOT EXISTS,
     NOT EXISTS + EXCEPT, hoặc HAVING COUNT(...) = (SELECT COUNT ...)

Một câu SQL có thể mang nhiều nhãn (multi-label). "Mức chính" = nhãn có số lớn nhất.
Câu chỉ dùng nhiều bảng qua truy vấn lồng (WHERE x IN (SELECT ... FROM bảng_khác))
không có JOIN nên không thuộc mức 1–6; được gắn nhãn phụ NESTED và mức chính 0 ("khác").

Dùng như thư viện:
    from sql_category import classify
    classify("SELECT COUNT(*) FROM member GROUP BY position")
    # -> {'tags': ['SINGLE_TABLE', 'GROUP_BY'], 'level': 5, 'tables': ['member'], 'nested': False}

Dùng từ dòng lệnh (gán nhãn tập dev của BIRD, xuất CSV):
    python app/scripts/sql_category.py                      # chỉ student_club
    python app/scripts/sql_category.py --db_id all          # toàn bộ 1.534 câu dev
    python app/scripts/sql_category.py --sql "SELECT ..."   # thử 1 câu
"""
import argparse
import csv
import json
import os
import re
import sys
from collections import Counter

# Windows console (cp1258/cp1252) không in được tiếng Việt -> ép UTF-8
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ---- nhãn ----
SINGLE_TABLE, JOIN, SET_OP, OUTER_JOIN, GROUP_BY, DIVISION = (
    'SINGLE_TABLE', 'JOIN', 'SET_OP', 'OUTER_JOIN', 'GROUP_BY', 'DIVISION')
NESTED = 'NESTED'

LEVEL_OF = {SINGLE_TABLE: 1, JOIN: 2, SET_OP: 3, OUTER_JOIN: 4, GROUP_BY: 5, DIVISION: 6}
LEVEL_NAME = {
    0: 'Khác (nhiều bảng qua truy vấn lồng)',
    1: '1. Dễ - 1 bảng',
    2: '2. Kết bảng (inner join)',
    3: '3. Union / Intersect / Except',
    4: '4. Kết ngoài (outer join)',
    5: '5. Group by',
    6: '6. Phép chia',
}
TAG_ORDER = [SINGLE_TABLE, JOIN, SET_OP, OUTER_JOIN, GROUP_BY, DIVISION, NESTED]

# Từ khoá kết thúc mệnh đề FROM (để phát hiện kết ngầm "FROM a, b")
_FROM_END = {'WHERE', 'GROUP', 'ORDER', 'LIMIT', 'HAVING', 'UNION', 'INTERSECT', 'EXCEPT',
             'MINUS', 'JOIN', 'INNER', 'LEFT', 'RIGHT', 'FULL', 'CROSS', 'NATURAL', 'ON', 'USING',
             'WINDOW'}

_TOKEN_RE = re.compile(r"""
    '(?:[^']|'')*'            # chuỗi 'abc'
  | "(?:[^"]|"")*"            # định danh "abc"
  | `[^`]*`                   # định danh `abc`
  | \[[^\]]*\]                # định danh [abc]
  | [A-Za-z_][A-Za-z0-9_$]*   # từ
  | \d+(?:\.\d+)?             # số
  | <>|!=|<=|>=|\|\||\S       # toán tử / dấu câu
""", re.VERBOSE)


def _tokens(sql: str):
    """Tách token; chuỗi ký tự -> STR, định danh có ngoặc -> giữ tên (chữ thường)."""
    out = []
    for t in _TOKEN_RE.findall(sql):
        if t.startswith("'"):
            out.append(('STR', t))
        elif t[0] in '"`[':
            out.append(('ID', t[1:-1].lower()))
        elif re.match(r'[A-Za-z_]', t):
            out.append(('WORD', t))
        else:
            out.append(('SYM', t))
    return out


def _up(tok):
    return tok[1].upper() if tok[0] == 'WORD' else None


def classify(sql: str) -> dict:
    toks = _tokens(sql or '')
    n = len(toks)
    tags = set()
    tables = set()
    inner_join = outer_join = implicit_join = False
    not_exists = 0
    set_op = False
    nested = False

    for i, tok in enumerate(toks):
        w = _up(tok)
        if w is None:
            if tok == ('SYM', '(') and i + 1 < n and _up(toks[i + 1]) == 'SELECT':
                nested = True
            continue
        nxt = toks[i + 1] if i + 1 < n else None

        if w in ('UNION', 'INTERSECT', 'EXCEPT', 'MINUS'):
            set_op = True
        elif w == 'NOT' and nxt and _up(nxt) == 'EXISTS':
            not_exists += 1
        elif w == 'JOIN':
            # nhìn lùi bỏ qua OUTER để biết LEFT/RIGHT/FULL
            j = i - 1
            if j >= 0 and _up(toks[j]) == 'OUTER':
                j -= 1
            if j >= 0 and _up(toks[j]) in ('LEFT', 'RIGHT', 'FULL'):
                outer_join = True
            else:
                inner_join = True
            if nxt and nxt[0] in ('WORD', 'ID'):
                tables.add(nxt[1].lower())
        elif w == 'FROM':
            if nxt and nxt[0] in ('WORD', 'ID') and _up(nxt) != 'SELECT':
                tables.add(nxt[1].lower())
            # quét tiếp trong cùng mức ngoặc để tìm dấu phẩy => kết ngầm
            depth = 0
            for k in range(i + 1, n):
                t = toks[k]
                if t == ('SYM', '('):
                    depth += 1
                elif t == ('SYM', ')'):
                    if depth == 0:
                        break
                    depth -= 1
                elif depth == 0:
                    if t == ('SYM', ';') or _up(t) in _FROM_END:
                        break
                    if t == ('SYM', ','):
                        implicit_join = True
                        if k + 1 < n and toks[k + 1][0] in ('WORD', 'ID'):
                            tables.add(toks[k + 1][1].lower())

    upper = ' '.join(t[1].upper() if t[0] == 'WORD' else t[1] for t in toks if t[0] != 'STR')
    division = (
        not_exists >= 2
        or (not_exists >= 1 and set_op and 'EXCEPT' in upper)
        or re.search(r'HAVING COUNT \( [^)]*\) = \( SELECT COUNT', upper) is not None
    )

    if inner_join or implicit_join:
        tags.add(JOIN)
    if outer_join:
        tags.add(OUTER_JOIN)
    if set_op:
        tags.add(SET_OP)
    if re.search(r'\bGROUP BY\b', upper):
        tags.add(GROUP_BY)
    if division:
        tags.add(DIVISION)
    if nested:
        tags.add(NESTED)
    if not (inner_join or implicit_join or outer_join) and len(tables) == 1:
        tags.add(SINGLE_TABLE)

    levels = [LEVEL_OF[t] for t in tags if t in LEVEL_OF]
    level = max(levels) if levels else 0
    return {'tags': [t for t in TAG_ORDER if t in tags], 'level': level,
            'tables': sorted(tables), 'nested': nested}


# ---------------------------------------------------------------- CLI

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
BIRD = os.path.join(ROOT, 'src', 'DAMO-ConvAI', 'bird')
DEV_JSON = os.path.join(BIRD, 'data', 'dev.json')
GOLD_SQL = os.path.join(BIRD, 'llm', 'data', 'dev_gold.sql')


def load_dev_with_gold():
    dev = json.load(open(DEV_JSON, encoding='utf-8'))
    with open(GOLD_SQL, encoding='utf-8') as f:
        gold = [line.rstrip('\n').split('\t')[0] for line in f]
    for i, q in enumerate(dev):
        q['question_id'] = i
        q['gold_sql'] = gold[i]
    return dev


def label_dev(db_id: str):
    dev = load_dev_with_gold()
    if db_id != 'all':
        dev = [q for q in dev if q['db_id'] == db_id]
    rows = []
    for q in dev:
        c = classify(q['gold_sql'])
        rows.append({'question_id': q['question_id'], 'db_id': q['db_id'],
                     'difficulty': q['difficulty'], 'level': c['level'],
                     'level_name': LEVEL_NAME[c['level']], 'tags': '|'.join(c['tags']),
                     'n_tables': len(c['tables']), 'question': q['question'],
                     'gold_sql': q['gold_sql']})
    return rows


def print_summary(rows):
    print(f'\nTổng: {len(rows)} câu')
    print('\nTheo MỨC CHÍNH (mỗi câu đếm 1 lần):')
    lv = Counter(r['level'] for r in rows)
    for k in sorted(LEVEL_NAME):
        print(f'  {LEVEL_NAME[k]:40} {lv.get(k, 0):5}')
    print('\nTheo NHÃN (một câu có thể có nhiều nhãn):')
    tg = Counter(t for r in rows for t in r['tags'].split('|') if t)
    for t in TAG_ORDER:
        print(f'  {t:40} {tg.get(t, 0):5}')


def main():
    ap = argparse.ArgumentParser(description='Gán nhãn 6 mức truy vấn cho gold SQL của BIRD dev')
    ap.add_argument('--db_id', default='student_club', help="tên CSDL, hoặc 'all'")
    ap.add_argument('--sql', help='chỉ phân loại 1 câu SQL rồi thoát')
    ap.add_argument('--out', help='đường dẫn CSV (mặc định docs/pttk/data/sql_category_<db>.csv)')
    args = ap.parse_args()

    if args.sql:
        c = classify(args.sql)
        print(json.dumps({**c, 'level_name': LEVEL_NAME[c['level']]}, ensure_ascii=False, indent=2))
        return

    rows = label_dev(args.db_id)
    out = args.out or os.path.join(ROOT, 'docs', 'pttk', 'data', f'sql_category_{args.db_id}.csv')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', newline='', encoding='utf-8-sig') as f:   # utf-8-sig: Excel đọc đúng tiếng Việt
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print_summary(rows)
    print(f'\n-> {out}')


if __name__ == '__main__':
    main()
