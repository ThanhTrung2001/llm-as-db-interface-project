"""Dựng prompt theo đúng khuôn của BIRD (schema CREATE TABLE + comment), lọc theo vai trò."""
import re
from functools import lru_cache
from typing import Optional

from . import config, trace
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


# Câu kết thúc prompt, đúng như lúc benchmark từng provider:
#  - openai  : openai_request.generate_combined_prompts_one()  (giữ câu nhắc của gpt_request.py gốc)
#  - còn lại : ollama_request / groq_request.generate_combined_prompts_one()
OPENAI_TAIL = '\nGenerate the SQL after thinking step by step: ' + '\nSELECT '
CHAT_TAIL = '\nRespond with the final SQLite query only, inside a ```sql code block. Do not add any explanation.'


def prompt_tail(provider: str) -> str:
    return OPENAI_TAIL if provider == 'openai' else CHAT_TAIL


def build_prompt(question: str, knowledge: Optional[str], role: str, provider: str = 'ollama') -> str:
    r = config.restrictions(role)
    schema = schema_prompt(role)
    trace.step(
        '2b.4a', 'prompt.schema_prompt',
        'Đọc các câu CREATE TABLE trong sqlite_master của student_club.sqlite, bỏ bảng/cột mà vai trò '
        'không được xem (BR03). Kết quả được cache theo vai trò.',
        [('role', role, 'Vai trò người hỏi: member | board | admin'),
         ('bảng bị ẩn', r['tables'], 'Theo config.RESTRICTED; rỗng = thấy hết'),
         ('cột bị ẩn', r['columns'], '(bảng, cột) bị xoá khỏi CREATE TABLE')],
        schema, output_desc='Phần schema đặt ở đầu prompt (giống BIRD: các câu CREATE TABLE)')

    comment = comment_prompt(question, knowledge)
    trace.step(
        '2b.4b', 'prompt.comment_prompt',
        'Dựng phần comment cuối prompt giống generate_comment_prompt() của BIRD: có External Knowledge '
        'nếu có evidence, rồi câu hỏi.',
        [('question', question, 'Câu hỏi tiếng Anh/Việt người dùng hỏi'),
         ('knowledge', knowledge, 'Evidence nguyên văn; None = không có dòng External Knowledge')],
        comment)

    tail = prompt_tail(provider)
    full = schema + '\n\n' + comment + tail
    trace.step(
        '2b.4', 'prompt.build_prompt',
        'Ghép schema + "\\n\\n" + comment + câu kết thúc theo provider, đúng như script benchmark '
        '(openai → openai_request.py; ollama/groq → ollama_request.py).',
        [('question', question, None), ('knowledge', knowledge, None), ('role', role, None),
         ('provider', provider, 'Chọn câu kết thúc prompt'),
         ('tail', tail, 'openai: "Generate the SQL after thinking step by step: \\nSELECT " (model viết tiếp sau '
                        'SELECT); còn lại: yêu cầu trả SQL trong khối ```sql')],
        full, output_desc='Prompt hoàn chỉnh gửi cho LLM')
    return full
