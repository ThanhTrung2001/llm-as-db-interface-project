"""
Gọi LLM và tách SQL — giống luồng benchmark (ollama_request.py / openai_request.py).

OpenAI, Groq, Ollama đều gọi qua cùng một client OpenAI
(Ollama có API tương thích OpenAI tại http://localhost:11434/v1).

Phía app chỉ gửi VĂN BẢN đi và nhận VĂN BẢN về. Các bước tokenize → embedding → transformer →
chọn từng token → detokenize đều chạy bên trong model server (Ollama / OpenAI). Để demo được các bước đó,
call_llm(..., trace=dict) ghi lại những gì server cho biết:
    usage.prompt_tokens      số token của prompt sau khi tokenize
    logprobs                 từng token model sinh ra + xác suất + các ứng viên khác ở mỗi bước
    (inside_model.py chạy lại các bước tokenize / embedding / detokenize bằng file model để đối chiếu)
"""
import math
import os
import re
import time

from dotenv import load_dotenv
from openai import BadRequestError, OpenAI

from . import config

# Tham số gọi API đúng như openai_request.call_openai() lúc benchmark GPT-3.5-Turbo
OPENAI_MAX_TOKENS = 256
OPENAI_STOP = ['--', '\n\n', ';', '#']

load_dotenv(os.path.join(config.ROOT, '.env'))


class LLMError(Exception):
    pass


TOP_LOGPROBS = 5  # số ứng viên hiển thị ở mỗi bước sinh token


def call_llm(model: dict, prompt: str, max_tokens: int = 512, stop: list = None, timeout_s: float = 120,
             trace: dict = None) -> str:
    """Gửi prompt cho LLM (một tin nhắn user, temperature = 0), trả về văn bản thô model sinh ra.

    trace (tuỳ chọn): dict để ghi lại request đã gửi, số token, từng token sinh ra kèm xác suất (logprobs).
    Xin logprobs không làm đổi kết quả (temperature = 0 vẫn chọn token xác suất cao nhất);
    server nào không hỗ trợ logprobs (Groq) thì gọi lại không kèm logprobs.
    """
    api_key = os.environ.get(model['api_key_env'] or '', '') or 'ollama'  # Ollama không cần khoá
    if model['provider'] != 'ollama' and api_key == 'ollama':
        raise LLMError(f'Chưa cấu hình khoá API ({model["api_key_env"]}) trong .env')
    params = dict(model=model['model_tag'], messages=[{'role': 'user', 'content': prompt}],
                  temperature=0, max_tokens=max_tokens, **({'stop': stop} if stop else {}))
    want_logprobs = trace is not None
    started = time.monotonic()
    try:
        client = OpenAI(api_key=api_key, base_url=model['base_url'] or None, timeout=timeout_s)
        try:
            extra = {'logprobs': True, 'top_logprobs': TOP_LOGPROBS} if want_logprobs else {}
            resp = client.chat.completions.create(**params, **extra)
        except BadRequestError:
            if not want_logprobs:
                raise
            want_logprobs = False  # server không nhận tham số logprobs → gọi lại như bình thường
            resp = client.chat.completions.create(**params)
    except Exception as e:  # mạng, khoá sai, Ollama chưa chạy, model chưa pull...
        raise LLMError(f'Lỗi gọi model: {e}') from e

    choice = resp.choices[0]
    if trace is not None:
        trace['endpoint'] = (model['base_url'] or 'https://api.openai.com/v1') + '/chat/completions'
        trace['request'] = {**params, 'messages': [{'role': 'user', 'content': f'<prompt ở bước 2: {len(prompt)} ký tự>'}],
                            **({'logprobs': True, 'top_logprobs': TOP_LOGPROBS} if want_logprobs else {})}
        trace['elapsed_ms'] = int((time.monotonic() - started) * 1000)
        trace['finish_reason'] = choice.finish_reason
        if resp.usage:
            trace['prompt_tokens'] = resp.usage.prompt_tokens
            trace['completion_tokens'] = resp.usage.completion_tokens
        trace['tokens'] = _tokens_from_logprobs(choice)
    return choice.message.content or ''


