"""UC02f Diễn giải kết quả: biến bảng kết quả thành câu trả lời cho người không biết SQL."""
import json

from . import llm, trace

MAX_ROWS_TO_LLM = 30   # chỉ gửi phần đầu kết quả cho model (tối thiểu hoá dữ liệu gửi ra ngoài)
MAX_LIST = 10


def _fmt(v) -> str:
    if v is None:
        return '(empty)'
    if isinstance(v, float):
        return f'{v:,.2f}'.rstrip('0').rstrip('.')
    return str(v)


def template_answer(columns: list, rows: list) -> str:
    """Câu trả lời dựng theo mẫu — không cần model, dùng khi model lỗi ở bước diễn giải."""
    n = len(rows)
    if n == 0:
        return 'No matching data was found.'
    if n == 1 and len(columns) == 1:
        return f'Result: {_fmt(rows[0][0])}.'
    if n == 1:
        return 'Result: ' + '; '.join(f'{c} = {_fmt(v)}' for c, v in zip(columns, rows[0])) + '.'
    if len(columns) == 1:
        items = ', '.join(_fmt(r[0]) for r in rows[:MAX_LIST])
        more = f' and {n - MAX_LIST} more' if n > MAX_LIST else ''
        return f'{n} results: {items}{more}.'
    return f'{n} rows returned — see the table below.'


def llm_answer(model: dict, question: str, columns: list, rows: list) -> str:
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
    trace.step(
        '5a', 'answer.llm_answer (dựng prompt)',
        f'Dựng prompt yêu cầu LLM trả lời 1–3 câu tiếng Anh, chỉ dựa vào tối đa {MAX_ROWS_TO_LLM} dòng đầu kết quả.',
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
               'Model dùng để diễn giải; None → dựng câu theo mẫu')]
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
