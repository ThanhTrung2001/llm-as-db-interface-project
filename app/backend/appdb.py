"""
CSDL của ứng dụng (app/data/app.sqlite) — tách khỏi CSDL nguồn student_club (chỉ đọc). Gồm 2 bảng:
  model_config : các model chọn được ở ô "Model"
  dev_question : 158 câu hỏi mẫu student_club của BIRD dev (câu hỏi, evidence, SQL đáp án) — ô "Câu hỏi mẫu"
"""
import json
import os
import sqlite3

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS model_config (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    provider    TEXT NOT NULL CHECK (provider IN ('openai', 'groq', 'ollama')),
    model_tag   TEXT NOT NULL,           -- tên model gửi trong request, ví dụ qwen2.5-coder:7b
    base_url    TEXT,                    -- địa chỉ API tương thích OpenAI; NULL = api.openai.com
    api_key_env TEXT,                    -- tên biến môi trường (.env) chứa khoá API; NULL = không cần khoá
    is_active   INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS dev_question (
    id         INTEGER PRIMARY KEY,      -- question_id trong dev.json (1312–1469)
    question   TEXT NOT NULL,
    evidence   TEXT,                     -- External Knowledge của BIRD
    gold_sql   TEXT NOT NULL,            -- SQL đáp án
    difficulty TEXT NOT NULL CHECK (difficulty IN ('simple', 'moderate', 'challenging'))
);
"""

OLLAMA_V1 = 'http://localhost:11434/v1'
SEED_MODELS = [
    # (name, provider, model_tag, base_url, api_key_env)
    ('GPT-3.5-Turbo', 'openai', 'gpt-3.5-turbo', None, 'OPEN_AI_KEY'),
    ('DeepSeek-Coder-V2', 'ollama', 'deepseek-coder-v2:16b', OLLAMA_V1, None),
    ('Gemma3', 'ollama', 'gemma3:12b', OLLAMA_V1, None),
    ('Qwen2.5-Coder', 'ollama', 'qwen2.5-coder:7b', OLLAMA_V1, None),
    ('GPT-OSS-20B (Groq)', 'groq', 'openai/gpt-oss-20b', 'https://api.groq.com/openai/v1', 'GROQ_API_KEY'),
]


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.APP_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def load_student_club_questions() -> list:
    """Đọc dev.json của BIRD, giữ các câu có db_id = 'student_club'. Trả về list các tuple để INSERT."""
    with open(config.DEV_JSON, encoding='utf-8') as f:
        dev = json.load(f)
    return [(q['question_id'], q['question'], q['evidence'], q['SQL'], q['difficulty'])
            for q in dev if q['db_id'] == 'student_club']


def init_db(reset: bool = False) -> None:
    """Tạo app.sqlite nếu chưa có: tạo 2 bảng, thêm danh sách model, nạp 158 câu hỏi mẫu."""
    os.makedirs(os.path.dirname(config.APP_DB), exist_ok=True)
    if reset and os.path.exists(config.APP_DB):
        os.remove(config.APP_DB)

    conn = connect()
    try:
        conn.executescript(SCHEMA)
        if conn.execute('SELECT COUNT(*) FROM model_config').fetchone()[0] == 0:
            conn.executemany('INSERT INTO model_config (name, provider, model_tag, base_url, api_key_env) '
                             'VALUES (?,?,?,?,?)', SEED_MODELS)
        if conn.execute('SELECT COUNT(*) FROM dev_question').fetchone()[0] == 0:
            conn.executemany('INSERT INTO dev_question (id, question, evidence, gold_sql, difficulty) '
                             'VALUES (?,?,?,?,?)', load_student_club_questions())
        conn.commit()
    finally:
        conn.close()


if __name__ == '__main__':
    init_db(reset=True)
    print(f'Đã khởi tạo {config.APP_DB}')