def _tokens_from_logprobs(choice) -> list:
    """Đổi logprobs của server thành [{token, prob, top: [{token, prob}, ...]}, ...] (prob = e^logprob)."""
    content = getattr(choice.logprobs, 'content', None) if choice.logprobs else None
    return [{'token': t.token, 'prob': math.exp(t.logprob), 'bytes': t.bytes,
             'top': [{'token': a.token, 'prob': math.exp(a.logprob)} for a in (t.top_logprobs or [])]}
            for t in (content or [])]


def call_llm_for_sql(model: dict, prompt: str, trace: dict = None) -> str:
    """Gửi prompt Text-to-SQL cho LLM với đúng tham số lúc benchmark, trả về văn bản thô.

    openai  : max_tokens = 256, stop = ['--', '\\n\\n', ';', '#']   (như openai_request.call_openai)
    còn lại : max_tokens = 512, không stop                          (như ollama_request.call_ollama)
    """
    if model['provider'] == 'openai':
        return call_llm(model, prompt, max_tokens=OPENAI_MAX_TOKENS, stop=OPENAI_STOP, trace=trace)
    return call_llm(model, prompt, trace=trace)


# ---------- tách SQL khỏi văn bản thô (chép từ ollama_request.py / openai_request.py) ----------

SQL_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)  # khối ```sql ... ``` đủ hai đầu
OPEN_FENCE_RE = re.compile(r"```(?:sql)?\s*", re.IGNORECASE)                    # chỉ có ```sql mở (bị cắt cụt)
THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)      # đoạn suy luận <think>...</think>


def _log(steps, what: str, text: str) -> str:
    """Ghi lại một bước tách SQL (để hiển thị trên giao diện); trả lại nguyên text."""
    if steps is not None:
        steps.append({'what': what, 'text': text})
    return text


def extract_sql_chat(raw_text: str, steps: list = None) -> str:
    """Tách SQL cho model chat (Ollama, Groq) — giống ollama_request.extract_sql.

    Ví dụ: "<think>...</think>\\n```sql\\nSELECT COUNT(*) FROM event;\\n```"  →  "SELECT COUNT(*) FROM event"
    """
    text = THINK_TAG_RE.sub('', raw_text)          # 1. bỏ đoạn suy luận <think>...</think> (nếu có)
    if text != raw_text:
        _log(steps, 'Bỏ đoạn suy luận <think>...</think>', text)
    match = SQL_FENCE_RE.search(text)
    if match:
        text = _log(steps, 'Lấy nội dung trong khối ```sql ... ```', match.group(1))      # 2a
    else:
        text = _log(steps, 'Không có khối ``` đóng: bỏ ```sql ở đầu (nếu có)',
                    OPEN_FENCE_RE.sub('', text, count=1))                                # 2b
    return _log(steps, "Cắt ở dấu ';' đầu tiên, bỏ khoảng trắng", text.strip().split(';')[0].strip())  # 3


def extract_sql_openai(raw_text: str, steps: list = None) -> str:
    """Tách SQL cho GPT-3.5-Turbo — giống openai_request.extract_sql.

    Prompt kết thúc bằng "SELECT ", model chỉ viết tiếp phần sau, nên ghép lại "SELECT " + phần model viết.
    Ví dụ: "COUNT(*) FROM event"  →  "SELECT COUNT(*) FROM event"
    """
    text = raw_text.strip()
    match = SQL_FENCE_RE.search(text)
    if match:
        text = _log(steps, 'Lấy nội dung trong khối ```sql ... ```', match.group(1).strip())        # 1a
    else:
        text = _log(steps, 'Bỏ ```sql mở ở đầu (nếu có)', OPEN_FENCE_RE.sub('', text, count=1).strip())  # 1b
    if text.upper().startswith('SELECT'):
        text = _log(steps, 'Model tự viết lại "SELECT" → bỏ để khỏi lặp', text[len('SELECT'):].lstrip())  # 2
    text = _log(steps, "Cắt ở dấu ';' đầu tiên", text.split(';')[0].strip())                           # 3
    return _log(steps, 'Ghép "SELECT " (cuối prompt) + phần model viết tiếp',
                ('SELECT ' + text) if text else '')                                                     # 4


def extract_sql(provider: str, raw_text: str, steps: list = None) -> str:
    """Tách câu SQL khỏi văn bản thô model trả về. Trả về '' nếu model không sinh được SQL.
    steps (tuỳ chọn): list để ghi lại từng bước biến đổi văn bản."""
    if provider == 'openai':
        return extract_sql_openai(raw_text, steps)
    return extract_sql_chat(raw_text, steps)
