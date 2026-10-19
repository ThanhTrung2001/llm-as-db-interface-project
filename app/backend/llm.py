"""Gọi dịch vụ LLM. OpenAI, Groq, OpenRouter, Ollama đều dùng API tương thích OpenAI."""
import os

from dotenv import load_dotenv
from openai import OpenAI

from . import config  # noqa: F401  (thêm BIRD_SRC vào sys.path)
from ollama_request import extract_sql  # tách SQL khỏi ```sql ...``` như lúc benchmark

load_dotenv(os.path.join(config.ROOT, '.env'))


class LLMError(Exception):
    pass


def complete(model: dict, prompt: str, max_tokens: int = 512, timeout_s: float = 120) -> str:
    api_key = os.environ.get(model['api_key_env'] or '', '') or 'ollama'
    if model['provider'] != 'ollama' and api_key == 'ollama':
        raise LLMError(f'Chưa cấu hình khoá API ({model["api_key_env"]}) trong .env')
    try:
        client = OpenAI(api_key=api_key, base_url=model['base_url'] or None, timeout=timeout_s)
        resp = client.chat.completions.create(
            model=model['model_tag'],
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0,
            max_tokens=max_tokens,
        )
    except Exception as e:  # mạng, khoá sai, model chưa pull...
        raise LLMError(f'Lỗi gọi model: {e}') from e
    return resp.choices[0].message.content or ''


def generate_sql(model: dict, prompt: str, timeout_s: float = 120) -> str:
    sql = extract_sql(complete(model, prompt, timeout_s=timeout_s))
    return '' if sql == 'SELECT' else sql  # extract_sql trả "SELECT" khi rỗng
