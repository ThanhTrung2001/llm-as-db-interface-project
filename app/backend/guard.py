"""
Lớp an toàn truy vấn: BR01 (chỉ 1 câu SELECT), BR02 (timeout, giới hạn dòng),
BR03 (phân quyền theo vai trò, chặn ở tầng engine bằng sqlite3 authorizer).
"""
import pathlib
import re
import sqlite3
import time

import sqlparse

from . import config

WRITE_KEYWORDS = {
    'INSERT', 'UPDATE', 'DELETE', 'REPLACE', 'UPSERT', 'CREATE', 'DROP', 'ALTER',
    'ATTACH', 'DETACH', 'PRAGMA', 'VACUUM', 'REINDEX', 'ANALYZE', 'BEGIN', 'COMMIT', 'ROLLBACK',
}
ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
                   sqlite3.SQLITE_RECURSIVE}


class QueryRejected(Exception):
    """status là một trạng thái kết thúc của QueryLog."""

    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def check_select(sql: str) -> str:
    """Trả về SQL đã làm sạch nếu là đúng một câu SELECT, ngược lại raise QueryRejected."""
    sql = (sql or '').strip()
    statements = [s for s in sqlparse.split(sql) if s.strip().strip(';').strip()]
    if not statements:
        raise QueryRejected('FAILED_GENERATION', 'The model did not produce a query.')
    if len(statements) > 1:
        raise QueryRejected('REJECTED_UNSAFE', 'Only a single statement is allowed.')
    stmt = statements[0].strip().rstrip(';').strip()
    words = re.findall(r'[A-Za-z_]+', sqlparse.format(stmt, strip_comments=True).upper())
    if not words:
        raise QueryRejected('FAILED_GENERATION', 'The model did not produce a query.')
    # "WITH ... DELETE" lọt qua đây sẽ bị authorizer chặn ở tầng engine
    if words[0] in WRITE_KEYWORDS:
        raise QueryRejected('REJECTED_UNSAFE', 'Only read queries (SELECT) are allowed.')
    if words[0] not in ('SELECT', 'WITH'):
        raise QueryRejected('FAILED_GENERATION', 'The model output is not a SELECT statement.')
    return stmt


def _authorizer(role: str, denied: list):
    r = config.restrictions(role)

    def auth(action, arg1, arg2, _db, _src):
        if action not in ALLOWED_ACTIONS:
            denied.append(('unsafe', action))
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_READ:
            if arg1 in r['tables']:
                denied.append(('permission', arg1))
                return sqlite3.SQLITE_DENY
            if (arg1, arg2) in r['columns']:
                denied.append(('permission', f'{arg1}.{arg2}'))
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    return auth


def connect_readonly(db_path: str = None) -> sqlite3.Connection:
    uri = pathlib.Path(db_path or config.CLUB_DB).resolve().as_uri() + '?mode=ro'
    return sqlite3.connect(uri, uri=True, check_same_thread=False)


def execute(sql: str, role: str, timeout_s: float = None, db_path: str = None):
    """Thực thi chỉ đọc theo quyền của role. Trả về (columns, rows) — rows đầy đủ."""
    timeout_s = timeout_s or config.QUERY_TIMEOUT_S
    denied = []
    conn = connect_readonly(db_path)
    try:
        conn.set_authorizer(_authorizer(role, denied))
        deadline = time.monotonic() + timeout_s
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
        try:
            cur = conn.execute(sql)
            rows = cur.fetchall()
        except sqlite3.DatabaseError as e:
            if denied:
                kind, what = denied[0]
                if kind == 'permission':
                    raise QueryRejected('REJECTED_PERMISSION',
                                        f'Your role is not allowed to access "{what}".')
                raise QueryRejected('REJECTED_UNSAFE', 'Only read queries (SELECT) are allowed.')
            if 'interrupted' in str(e):
                raise QueryRejected('TIMEOUT', f'Query exceeded {timeout_s:g} seconds.')
            raise QueryRejected('EXEC_ERROR', str(e))
        columns = [d[0] for d in cur.description or []]
        return columns, rows
    finally:
        conn.close()
