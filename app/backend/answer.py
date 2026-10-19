"""UC02f Diễn giải kết quả: biến bảng kết quả thành câu trả lời cho người không biết SQL."""
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
    """Câu trả lời dựng theo mẫu — không cần model, dùng cho chế độ phát lại và khi model lỗi."""
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
    sample = [dict(zip(columns, [_fmt(v) for v in r])) for r in rows[:MAX_ROWS_TO_LLM]]
    prompt = (
        'Bạn là trợ lý của một câu lạc bộ sinh viên. Dựa DUY NHẤT vào kết quả truy vấn bên dưới, '
        'hãy trả lời câu hỏi bằng tiếng Việt, ngắn gọn (1–3 câu), nêu rõ con số hoặc tên cụ thể. '
        'Không nhắc tới SQL, bảng hay cột. Không suy đoán ngoài dữ liệu. '
        'Nếu kết quả rỗng, nói là không có dữ liệu phù hợp.\n\n'
        f'Câu hỏi: {question}\n'
        f'Tổng số dòng kết quả: {len(rows)}'
        f'{" (chỉ hiển thị " + str(MAX_ROWS_TO_LLM) + " dòng đầu)" if len(rows) > MAX_ROWS_TO_LLM else ""}\n'
        f'Kết quả: {json.dumps(sample, ensure_ascii=False)}'
    )
    return llm.complete(model, prompt, max_tokens=300).strip()


def make_answer(question: str, columns: list, rows: list, model: dict = None) -> tuple:
    """Trả về (câu trả lời, nguồn) với nguồn là 'llm' hoặc 'template'."""
    if model is not None:
        try:
            text = llm_answer(model, question, columns, rows)
            if text:
                return text, 'llm'
        except llm.LLMError:
            pass  # model lỗi ở bước diễn giải thì vẫn trả lời được bằng mẫu
    return template_answer(columns, rows), 'template'
