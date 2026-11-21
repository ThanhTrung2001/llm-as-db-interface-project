"""
ClubQuery API.  Chạy:  venv/Scripts/python -m uvicorn app.backend.main:app --reload
Mở http://127.0.0.1:8000

    POST /api/ask                 hỏi đáp Text-to-SQL → service.ask()
    GET  /api/dev-questions       158 câu hỏi mẫu student_club (ô "Câu hỏi mẫu")
    GET  /api/models              model đang bật (ô "Model")
    GET  /api/benchmark/summary   EX theo model × cấu hình × độ khó (tab Benchmark)
"""
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import appdb, config, service


@asynccontextmanager
async def lifespan(_app):
    appdb.init_db()  # tạo app.sqlite lần đầu: model, câu hỏi mẫu, kết quả benchmark
    yield


app = FastAPI(title='ClubQuery', description='Hỏi đáp dữ liệu CLB sinh viên bằng ngôn ngữ tự nhiên',
              lifespan=lifespan)


def db():
    conn = appdb.connect()
    try:
        yield conn
    finally:
        conn.close()


class AskIn(BaseModel):
    model_id: int                          # model trong model_config
    question: Optional[str] = None         # câu tự gõ (bỏ qua nếu chọn câu mẫu)
    dev_question_id: Optional[int] = None  # câu mẫu BIRD; None = câu tự gõ
    use_evidence: bool = True              # câu mẫu: có đưa evidence vào prompt không
    evidence: Optional[str] = None         # câu tự gõ: evidence tự nhập (tuỳ chọn)


@app.post('/api/ask')
def ask(body: AskIn, conn=Depends(db)):
    if not body.question and body.dev_question_id is None:
        raise HTTPException(422, 'Hãy nhập câu hỏi hoặc chọn câu hỏi mẫu')
    try:
        return service.ask(conn, body.question or '', body.model_id, body.dev_question_id,
                           body.use_evidence, body.evidence)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get('/api/dev-questions')
def dev_questions(conn=Depends(db)):
    return [dict(r) for r in conn.execute('SELECT id, question, evidence, difficulty FROM dev_question ORDER BY id')]


@app.get('/api/models')
def models(conn=Depends(db)):
    return [dict(r) for r in conn.execute('SELECT * FROM model_config WHERE is_active = 1 ORDER BY id')]


CONFIG_ORDER = "CASE r.config WHEN 'no_evidence' THEN 0 WHEN 'evidence' THEN 1 ELSE 2 END"


@app.get('/api/benchmark/summary')
def benchmark_summary(conn=Depends(db)):
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


@app.get('/')
def index():
    return FileResponse(f'{config.FRONTEND_DIR}/index.html')


app.mount('/static', StaticFiles(directory=config.FRONTEND_DIR), name='static')
