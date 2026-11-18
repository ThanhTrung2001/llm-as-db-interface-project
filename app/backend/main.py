"""
ClubQuery API.  Chạy:  venv/Scripts/python -m uvicorn app.backend.main:app --reload
Mở http://127.0.0.1:8000
"""
import csv
import io
import secrets
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import appdb, config, guard, service

@asynccontextmanager
async def lifespan(_app):
    appdb.init_db()
    yield


app = FastAPI(title='ClubQuery', description='Hỏi đáp dữ liệu CLB sinh viên bằng ngôn ngữ tự nhiên',
              lifespan=lifespan)
SESSIONS: dict = {}  # token -> user_id (đơn giản, đủ cho demo)


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
        raise HTTPException(401, 'Chưa đăng nhập')
    return dict(row)


def require(*roles):
    def dep(user=Depends(current_user)):
        if user['role'] not in roles:
            raise HTTPException(403, 'Bạn không có quyền thực hiện chức năng này')
        return user
    return dep


admin_only = require('admin')

# ---------- UC01 Đăng nhập ----------


class LoginIn(BaseModel):
    username: str
    password: str


@app.post('/api/login')
def login(body: LoginIn, conn=Depends(db)):
    row = conn.execute('SELECT * FROM user_account WHERE username = ?', (body.username,)).fetchone()
    if not row or not row['is_active'] or not appdb.verify_password(body.password, row['password_hash']):
        raise HTTPException(401, 'Sai tên đăng nhập hoặc mật khẩu')
    token = secrets.token_urlsafe(24)
    SESSIONS[token] = row['id']
    return {'token': token, 'user': {k: row[k] for k in ('id', 'username', 'full_name', 'role')}}


@app.post('/api/logout')
def logout(authorization: str = Header(default='')):
    SESSIONS.pop(authorization.removeprefix('Bearer ').strip(), None)
    return {'ok': True}


@app.get('/api/me')
def me(user=Depends(current_user)):
    return user

# ---------- UC02 Đặt câu hỏi ----------


class AskIn(BaseModel):
    question: Optional[str] = None
    mode: str = Field('live', pattern='^(live|replay)$')
    model_id: Optional[int] = None
    run_id: Optional[int] = None
    dev_question_id: Optional[int] = None
    use_evidence: bool = True
    evidence: Optional[str] = None


@app.post('/api/ask')
def ask(body: AskIn, user=Depends(current_user), conn=Depends(db)):
    if not body.question and body.dev_question_id is None:
        raise HTTPException(422, 'Hãy nhập câu hỏi hoặc chọn câu hỏi mẫu')
    try:
        return service.ask(conn, user, body.question or '', body.mode, body.model_id, body.run_id,
                           body.dev_question_id, body.use_evidence, body.evidence)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get('/api/dev-questions')
def dev_questions(user=Depends(current_user), conn=Depends(db)):
    return [dict(r) for r in conn.execute('SELECT id, question, evidence, difficulty FROM dev_question ORDER BY id')]


@app.get('/api/models')
def models(user=Depends(current_user), conn=Depends(db)):
    sql = 'SELECT * FROM model_config' + ('' if user['role'] == 'admin' else ' WHERE is_active = 1')
    return [dict(r) for r in conn.execute(sql + ' ORDER BY id')]

# ---------- UC03 Lịch sử, UC04 Đánh giá, UC05 Xuất CSV, UC10 Nhật ký ----------


LOG_SELECT = ('SELECT l.*, m.name AS model_name, u.username FROM query_log l '
              'LEFT JOIN model_config m ON m.id = l.model_id JOIN user_account u ON u.id = l.user_id ')


@app.get('/api/history')
def history(user=Depends(current_user), conn=Depends(db)):
    return [dict(r) for r in conn.execute(LOG_SELECT + 'WHERE l.user_id = ? ORDER BY l.id DESC LIMIT 100',
                                          (user['id'],))]


@app.get('/api/logs')
def logs(status: Optional[str] = None, user=Depends(admin_only), conn=Depends(db)):
    where, args = ('WHERE l.status = ? ', (status,)) if status else ('', ())
    rows = [dict(r) for r in conn.execute(LOG_SELECT + where + 'ORDER BY l.id DESC LIMIT 500', args)]
    stats = [dict(r) for r in conn.execute(
        'SELECT status, COUNT(*) AS n, ROUND(AVG(latency_ms)) AS avg_ms FROM query_log GROUP BY status')]
    return {'rows': rows, 'stats': stats}


class FeedbackIn(BaseModel):
    query_log_id: int
    rating: int = Field(..., ge=-1, le=1)
    comment: Optional[str] = None


@app.post('/api/feedback')
def feedback(body: FeedbackIn, user=Depends(current_user), conn=Depends(db)):
    if body.rating == 0:
        raise HTTPException(422, 'rating phải là 1 (đúng) hoặc -1 (sai)')
    log = conn.execute('SELECT user_id FROM query_log WHERE id = ?', (body.query_log_id,)).fetchone()
    if not log or log['user_id'] != user['id']:
        raise HTTPException(404, 'Không tìm thấy câu hỏi trong lịch sử của bạn')
    conn.execute('INSERT INTO feedback (query_log_id, user_id, rating, comment, created_at) VALUES (?,?,?,?,?) '
                 'ON CONFLICT (query_log_id, user_id) DO UPDATE SET rating = excluded.rating, '
                 'comment = excluded.comment, created_at = excluded.created_at',
                 (body.query_log_id, user['id'], body.rating, body.comment, appdb.now()))
    conn.commit()
    return {'ok': True}


