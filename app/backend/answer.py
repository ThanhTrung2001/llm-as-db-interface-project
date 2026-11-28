"""
Diễn giải kết quả: gửi câu hỏi + tối đa 30 dòng đầu của kết quả SQL cho chính model đã sinh SQL,
nhờ nó viết câu trả lời ngắn. Model lỗi thì không có câu trả lời (answer = None).
"""
import json

from . import llm

MAX_ROWS_TO_LLM = 30


def make_answer(model: dict, question: str, columns: list, rows: list):
    first_rows = [dict(zip(columns, r)) for r in rows[:MAX_ROWS_TO_LLM]]
    prompt = (
        'You are an assistant for a student club. Based ONLY on the query result below, '
        'answer the question in English, briefly (1-3 sentences), stating the specific numbers or names. '
        'Do not mention SQL, tables or columns. Do not speculate beyond the data. '
        'If the result is empty, say that no matching data was found.\n\n'
        f'Question: {question}\n'
        f'Total result rows: {len(rows)}\n'
        f'Result (first {MAX_ROWS_TO_LLM} rows at most): {json.dumps(first_rows, ensure_ascii=False, default=str)}'
    )
    try:
        return llm.call_llm(model, prompt, max_tokens=300).strip() or None
    except llm.LLMError:
        return None
