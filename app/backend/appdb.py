"""CSDL của ứng dụng (app.sqlite) — tách khỏi CSDL nguồn student_club (chỉ đọc)."""
import hashlib
import json
import os
import secrets
import sqlite3
from datetime import datetime

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_account (
    id            INTEGER PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    full_name     TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('member', 'board', 'admin')),
    is_active     INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS model_config (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    provider    TEXT NOT NULL CHECK (provider IN ('openai', 'groq', 'openrouter', 'ollama')),
    model_tag   TEXT NOT NULL,
    base_url    TEXT,
    api_key_env TEXT,
    is_active   INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS dev_question (
    id         INTEGER PRIMARY KEY,          -- chỉ số câu hỏi trong dev.json
    question   TEXT NOT NULL,
    evidence   TEXT,
    gold_sql   TEXT NOT NULL,
    difficulty TEXT NOT NULL CHECK (difficulty IN ('simple', 'moderate', 'challenging'))
);
CREATE TABLE IF NOT EXISTS benchmark_run (
    id          INTEGER PRIMARY KEY,
    model_id    INTEGER NOT NULL REFERENCES model_config(id),
    config      TEXT NOT NULL CHECK (config IN ('no_evidence', 'evidence', 'evidence_norm')),
    source      TEXT NOT NULL,
    note        TEXT,
    ex          REAL NOT NULL,               -- EX trên student_club
    full_dev_ex REAL,                        -- EX toàn dev (1534 câu) nếu có
    imported_at TEXT NOT NULL,
    UNIQUE (model_id, config)
);
CREATE TABLE IF NOT EXISTS benchmark_item (
    run_id        INTEGER NOT NULL REFERENCES benchmark_run(id) ON DELETE CASCADE,
    question_id   INTEGER NOT NULL REFERENCES dev_question(id),
    predicted_sql TEXT NOT NULL,
    is_correct    INTEGER NOT NULL,
    PRIMARY KEY (run_id, question_id)
);
CREATE TABLE IF NOT EXISTS query_log (
    id              INTEGER PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES user_account(id),
    question        TEXT NOT NULL,
    mode            TEXT NOT NULL CHECK (mode IN ('live', 'replay')),
    model_id        INTEGER REFERENCES model_config(id),
    run_id          INTEGER REFERENCES benchmark_run(id),
    dev_question_id INTEGER REFERENCES dev_question(id),
    evidence_used   TEXT,
    generated_sql   TEXT,
    answer          TEXT,                    -- câu trả lời đã diễn giải (UC02f)
    status          TEXT NOT NULL,
    error           TEXT,
    latency_ms      INTEGER NOT NULL,
    row_count       INTEGER,
    is_correct      INTEGER,
    created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
    id           INTEGER PRIMARY KEY,
    query_log_id INTEGER NOT NULL REFERENCES query_log(id),
    user_id      INTEGER NOT NULL REFERENCES user_account(id),
    rating       INTEGER NOT NULL CHECK (rating IN (-1, 1)),
    comment      TEXT,
    created_at   TEXT NOT NULL,
    UNIQUE (query_log_id, user_id)
);
"""

SEED_USERS = [
    ('admin', 'Quản trị viên', 'admin123', 'admin'),
    ('thuquy', 'Thủ quỹ CLB', 'thuquy123', 'board'),
    ('thanhvien', 'Thành viên CLB', 'thanhvien123', 'member'),
]
OLLAMA_V1 = 'http://localhost:11434/v1'
SEED_MODELS = [
    ('GPT-3.5-Turbo', 'openai', 'gpt-3.5-turbo', None, 'OPEN_AI_KEY'),
    ('DeepSeek-Coder-V2', 'ollama', 'deepseek-coder-v2:16b', OLLAMA_V1, None),
    ('Gemma3', 'ollama', 'gemma3:12b', OLLAMA_V1, None),
    ('Qwen2.5-Coder', 'ollama', 'qwen2.5-coder:7b', OLLAMA_V1, None),
    ('GPT-OSS-20B (Groq)', 'groq', 'openai/gpt-oss-20b', 'https://api.groq.com/openai/v1', 'GROQ_API_KEY'),
]
# EX toàn dev đã đo (PROJECT_LOG.md mục 8, 8.1). Bỏ trống khi chưa có số chốt.
FULL_DEV_EX = {
    ('GPT-3.5-Turbo', 'no_evidence'): 31.23,
    ('GPT-3.5-Turbo', 'evidence'): 47.78,
    ('GPT-3.5-Turbo', 'evidence_norm'): 48.11,
    ('DeepSeek-Coder-V2', 'evidence_norm'): 43.22,
    ('Gemma3', 'evidence_norm'): 49.54,
    ('Qwen2.5-Coder', 'evidence'): 53.85,
    ('Qwen2.5-Coder', 'evidence_norm'): 54.17,
}


def now() -> str:
    return datetime.now().isoformat(timespec='seconds')


def hash_password(password: str, salt: str = None) -> str:
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100_000).hex()
    return f'{salt}${digest}'


def verify_password(password: str, stored: str) -> bool:
    salt = stored.split('$', 1)[0]
    return secrets.compare_digest(hash_password(password, salt), stored)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.APP_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def import_benchmark(conn: sqlite3.Connection, data: dict) -> int:
    """UC08: nạp file benchmark (định dạng của app/scripts/per_db_ex.py). Trả về số lượt chạy."""
    conn.executemany(
        'INSERT OR REPLACE INTO dev_question (id, question, evidence, gold_sql, difficulty) VALUES (?,?,?,?,?)',
        [(q['question_id'], q['question'], q['evidence'], q['gold_sql'], q['difficulty'])
         for q in data['questions']])
    for run in data['runs']:
        model = conn.execute('SELECT id FROM model_config WHERE name = ?', (run['model'],)).fetchone()
        if model is None:
            raise ValueError(f'Model "{run["model"]}" chưa có trong cấu hình model')
        conn.execute('DELETE FROM benchmark_run WHERE model_id = ? AND config = ?', (model['id'], run['config']))
        run_id = conn.execute(
            'INSERT INTO benchmark_run (model_id, config, source, note, ex, full_dev_ex, imported_at) '
            'VALUES (?,?,?,?,?,?,?)',
            (model['id'], run['config'], run['source'], run.get('note'), run['total'],
             run.get('full_dev_ex', FULL_DEV_EX.get((run['model'], run['config']))), now())).lastrowid
        conn.executemany(
            'INSERT INTO benchmark_item (run_id, question_id, predicted_sql, is_correct) VALUES (?,?,?,?)',
            [(run_id, it['question_id'], it['predicted_sql'], it['is_correct']) for it in run['items']])
    conn.commit()
    return len(data['runs'])


def init_db(reset: bool = False) -> None:
    os.makedirs(os.path.dirname(config.APP_DB), exist_ok=True)
    if reset and os.path.exists(config.APP_DB):
        os.remove(config.APP_DB)
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        # nâng cấp app.sqlite tạo trước khi có cột answer
        if 'answer' not in [c[1] for c in conn.execute('PRAGMA table_info(query_log)')]:
            conn.execute('ALTER TABLE query_log ADD COLUMN answer TEXT')
        if conn.execute('SELECT COUNT(*) FROM user_account').fetchone()[0] == 0:
            conn.executemany(
                'INSERT INTO user_account (username, full_name, password_hash, role) VALUES (?,?,?,?)',
                [(u, n, hash_password(p), r) for u, n, p, r in SEED_USERS])
            conn.executemany(
                'INSERT INTO model_config (name, provider, model_tag, base_url, api_key_env) VALUES (?,?,?,?,?)',
                SEED_MODELS)
            conn.commit()
            if os.path.exists(config.BENCHMARK_JSON):
                with open(config.BENCHMARK_JSON, encoding='utf-8') as f:
                    import_benchmark(conn, json.load(f))
    finally:
        conn.close()


if __name__ == '__main__':
    init_db(reset=True)
    print(f'Đã khởi tạo {config.APP_DB}')
