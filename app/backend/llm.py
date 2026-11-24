"""
Gọi LLM và tách SQL — giống luồng benchmark (ollama_request.py / openai_request.py).

OpenAI, Groq, Ollama đều gọi qua cùng một client OpenAI
(Ollama có API tương thích OpenAI tại http://localhost:11434/v1).
"""
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

from . import config

# Tham số gọi API đúng như openai_request.call_openai() lúc benchmark GPT-3.5-Turbo
OPENAI_MAX_TOKENS = 256
OPENAI_STOP = ['--', '\n\n', ';', '#']

load_dotenv(os.path.join(config.ROOT, '.env'))


class LLMError(Exception):
    pass


def call_llm(model: dict, prompt: str, max_tokens: int = 512, stop: list = None, timeout_s: float = 120) -> str:
    """Gửi prompt cho LLM (một tin nhắn user, temperature = 0), trả về văn bản thô model sinh ra."""
    api_key = os.environ.get(model['api_key_env'] or '', '') or 'ollama'  # Ollama không cần khoá
    if model['provider'] != 'ollama' and api_key == 'ollama':
        raise LLMError(f'Chưa cấu hình khoá API ({model["api_key_env"]}) trong .env')
    try:
        client = OpenAI(api_key=api_key, base_url=model['base_url'] or None, timeout=timeout_s)
        resp = client.chat.completions.create(
            model=model['model_tag'],
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0,
            max_tokens=max_tokens,
            **({'stop': stop} if stop else {}),
        )
    except Exception as e:  # mạng, khoá sai, Ollama chưa chạy, model chưa pull...
        raise LLMError(f'Lỗi gọi model: {e}') from e
    return resp.choices[0].message.content or ''


def call_llm_for_sql(model: dict, prompt: str) -> str:
    """Gửi prompt Text-to-SQL cho LLM với đúng tham số lúc benchmark, trả về văn bản thô.

    openai  : max_tokens = 256, stop = ['--', '\\n\\n', ';', '#']   (như openai_request.call_openai)
    còn lại : max_tokens = 512, không stop                          (như ollama_request.call_ollama)
    """
    if model['provider'] == 'openai':
        return call_llm(model, prompt, max_tokens=OPENAI_MAX_TOKENS, stop=OPENAI_STOP)
    return call_llm(model, prompt)


# ---------- tách SQL khỏi văn bản thô (chép từ ollama_request.py / openai_request.py) ----------

SQL_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)  # khối ```sql ... ``` đủ hai đầu
OPEN_FENCE_RE = re.compile(r"```(?:sql)?\s*", re.IGNORECASE)                    # chỉ có ```sql mở (bị cắt cụt)
THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)      # đoạn suy luận <think>...</think>


def extract_sql_chat(raw_text: str) -> str:
    """Tách SQL cho model chat (Ollama, Groq) — giống ollama_request.extract_sql.

    Ví dụ: "<think>...</think>\\n```sql\\nSELECT COUNT(*) FROM event;\\n```"  →  "SELECT COUNT(*) FROM event"
    """
    text = THINK_TAG_RE.sub('', raw_text)          # 1. bỏ đoạn suy luận <think>...</think> (nếu có)
    match = SQL_FENCE_RE.search(text)
    if match:
        text = match.group(1)                      # 2a. lấy nội dung trong khối ```sql ... ```
    else:
        text = OPEN_FENCE_RE.sub('', text, count=1)  # 2b. không có khối đóng: chỉ bỏ ```sql ở đầu
    return text.strip().split(';')[0].strip()      # 3. cắt ở dấu ';' đầu tiên


def extract_sql_openai(raw_text: str) -> str:
    """Tách SQL cho GPT-3.5-Turbo — giống openai_request.extract_sql.

    Prompt kết thúc bằng "SELECT ", model chỉ viết tiếp phần sau, nên ghép lại "SELECT " + phần model viết.
    Ví dụ: "COUNT(*) FROM event"  →  "SELECT COUNT(*) FROM event"
    """
    text = raw_text.strip()
    match = SQL_FENCE_RE.search(text)
    if match:
        text = match.group(1).strip()              # 1a. model vẫn bọc ```sql ... ``` → lấy nội dung trong
    else:
        text = OPEN_FENCE_RE.sub('', text, count=1).strip()  # 1b. bỏ ```sql mở ở đầu (nếu có)
    if text.upper().startswith('SELECT'):
        text = text[len('SELECT'):].lstrip()       # 2. model tự viết lại "SELECT" → bỏ để khỏi bị lặp
    text = text.split(';')[0].strip()              # 3. cắt ở dấu ';' đầu tiên
    return ('SELECT ' + text) if text else ''      # 4. ghép lại "SELECT " + phần còn lại


def extract_sql(provider: str, raw_text: str) -> str:
    """Tách câu SQL khỏi văn bản thô model trả về. Trả về '' nếu model không sinh được SQL."""
    if provider == 'openai':
        return extract_sql_openai(raw_text)
    return extract_sql_chat(raw_text)
