"""Run: python src/test_evidence_norm.py  (no pytest needed)"""
from evidence_norm import has_pseudo_fn, normalize_pseudo_sql

CASES = [
    ("DIVIDE(COUNT(a), COUNT(b)) * 100",
     "CAST(COUNT(a) AS REAL) / COUNT(b) * 100"),
    ("SUBTRACT(DIVIDE(a, b), DIVIDE(c, d))",
     "(CAST(a AS REAL) / b) - (CAST(c AS REAL) / d)"),
    ("created after the year 2013 refers to year (CreationDate) > 2013",
     "created after the year 2013 refers to CAST(STRFTIME('%Y', CreationDate) AS INTEGER) > 2013"),
    ("Divide (Count(UserId where it's \"Teacher\"), Count(UserId)) * 100",
     "CAST(Count(UserId where it's \"Teacher\") AS REAL) / Count(UserId) * 100"),
    ("x = DIVIDE(SUM(name = 'a, b'), COUNT(id))",
     "x = CAST(SUM(name = 'a, b') AS REAL) / COUNT(id)"),
    # malformed evidence (';' instead of ',', unbalanced parens) is left untouched
    ("DIVIDE(SUM(element = 'pb'); COUNT(molecule_id))",
     "DIVIDE(SUM(element = 'pb'); COUNT(molecule_id))"),
    ("DIVIDE(COUNT(a)))*100, (COUNT(b))",
     "DIVIDE(COUNT(a)))*100, (COUNT(b))"),
    # a malformed outer call must not block a well-formed inner one
    ("MULTIPLY(DIVIDE(a, b))",
     "MULTIPLY(CAST(a AS REAL) / b)"),
    ("Male refers to gender = 'M'", "Male refers to gender = 'M'"),
    ("", ""),
    (None, None),
]

if __name__ == '__main__':
    failed = 0
    for src, want in CASES:
        got = normalize_pseudo_sql(src)
        if got != want:
            failed += 1
            print(f'FAIL\n  in:   {src}\n  want: {want}\n  got:  {got}')
    assert has_pseudo_fn('SELECT DIVIDE(a, b)') and not has_pseudo_fn('SELECT a / b')
    print(f'{len(CASES) - failed}/{len(CASES)} passed')
    raise SystemExit(1 if failed else 0)
