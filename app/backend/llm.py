"""
Gọi LLM và tách SQL — giống luồng benchmark (ollama_request.py / openai_request.py).

OpenAI, Groq, Ollama đều gọi qua cùng một client OpenAI
(Ollama có API tương thích OpenAI tại http://localhost:11434/v1).
"""
import os

from dotenv import load_dotenv
from openai import OpenAI

from . import config  # config: thêm bird/llm/src vào sys.path để import script benchmark
from ollama_request import extract_sql as ollama_extract_sql  # hàm tách SQL lúc benchmark Ollama
from openai_request import extract_sql as openai_extract_sql  # hàm tách SQL lúc benchmark GPT-3.5-Turbo

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


def extract_sql(provider: str, raw_text: str) -> str:
    """Tách câu SQL khỏi văn bản thô bằng đúng hàm extract_sql của script benchmark.
    Trả về '' nếu model không sinh được SQL.

    openai  : bỏ khối ```sql nếu có, bỏ chữ SELECT thừa ở đầu, cắt ở ';', ghép lại "SELECT " + phần còn lại
              (prompt kết thúc bằng "SELECT ", model chỉ viết tiếp phần sau)
    còn lại : bỏ <think>...</think>, lấy nội dung trong ```sql ... ```, cắt ở dấu ';' đầu tiên
    """
    if provider == 'openai':
        sql = openai_extract_sql(raw_text)
    else:
        sql = ollama_extract_sql(raw_text)
    return '' if sql == 'SELECT' else sql  # hàm của benchmark trả "SELECT" khi không tách được gì
