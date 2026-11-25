"""
ClubQuery API.  Chạy:  venv/Scripts/python -m uvicorn app.backend.main:app --reload
Mở http://127.0.0.1:8000
"""
import csv
import io
import secrets
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import appdb, club_api, config, guard, service
from .deps import SESSIONS, current_user, db, need, rows


@asynccontextmanager
async def lifespan(_app):
    appdb.init_db()
    yield


app = FastAPI(title='ClubQuery', description='Student club management with natural-language questions over club data',
              lifespan=lifespan)
app.include_router(club_api.router)
admin_only = need('system.admin')


@app.exception_handler(RequestValidationError)
async def validation_error(_req: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = '.'.join(str(x) for x in first.get('loc', [])[1:]) or 'input'
    return JSONResponse(status_code=422, content={'detail': f'Invalid field "{field}": {first.get("msg", "")}'})

# ---------- UC01 Đăng nhập, đổi mật khẩu ----------


class LoginIn(BaseModel):
    username: str
    password: str


def _me(user: dict) -> dict:
    return {k: user[k] for k in ('id', 'username', 'full_name', 'role')} | {
        'role_name': config.ROLE_NAME.get(user['role'], user['role']),
        'permissions': sorted(config.PERMISSIONS.get(user['role'], set())),
    }


@app.post('/api/login')
def login(body: LoginIn, conn=Depends(db)):
    row = conn.execute('SELECT * FROM user_account WHERE username = ?', (body.username.strip(),)).fetchone()
    if not row or not row['is_active'] or not appdb.verify_password(body.password, row['password_hash']):
        raise HTTPException(401, 'Incorrect username or password')
    token = secrets.token_urlsafe(24)
    SESSIONS[token] = row['id']
    return {'token': token, 'user': _me(dict(row))}


@app.post('/api/logout')
def logout(authorization: str = Header(default='')):
    SESSIONS.pop(authorization.removeprefix('Bearer ').strip(), None)
    return {'ok': True}


@app.get('/api/me')
def me(user=Depends(current_user)):
    return _me(user)


class PasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6)


@app.post('/api/me/password')
def change_password(body: PasswordIn, user=Depends(current_user), conn=Depends(db)):
    stored = conn.execute('SELECT password_hash FROM user_account WHERE id = ?', (user['id'],)).fetchone()[0]
    if not appdb.verify_password(body.old_password, stored):
        raise HTTPException(422, 'Current password is incorrect')
    conn.execute('UPDATE user_account SET password_hash = ? WHERE id = ?',
                 (appdb.hash_password(body.new_password), user['id']))
    conn.commit()
    return {'ok': True}


@app.get('/api/roles')
def roles(user=Depends(current_user)):
    """Ma trận phân quyền (hiển thị cho người dùng biết mình được làm gì)."""
    return {'roles': config.ROLE_NAME, 'permissions': config.PERMISSION_NAME,
            'matrix': {r: sorted(p) for r, p in config.PERMISSIONS.items()}}

# ---------- UC02 Hỏi đáp ----------


class AskIn(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)
    model_id: Optional[int] = None
    evidence: Optional[str] = Field(None, max_length=2000)  # tri thức ngoài → dòng External Knowledge của prompt
    sample_id: Optional[int] = None                          # câu mẫu BIRD được chọn (để ghi log)


@app.post('/api/ask')
def ask(body: AskIn, user=Depends(current_user), conn=Depends(db)):
    try:
        return service.ask(conn, user, body.question, body.model_id, body.evidence, body.sample_id)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get('/api/sample-questions')
def sample_questions(user=Depends(current_user), conn=Depends(db)):
    """158 câu hỏi dev của BIRD trên student_club, kèm evidence (tri thức ngoài)."""
    return rows(conn, 'SELECT id, question, evidence, difficulty FROM sample_question ORDER BY id')


@app.get('/api/models')
def models(user=Depends(current_user), conn=Depends(db)):
    if config.can(user['role'], 'system.admin'):
        return rows(conn, 'SELECT * FROM model_config ORDER BY is_default DESC, id')
    return rows(conn, 'SELECT id, name, provider, is_default FROM model_config WHERE is_active = 1 '
                      'ORDER BY is_default DESC, id')

# ---------- UC03 Lịch sử, UC04 Đánh giá, UC05 Xuất CSV, UC19 Nhật ký truy vấn ----------


LOG_SELECT = ('SELECT l.*, m.name AS model_name, u.username, u.full_name, f.rating FROM query_log l '
              'LEFT JOIN model_config m ON m.id = l.model_id JOIN user_account u ON u.id = l.user_id '
              'LEFT JOIN feedback f ON f.query_log_id = l.id AND f.user_id = l.user_id ')


@app.get('/api/history')
def history(user=Depends(current_user), conn=Depends(db)):
    return rows(conn, LOG_SELECT + 'WHERE l.user_id = ? ORDER BY l.id DESC LIMIT 200', (user['id'],))


@app.get('/api/logs')
def logs(status: Optional[str] = None, user=Depends(admin_only), conn=Depends(db)):
    where, args = ('WHERE l.status = ? ', (status,)) if status else ('', ())
    return {
        'rows': rows(conn, LOG_SELECT + where + 'ORDER BY l.id DESC LIMIT 500', args),
        'stats': rows(conn, 'SELECT status, COUNT(*) AS n, ROUND(AVG(latency_ms)) AS avg_ms FROM query_log '
                            'GROUP BY status ORDER BY n DESC'),
        'feedback': rows(conn, 'SELECT rating, COUNT(*) AS n FROM feedback GROUP BY rating'),
    }


