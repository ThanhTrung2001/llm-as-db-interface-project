"""UC02f Diễn giải kết quả: biến bảng kết quả thành câu trả lời cho người không biết SQL."""
import json

from . import llm, trace

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
    trace.step(
        '5a', 'answer.llm_answer (dựng prompt)',
        f'Dựng prompt yêu cầu LLM trả lời 1–3 câu tiếng Việt, chỉ dựa vào tối đa {MAX_ROWS_TO_LLM} dòng đầu kết quả.',
        [('question', question, 'Câu hỏi gốc'),
         ('columns', columns, 'Tên cột của kết quả SQL'),
         ('rows', [tuple(r) for r in rows], f'Kết quả SQL đầy đủ; chỉ {MAX_ROWS_TO_LLM} dòng đầu được gửi đi')],
        prompt, output_desc='Prompt diễn giải gửi cho llm.complete (bước 5b)')
    return llm.complete(model, prompt, max_tokens=300, label='5b').strip()


def make_answer(question: str, columns: list, rows: list, model: dict = None) -> tuple:
    """Trả về (câu trả lời, nguồn) với nguồn là 'llm' hoặc 'template'."""
    params = [('question', question, 'Câu hỏi gốc'),
              ('columns', columns, 'Tên cột kết quả'),
              ('rows', f'<{len(rows)} dòng, xem bước 4>', 'Kết quả SQL'),
              ('model', model and model.get('model_tag'),
               'Model dùng để diễn giải; None (chế độ replay) → dựng câu theo mẫu')]
    note = None
    if model is not None:
        try:
            text = llm_answer(model, question, columns, rows)
            if text:
                trace.step('5', 'answer.make_answer',
                           'Biến bảng kết quả thành câu trả lời cho người không biết SQL.',
                           params, (text, 'llm'), output_desc='(câu trả lời, nguồn) — nguồn "llm"')
                return text, 'llm'
            note = 'LLM trả về rỗng → chuyển sang dựng câu theo mẫu'
        except llm.LLMError as e:
            note = f'LLM lỗi ({e}) → chuyển sang dựng câu theo mẫu'
            # model lỗi ở bước diễn giải thì vẫn trả lời được bằng mẫu
    text = template_answer(columns, rows)
    trace.step('5', 'answer.make_answer → template_answer',
               'Dựng câu trả lời theo mẫu, không gọi model: 0 dòng / 1 giá trị / 1 dòng / 1 cột / nhiều cột.',
               params, (text, 'template'), output_desc='(câu trả lời, nguồn) — nguồn "template"', note=note)
    return text, 'template'
