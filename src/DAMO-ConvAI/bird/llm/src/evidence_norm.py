"""
Gap 3 — normalize BIRD's pseudo-SQL evidence into valid SQLite.

BIRD's human-written evidence uses functions SQLite doesn't have (DIVIDE, SUBTRACT, MULTIPLY,
YEAR, ...). Models often copy them verbatim into the predicted SQL, which then fails with
"no such function". normalize_pseudo_sql() rewrites the evidence into SQLite before it goes
into the prompt (--normalize_evidence in openai_request2.py / ollama_request2.py).
"""
import re
from typing import List, Optional

PSEUDO_FN_RE = re.compile(r'\b(DIVIDE|SUBTRACT|MULTIPLY|ADD|YEAR|MONTH|DAY)\s*\(', re.IGNORECASE)


def _split_args(s: str) -> List[str]:
    """Split 'a, b' on top-level commas only (ignores commas inside (...) and string literals)."""
    args, depth, quote, cur = [], 0, None, ''
    for k, ch in enumerate(s):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"`" and (k == 0 or not s[k - 1].isalnum()):  # skip apostrophes like it's
            quote = ch
        elif ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif ch == ',' and depth == 0:
            args.append(cur.strip())
            cur = ''
            continue
        cur += ch
    args.append(cur.strip())
    return args


def _rewrite(fn: str, args: List[str]) -> Optional[str]:
    fn = fn.upper()
    if fn == 'DIVIDE' and len(args) == 2:
        return f'CAST({args[0]} AS REAL) / {args[1]}'
    if fn == 'SUBTRACT' and len(args) == 2:
        return f'({args[0]}) - ({args[1]})'
    if fn == 'MULTIPLY' and len(args) == 2:
        return f'({args[0]}) * ({args[1]})'
    if fn == 'ADD' and len(args) == 2:
        return f'({args[0]}) + ({args[1]})'
    if fn in ('YEAR', 'MONTH', 'DAY') and len(args) == 1:
        fmt = {'YEAR': '%Y', 'MONTH': '%m', 'DAY': '%d'}[fn]
        return f"CAST(STRFTIME('{fmt}', {args[0]}) AS INTEGER)"
    return None  # malformed / unexpected arity -> leave untouched


def normalize_pseudo_sql(text: Optional[str]) -> Optional[str]:
    """Rewrite pseudo-functions innermost-first, so SUBTRACT(DIVIDE(a, b), DIVIDE(c, d)) works.
    Calls that can't be parsed (unbalanced parens, wrong arity) are left as they are."""
    if not text:
        return text
    skip = set()  # start offsets of calls we failed to rewrite
    for _ in range(50):
        target = None
        for m in PSEUDO_FN_RE.finditer(text):
            if m.start() in skip:
                continue
            depth, j = 1, m.end()
            while j < len(text) and depth:
                depth += {'(': 1, ')': -1}.get(text[j], 0)
                j += 1
            if depth != 0:
                skip.add(m.start())
                continue
            inner = text[m.end():j - 1]
            if any(m.end() + n.start() not in skip for n in PSEUDO_FN_RE.finditer(inner)):
                continue  # has a rewritable call nested inside: do that one first
            target = (m, j, inner)
            break
        if target is None:
            break
        m, j, inner = target
        new = _rewrite(m.group(1), _split_args(inner))
        if new is None:
            skip.add(m.start())
            continue
        text = text[:m.start()] + new + text[j:]
        skip = {s for s in skip if s < m.start()}  # offsets after the edit have shifted
    return text


def has_pseudo_fn(text: Optional[str]) -> bool:
    return bool(text) and bool(PSEUDO_FN_RE.search(text))
