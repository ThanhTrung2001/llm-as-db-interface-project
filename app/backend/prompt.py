"""
Dựng prompt Text-to-SQL đúng khuôn của BIRD (giống generate_combined_prompts_one() của script benchmark):

    prompt = build_schema_part()                   ← các câu CREATE TABLE của student_club, cách nhau "\\n\\n"
           + "\\n\\n"
           + build_question_part(question, evidence) ← "-- External Knowledge: <evidence>"  (nếu có)
                                                       "-- Using valid SQLite ... answer the following questions ..."
                                                       "-- <câu hỏi>"
           + CHAT_INSTRUCTION                        ← câu chặn cuối, dùng chung cho mọi model
"""
import sqlite3
from functools import lru_cache
from typing import Optional

from . import config

# Câu chặn cuối prompt, chép nguyên văn từ ollama_request.py / groq_request.py
CHAT_INSTRUCTION = '\nRespond with the final SQLite query only, inside a ```sql code block. Do not add any explanation.'


@lru_cache(maxsize=None)
def build_schema_part() -> str:
    """Lấy câu CREATE TABLE của mọi bảng trong student_club.sqlite (bỏ sqlite_sequence), nối bằng "\\n\\n".
    Giống generate_schema_prompt() của BIRD."""
    conn = sqlite3.connect(f'file:{config.SOURCE_DB}?mode=ro', uri=True)
    try:
        tables = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table'").fetchall()
    finally:
        conn.close()
    return '\n\n'.join(sql for name, sql in tables if name != 'sqlite_sequence')


def build_question_part(question: str, evidence: Optional[str] = None) -> str:
    """Phần comment chứa evidence (nếu có) và câu hỏi. Giống generate_comment_prompt() của BIRD."""
    if not evidence:
        return ('-- Using valid SQLite, answer the following questions for the tables provided above.\n'
                f'-- {question}')
    return (f'-- External Knowledge: {evidence}\n'
            '-- Using valid SQLite and understading External Knowledge, answer the following questions '
            f'for the tables provided above.\n-- {question}')


def build_prompt(question: str, evidence: Optional[str]) -> str:
    """Ghép prompt hoàn chỉnh: schema + "\\n\\n" + câu hỏi + câu chặn."""
    return build_schema_part() + '\n\n' + build_question_part(question, evidence) + CHAT_INSTRUCTION