@app.get('/api/export/{log_id}')
def export_csv(log_id: int, user=Depends(require('board', 'admin')), conn=Depends(db)):
    log = conn.execute('SELECT * FROM query_log WHERE id = ?', (log_id,)).fetchone()
    if not log or (log['user_id'] != user['id'] and user['role'] != 'admin') or log['status'] != 'EXECUTED':
        raise HTTPException(404, 'Không có kết quả để xuất')
    try:
        columns, rows = guard.execute(guard.check_select(log['generated_sql']), user['role'])
    except guard.QueryRejected as e:
        raise HTTPException(409, e.message)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(columns)
    w.writerows(rows)
    return StreamingResponse(iter(['﻿' + buf.getvalue()]), media_type='text/csv',
                             headers={'Content-Disposition': f'attachment; filename=clubquery_{log_id}.csv'})

# ---------- UC07 Cấu hình model ----------


class ModelIn(BaseModel):
    model_tag: str
    base_url: Optional[str] = None
    is_active: bool = True


@app.put('/api/models/{model_id}')
def update_model(model_id: int, body: ModelIn, user=Depends(admin_only), conn=Depends(db)):
    cur = conn.execute('UPDATE model_config SET model_tag = ?, base_url = ?, is_active = ? WHERE id = ?',
                       (body.model_tag, body.base_url or None, int(body.is_active), model_id))
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, 'Không có model này')
    return {'ok': True}

# ---------- UC08 Nhập benchmark, UC09 Dashboard ----------

CONFIG_ORDER = "CASE r.config WHEN 'no_evidence' THEN 0 WHEN 'evidence' THEN 1 ELSE 2 END"


@app.post('/api/benchmark/import')
def benchmark_import(body: dict, user=Depends(admin_only), conn=Depends(db)):
    if not isinstance(body.get('questions'), list) or not isinstance(body.get('runs'), list):
        raise HTTPException(422, 'File không đúng định dạng (cần "questions" và "runs")')
    try:
        n = appdb.import_benchmark(conn, body)
    except (KeyError, ValueError) as e:
        conn.rollback()
        raise HTTPException(422, f'File không hợp lệ: {e}')
    return {'runs': n}


@app.get('/api/benchmark/runs')
def benchmark_runs(user=Depends(current_user), conn=Depends(db)):
    return [dict(r) for r in conn.execute(
        'SELECT r.id, r.model_id, m.name AS model_name, r.config, r.note, r.ex, r.full_dev_ex '
        'FROM benchmark_run r JOIN model_config m ON m.id = r.model_id ORDER BY m.id, ' + CONFIG_ORDER)]


@app.get('/api/benchmark/summary')
def benchmark_summary(user=Depends(require('board', 'admin')), conn=Depends(db)):
    rows = conn.execute(
        'SELECT r.id, m.name AS model_name, r.config, r.note, r.ex, r.full_dev_ex, q.difficulty, '
        'ROUND(100.0 * AVG(b.is_correct), 2) AS ex_level, COUNT(*) AS n '
        'FROM benchmark_run r JOIN model_config m ON m.id = r.model_id '
        'JOIN benchmark_item b ON b.run_id = r.id JOIN dev_question q ON q.id = b.question_id '
        'GROUP BY r.id, q.difficulty ORDER BY m.id, ' + CONFIG_ORDER).fetchall()
    out = {}
    for r in rows:
        run = out.setdefault(r['id'], {k: r[k] for k in ('id', 'model_name', 'config', 'note', 'ex', 'full_dev_ex')}
                             | {'levels': {}})
        run['levels'][r['difficulty']] = {'ex': r['ex_level'], 'n': r['n']}
    return list(out.values())

# ---------- UC11 Tài khoản ----------


class UserIn(BaseModel):
    username: str = Field(..., min_length=3)
    full_name: str
    role: str = Field(..., pattern='^(member|board|admin)$')
    password: Optional[str] = None
    is_active: bool = True


@app.get('/api/users')
def users(user=Depends(admin_only), conn=Depends(db)):
    return [dict(r) for r in conn.execute('SELECT id, username, full_name, role, is_active FROM user_account')]


@app.post('/api/users')
def add_user(body: UserIn, user=Depends(admin_only), conn=Depends(db)):
    if not body.password or len(body.password) < 6:
        raise HTTPException(422, 'Mật khẩu tối thiểu 6 ký tự')
    try:
        new_id = conn.execute('INSERT INTO user_account (username, full_name, password_hash, role, is_active) '
                              'VALUES (?,?,?,?,?)', (body.username, body.full_name,
                                                     appdb.hash_password(body.password), body.role,
                                                     int(body.is_active))).lastrowid
    except Exception:
        raise HTTPException(409, 'Tên đăng nhập đã tồn tại')
    conn.commit()
    return {'id': new_id}


@app.put('/api/users/{user_id}')
def update_user(user_id: int, body: UserIn, user=Depends(admin_only), conn=Depends(db)):
    if user_id == user['id'] and (body.role != 'admin' or not body.is_active):
        raise HTTPException(422, 'Không thể tự hạ quyền hoặc khoá chính mình')
    conn.execute('UPDATE user_account SET full_name = ?, role = ?, is_active = ? WHERE id = ?',
                 (body.full_name, body.role, int(body.is_active), user_id))
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
