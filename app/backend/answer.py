"""
Diễn giải kết quả: biến bảng kết quả SQL thành câu trả lời ngắn.
  - llm_answer()      : gửi câu hỏi + tối đa 30 dòng kết quả cho chính model đã sinh SQL.
  - template_answer() : model lỗi / trả rỗng thì dựng câu theo mẫu, không gọi model.
"""
import json

from . import llm

MAX_ROWS_TO_LLM = 30   # chỉ gửi phần đầu kết quả cho model (tối thiểu hoá dữ liệu gửi ra ngoài)
MAX_LIST = 10


def _fmt(v) -> str:
    if v is None:
        return '(trống)'
    if isinstance(v, float):
        return f'{v:,.2f}'.rstrip('0').rstrip('.')
    return str(v)


def template_answer(columns: list, rows: list) -> str:
    """Câu trả lời dựng theo mẫu — không cần model, dùng khi model lỗi ở bước diễn giải."""
    n = len(rows)
    if n == 0:
        return 'Không có dữ liệu phù hợp với câu hỏi.'
    if n == 1 and len(columns) == 1:
        return f'Kết quả: {_fmt(rows[0][0])}.'
    if n == 1:
        return 'Kết quả: ' + '; '.join(f'{c} = {_fmt(v)}' for c, v in zip(columns, rows[0])) + '.'
    if len(columns) == 1:
        items = ', '.join(_fmt(r[0]) for r in rows[:MAX_LIST])
        more = f' và {n - MAX_LIST} kết quả khác' if n > MAX_LIST else ''
        return f'Có {n} kết quả: {items}{more}.'
    return f'Có {n} dòng kết quả, xem bảng bên dưới.'


def llm_answer(model: dict, question: str, columns: list, rows: list) -> str:
    """Nhờ model viết câu trả lời 1–3 câu, chỉ dựa vào tối đa 30 dòng đầu của kết quả SQL."""
    sample = [dict(zip(columns, [None if v is None else _fmt(v) for v in r])) for r in rows[:MAX_ROWS_TO_LLM]]
    prompt = (
        'You are an assistant for a student club. Based ONLY on the query result below, '
        'answer the question in English, briefly (1-3 sentences), stating the specific numbers or names. '
        'Do not mention SQL, tables or columns. Do not speculate beyond the data. '
        'If the result is empty, say that no matching data was found.\n\n'
        f'Question: {question}\n'
        f'Total result rows: {len(rows)}'
        f'{" (only the first " + str(MAX_ROWS_TO_LLM) + " are shown)" if len(rows) > MAX_ROWS_TO_LLM else ""}\n'
        f'Result: {json.dumps(sample, ensure_ascii=False)}'
    )
    return llm.call_llm(model, prompt, max_tokens=300).strip()


def make_answer(question: str, columns: list, rows: list, model: dict) -> tuple:
    """Diễn giải kết quả thành câu trả lời. Trả về (câu trả lời, nguồn) với nguồn là 'llm' hoặc 'template'."""
    try:
        text = llm_answer(model, question, columns, rows)
        if text:
            return text, 'llm'
    except llm.LLMError:
        pass  # model lỗi ở bước diễn giải thì vẫn trả lời được bằng mẫu
    return template_answer(columns, rows), 'template'