class FeedbackIn(BaseModel):
    query_log_id: int
    rating: int = Field(..., ge=-1, le=1)
    comment: Optional[str] = None


@app.post('/api/feedback')
def feedback(body: FeedbackIn, user=Depends(current_user), conn=Depends(db)):
    if body.rating == 0:
        raise HTTPException(422, 'rating must be 1 (correct) or -1 (wrong)')
    log = conn.execute('SELECT user_id FROM query_log WHERE id = ?', (body.query_log_id,)).fetchone()
    if not log or log['user_id'] != user['id']:
        raise HTTPException(404, 'Question not found in your history')
    conn.execute('INSERT INTO feedback (query_log_id, user_id, rating, comment, created_at) VALUES (?,?,?,?,?) '
                 'ON CONFLICT (query_log_id, user_id) DO UPDATE SET rating = excluded.rating, '
                 'comment = excluded.comment, created_at = excluded.created_at',
                 (body.query_log_id, user['id'], body.rating, body.comment, appdb.now()))
    conn.commit()
    return {'ok': True}


@app.get('/api/export/{log_id}')
def export_csv(log_id: int, user=Depends(current_user), conn=Depends(db)):
    log = conn.execute('SELECT * FROM query_log WHERE id = ?', (log_id,)).fetchone()
    if not log or log['user_id'] != user['id'] or log['status'] != 'EXECUTED':
        raise HTTPException(404, 'No result to export')
    try:  # chạy lại với quyền hiện tại của người dùng (quyền có thể đã bị thu hồi)
        columns, data = guard.execute(guard.check_select(log['generated_sql']), user['role'])
    except guard.QueryRejected as e:
        raise HTTPException(409, e.message)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(columns)
    w.writerows(data)
    return StreamingResponse(iter(['﻿' + buf.getvalue()]), media_type='text/csv',
                             headers={'Content-Disposition': f'attachment; filename=clubquery_{log_id}.csv'})

# ---------- UC17 Cấu hình model ----------


class ModelIn(BaseModel):
    model_tag: str = Field(..., min_length=1)
    base_url: Optional[str] = None
    is_active: bool = True
    is_default: bool = False


@app.put('/api/models/{model_id}')
def update_model(model_id: int, body: ModelIn, user=Depends(admin_only), conn=Depends(db)):
    if body.is_default and not body.is_active:
        raise HTTPException(422, 'The default model must be enabled')
    if body.is_default:
        conn.execute('UPDATE model_config SET is_default = 0')
    cur = conn.execute('UPDATE model_config SET model_tag = ?, base_url = ?, is_active = ?, is_default = ? '
                       'WHERE id = ?', (body.model_tag.strip(), (body.base_url or '').strip() or None,
                                        int(body.is_active), int(body.is_default), model_id))
    if cur.rowcount == 0:
        raise HTTPException(404, 'Model not found')
    conn.commit()
    return {'ok': True}

# ---------- UC18 Tài khoản ----------


class UserIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=40, pattern=r'^[a-zA-Z0-9_.]+$')
    full_name: str = Field(..., min_length=2)
    role: str
    password: Optional[str] = None
    is_active: bool = True


@app.get('/api/users')
def users(user=Depends(admin_only), conn=Depends(db)):
    return rows(conn, 'SELECT id, username, full_name, role, is_active FROM user_account ORDER BY id')


def _check_role(role: str):
    if role not in config.ROLES:
        raise HTTPException(422, 'Invalid role')


@app.post('/api/users')
def add_user(body: UserIn, user=Depends(admin_only), conn=Depends(db)):
    _check_role(body.role)
    if not body.password or len(body.password) < 6:
        raise HTTPException(422, 'Password must be at least 6 characters')
    if conn.execute('SELECT 1 FROM user_account WHERE username = ?', (body.username,)).fetchone():
        raise HTTPException(409, 'Username already exists')
    new_id = conn.execute('INSERT INTO user_account (username, full_name, password_hash, role, is_active) '
                          'VALUES (?,?,?,?,?)', (body.username, body.full_name.strip(),
                                                 appdb.hash_password(body.password), body.role,
                                                 int(body.is_active))).lastrowid
    conn.commit()
    return {'id': new_id}


@app.put('/api/users/{user_id}')
def update_user(user_id: int, body: UserIn, user=Depends(admin_only), conn=Depends(db)):
    _check_role(body.role)
    if user_id == user['id'] and (body.role != 'admin' or not body.is_active):
        raise HTTPException(422, 'You cannot demote or deactivate yourself')
    if body.password and len(body.password) < 6:
        raise HTTPException(422, 'Password must be at least 6 characters')
    cur = conn.execute('UPDATE user_account SET full_name = ?, role = ?, is_active = ? WHERE id = ?',
                       (body.full_name.strip(), body.role, int(body.is_active), user_id))
    if cur.rowcount == 0:
        raise HTTPException(404, 'Account not found')
    if body.password:
        conn.execute('UPDATE user_account SET password_hash = ? WHERE id = ?',
                     (appdb.hash_password(body.password), user_id))
    conn.commit()
    return {'ok': True}

# ---------- Giao diện ----------


@app.get('/')
def index():
    return FileResponse(f'{config.FRONTEND_DIR}/index.html')


app.mount('/static', StaticFiles(directory=config.FRONTEND_DIR), name='static')
