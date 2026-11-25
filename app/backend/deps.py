"""Phụ thuộc dùng chung cho các API: kết nối CSDL, người dùng hiện tại, kiểm tra quyền (BR05)."""
from fastapi import Depends, Header, HTTPException

from . import appdb, config

SESSIONS: dict = {}  # token -> user_id (lưu trong bộ nhớ, đủ cho phạm vi đồ án)


def db():
    conn = appdb.connect()
    try:
        yield conn
    finally:
        conn.close()


def current_user(authorization: str = Header(default=''), conn=Depends(db)) -> dict:
    token = authorization.removeprefix('Bearer ').strip()
    user_id = SESSIONS.get(token)
    row = user_id and conn.execute('SELECT id, username, full_name, role, is_active FROM user_account '
                                   'WHERE id = ?', (user_id,)).fetchone()
    if not row or not row['is_active']:
        raise HTTPException(401, 'Not logged in')
    return dict(row)


def need(*perms):
    """Cho qua nếu vai trò có ít nhất một trong các quyền."""
    def dep(user=Depends(current_user)):
        if not any(config.can(user['role'], p) for p in perms):
            raise HTTPException(403, 'You do not have permission to perform this action')
        return user
    return dep


def rows(conn, sql: str, args=()) -> list:
    return [dict(r) for r in conn.execute(sql, args)]


def one(conn, sql: str, args=()):
    r = conn.execute(sql, args).fetchone()
    return dict(r) if r else None
