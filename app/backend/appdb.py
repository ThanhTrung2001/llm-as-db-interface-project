"""
Hai CSDL của ClubQuery:
  - app.sqlite  (main) : tài khoản, model, nhật ký truy vấn, đánh giá, từ điển, duyệt chi, nhật ký thay đổi.
  - club.sqlite (club) : dữ liệu nghiệp vụ CLB, chép từ student_club.sqlite của BIRD lần đầu chạy.
connect() ATTACH club.sqlite vào cùng kết nối để một thao tác nghiệp vụ (vd. duyệt chi: sửa expense,
cập nhật budget, ghi expense_review và audit_log) nằm trong MỘT giao dịch.
"""
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
from datetime import datetime

from . import config

SCHEMA_VERSION = 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_account (
    id            INTEGER PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    full_name     TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('president', 'treasurer', 'event', 'admin')),
    is_active     INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS model_config (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    provider    TEXT NOT NULL CHECK (provider IN ('groq', 'openrouter', 'ollama')),
    model_tag   TEXT NOT NULL,
    base_url    TEXT,
    api_key_env TEXT,
    is_active   INTEGER NOT NULL DEFAULT 1,
    is_default  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS glossary_term (
    id         INTEGER PRIMARY KEY,
    term       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    definition TEXT NOT NULL,
    is_active  INTEGER NOT NULL DEFAULT 1,
    updated_by INTEGER REFERENCES user_account(id),
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS query_log (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES user_account(id),
    question      TEXT NOT NULL,
    model_id      INTEGER REFERENCES model_config(id),
    sample_id     INTEGER REFERENCES sample_question(id),  -- câu mẫu BIRD được chọn (nếu có)
    evidence      TEXT,                      -- tri thức ngoài người dùng nhập / đi kèm câu mẫu
    glossary_used TEXT,                      -- thuật ngữ trong từ điển đã ghép vào prompt
    generated_sql TEXT,
    answer        TEXT,
    status        TEXT NOT NULL,
    error         TEXT,
    latency_ms    INTEGER NOT NULL,
    row_count     INTEGER,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sample_question (  -- 158 câu hỏi dev của BIRD trên student_club (kèm evidence)
    id         INTEGER PRIMARY KEY,          -- question_id trong dev.json
    question   TEXT NOT NULL,
    evidence   TEXT,
    difficulty TEXT NOT NULL CHECK (difficulty IN ('simple', 'moderate', 'challenging'))
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
CREATE TABLE IF NOT EXISTS expense_review (   -- quy trình duyệt chi cho khoản chi lập trên hệ thống
    expense_id  TEXT PRIMARY KEY,              -- = club.expense.expense_id
    proposed_by INTEGER NOT NULL REFERENCES user_account(id),
    proposed_at TEXT NOT NULL,
    reviewed_by INTEGER REFERENCES user_account(id),
    reviewed_at TEXT,
    note        TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES user_account(id),
    action      TEXT NOT NULL CHECK (action IN ('CREATE', 'UPDATE', 'DELETE', 'APPROVE', 'REJECT')),
    entity      TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    summary     TEXT NOT NULL,
    detail      TEXT,                          -- JSON trước/sau
    created_at  TEXT NOT NULL
);
"""

SEED_USERS = [
    ('chunhiem', 'Minh Anh Nguyen', 'chunhiem123', 'president'),
    ('thuquy', 'Thu Ha Tran', 'thuquy123', 'treasurer'),
    ('bansukien', 'Quoc Bao Le', 'bansukien123', 'event'),
    ('admin', 'System Administrator', 'admin123', 'admin'),
]
OLLAMA_V1 = 'http://localhost:11434/v1'
SEED_MODELS = [  # (tên, provider, model_tag, base_url, api_key_env, mặc định)
    ('Qwen2.5-Coder', 'ollama', 'qwen2.5-coder:7b', OLLAMA_V1, None, 1),
    ('DeepSeek-Coder-V2', 'ollama', 'deepseek-coder-v2:16b', OLLAMA_V1, None, 0),
    ('Gemma3', 'ollama', 'gemma3:12b', OLLAMA_V1, None, 0),
    ('GPT-OSS-20B (Groq)', 'groq', 'openai/gpt-oss-20b', 'https://api.groq.com/openai/v1', 'GROQ_API_KEY', 0),
]
# Tri thức nghiệp vụ của CLB — chính là "evidence" trong bài báo BIRD, do CLB tự duy trì.
SEED_GLOSSARY = [
    ('full name', 'first_name and last_name of member'),
    ('active member', "member.position <> 'Inactive'"),
    ('officer', "member.position NOT IN ('Member', 'Inactive')"),
    ('meeting', "event.type = 'Meeting'"),
    ('upcoming event', "event.status IN ('Planning', 'Open')"),
    ('dues', "income.source = 'Dues'"),
    ('approved expense', "expense.approved = 'true'"),
    ('pending expense', "expense.approved = 'pending'"),
    ('remaining budget', 'budget.remaining'),
    ('over budget', 'budget.remaining < 0'),
    ('attendance', 'attendance links member (link_to_member) and event (link_to_event)'),
]


def now() -> str:
    return datetime.now().isoformat(timespec='seconds')


def new_id() -> str:
    """Khoá chính dạng của dữ liệu gốc (Airtable): 'rec' + 14 ký tự."""
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    return 'rec' + ''.join(secrets.choice(alphabet) for _ in range(14))


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
    conn.execute('ATTACH DATABASE ? AS club', (config.CLUB_DB,))
    return conn


def audit(conn, user: dict, action: str, entity: str, entity_id: str, summary: str,
          before: dict = None, after: dict = None) -> None:
    """Ghi nhật ký thay đổi (BR10). Gọi trong cùng giao dịch với thao tác nghiệp vụ."""
    detail = json.dumps({'before': before, 'after': after}, ensure_ascii=False, default=str) \
        if (before or after) else None
    conn.execute('INSERT INTO audit_log (user_id, action, entity, entity_id, summary, detail, created_at) '
                 'VALUES (?,?,?,?,?,?,?)', (user['id'], action, entity, entity_id, summary, detail, now()))


def init_club_db(reset: bool = False) -> None:
    os.makedirs(os.path.dirname(config.CLUB_DB), exist_ok=True)
    if reset and os.path.exists(config.CLUB_DB):
        os.remove(config.CLUB_DB)
    if not os.path.exists(config.CLUB_DB):
        if not os.path.exists(config.SOURCE_DB):
            raise FileNotFoundError(f'Không thấy CSDL nguồn {config.SOURCE_DB} — xem README, Bước 3')
        shutil.copyfile(config.SOURCE_DB, config.CLUB_DB)


def load_sample_questions(conn) -> int:
    """Nạp các câu hỏi dev của BIRD thuộc student_club (kèm evidence) làm câu hỏi mẫu."""
    if not os.path.exists(config.DEV_JSON):
        return 0
    with open(config.DEV_JSON, encoding='utf-8') as f:
        rows = [(q['question_id'], q['question'], q['evidence'] or None, q['difficulty'])
                for q in json.load(f) if q['db_id'] == 'student_club']
    conn.executemany('INSERT OR REPLACE INTO sample_question (id, question, evidence, difficulty) VALUES (?,?,?,?)',
                     rows)
    return len(rows)


def init_db(reset: bool = False) -> None:
    os.makedirs(os.path.dirname(config.APP_DB), exist_ok=True)
    init_club_db(reset)
    if os.path.exists(config.APP_DB):
        c = sqlite3.connect(config.APP_DB)
        version = c.execute('PRAGMA user_version').fetchone()[0]
        c.close()
        if reset or version != SCHEMA_VERSION:  # app.sqlite của phiên bản cũ (có benchmark) → tạo lại
            os.remove(config.APP_DB)
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        conn.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
        if conn.execute('SELECT COUNT(*) FROM user_account').fetchone()[0] == 0:
            conn.executemany(
                'INSERT INTO user_account (username, full_name, password_hash, role) VALUES (?,?,?,?)',
                [(u, n, hash_password(p), r) for u, n, p, r in SEED_USERS])
            conn.executemany(
                'INSERT INTO model_config (name, provider, model_tag, base_url, api_key_env, is_default) '
                'VALUES (?,?,?,?,?,?)', SEED_MODELS)
            conn.executemany('INSERT INTO glossary_term (term, definition, updated_at) VALUES (?,?,?)',
                             [(t, d, now()) for t, d in SEED_GLOSSARY])
            load_sample_questions(conn)
            conn.commit()
    finally:
        conn.close()


if __name__ == '__main__':
    init_db(reset=True)
    print(f'Đã khởi tạo {config.APP_DB} và {config.CLUB_DB}')
