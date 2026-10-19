"""Dựng prompt theo đúng khuôn của BIRD (schema CREATE TABLE + comment), lọc theo vai trò."""
import re
from functools import lru_cache
from typing import Optional

from . import config
from .guard import connect_readonly


@lru_cache(maxsize=None)
def schema_prompt(role: str) -> str:
    """Schema chỉ gồm bảng/cột vai trò được xem (lớp thứ 2, bổ sung cho authorizer)."""
    r = config.restrictions(role)
    conn = connect_readonly()
    try:
        tables = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table'").fetchall()
    finally:
        conn.close()
    parts = []
    for name, sql in tables:
        if name == 'sqlite_sequence' or name in r['tables']:
            continue
        for table, column in r['columns']:
            if table == name:
                sql = re.sub(rf'^\s*{re.escape(column)}\s+\w+,?\s*\n', '', sql, flags=re.MULTILINE)
        parts.append(sql)
    return '\n\n'.join(parts)


def comment_prompt(question: str, knowledge: Optional[str] = None) -> str:
    # giống generate_comment_prompt() của BIRD
    if not knowledge:
        return ('-- Using valid SQLite, answer the following questions for the tables provided above.\n'
                f'-- {question}')
    return (f'-- External Knowledge: {knowledge}\n'
            '-- Using valid SQLite and understading External Knowledge, answer the following questions '
            f'for the tables provided above.\n-- {question}')


def build_prompt(question: str, knowledge: Optional[str], role: str) -> str:
    # giống ollama_request.generate_combined_prompts_one(): prompt tường minh cho model chat
    return (schema_prompt(role) + '\n\n' + comment_prompt(question, knowledge)
            + '\nRespond with the final SQLite query only, inside a ```sql code block. '
              'Do not add any explanation.')
